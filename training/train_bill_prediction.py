"""Train and register the customer bill prediction model with MLflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from customer_bill.model import NaiveProjectionRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = Path(
    os.getenv("GRIDVISION_LOG_DIR", PROJECT_ROOT / "logs")
).resolve()
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "gold" / "customer_gold.parquet"
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "models" / "customer_bill_prediction.pkl"
DEFAULT_MODEL_NAME = "customer-bill-prediction"
MLFLOW_EXPERIMENT_NAME = "gridvision-customer-bill-prediction-v2"
TARGET = "target_month_kwh"
DATE_COLUMN = "month_start"
CATEGORICAL_FEATURES = (
    "idf_kw",
    "specific_use_type",
    "building_type",
    "vintage",
    "usetype",
)
NUMERIC_FEATURES = (
    "building_area_m2",
    "footprint_area_m2",
    "effective_year_built",
    "id_grid_finer",
    "latitude",
    "longitude",
    "cutoff_day",
    "days_in_month",
    "month_of_year",
    "month_sin",
    "month_cos",
    "prior_month_kwh",
    "prior_month_kwh_per_m2",
    "observed_hours_to_cutoff",
    "cumulative_energy_kwh",
    "recent_7d_energy_kwh",
    "recent_7d_mean_hourly_kwh",
    "mean_hourly_energy_to_cutoff",
    "cumulative_energy_per_m2",
    "naive_projected_month_kwh",
)
FEATURES = list(NUMERIC_FEATURES + CATEGORICAL_FEATURES)
PARAMETER_CANDIDATES = (
    {"max_iter": 80, "learning_rate": 0.08, "max_leaf_nodes": 15, "l2_regularization": 0.0},
    {"max_iter": 120, "learning_rate": 0.05, "max_leaf_nodes": 15, "l2_regularization": 1.0},
    {"max_iter": 120, "learning_rate": 0.08, "max_leaf_nodes": 31, "l2_regularization": 1.0},
)
TRACKED_PACKAGES = (
    "mlflow",
    "numpy",
    "pandas",
    "pyarrow",
    "scikit-learn",
    "duckdb",
)


def _dataset_lineage(data_path: Path) -> dict[str, Any]:
    data_root = data_path.resolve().parent.parent
    latest_manifest = (
        data_root
        / "metadata"
        / "dataset_versions"
        / "customer_gold"
        / "latest.json"
    )
    if not latest_manifest.is_file():
        return {
            "tracked": False,
            "dataset_path": str(data_path.resolve()),
        }
    manifest = json.loads(latest_manifest.read_text(encoding="utf-8"))

    def resolve_manifest_path(
        value: str, *, root: Path, container_root: Path, host_root: Path
    ) -> Path:
        path = Path(value)
        if not path.is_absolute():
            return root / path
        try:
            relative_path = path.relative_to(container_root)
        except ValueError:
            return path
        return host_root / relative_path

    report_path = resolve_manifest_path(
        manifest["quality_report"],
        root=data_root,
        container_root=Path("/opt/gridvision/logs"),
        host_root=LOG_ROOT,
    )
    versioned_dataset_path = resolve_manifest_path(
        manifest["versioned_dataset_path"],
        root=data_root,
        container_root=Path("/opt/gridvision/data"),
        host_root=data_root,
    )
    if not versioned_dataset_path.is_file():
        raise FileNotFoundError(
            f"Versioned gold dataset snapshot is missing: {versioned_dataset_path}"
        )
    if not report_path.is_file():
        raise FileNotFoundError(f"Gold dataset quality report is missing: {report_path}")
    return {
        "tracked": True,
        "dataset_name": manifest["dataset_name"],
        "dataset_version": manifest["dataset_version"],
        "dataset_path": str(data_path.resolve()),
        "dataset_rows": int(manifest["row_count"]),
        "quality_passed": bool(manifest["quality_passed"]),
        "quality_report": str(report_path),
        "manifest_path": str(latest_manifest),
        "versioned_dataset_path": str(versioned_dataset_path),
        "parent_dataset_versions": manifest.get("parent_dataset_versions", {}),
    }


def _package_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in TRACKED_PACKAGES:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".stage",
        delete=False,
    ) as temporary_file:
        stage_path = Path(temporary_file.name)
        json.dump(payload, temporary_file, indent=2, sort_keys=True, default=str)
        temporary_file.write("\n")
    try:
        os.replace(stage_path, path)
    finally:
        stage_path.unlink(missing_ok=True)


def _model_card(
    *,
    model_name: str,
    model_version: str,
    model_alias: str,
    selected_model: str,
    dataset: dict[str, Any],
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
    parameters: dict[str, Any],
    run_id: str,
    split_ranges: dict[str, str],
) -> str:
    dataset_version = dataset.get("dataset_version", "untracked")
    return f"""# Model Card: {model_name} v{model_version}

## Summary

- **Task:** Estimate a residential customer's target-month energy consumption (kWh) from cutoff-time observations.
- **Registered alias:** `{model_alias}`
- **Selected estimator:** `{selected_model}`
- **MLflow run:** `{run_id}`
- **Training dataset version:** `{dataset_version}`
- **Dataset quality passed:** `{dataset.get('quality_passed', 'not recorded')}`

## Intended use

This model is an experimental, decision-support estimate for customer bill prediction. It is not a meter reading, a guaranteed invoice, or a substitute for a utility's billing system. The configured tariff is illustrative and must be replaced with the customer's applicable tariff before interpreting bill estimates.

## Data and evaluation

- **Dataset path:** `{dataset.get("dataset_path", "unknown")}`
- **Versioned dataset snapshot:** `{dataset.get("versioned_dataset_path", "not recorded")}`
- **Dataset rows recorded in manifest:** `{dataset.get("dataset_rows", "unknown")}`
- **Target:** `{TARGET}` (full target-month kWh)
- **Split:** Chronological by month into train, validation, and held-out test sets; rows from a month are kept together.
- **Partition month ranges:** `{json.dumps(split_ranges, sort_keys=True)}`
- **Validation metrics:** `{json.dumps(validation_metrics, sort_keys=True)}`
- **Held-out test metrics:** `{json.dumps(test_metrics, sort_keys=True)}`
- **Best tuned candidate parameters:** `{json.dumps(parameters, sort_keys=True)}`
- **Input features:** {", ".join(FEATURES)}

## Limitations and risks

- Evaluation is based on the supplied sampled dataset and may not represent other buildings, regions, seasons, or meter behavior.
- The source dataset does not provide customer-specific billing tariffs; any currency estimate uses an illustrative configured tariff.
- Performance can degrade under missing, delayed, shifted, or out-of-distribution meter readings or building attributes.
- The prediction is for monthly energy consumption; the model does not verify a final utility invoice.
- Validate data quality, local tariff rules, and performance on representative recent data before operational use.

## Reproducibility

- **Features and target:** recorded above and in the MLflow model signature.
- **Selected model parameters:** recorded above and as MLflow run parameters.
- **Dataset lineage:** `{json.dumps(dataset.get("parent_dataset_versions", {}), sort_keys=True)}`
- **Model artifact:** logged with the MLflow run; a local pickle is also exported alongside its metadata.
"""


def _make_pipeline(parameters: dict[str, Any]) -> Pipeline:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric, list(NUMERIC_FEATURES)),
            ("categorical", categorical, list(CATEGORICAL_FEATURES)),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                HistGradientBoostingRegressor(
                    random_state=42,
                    early_stopping=False,
                    **parameters,
                ),
            ),
        ]
    )


def _load_dataset(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Customer bill gold dataset was not found: {path}")
    data = pd.read_parquet(path)
    required = set(FEATURES + [TARGET, DATE_COLUMN])
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Gold dataset is missing required columns: {missing}")
    data[DATE_COLUMN] = pd.to_datetime(data[DATE_COLUMN], errors="raise")
    data = data.dropna(subset=[TARGET, DATE_COLUMN]).sort_values(
        [DATE_COLUMN, "cutoff_day"]
    )
    if data.empty:
        raise ValueError("Gold dataset contains no usable labeled records.")
    if not np.isfinite(data[TARGET].to_numpy(dtype=float)).all():
        raise ValueError("Gold dataset target contains non-finite values.")
    for feature in NUMERIC_FEATURES:
        data[feature] = pd.to_numeric(data[feature], errors="raise").astype("float64")
    return data.reset_index(drop=True)


def _temporal_split(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[pd.Timestamp]]:
    months = list(pd.Index(data[DATE_COLUMN].drop_duplicates()).sort_values())
    if len(months) < 8:
        raise ValueError(
            f"At least 8 distinct target months are required for temporal training; found {len(months)}."
        )
    train_end = max(3, int(len(months) * 0.70))
    validation_end = max(train_end + 1, int(len(months) * 0.85))
    validation_end = min(validation_end, len(months) - 1)
    train_months = set(months[:train_end])
    validation_months = set(months[train_end:validation_end])
    test_months = set(months[validation_end:])
    train = data[data[DATE_COLUMN].isin(train_months)]
    validation = data[data[DATE_COLUMN].isin(validation_months)]
    test = data[data[DATE_COLUMN].isin(test_months)]
    if train.empty or validation.empty or test.empty:
        raise ValueError("Temporal train/validation/test split produced an empty partition.")
    return train, validation, test, months[:train_end]


def _temporal_cv_splits(
    train: pd.DataFrame,
    train_months: list[pd.Timestamp],
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Create expanding-window folds that never split rows from the same month."""
    months = pd.Index(train_months)
    if len(months) < 5:
        raise ValueError("At least 5 training months are needed for temporal tuning.")
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    validation_width = max(1, len(months) // 5)
    for validation_start in (
        len(months) - 3 * validation_width,
        len(months) - 2 * validation_width,
        len(months) - validation_width,
    ):
        if validation_start < 2:
            continue
        validation_months = set(months[validation_start : validation_start + validation_width])
        train_month_set = set(months[:validation_start])
        training_rows = np.flatnonzero(train[DATE_COLUMN].isin(train_month_set).to_numpy())
        validation_rows = np.flatnonzero(train[DATE_COLUMN].isin(validation_months).to_numpy())
        if len(training_rows) and len(validation_rows):
            folds.append((training_rows, validation_rows))
    if len(folds) < 2:
        raise ValueError("Unable to create at least two chronological tuning folds.")
    return folds


def _metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae_kwh": float(mean_absolute_error(actual, predicted)),
        "rmse_kwh": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
    }


def train_and_log(
    data_path: Path = DEFAULT_DATA_PATH,
    tracking_uri: str | None = None,
    model_name: str | None = None,
    alias: str | None = None,
    artifact_path: Path = DEFAULT_ARTIFACT_PATH,
) -> dict[str, Any]:
    """Select against a simple baseline, evaluate on holdout, and log the champion."""
    resolved_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI")
    if not resolved_uri:
        raise ValueError("Set MLFLOW_TRACKING_URI before starting model training.")
    selected_model_name = model_name or os.getenv("MLFLOW_MODEL_NAME", DEFAULT_MODEL_NAME)
    selected_alias = alias or os.getenv("MLFLOW_MODEL_ALIAS", "champion")
    mlflow.set_tracking_uri(resolved_uri)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    data_path = data_path.resolve()
    dataset = _dataset_lineage(data_path)
    if dataset.get("tracked") and not dataset.get("quality_passed"):
        raise ValueError(
            "Gold dataset has a failed data-quality report; refusing to train."
        )
    data = _load_dataset(data_path)
    train, validation, test, train_months = _temporal_split(data)
    split_ranges = {
        name: (
            f"{partition[DATE_COLUMN].min().date()} to "
            f"{partition[DATE_COLUMN].max().date()}"
        )
        for name, partition in (
            ("train", train),
            ("validation", validation),
            ("test", test),
        )
    }
    x_train, y_train = train[FEATURES], train[TARGET].astype(float)
    x_validation, y_validation = validation[FEATURES], validation[TARGET].astype(float)
    x_test, y_test = test[FEATURES], test[TARGET].astype(float)

    folds = _temporal_cv_splits(train, train_months)
    best_parameters: dict[str, Any] | None = None
    best_cv_mae = float("inf")
    cv_results: list[dict[str, Any]] = []
    for candidate_index, parameters in enumerate(PARAMETER_CANDIDATES, start=1):
        fold_errors = []
        for training_indices, validation_indices in folds:
            estimator = _make_pipeline(parameters)
            estimator.fit(x_train.iloc[training_indices], y_train.iloc[training_indices])
            fold_errors.append(
                mean_absolute_error(
                    y_train.iloc[validation_indices],
                    estimator.predict(x_train.iloc[validation_indices]),
                )
            )
        candidate_mae = float(np.mean(fold_errors))
        cv_results.append(
            {
                "candidate": candidate_index,
                "parameters": parameters,
                "fold_mae_kwh": [float(error) for error in fold_errors],
                "mean_cv_mae_kwh": candidate_mae,
            }
        )
        if candidate_mae < best_cv_mae:
            best_cv_mae = candidate_mae
            best_parameters = parameters
    if best_parameters is None:
        raise RuntimeError("Hyperparameter search did not produce a candidate model.")

    tuned_model = _make_pipeline(best_parameters).fit(x_train, y_train)
    tuned_validation_predictions = tuned_model.predict(x_validation)
    tuned_validation_mae = float(mean_absolute_error(y_validation, tuned_validation_predictions))
    baseline_model = NaiveProjectionRegressor().fit(x_train, y_train)
    baseline_validation_predictions = baseline_model.predict(x_validation)
    baseline_validation_mae = float(mean_absolute_error(y_validation, baseline_validation_predictions))

    if tuned_validation_mae < baseline_validation_mae:
        selected_model: Any = _make_pipeline(best_parameters)
        selected_model.fit(
            pd.concat([x_train, x_validation], ignore_index=True),
            pd.concat([y_train, y_validation], ignore_index=True),
        )
        selected_kind = "hist_gradient_boosting"
    else:
        selected_model = NaiveProjectionRegressor().fit(
            pd.concat([x_train, x_validation], ignore_index=True),
            pd.concat([y_train, y_validation], ignore_index=True),
        )
        selected_kind = "naive_month_projection"

    test_predictions = selected_model.predict(x_test)
    test_metrics = _metrics(y_test, test_predictions)
    validation_metrics = {
        "selected_validation_mae_kwh": min(tuned_validation_mae, baseline_validation_mae),
        "tuned_validation_mae_kwh": tuned_validation_mae,
        "baseline_validation_mae_kwh": baseline_validation_mae,
        "tuned_cv_mae_kwh": best_cv_mae,
    }

    with mlflow.start_run(run_name=f"customer-bill-{selected_kind}") as run:
        package_versions = _package_versions()
        mlflow.set_tags(
            {
                "task": "customer_bill_prediction",
                "selected_model": selected_kind,
                "target": TARGET,
                "split_strategy": "chronological_by_month",
                "dataset_version": dataset.get("dataset_version", "untracked"),
                "dataset_quality_passed": str(
                    dataset.get("quality_passed", "not_recorded")
                ).lower(),
            }
        )
        mlflow.log_params(
            {
                "model_name": selected_model_name,
                "model_alias": selected_alias,
                "training_rows": len(train),
                "validation_rows": len(validation),
                "test_rows": len(test),
                "training_months": len(train_months),
                "feature_count": len(FEATURES),
                "selected_model": selected_kind,
                "tuned_parameters": json.dumps(best_parameters, sort_keys=True),
                "dataset_version": dataset.get("dataset_version", "untracked"),
                "dataset_path": str(data_path),
                **{
                    f"{name}_month_range": date_range
                    for name, date_range in split_ranges.items()
                },
                "dataset_quality_passed": dataset.get(
                    "quality_passed", "not_recorded"
                ),
                **{
                    f"version_{key.replace('-', '_')}": value
                    for key, value in package_versions.items()
                },
            }
        )
        for key, value in {**validation_metrics, **test_metrics}.items():
            mlflow.log_metric(key, value)
        for candidate in cv_results:
            mlflow.log_metric(
                f"candidate_{candidate['candidate']}_mean_cv_mae_kwh",
                candidate["mean_cv_mae_kwh"],
            )
        signature = infer_signature(x_validation, selected_model.predict(x_validation))
        model_info = mlflow.sklearn.log_model(
            sk_model=selected_model,
            artifact_path="model",
            code_paths=[str(Path(__file__).resolve().parent / "customer_bill")],
            signature=signature,
            input_example=x_validation.head(3),
            registered_model_name=selected_model_name,
        )
        client = mlflow.tracking.MlflowClient()
        if not model_info.registered_model_version:
            raise RuntimeError(
                f"MLflow did not register a version of {selected_model_name}."
            )
        model_version = str(model_info.registered_model_version)
        model_metadata = {
            "model_name": selected_model_name,
            "model_version": model_version,
            "model_alias": selected_alias,
            "mlflow_run_id": run.info.run_id,
            "selected_model": selected_kind,
            "target": TARGET,
            "features": FEATURES,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
            "hyperparameter_search": cv_results,
            "dataset": dataset,
            "package_versions": package_versions,
            "tariff_inr_per_kwh": float(
                os.getenv("CUSTOMER_TARIFF_INR_PER_KWH", "10.0")
            ),
        }
        artifact_path = artifact_path.resolve()
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=artifact_path.parent,
            prefix=f".{artifact_path.stem}.",
            suffix=".stage",
            delete=False,
        ) as temporary_file:
            stage_path = Path(temporary_file.name)
        try:
            joblib.dump({"model": selected_model, **model_metadata}, stage_path)
            os.replace(stage_path, artifact_path)
        finally:
            stage_path.unlink(missing_ok=True)
        model_metadata["pickle_sha256"] = _sha256(artifact_path)
        model_card_path = (
            LOG_ROOT
            / "model_cards"
            / f"{selected_model_name}-v{model_version}.md"
        )
        model_card_path.parent.mkdir(parents=True, exist_ok=True)
        model_card = _model_card(
            model_name=selected_model_name,
            model_version=model_version,
            model_alias=selected_alias,
            selected_model=selected_kind,
            dataset=dataset,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            parameters=best_parameters,
            run_id=run.info.run_id,
            split_ranges=split_ranges,
        )
        model_card_path.write_text(model_card, encoding="utf-8")
        metadata_path = artifact_path.with_suffix(".metadata.json")
        model_metadata.update(
            {
                "model_card_path": str(model_card_path),
                "metadata_path": str(metadata_path),
                "split_month_ranges": split_ranges,
                "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_json(metadata_path, model_metadata)
        metrics_path = (
            LOG_ROOT
            / "model_metrics"
            / f"{selected_model_name}-v{model_version}.json"
        )
        metrics_record = {
            "schema_version": 1,
            "logged_at_utc": model_metadata["logged_at_utc"],
            "model_name": selected_model_name,
            "model_version": model_version,
            "model_alias": selected_alias,
            "mlflow_run_id": run.info.run_id,
            "selected_model": selected_kind,
            "parameters": best_parameters,
            "candidate_search": cv_results,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
            "split_month_ranges": split_ranges,
            "dataset": dataset,
            "package_versions": package_versions,
        }
        _write_json(metrics_path, metrics_record)
        training_log_path = LOG_ROOT / "training" / f"{run.info.run_id}.json"
        _write_json(
            training_log_path,
            {
                "schema_version": 1,
                "logged_at_utc": model_metadata["logged_at_utc"],
                "status": "completed",
                "model_name": selected_model_name,
                "model_version": model_version,
                "model_alias": selected_alias,
                "mlflow_run_id": run.info.run_id,
                "artifact_path": str(artifact_path),
                "metadata_path": str(metadata_path),
                "model_card_path": str(model_card_path),
                "metrics_path": str(metrics_path),
                "dataset_version": dataset.get("dataset_version", "untracked"),
                "rows": {
                    "train": len(train),
                    "validation": len(validation),
                    "test": len(test),
                },
            },
        )
        mlflow.log_dict(model_metadata, "model_metadata.json")
        mlflow.log_artifact(str(metadata_path), artifact_path="local_exports")
        mlflow.log_artifact(str(model_card_path), artifact_path="documentation")
        mlflow.log_artifact(str(artifact_path), artifact_path="local_exports")
        mlflow.log_artifact(str(metrics_path), artifact_path="model_metrics")
        mlflow.log_artifact(str(training_log_path), artifact_path="training")
        if dataset.get("tracked"):
            mlflow.log_artifact(
                dataset["manifest_path"],
                artifact_path="dataset_lineage",
            )
            mlflow.log_artifact(
                dataset["quality_report"],
                artifact_path="data_quality",
            )
            mlflow.log_artifact(
                dataset["versioned_dataset_path"],
                artifact_path="dataset_lineage",
            )
        client.set_registered_model_alias(
            selected_model_name,
            selected_alias,
            model_version,
        )
        for key, value in {
            "dataset_version": dataset.get("dataset_version", "untracked"),
            "selected_model": selected_kind,
            "training_run_id": run.info.run_id,
        }.items():
            client.set_model_version_tag(
                selected_model_name,
                model_version,
                key,
                str(value),
            )
        return {
            "run_id": run.info.run_id,
            "model_name": selected_model_name,
            "model_version": model_version,
            "model_alias": selected_alias,
            "selected_model": selected_kind,
            "artifact_path": str(artifact_path),
            "metadata_path": str(metadata_path),
            "model_card_path": str(model_card_path),
            "metrics_path": str(metrics_path),
            "training_log_path": str(training_log_path),
            "pickle_sha256": model_metadata["pickle_sha256"],
            "dataset_version": dataset.get("dataset_version", "untracked"),
            "dataset_quality_passed": dataset.get(
                "quality_passed", "not_recorded"
            ),
            "package_versions": package_versions,
            "validation": validation_metrics,
            "test": test_metrics,
            "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--alias", default=None)
    parser.add_argument("--artifact-path", type=Path, default=DEFAULT_ARTIFACT_PATH)
    arguments = parser.parse_args()
    try:
        result = train_and_log(
            data_path=arguments.data_path,
            tracking_uri=arguments.tracking_uri,
            model_name=arguments.model_name,
            alias=arguments.alias,
            artifact_path=arguments.artifact_path,
        )
    except Exception as exc:
        failed_at = datetime.now(timezone.utc)
        _write_json(
            LOG_ROOT
            / "training"
            / f"failed-{failed_at.strftime('%Y%m%dT%H%M%S.%fZ')}.json",
            {
                "schema_version": 1,
                "logged_at_utc": failed_at.isoformat(),
                "status": "failed",
                "data_path": str(arguments.data_path.resolve()),
                "model_name": arguments.model_name or DEFAULT_MODEL_NAME,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
