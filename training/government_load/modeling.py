from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb
import joblib
import mlflow
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from lightgbm import LGBMRegressor

from training.government_load.config import PipelineSettings
from training.government_load.sql import identifier, sql_string

TRAIN_START = "2018-01-01 00:00:00"
TRAIN_END = "2018-10-01 00:00:00"
VALIDATION_END = "2018-12-01 00:00:00"
EXPERIMENT_NAME = "gridvision-government-load-forecasting"


def _load_features(path: Path) -> list[str]:
    features = joblib.load(path)
    if not isinstance(features, list) or not features:
        raise ValueError(f"Expected a non-empty list of feature names in {path}")
    if not all(isinstance(feature, str) for feature in features):
        raise ValueError(f"Feature names in {path} must all be strings")
    if len(features) != len(set(features)):
        raise ValueError(f"Feature names in {path} contain duplicates")
    return features


def _load_training_split(
    connection: duckdb.DuckDBPyConnection,
    input_path: Path,
    features: list[str],
    start: str,
    end: str,
    max_rows: int,
) -> pd.DataFrame:
    input_sql = sql_string(input_path)
    columns = [
        identifier("id.grid.coarse"),
        identifier("target_timestamp"),
        *(identifier(feature) for feature in features),
        identifier("target_energy"),
    ]
    return connection.execute(
        f"""
        SELECT {", ".join(columns)}
        FROM (
            SELECT {", ".join(columns)}
            FROM read_parquet({input_sql})
            WHERE target_timestamp >= TIMESTAMP '{start}'
              AND target_timestamp < TIMESTAMP '{end}'
              AND target_energy IS NOT NULL
        ) AS eligible_rows
        USING SAMPLE reservoir({max_rows} ROWS) REPEATABLE (42)
        """
    ).fetchdf()


def _features_as_float32(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    result = frame.loc[:, features].astype(np.float32)
    return result.replace([np.inf, -np.inf], np.nan)


def _regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residual = predicted - actual
    absolute_error = np.abs(residual)
    squared_error = residual**2
    actual_sum = float(np.abs(actual).sum())
    actual_variance = float(np.var(actual))
    nonzero_actual = actual != 0
    positive_actual = actual >= 0
    clipped_actual = actual[positive_actual]
    clipped_prediction = np.maximum(predicted[positive_actual], 0)
    metrics = {
        "rows": float(len(actual)),
        "mae": float(np.mean(absolute_error)),
        "rmse": float(np.sqrt(np.mean(squared_error))),
        "median_absolute_error": float(np.median(absolute_error)),
        "max_absolute_error": float(np.max(absolute_error)),
        "mean_error": float(np.mean(residual)),
        "error_std": float(np.std(residual)),
        "absolute_error_p90": float(np.quantile(absolute_error, 0.90)),
        "absolute_error_p95": float(np.quantile(absolute_error, 0.95)),
        "absolute_error_p99": float(np.quantile(absolute_error, 0.99)),
        "negative_prediction_rate": float(np.mean(predicted < 0)),
        "mean_actual": float(np.mean(actual)),
        "mean_prediction": float(np.mean(predicted)),
        "actual_std": float(np.std(actual)),
        "prediction_std": float(np.std(predicted)),
        "actual_min": float(np.min(actual)),
        "actual_max": float(np.max(actual)),
        "prediction_min": float(np.min(predicted)),
        "prediction_max": float(np.max(predicted)),
    }
    if actual_variance > 0:
        metrics["r2"] = float(1 - np.mean(squared_error) / actual_variance)
        metrics["explained_variance"] = float(
            1 - np.var(residual) / actual_variance
        )
    if actual_sum > 0:
        metrics["wape"] = float(absolute_error.sum() / actual_sum)
    if nonzero_actual.any():
        metrics["mape_nonzero"] = float(
            np.mean(absolute_error[nonzero_actual] / np.abs(actual[nonzero_actual]))
        )
    if positive_actual.any():
        metrics["rmsle"] = float(
            np.sqrt(
                np.mean(
                    (
                        np.log1p(clipped_prediction)
                        - np.log1p(clipped_actual)
                    )
                    ** 2
                )
            )
        )
    return metrics


def _group_metrics(
    frame: pd.DataFrame,
    actual: np.ndarray,
    predictions: dict[str, np.ndarray],
    column: str,
) -> pd.DataFrame:
    rows = []
    for group_value, indices in frame.groupby(column, sort=True).indices.items():
        positions = np.asarray(indices)
        row: dict[str, Any] = {column: group_value, "rows": len(positions)}
        for model_name, values in predictions.items():
            metrics = _regression_metrics(actual[positions], values[positions])
            row.update(
                {
                    f"{model_name}_{metric}": value
                    for metric, value in metrics.items()
                    if metric != "rows"
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _feature_importance(
    original_model: LGBMRegressor,
    log_model: LGBMRegressor,
    features: list[str],
) -> pd.DataFrame:
    frames = []
    for name, model in (("original", original_model), ("log", log_model)):
        frames.append(
            pd.DataFrame(
                {
                    "model": name,
                    "feature": features,
                    "gain": model.booster_.feature_importance(importance_type="gain"),
                    "split": model.booster_.feature_importance(importance_type="split"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True).sort_values(
        ["model", "gain"], ascending=[True, False]
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _model_card(
    run_id: str,
    model_path: Path,
    settings: PipelineSettings,
    metrics: dict[str, Any],
    routing_counts: dict[str, int],
    feature_count: int,
) -> str:
    validation = metrics["validation"]
    lines = [
        "# Government load forecasting model",
        "",
        f"- **MLflow run:** `{run_id}`",
        f"- **Training data:** `{settings.input_path}`",
        f"- **Hybrid model artifact:** `{model_path}`",
        f"- **Training rows sampled:** {metrics['sampled_rows']['training']:,}",
        f"- **Validation rows sampled:** {metrics['sampled_rows']['validation']:,}",
        f"- **Feature count:** {feature_count}",
        f"- **Trees per component:** {settings.n_estimators}",
        f"- **Validation routing counts:** `{json.dumps(routing_counts, sort_keys=True)}`",
        "",
        "## Validation metrics",
        "",
        "| Model | MAE | RMSE | R² | WAPE | RMSLE |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for model_name, values in validation.items():
        lines.append(
            "| "
            + model_name
            + " | "
            + " | ".join(
                f"{values.get(metric, float('nan')):.6g}"
                for metric in ("mae", "rmse", "r2", "wape", "rmsle")
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "The validation routing table selects the lower-MAE component model "
            "for each grid. The original component predicts the target directly; "
            "the log component predicts `log1p(target_energy)` and is inverse "
            "transformed with `expm1(max(prediction, 0))`.",
            "",
            "## Reproducibility and limitations",
            "",
            "Validation rows are sampled deterministically with DuckDB reservoir "
            "sampling (seed 42) and configured row caps. The recorded validation "
            "metrics therefore describe that sample, not the complete source "
            "population. Grid routing is derived only from validation metrics.",
            "",
            "The joblib bundle is pickle-based. Load it only from a trusted source.",
            "",
        ]
    )
    return "\n".join(lines)


def train_hybrid_model(settings: PipelineSettings) -> dict[str, Any]:
    """Fit original and log-target LightGBM models and choose per-grid routing."""
    input_path = settings.input_path.expanduser().resolve()
    feature_path = settings.feature_columns_path.expanduser().resolve()
    model_path = settings.model_path.expanduser().resolve()
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not tracking_uri:
        raise ValueError(
            "Set MLFLOW_TRACKING_URI before training the government load model."
        )
    if not input_path.is_file():
        raise FileNotFoundError(f"Training parquet file not found: {input_path}")
    if not feature_path.is_file():
        raise FileNotFoundError(f"Feature-column file not found: {feature_path}")

    features = _load_features(feature_path)
    connection = duckdb.connect()
    try:
        connection.execute(f"SET memory_limit = {sql_string(settings.memory_limit)}")
        connection.execute(f"SET threads = {settings.threads}")
        schema = {
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({sql_string(input_path)})"
            ).fetchall()
        }
        required = {"id.grid.coarse", "target_timestamp", "target_energy", *features}
        missing = sorted(required - schema)
        if missing:
            raise ValueError(f"Training data is missing required columns: {missing}")
        train = _load_training_split(
            connection,
            input_path,
            features,
            TRAIN_START,
            TRAIN_END,
            settings.max_training_rows,
        )
        validation = _load_training_split(
            connection,
            input_path,
            features,
            TRAIN_END,
            VALIDATION_END,
            settings.max_validation_rows,
        )
    finally:
        connection.close()

    if train.empty:
        raise ValueError("No training rows found in the January-September 2018 window")
    if validation.empty:
        raise ValueError("No validation rows found in the October-November 2018 window")
    y_train = train["target_energy"].to_numpy(dtype=np.float64)
    y_validation = validation["target_energy"].to_numpy(dtype=np.float64)
    if not np.isfinite(y_train).all() or not np.isfinite(y_validation).all():
        raise ValueError("Training and validation targets must be finite")
    if (y_train < 0).any() or (y_validation < 0).any():
        raise ValueError("The log-target model requires non-negative energy values")

    x_train = _features_as_float32(train, features)
    x_validation = _features_as_float32(validation, features)
    grid_ids = validation["id.grid.coarse"].to_numpy()
    validation_metadata = validation[
        [
            column
            for column in (
                "id.grid.coarse",
                "target_timestamp",
                "forecast_horizon_hours",
            )
            if column in validation.columns
        ]
    ].copy()
    persistence_predictions = (
        x_validation["energy_at_origin"].to_numpy(dtype=np.float64)
        if "energy_at_origin" in x_validation.columns
        else None
    )
    training_rows = len(train)
    validation_rows = len(validation)
    del train, validation
    model_options = {
        "n_estimators": settings.n_estimators,
        "learning_rate": 0.05,
        "max_bin": 127,
        "min_child_samples": 100,
        "colsample_bytree": 0.8,
        "subsample": 0.8,
        "subsample_freq": 1,
        "reg_lambda": 1.0,
        "n_jobs": settings.threads,
        "random_state": 42,
        "verbosity": -1,
    }

    print(
        f"Fitting two models on {training_rows:,} sampled rows; "
        f"validating on {validation_rows:,} sampled rows"
    )
    original_model = LGBMRegressor(objective="regression", **model_options)
    original_model.fit(x_train, y_train)
    log_model = LGBMRegressor(objective="regression", **model_options)
    log_model.fit(x_train, np.log1p(y_train))

    train_predictions = {
        "original": original_model.predict(x_train),
        "log": np.expm1(np.maximum(log_model.predict(x_train), 0)),
    }
    original_predictions = original_model.predict(x_validation)
    log_predictions = np.expm1(
        np.maximum(log_model.predict(x_validation), 0)
    )
    if not all(
        np.isfinite(values).all()
        for values in (*train_predictions.values(), original_predictions, log_predictions)
    ):
        raise ValueError("Model produced non-finite training or validation predictions")
    training_metrics = {
        model_name: _regression_metrics(y_train, values)
        for model_name, values in train_predictions.items()
    }
    validation_predictions = {
        "original": original_predictions,
        "log": log_predictions,
    }
    validation_mae = {
        "original": float(np.mean(np.abs(y_validation - original_predictions))),
        "log": float(np.mean(np.abs(y_validation - log_predictions))),
    }
    routing_rows = []
    for grid_id in pd.unique(grid_ids):
        positions = np.flatnonzero(grid_ids == grid_id)
        original_mae = float(
            np.mean(np.abs(y_validation[positions] - original_predictions[positions]))
        )
        log_mae = float(
            np.mean(np.abs(y_validation[positions] - log_predictions[positions]))
        )
        routing_rows.append(
            {
                "grid_id": grid_id,
                "selected_model": "log" if log_mae < original_mae else "original",
            }
        )
    routing = pd.DataFrame(routing_rows).sort_values("grid_id").reset_index(drop=True)
    routing_counts = routing["selected_model"].value_counts().to_dict()
    routed_models = dict(zip(routing["grid_id"], routing["selected_model"], strict=True))
    hybrid_predictions = np.where(
        pd.Series(grid_ids).map(routed_models).to_numpy() == "log",
        log_predictions,
        original_predictions,
    )
    validation_predictions["hybrid"] = hybrid_predictions
    metric_predictions = dict(validation_predictions)
    persistence_metrics: dict[str, float] | None = None
    if persistence_predictions is not None:
        validation_predictions["persistence"] = persistence_predictions
        valid_persistence = np.isfinite(persistence_predictions)
        if valid_persistence.all():
            metric_predictions["persistence"] = persistence_predictions
        elif valid_persistence.any():
            persistence_metrics = _regression_metrics(
                y_validation[valid_persistence],
                persistence_predictions[valid_persistence],
            )
    validation_metrics = {
        model_name: _regression_metrics(y_validation, values)
        for model_name, values in metric_predictions.items()
    }
    if persistence_metrics is not None:
        validation_metrics["persistence"] = persistence_metrics
    sampled_rows = {"training": training_rows, "validation": validation_rows}
    metrics = {
        "training": training_metrics,
        "validation": validation_metrics,
        "sampled_rows": sampled_rows,
        "persistence_evaluation_rows": (
            int(np.isfinite(persistence_predictions).sum())
            if persistence_predictions is not None
            else 0
        ),
    }
    validation_frame = validation_metadata.copy()
    validation_frame["actual"] = y_validation
    for model_name, values in validation_predictions.items():
        validation_frame[f"{model_name}_prediction"] = values
        validation_frame[f"{model_name}_error"] = values - y_validation
        validation_frame[f"{model_name}_absolute_error"] = np.abs(
            values - y_validation
        )
    validation_frame["selected_model"] = (
        pd.Series(grid_ids).map(routed_models).to_numpy()
    )
    grid_metrics = _group_metrics(
        validation_metadata,
        y_validation,
        metric_predictions,
        "id.grid.coarse",
    )
    horizon_metrics = (
        _group_metrics(
            validation_metadata,
            y_validation,
            metric_predictions,
            "forecast_horizon_hours",
        )
        if "forecast_horizon_hours" in validation_metadata.columns
        else pd.DataFrame()
    )
    feature_profile = x_train.describe(
        percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]
    ).transpose()
    feature_profile.index.name = "feature"
    feature_profile.reset_index(inplace=True)
    importance = _feature_importance(original_model, log_model, features)

    artifact = {
        "original_model": original_model,
        "log_model": log_model,
        "features": features,
        "routing": routing,
        "config": {
            "model_name": "Hybrid grid energy forecaster",
            "training_year": 2018,
            "target_column": "target_energy",
            "feature_count": len(features),
            "grid_count": len(routing),
            "original_model_params": model_options,
            "sampled_rows": sampled_rows,
            "sampling_method": "DuckDB reservoir sampling with seed 42",
            "max_training_rows": settings.max_training_rows,
            "max_validation_rows": settings.max_validation_rows,
            "log_target_transform": "log1p",
            "log_inverse_transform": "expm1(max(prediction, 0))",
            "routing_rule": "Choose the model with lower per-grid validation MAE.",
            "routing_counts": routing_counts,
        },
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = model_path.with_name(
        f".{model_path.stem}.{uuid.uuid4().hex}.tmp.joblib"
    )
    try:
        joblib.dump(artifact, temporary)
        os.replace(temporary, model_path)
    finally:
        temporary.unlink(missing_ok=True)

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name="government-load-hybrid") as run:
        run_id = run.info.run_id
        logged_at = datetime.now(timezone.utc).isoformat()
        log_root = Path(
            os.getenv(
                "GRIDVISION_LOG_DIR",
                Path(__file__).resolve().parents[2] / "logs",
            )
        ).expanduser().resolve()
        run_artifact_dir = log_root / "training" / "government" / run_id
        run_artifact_dir.mkdir(parents=True, exist_ok=True)
        validation_prediction_path = run_artifact_dir / "validation_predictions.parquet"
        validation_frame.to_parquet(validation_prediction_path, index=False)
        grid_metrics_path = run_artifact_dir / "validation_metrics_by_grid.csv"
        grid_metrics.to_csv(grid_metrics_path, index=False)
        horizon_metrics_path: Path | None = None
        if not horizon_metrics.empty:
            horizon_metrics_path = (
                run_artifact_dir / "validation_metrics_by_horizon.csv"
            )
            horizon_metrics.to_csv(horizon_metrics_path, index=False)
        routing_path = run_artifact_dir / "grid_model_routing.csv"
        routing.to_csv(routing_path, index=False)
        importance_path = run_artifact_dir / "feature_importance.csv"
        importance.to_csv(importance_path, index=False)
        feature_profile_path = run_artifact_dir / "training_feature_profile.csv"
        feature_profile.to_csv(feature_profile_path, index=False)
        features_path = run_artifact_dir / "feature_columns.json"
        _write_json(features_path, {"features": features})
        original_model_path = run_artifact_dir / "original_model.txt"
        log_model_path = run_artifact_dir / "log_target_model.txt"
        original_model.booster_.save_model(str(original_model_path))
        log_model.booster_.save_model(str(log_model_path))
        model_card_path = (
            log_root / "model_cards" / f"government-load-{run_id}.md"
        )
        model_card_path.parent.mkdir(parents=True, exist_ok=True)
        model_card_path.write_text(
            _model_card(
                run_id,
                model_path,
                settings,
                metrics,
                routing_counts,
                len(features),
            ),
            encoding="utf-8",
        )
        package_versions = {
            package: version(package)
            for package in (
                "duckdb",
                "lightgbm",
                "mlflow",
                "numpy",
                "pandas",
                "pyarrow",
                "scikit-learn",
            )
        }
        model_metadata = {
            "schema_version": 1,
            "logged_at_utc": logged_at,
            "experiment": EXPERIMENT_NAME,
            "run_id": run_id,
            "training_dataset": str(input_path),
            "feature_columns_path": str(feature_path),
            "model_path": str(model_path),
            "model_sha256": _sha256(model_path),
            "training_window": {"start": TRAIN_START, "end": TRAIN_END},
            "validation_window": {"start": TRAIN_END, "end": VALIDATION_END},
            "sampled_rows": sampled_rows,
            "sampling_method": "DuckDB reservoir sampling with seed 42",
            "feature_count": len(features),
            "features": features,
            "grid_count": len(routing),
            "routing_counts": routing_counts,
            "model_parameters": model_options,
            "resource_settings": {
                "memory_limit": settings.memory_limit,
                "threads": settings.threads,
                "max_training_rows": settings.max_training_rows,
                "max_validation_rows": settings.max_validation_rows,
            },
            "metrics": metrics,
            "package_versions": package_versions,
            "model_card_path": str(model_card_path),
            "run_artifact_directory": str(run_artifact_dir),
        }
        metadata_path = run_artifact_dir / "model_metadata.json"
        _write_json(metadata_path, model_metadata)
        metrics_path = log_root / "model_metrics" / f"government-load-{run_id}.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(
            metrics_path,
            {
                "schema_version": 1,
                "logged_at_utc": logged_at,
                "run_id": run_id,
                "model_metadata": model_metadata,
                "metrics": metrics,
                "validation_metrics_by_grid": grid_metrics.to_dict(orient="records"),
                "validation_metrics_by_horizon": horizon_metrics.to_dict(
                    orient="records"
                ),
            },
        )
        training_log_path = log_root / "training" / f"government-load-{run_id}.json"
        _write_json(
            training_log_path,
            {
                "schema_version": 1,
                "logged_at_utc": logged_at,
                "status": "completed",
                "run_id": run_id,
                "experiment": EXPERIMENT_NAME,
                "model_path": str(model_path),
                "model_card_path": str(model_card_path),
                "metrics_path": str(metrics_path),
                "artifact_directory": str(run_artifact_dir),
                "sampled_rows": sampled_rows,
            },
        )
        mlflow.set_tags(
            {
                "task": "government_load_forecasting",
                "target": "target_energy",
                "validation_routing": "per_grid_mae",
                "split_strategy": "chronological_2018",
                "sampling_method": "reservoir_seed_42",
                "dataset_path": str(input_path),
            }
        )
        mlflow.log_params(
            {
                "training_dataset": str(input_path),
                "model_artifact": str(model_path),
                "training_rows": training_rows,
                "validation_rows": validation_rows,
                "feature_count": len(features),
                "grid_count": len(routing),
                "n_estimators": settings.n_estimators,
                "threads": settings.threads,
                "max_training_rows": settings.max_training_rows,
                "max_validation_rows": settings.max_validation_rows,
                "routed_log_grids": int(routing_counts.get("log", 0)),
                "routed_original_grids": int(routing_counts.get("original", 0)),
                "memory_limit": settings.memory_limit,
                "learning_rate": model_options["learning_rate"],
                "max_bin": model_options["max_bin"],
                "min_child_samples": model_options["min_child_samples"],
                "colsample_bytree": model_options["colsample_bytree"],
                "subsample": model_options["subsample"],
                "subsample_freq": model_options["subsample_freq"],
                "reg_lambda": model_options["reg_lambda"],
                "random_state": model_options["random_state"],
                "sampling_seed": 42,
                **{
                    f"version_{package.replace('-', '_')}": package_version
                    for package, package_version in package_versions.items()
                },
            }
        )
        logged_metrics = {
            f"validation_{model_name}_{metric_name}": float(
                validation_metrics[model_name][metric_name]
            )
            for model_name in ("original", "log", "hybrid", "persistence")
            if model_name in validation_metrics
            for metric_name in ("mae", "rmse", "r2")
            if metric_name in validation_metrics[model_name]
        }
        logged_metrics.update(
            {
                "validation_hybrid_wape": validation_metrics["hybrid"]["wape"],
                "validation_hybrid_rmsle": validation_metrics["hybrid"]["rmsle"],
                "validation_hybrid_negative_prediction_rate": (
                    validation_metrics["hybrid"]["negative_prediction_rate"]
                ),
            }
        )
        mlflow.log_metrics(logged_metrics)
        mlflow.log_dict(model_metadata, "model_metadata.json")
        mlflow.log_artifact(str(model_path), artifact_path="model")
        mlflow.log_artifact(str(model_card_path), artifact_path="documentation")
        mlflow.log_artifact(str(metrics_path), artifact_path="model_metrics")
        mlflow.log_artifact(str(training_log_path), artifact_path="training")
        mlflow.log_artifacts(
            str(run_artifact_dir),
            artifact_path="training_artifacts",
        )
    result = {
        "model_path": str(model_path),
        "training_rows": training_rows,
        "validation_rows": validation_rows,
        "routing_counts": routing_counts,
        "validation_mae": validation_mae,
        "validation_metrics": validation_metrics,
        "mlflow_run_id": run_id,
        "model_card_path": str(model_card_path),
        "metrics_path": str(metrics_path),
        "training_log_path": str(training_log_path),
        "artifact_directory": str(run_artifact_dir),
        "model_sha256": model_metadata["model_sha256"],
    }
    print(
        f"Saved hybrid model to {model_path}"
    )
    print(f"Per-grid routing: {routing_counts}")
    print(f"Government training result: {result}")
    return result


def _load_model_artifact(path: Path) -> tuple[Any, Any, list[str], dict[Any, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")
    artifact = joblib.load(path)
    if not isinstance(artifact, dict):
        raise ValueError("Hybrid model artifact must be a dictionary")
    required = {"original_model", "log_model", "features", "routing"}
    missing = required - artifact.keys()
    if missing:
        raise ValueError(f"Hybrid model artifact is missing keys: {sorted(missing)}")
    features = artifact["features"]
    if not isinstance(features, list) or not all(
        isinstance(feature, str) for feature in features
    ):
        raise ValueError("Hybrid model artifact has an invalid feature list")
    routing_frame = artifact["routing"]
    if not isinstance(routing_frame, pd.DataFrame) or not {
        "grid_id",
        "selected_model",
    }.issubset(routing_frame.columns):
        raise ValueError("Hybrid model artifact has an invalid routing table")
    if routing_frame["grid_id"].duplicated().any():
        raise ValueError("Hybrid model routing table contains duplicate grid IDs")
    if routing_frame[["grid_id", "selected_model"]].isna().any().any():
        raise ValueError("Hybrid model routing table contains null values")
    invalid = set(routing_frame["selected_model"]) - {"original", "log"}
    if invalid:
        raise ValueError(f"Unknown model names in routing table: {sorted(invalid)}")
    routing = dict(
        zip(routing_frame["grid_id"], routing_frame["selected_model"], strict=True)
    )
    return (
        artifact["original_model"],
        artifact["log_model"],
        features,
        routing,
    )


def predict(
    settings: PipelineSettings,
    *,
    batch_size: int | None = None,
) -> Path:
    """Predict in Arrow batches, keeping the full input out of memory."""
    input_path = settings.input_path.expanduser().resolve()
    output_path = settings.output_path.expanduser().resolve()
    model_path = settings.model_path.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Prediction parquet file not found: {input_path}")
    if input_path == output_path:
        raise ValueError("Prediction output must not overwrite its input")

    original_model, log_model, features, routing = _load_model_artifact(model_path)
    source = pq.ParquetFile(input_path)
    available = set(source.schema_arrow.names)
    if "id.grid.coarse" not in available:
        raise ValueError("Prediction data must include the id.grid.coarse routing key")
    missing = sorted(set(features) - available)
    if missing:
        raise ValueError(f"Prediction data is missing model features: {missing}")

    metadata = [
        column
        for column in (
            "id.grid.coarse",
            "forecast_origin_timestamp",
            "target_timestamp",
            "forecast_horizon_hours",
            "target_energy",
        )
        if column in available
    ]
    columns = list(dict.fromkeys([*metadata, *features]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp.parquet"
    )
    writer: pq.ParquetWriter | None = None
    saw_rows = False
    try:
        for batch in source.iter_batches(
            batch_size=batch_size or settings.batch_size,
            columns=columns,
        ):
            saw_rows = True
            frame = batch.to_pandas()
            x = _features_as_float32(frame, features)
            selected = (
                frame["id.grid.coarse"].map(routing).fillna("original").to_numpy()
            )
            predictions = np.empty(len(frame), dtype=np.float64)
            for model_name, estimator in (
                ("original", original_model),
                ("log", log_model),
            ):
                positions = np.flatnonzero(selected == model_name)
                if positions.size == 0:
                    continue
                values = estimator.predict(x.iloc[positions])
                if model_name == "log":
                    values = np.expm1(np.maximum(values, 0))
                predictions[positions] = values

            result = frame.loc[:, metadata].copy()
            result["selected_model"] = selected
            result["prediction"] = predictions
            table = pa.Table.from_pandas(result, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
        if not saw_rows or writer is None:
            raise ValueError(f"No rows found in prediction input: {input_path}")
        writer.close()
        writer = None
        os.replace(temporary, output_path)
    finally:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)

    print(f"Wrote predictions to {output_path}")
    return output_path
