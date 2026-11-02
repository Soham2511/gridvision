"""MLflow tracking for GridVision training and held-out evaluation."""

from __future__ import annotations

import json
import importlib.util
import logging
import math
import os
from pathlib import Path
import sys
from typing import Any

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[5]

TRACKED_METRICS = {
    "validation_detection": (
        "precision",
        "recall",
        "f1",
        "pr_auc",
        "event_precision",
        "event_recall",
        "event_detection_delay_hours",
        "false_alerts_per_customer",
    ),
    "test_detection": (
        "precision",
        "recall",
        "f1",
        "pr_auc",
        "event_precision",
        "event_recall",
        "event_detection_delay_hours",
        "false_alerts_per_customer",
    ),
    "test_classification": ("macro_f1",),
    "spatial_event_localization": (
        "event_precision",
        "event_recall",
        "event_f1",
        "event_detection_delay_hours",
        "cluster_event_purity",
    ),
}


def important_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    """Return only selected finite scalar evaluation metrics for MLflow."""
    tracked: dict[str, float] = {}
    for section, names in TRACKED_METRICS.items():
        values = metrics.get(section, {})
        if not isinstance(values, dict):
            continue
        for name in names:
            value = values.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_value = float(value)
                if math.isfinite(numeric_value):
                    tracked[f"{section}.{name}"] = numeric_value
    return tracked


def run_tracked_existing_model(
    model_path: str | Path,
    report_dir: str | Path,
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
) -> dict[str, Any]:
    """Track a validated local bundle and its saved evaluation without retraining."""
    try:
        import mlflow
    except ImportError as error:
        raise RuntimeError(
            "MLflow is required for tracked inference. Install requirements.txt."
        ) from error

    from gridvision_pipeline import load_model_bundle

    artifact = Path(model_path).resolve()
    reports = Path(report_dir).resolve()
    metrics_path = reports / "evaluation_metrics.json"
    localization_path = reports / "event_localization_evaluation.json"
    missing = [str(path) for path in (artifact, metrics_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Cannot reuse anomaly artifacts; required files are missing: "
            + ", ".join(missing)
        )
    bundle = load_model_bundle(artifact)
    evaluation = json.loads(metrics_path.read_text(encoding="utf-8"))
    selected_tracking_uri = tracking_uri or os.environ.get(
        "MLFLOW_TRACKING_URI",
        "http://127.0.0.1:15001",
    )
    mlflow.set_tracking_uri(selected_tracking_uri)
    selected_experiment_name = (
        experiment_name
        or os.environ.get("MLFLOW_EXPERIMENT_NAME", "gridvision-anomaly-detection")
    )
    mlflow.set_experiment(selected_experiment_name)
    tracked = important_metrics(evaluation.get("metrics", evaluation))
    with mlflow.start_run(run_name="gridvision-anomaly-artifact-reuse") as run:
        mlflow.log_param("artifact_reused", True)
        mlflow.log_param("model_artifact", str(artifact))
        mlflow.log_metrics(tracked)
        mlflow.log_artifact(str(artifact), artifact_path="model")
        mlflow.log_artifact(str(metrics_path), artifact_path="evaluation")
        if localization_path.is_file():
            mlflow.log_artifact(str(localization_path), artifact_path="evaluation")
        model_name = os.environ.get(
            "ANOMALY_MLFLOW_MODEL_NAME", "gridvision-anomaly-detection"
        )
        registered_model = mlflow.register_model(
            f"runs:/{run.info.run_id}/model/{artifact.name}", model_name
        )
        alias = os.environ.get("ANOMALY_MLFLOW_MODEL_ALIAS", "champion")
        mlflow.MlflowClient().set_registered_model_alias(
            model_name, alias, registered_model.version
        )
    return {
        "run_id": run.info.run_id,
        "experiment_name": selected_experiment_name,
        "registered_model": model_name,
        "registered_version": registered_model.version,
        "model_version": bundle.get("model_version", "saved_bundle"),
        "metrics": tracked,
        "artifact_reused": True,
    }


def run_tracked_training(
    prepared_data_path: str | Path,
    model_path: str | Path,
    report_dir: str | Path,
    gold_features_path: str | Path | None = None,
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
) -> dict[str, Any]:
    """Train, evaluate, and log the compact GridVision model artifact set."""
    try:
        import mlflow
    except ImportError as error:
        raise RuntimeError(
            "MLflow is required for tracked training. Install requirements.txt."
        ) from error

    from gridvision_pipeline import GridVisionExperiment, PipelineConfig

    dataset_path = Path(prepared_data_path).resolve()
    gold_path = Path(gold_features_path).resolve() if gold_features_path else None
    model_destination = Path(model_path).resolve()
    reports = Path(report_dir).resolve()
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Prepared model dataset not found: {dataset_path}")

    selected_tracking_uri = tracking_uri or os.environ.get(
        "MLFLOW_TRACKING_URI",
        "http://127.0.0.1:15001",
    )
    mlflow.set_tracking_uri(selected_tracking_uri)
    selected_experiment_name = (
        experiment_name
        or os.environ.get("MLFLOW_EXPERIMENT_NAME", "gridvision-anomaly-detection")
    )
    mlflow.set_experiment(selected_experiment_name)

    config = PipelineConfig(
        parquet_path=str(dataset_path),
        gold_features_path=str(gold_path) if gold_path else None,
        model_path=str(model_destination),
        report_dir=str(reports),
    )
    experiment = GridVisionExperiment(config)
    logger.info("Starting GridVision tracked training on %s", dataset_path)
    with mlflow.start_run(run_name="gridvision-anomaly-training") as run:
        mlflow.log_params(
            {
                "random_seed": config.random_seed,
                "train_customer_sample": config.train_customer_sample,
                "validation_customer_sample": config.validation_customer_sample,
                "test_customer_sample": config.test_customer_sample,
                "training_events_per_class": config.training_events_per_class,
                "evaluation_events_per_class": config.evaluation_events_per_class,
                "point_feature_count": 30,
                "input_column_count": 5,
                "model_type": "RandomForestClassifier",
                "gold_features_enabled": gold_path is not None,
            }
        )
        try:
            result = experiment.run()
        except Exception:
            logger.exception("GridVision training failed for %s", dataset_path)
            raise

        selected_metrics = important_metrics(
            {
                **experiment.metrics,
                "spatial_event_localization": experiment.event_localization_metrics,
            }
        )
        mlflow.log_metrics(selected_metrics)
        mlflow.set_tags(
            {
                "dataset_path": str(dataset_path),
                "source_rows": str(experiment.profile["rows"]),
                "customer_overlap": str(experiment.split_integrity["customer_overlap"]),
                "labels_used_for_training": "synthetic injection only",
                "source_anomaly_labels_used": "false",
                "model_input_columns": "OBJECTID,timestamp,normalized_building_energy_kwh,latitude,longitude",
                "gold_features_path": str(gold_path) if gold_path else "not configured",
            }
        )
        artifacts = result["artifacts"]
        for artifact_key in (
            "model",
            "metrics",
            "event_localization_evaluation",
        ):
            artifact_path = Path(artifacts[artifact_key])
            if not artifact_path.is_file():
                raise FileNotFoundError(
                    f"Expected MLflow artifact was not created: {artifact_path}"
                )
            mlflow.log_artifact(
                str(artifact_path),
                artifact_path="model" if artifact_key == "model" else "evaluation",
            )
        model_name = os.environ.get(
            "ANOMALY_MLFLOW_MODEL_NAME", "gridvision-anomaly-detection"
        )
        registered_model = mlflow.register_model(
            f"runs:/{run.info.run_id}/model/{Path(artifacts['model']).name}",
            model_name,
        )
        alias = os.environ.get("ANOMALY_MLFLOW_MODEL_ALIAS", "champion")
        mlflow.MlflowClient().set_registered_model_alias(
            model_name, alias, registered_model.version
        )
        logger.info(
            "GridVision training completed: run_id=%s metrics=%s artifacts=%s",
            run.info.run_id,
            sorted(selected_metrics),
            ["model", "metrics", "event_localization_evaluation"],
        )
        return {
            "run_id": run.info.run_id,
            "experiment_name": selected_experiment_name,
            "registered_model": model_name,
            "registered_version": registered_model.version,
            "metrics": selected_metrics,
            "artifacts": {
                key: str(artifacts[key])
                for key in ("model", "metrics", "event_localization_evaluation")
            },
            "result": result,
        }


def main() -> None:
    """Prepare the source parquet and run a complete tracked training job."""
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError(
            "GridVision training is supported on Python 3.11–3.13; "
            f"this interpreter is Python {sys.version_info.major}.{sys.version_info.minor}."
        )
    if importlib.util.find_spec("mlflow") is None:
        raise RuntimeError(
            "MLflow is not installed in this Python environment. Install "
            "requirements.txt in a supported Python 3.11–3.13 environment."
        )

    from gridvision_data import build_gold_features, parse_bronze_to_silver
    from gridvision_logging import configure_logging

    configure_logging()
    source_path = Path(
        os.environ.get(
            "GRIDVISION_SOURCE_DATA",
                PROJECT_ROOT / "data" / "anomaly_prediction" / "synthetic_2019_normal.parquet",
        )
    )
    prepared_path = Path(
        os.environ.get(
            "GRIDVISION_SILVER_DATA",
            PROJECT_ROOT / "data" / "anomaly_prediction" / "silver" / "synthetic_2019_silver.parquet",
        )
    )
    gold_path = Path(
        os.environ.get(
            "GRIDVISION_GOLD_DATA",
            PROJECT_ROOT / "data" / "anomaly_prediction" / "gold" / "gridvision_model_features.parquet",
        )
    )
    logger.info("Preparing GridVision model inputs from %s", source_path)
    if source_path.is_file() and prepared_path.is_file():
        from gridvision_pipeline import inspect_parquet

        silver = inspect_parquet(prepared_path)
        silver["path"] = str(prepared_path)
        logger.info("Reusing prepared Silver anomaly data at %s", prepared_path)
    else:
        silver = parse_bronze_to_silver(source_path, prepared_path)
    if gold_path.is_file():
        from gridvision_pipeline import inspect_parquet

        gold = inspect_parquet(gold_path)
        gold["path"] = str(gold_path)
        logger.info("Reusing generated Gold anomaly features at %s", gold_path)
    else:
        gold = build_gold_features(silver["path"], gold_path)
    logger.info(
        "Built silver (%s rows) and gold (%s rows); starting tracked training",
        silver["rows"],
        gold["rows"],
    )
    model_path = Path(os.environ.get(
        "GRIDVISION_MODEL_PATH",
        PROJECT_ROOT / "models" / "anomaly_prediction" / "gridvision_anomaly_model.joblib",
    ))
    report_dir = Path(os.environ.get(
        "GRIDVISION_REPORT_DIR",
        PROJECT_ROOT / "reports" / "anomaly_prediction" / "training",
    ))
    if (
        os.environ.get("ANOMALY_FORCE_RETRAIN", "").lower() not in {"1", "true", "yes"}
        and model_path.is_file()
        and (report_dir / "evaluation_metrics.json").is_file()
    ):
        result = run_tracked_existing_model(
            model_path=model_path,
            report_dir=report_dir,
        )
    else:
        result = run_tracked_training(
            prepared_data_path=silver["path"],
            model_path=str(model_path),
            report_dir=str(report_dir),
            gold_features_path=gold["path"],
        )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
