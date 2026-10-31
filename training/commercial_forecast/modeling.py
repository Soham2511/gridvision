"""Chronological LightGBM training and MLflow tracking for commercial Gold."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from training.commercial_forecast.config import (
    DATA_ROOT,
    LOG_ROOT,
    PROJECT_ROOT,
    CommercialTrainingSettings,
)
from training.commercial_forecast.features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    prepare_features,
)
from training.commercial_forecast.predictor import CommercialPredictionPipeline

DATE_COLUMN = "target_timestamp"
ENTITY_COLUMN = "OBJECTID"


def _validate_manifest(path: Path, gold_path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Commercial Gold quality manifest is required before training: {path}"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("quality_passed", False):
        raise ValueError(
            "Commercial Gold's latest quality report failed; refusing to train."
        )
    manifest_dataset_path = Path(manifest.get("dataset_path", ""))
    if not _manifest_dataset_matches(manifest_dataset_path, gold_path):
        raise ValueError(
            "Commercial Gold manifest points to a different dataset than the training input."
        )
    return manifest


def _manifest_dataset_matches(manifest_path: Path, gold_path: Path) -> bool:
    if manifest_path.resolve() == gold_path.resolve():
        return True
    try:
        data_relative_path = gold_path.resolve().relative_to(DATA_ROOT.resolve())
    except ValueError:
        return False
    airflow_dataset_path = Path("/opt/gridvision/data") / data_relative_path
    return manifest_path.resolve() == airflow_dataset_path


def chronological_boundaries(
    timestamps: pd.Series,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return strictly increasing target-time boundaries for train/val/test."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("Train and validation fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train plus validation fractions must be below one")
    ordered = pd.Index(pd.to_datetime(timestamps, errors="raise").dropna().unique()).sort_values()
    if len(ordered) < 10:
        raise ValueError(
            f"At least 10 distinct target timestamps are required; found {len(ordered)}"
        )
    train_index = int(len(ordered) * train_fraction)
    validation_index = int(len(ordered) * (train_fraction + validation_fraction))
    train_index = min(max(train_index, 1), len(ordered) - 2)
    validation_index = min(max(validation_index, train_index + 1), len(ordered) - 1)
    return pd.Timestamp(ordered[train_index]), pd.Timestamp(ordered[validation_index])


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _read_sample(
    connection: duckdb.DuckDBPyConnection,
    gold_path: Path,
    start: pd.Timestamp | None,
    end: pd.Timestamp,
    max_rows: int,
    seed: int,
) -> pd.DataFrame:
    path_sql = "'" + str(gold_path).replace("'", "''") + "'"
    columns = [ENTITY_COLUMN, DATE_COLUMN, *FEATURE_COLUMNS, TARGET_COLUMN]
    projection = ", ".join(_quoted(column) for column in columns)
    start_clause = (
        f"AND {_quoted(DATE_COLUMN)} >= TIMESTAMP '{start}'" if start is not None else ""
    )
    query = f"""
        SELECT {projection}
        FROM (
            SELECT {projection}
            FROM read_parquet({path_sql})
            WHERE {_quoted(DATE_COLUMN)} < TIMESTAMP '{end}'
              {start_clause}
              AND {_quoted(TARGET_COLUMN)} IS NOT NULL
        ) eligible
        USING SAMPLE reservoir({int(max_rows)} ROWS) REPEATABLE ({int(seed)})
    """
    return connection.execute(query).fetchdf()


def _read_test_sample(
    connection: duckdb.DuckDBPyConnection,
    gold_path: Path,
    start: pd.Timestamp,
    max_rows: int,
    seed: int,
) -> pd.DataFrame:
    path_sql = "'" + str(gold_path).replace("'", "''") + "'"
    columns = [ENTITY_COLUMN, DATE_COLUMN, *FEATURE_COLUMNS, TARGET_COLUMN]
    projection = ", ".join(_quoted(column) for column in columns)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM (
            SELECT {projection}
            FROM read_parquet({path_sql})
            WHERE {_quoted(DATE_COLUMN)} >= TIMESTAMP '{start}'
              AND {_quoted(TARGET_COLUMN)} IS NOT NULL
        ) eligible
        USING SAMPLE reservoir({int(max_rows)} ROWS) REPEATABLE ({int(seed)})
        """
    ).fetchdf()


def _make_pipeline(settings: CommercialTrainingSettings) -> Pipeline:
    numeric_features = [
        feature for feature in FEATURE_COLUMNS if feature not in CATEGORICAL_FEATURES
    ]
    preprocess = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    encoded_missing_value=-1,
                ),
                CATEGORICAL_FEATURES,
            )
        ],
        remainder="passthrough",
        verbose_feature_names_out=False,
    )
    estimator = LGBMRegressor(
        objective="regression",
        n_estimators=settings.n_estimators,
        learning_rate=settings.learning_rate,
        num_leaves=settings.num_leaves,
        max_depth=settings.max_depth,
        min_child_samples=settings.min_child_samples,
        reg_lambda=settings.reg_lambda,
        n_jobs=settings.n_jobs,
        random_state=settings.random_state,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )
    return Pipeline([("preprocess", preprocess), ("model", estimator)])


def _make_candidate(settings: CommercialTrainingSettings, name: str) -> Any:
    """Build one estimator in the commercial candidate set."""
    if name in {"lightgbm_direct", "lightgbm_log1p"}:
        estimator = _make_pipeline(settings)
        if name == "lightgbm_log1p":
            return TransformedTargetRegressor(
                regressor=estimator, func=np.log1p, inverse_func=np.expm1,
                check_inverse=False,
            )
        return estimator
    if name == "hist_gradient_boosting":
        numeric = [f for f in FEATURE_COLUMNS if f not in CATEGORICAL_FEATURES]
        preprocess = ColumnTransformer(
            transformers=[("categorical", OrdinalEncoder(
                handle_unknown="use_encoded_value", unknown_value=-1,
                encoded_missing_value=-1,
            ), CATEGORICAL_FEATURES)], remainder="passthrough",
            verbose_feature_names_out=False,
        )
        return Pipeline([
            ("preprocess", preprocess),
            ("model", HistGradientBoostingRegressor(
                max_iter=settings.n_estimators, learning_rate=settings.learning_rate,
                max_leaf_nodes=settings.num_leaves, max_depth=None if settings.max_depth < 0 else settings.max_depth,
                min_samples_leaf=max(2, settings.min_child_samples),
                l2_regularization=settings.reg_lambda, random_state=settings.random_state,
            )),
        ])
    raise ValueError(f"Unknown commercial candidate: {name}")


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    return prepare_features(frame)


def _regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    if len(actual) == 0 or len(actual) != len(predicted):
        raise ValueError("Metrics require non-empty actual/prediction arrays of equal length")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics cannot be computed from non-finite values")
    absolute = np.abs(predicted - actual)
    denominator = float(np.abs(actual).sum())
    return {
        "rows": int(len(actual)),
        "mae": float(absolute.mean()),
        "rmse": float(np.sqrt(np.mean((predicted - actual) ** 2))),
        "wape": float(absolute.sum() / denominator) if denominator > 0 else None,
    }


def _group_metrics(
    frame: pd.DataFrame, actual: np.ndarray, predicted: np.ndarray, group_column: str
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value, indices in frame.groupby(group_column, sort=True, dropna=False).indices.items():
        positions = np.asarray(indices, dtype=int)
        result.append(
            {group_column: value, **_regression_metrics(actual[positions], predicted[positions])}
        )
    return result


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".stage")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def train_commercial_model(
    settings: CommercialTrainingSettings | None = None,
    *,
    tracking_uri: str | None = None,
) -> dict[str, Any]:
    """Train, evaluate, log, and conditionally register the building forecaster."""
    settings = settings or CommercialTrainingSettings.from_environment()
    gold_path = settings.gold_path.expanduser().resolve()
    manifest_path = settings.dataset_manifest_path.expanduser().resolve()
    model_path = settings.model_path.expanduser().resolve()
    if not gold_path.is_file():
        raise FileNotFoundError(f"Commercial Gold dataset not found: {gold_path}")
    manifest = _validate_manifest(manifest_path, gold_path)
    tracking = (tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "")).strip()
    if not tracking:
        raise ValueError("Set MLFLOW_TRACKING_URI before commercial training.")
    if (
        not 0 < settings.train_fraction < 1
        or not 0 < settings.validation_fraction < 1
        or settings.train_fraction + settings.validation_fraction >= 1
    ):
        raise ValueError("Chronological split fractions must leave non-empty train/validation/test ranges")

    connection = duckdb.connect()
    try:
        gold_sql = "'" + str(gold_path).replace("'", "''") + "'"
        available = {
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({gold_sql})"
            ).fetchall()
        }
        required = {*FEATURE_COLUMNS, TARGET_COLUMN, DATE_COLUMN, ENTITY_COLUMN}
        missing = sorted(required - available)
        if missing:
            raise ValueError(f"Commercial Gold is missing required columns: {missing}")
        count, train_boundary, validation_boundary, unique_timestamps = connection.execute(
            f"""
            SELECT COUNT(*),
                quantile_disc({DATE_COLUMN}, {settings.train_fraction}),
                quantile_disc({DATE_COLUMN}, {settings.train_fraction + settings.validation_fraction}),
                COUNT(DISTINCT {DATE_COLUMN})
            FROM read_parquet({gold_sql})
            WHERE {TARGET_COLUMN} IS NOT NULL
            """
        ).fetchone()
        if unique_timestamps < 10:
            raise ValueError(
                f"At least 10 distinct target timestamps are required; found {unique_timestamps}"
            )
        train_boundary = pd.Timestamp(train_boundary)
        validation_boundary = pd.Timestamp(validation_boundary)
        if not train_boundary < validation_boundary:
            raise ValueError("Chronological split boundaries are not strictly increasing")

        train = _read_sample(
            connection, gold_path, None, train_boundary,
            settings.max_training_rows, settings.seed,
        )
        validation = _read_sample(
            connection, gold_path, train_boundary, validation_boundary,
            settings.max_validation_rows, settings.seed + 1,
        )
        test = _read_test_sample(
            connection, gold_path, validation_boundary,
            settings.max_test_rows, settings.seed + 2,
        )
    finally:
        connection.close()

    if train.empty or validation.empty or test.empty:
        raise ValueError(
            "Chronological sampling produced an empty split; inspect Gold target-time coverage."
        )
    train[DATE_COLUMN] = pd.to_datetime(train[DATE_COLUMN], errors="raise")
    validation[DATE_COLUMN] = pd.to_datetime(validation[DATE_COLUMN], errors="raise")
    test[DATE_COLUMN] = pd.to_datetime(test[DATE_COLUMN], errors="raise")
    if not (
        train[DATE_COLUMN].max() < validation[DATE_COLUMN].min()
        and validation[DATE_COLUMN].max() < test[DATE_COLUMN].min()
    ):
        raise ValueError("Chronological split validation failed: target times overlap")

    x_train, x_validation, x_test = (_features(frame) for frame in (train, validation, test))
    y_train, y_validation, y_test = (
        pd.to_numeric(frame[TARGET_COLUMN], errors="coerce").to_numpy(dtype=np.float64)
        for frame in (train, validation, test)
    )
    if any(not np.isfinite(values).all() for values in (y_train, y_validation, y_test)):
        raise ValueError("Commercial Gold contains non-finite target labels")
    if any((values < 0).any() for values in (y_train, y_validation, y_test)):
        raise ValueError("Commercial Gold energy targets must be non-negative for log1p training")

    candidate_names = ("lightgbm_direct", "lightgbm_log1p", "hist_gradient_boosting")
    fitted_candidates: dict[str, CommercialPredictionPipeline] = {}
    predictions: dict[str, dict[str, np.ndarray]] = {name: {} for name in candidate_names}
    baselines: dict[str, np.ndarray] = {}
    for candidate_name in candidate_names:
        estimator = _make_candidate(settings, candidate_name)
        estimator.fit(x_train, y_train)
        prediction_pipeline = CommercialPredictionPipeline(estimator)
        fitted_candidates[candidate_name] = prediction_pipeline
    validation_actual = y_validation
    validation_scores = {
        name: _regression_metrics(validation_actual, np.maximum(
            np.asarray(model.predict(x_validation), dtype=float).reshape(-1), 0.0
        ))["mae"]
        for name, model in fitted_candidates.items()
    }
    champion_name = min(validation_scores, key=lambda name: (validation_scores[name], name))
    prediction_pipeline = fitted_candidates[champion_name]
    for name, frame, features in (
        ("train", train, x_train),
        ("validation", validation, x_validation),
        ("test", test, x_test),
    ):
        for candidate_name, candidate_model in fitted_candidates.items():
            values = np.asarray(candidate_model.predict(features), dtype=np.float64).reshape(-1)
            if len(values) != len(frame) or not np.isfinite(values).all():
                raise ValueError(f"{name} {candidate_name} predictions have invalid shape or non-finite values")
            predictions[candidate_name][name] = np.maximum(values, 0.0)
        baselines[name] = np.maximum(
            pd.to_numeric(frame["energy_at_origin"], errors="coerce")
            .to_numpy(dtype=np.float64),
            0.0,
        )
        if not np.isfinite(baselines[name]).all():
            raise ValueError(f"{name} persistence baseline contains non-finite values")

    actuals = {"train": y_train, "validation": y_validation, "test": y_test}
    metrics = {
        split: {
            **{candidate: _regression_metrics(actuals[split], predictions[candidate][split]) for candidate in candidate_names},
            "persistence_baseline": _regression_metrics(actuals[split], baselines[split]),
        }
        for split in ("train", "validation", "test")
    }
    # Champion metrics are the serving contract; candidates remain available for comparison.
    champion_predictions = {split: predictions[champion_name][split] for split in predictions[champion_name]}
    horizon_metrics = _group_metrics(
        test, y_test, champion_predictions["test"], "forecast_horizon_hours"
    )
    building_metrics = _group_metrics(test, y_test, champion_predictions["test"], ENTITY_COLUMN)
    validation_wape = metrics["validation"][champion_name]["wape"]
    baseline_mae = metrics["validation"]["persistence_baseline"]["mae"]
    champion_mae = metrics["validation"][champion_name]["mae"]
    gate_failures = []
    if validation_wape is None or validation_wape > settings.max_validation_wape:
        gate_failures.append(
            f"validation WAPE {validation_wape} exceeds {settings.max_validation_wape}"
        )
    if settings.require_baseline_improvement and champion_mae >= baseline_mae:
        gate_failures.append(
            f"champion validation MAE {champion_mae:.6g} does not beat persistence {baseline_mae:.6g}"
        )
    promotion_passed = not gate_failures

    timestamp_ranges = {
        split: {
            "min": frame[DATE_COLUMN].min().isoformat(),
            "max": frame[DATE_COLUMN].max().isoformat(),
        }
        for split, frame in (("train", train), ("validation", validation), ("test", test))
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_metadata = {
        "schema_version": 1,
        "model_type": champion_name,
        "champion_model": champion_name,
        "candidate_models": list(candidate_names),
        "feature_columns": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_FEATURES,
        "target_column": TARGET_COLUMN,
        "entity_column": ENTITY_COLUMN,
        "region_join_column": "id.grid.coarse",
        "dataset_path": str(gold_path),
        "dataset_version": manifest.get("dataset_version", "unknown"),
        "quality_report": manifest.get("quality_report"),
        "quality_manifest": str(manifest_path),
        "split_strategy": "chronological_target_timestamp_70_15_15",
        "split_ranges": timestamp_ranges,
        "promotion_passed": promotion_passed,
        "promotion_failures": gate_failures,
        "metrics": metrics,
    }
    bundle_path = model_path.with_name(f"{model_path.stem}.{uuid.uuid4().hex}.joblib")
    joblib.dump(
        {
            "pipeline": prediction_pipeline,
            "feature_columns": FEATURE_COLUMNS,
            "metadata": model_metadata,
        },
        bundle_path,
    )

    log_root = LOG_ROOT
    model_card_path = log_root / "model_cards" / "commercial" / f"commercial-{uuid.uuid4().hex[:12]}.md"
    metrics_path = log_root / "model_metrics" / "commercial" / f"commercial-{uuid.uuid4().hex[:12]}.json"
    training_log_path = log_root / "training" / "commercial" / f"commercial-{uuid.uuid4().hex[:12]}.json"
    metrics_payload = {
        "model": model_metadata,
        "metrics_by_horizon": horizon_metrics,
        "metrics_by_building": building_metrics,
        "sampled_rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "available_gold_rows": int(count),
        "unique_target_timestamps": int(unique_timestamps),
    }
    _write_json(metrics_path, metrics_payload)
    model_card_path.parent.mkdir(parents=True, exist_ok=True)
    model_card_path.write_text(
        "# Commercial building demand forecast\n\n"
        f"- Dataset version: `{model_metadata['dataset_version']}`\n"
        f"- Feature count: {len(FEATURE_COLUMNS)}\n"
        f"- Champion model: `{champion_name}` (selected by validation MAE)\n"
        f"- Compared candidates: `{', '.join(candidate_names)}` plus persistence baseline\n"
        f"- Promotion passed: {promotion_passed}\n"
        f"- Promotion checks: {json.dumps(gate_failures)}\n\n"
        "## Chronological split ranges\n\n"
        + "\n".join(
            f"- {name}: {bounds['min']} through {bounds['max']}"
            for name, bounds in timestamp_ranges.items()
        )
        + "\n\n## Validation and test metrics\n\n"
        + "```json\n"
        + json.dumps(metrics, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )

    tracking_uri = tracking
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(settings.experiment_name)
    registered_version = None
    run_id = ""
    run_name = f"commercial-building-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        mlflow.set_tags(
            {
                "task": "commercial_building_forecasting",
                "target": TARGET_COLUMN,
                "split_strategy": "chronological_target_timestamp",
                "promotion_status": "passed" if promotion_passed else "rejected",
                "champion_model": champion_name,
                "dataset_version": str(model_metadata["dataset_version"]),
            }
        )
        mlflow.log_params(
            {
                "dataset_path": str(gold_path),
                "dataset_version": str(model_metadata["dataset_version"]),
                "feature_count": len(FEATURE_COLUMNS),
                "feature_order": json.dumps(FEATURE_COLUMNS),
                "candidate_models": json.dumps([*candidate_names, "persistence_baseline"]),
                "champion_model": champion_name,
                "champion_selection_metric": "validation_mae",
                "categorical_features": json.dumps(CATEGORICAL_FEATURES),
                "train_fraction": settings.train_fraction,
                "validation_fraction": settings.validation_fraction,
                "sampling_seed": settings.seed,
                "n_estimators": settings.n_estimators,
                "learning_rate": settings.learning_rate,
                "num_leaves": settings.num_leaves,
                "max_depth": settings.max_depth,
                "min_child_samples": settings.min_child_samples,
                "reg_lambda": settings.reg_lambda,
                "random_state": settings.random_state,
                "max_validation_wape": settings.max_validation_wape,
                "require_baseline_improvement": settings.require_baseline_improvement,
                "sampled_train_rows": len(train),
                "sampled_validation_rows": len(validation),
                "sampled_test_rows": len(test),
            }
        )
        # Keep MLflow's Metrics tab focused on model selection, the baseline,
        # and holdout quality instead of logging every candidate/split combination.
        flat_metrics: dict[str, float] = {
            f"validation_{candidate_name}_mae": float(
                metrics["validation"][candidate_name]["mae"]
            )
            for candidate_name in candidate_names
        }
        for split, model_names in (
            ("validation", (champion_name, "persistence_baseline")),
            ("test", (champion_name, "persistence_baseline")),
            ("train", (champion_name,)),
        ):
            for model_name in model_names:
                for metric in ("mae", "rmse", "wape"):
                    value = metrics[split][model_name][metric]
                    if value is not None:
                        flat_metrics[f"{split}_{model_name}_{metric}"] = float(value)
        if len(flat_metrics) > 20:
            raise RuntimeError(
                f"Commercial MLflow metric budget exceeded: {len(flat_metrics)} > 20"
            )
        mlflow.log_metrics(flat_metrics)
        mlflow.log_dict(model_metadata, "model_metadata.json")
        mlflow.log_artifact(str(manifest_path), artifact_path="dataset_quality")
        quality_report_path = manifest.get("quality_report")
        if quality_report_path and Path(quality_report_path).is_file():
            mlflow.log_artifact(quality_report_path, artifact_path="dataset_quality")
        mlflow.log_artifact(str(metrics_path), artifact_path="evaluation")
        mlflow.log_artifact(str(model_card_path), artifact_path="documentation")
        mlflow.log_artifact(str(bundle_path), artifact_path="model_bundle")
        signature = infer_signature(x_test.head(20), champion_predictions["test"][:20])
        mlflow.sklearn.log_model(
            prediction_pipeline,
            artifact_path="commercial_model",
            signature=signature,
            input_example=x_test.head(5),
            code_paths=[str(PROJECT_ROOT / "training")],
        )
        _write_json(
            training_log_path,
            {
                "status": "rejected" if not promotion_passed else "evaluated",
                "run_id": run_id,
                "experiment": settings.experiment_name,
                "champion_model": champion_name,
                "candidate_models": list(candidate_names),
                "selection_metric": "validation_mae",
                "dataset_version": model_metadata["dataset_version"],
                "promotion_passed": promotion_passed,
                "promotion_failures": gate_failures,
                "metrics_path": str(metrics_path),
                "model_card_path": str(model_card_path),
            },
        )
        mlflow.log_artifact(str(training_log_path), artifact_path="training")

    if promotion_passed:
        model_uri = f"runs:/{run_id}/commercial_model"
        registered = mlflow.register_model(
            model_uri=model_uri,
            name=settings.model_name,
        )
        registered_version = str(registered.version)
        mlflow.MlflowClient(tracking_uri=tracking_uri).set_registered_model_alias(
            settings.model_name, settings.model_alias, registered.version
        )
        shutil_copy = model_path.with_suffix(model_path.suffix + ".stage")
        os.replace(bundle_path, shutil_copy)
        os.replace(shutil_copy, model_path)
    else:
        # The run and artifacts remain available for review, but rejected models
        # are neither written as the active artifact nor registered/promoted.
        bundle_path.unlink(missing_ok=True)

    training_record = {
        "status": "promoted" if promotion_passed else "rejected",
        "run_id": run_id,
        "experiment": settings.experiment_name,
        "champion_model": champion_name,
        "candidate_models": list(candidate_names),
        "selection_metric": "validation_mae",
        "registered_model": settings.model_name if registered_version else None,
        "registered_version": registered_version,
        "alias": settings.model_alias if registered_version else None,
        "model_path": str(model_path) if promotion_passed else None,
        "dataset_version": model_metadata["dataset_version"],
        "metrics_path": str(metrics_path),
        "model_card_path": str(model_card_path),
        "training_log_path": str(training_log_path),
        "promotion_passed": promotion_passed,
        "promotion_failures": gate_failures,
        "metrics": metrics,
        "metrics_by_horizon": horizon_metrics,
        "metrics_by_building": building_metrics,
        "split_ranges": timestamp_ranges,
    }
    _write_json(training_log_path, training_record)
    return training_record
