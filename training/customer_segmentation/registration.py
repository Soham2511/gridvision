"""MLflow tracking and registry integration for segmentation bundles."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.pipeline import Pipeline

from .config import SegmentationSettings

EXPERIMENT_NAME = os.getenv(
    "SEGMENTATION_MLFLOW_EXPERIMENT",
    "gridvision-government-customer-segmentation",
)
MODEL_PREFIX = os.getenv(
    "SEGMENTATION_MLFLOW_MODEL_PREFIX",
    "gridvision-government-customer-segmentation",
)


def _source_revision() -> tuple[str | None, bool | None]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return revision, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def register_models(settings: SegmentationSettings) -> dict[str, Any]:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not tracking_uri:
        raise RuntimeError("MLFLOW_TRACKING_URI is required to register segmentation models")
    mlflow.set_tracking_uri(tracking_uri)
    experiment = mlflow.set_experiment(EXPERIMENT_NAME)
    client = MlflowClient(tracking_uri=tracking_uri)
    metadata = json.loads((settings.output_dir / "model_metadata.json").read_text())
    model_version = metadata["model_version"]
    trained_models = metadata.get("trained_models", [])
    if not trained_models:
        return {
            "experiment": EXPERIMENT_NAME,
            "run_id": None,
            "models": [],
            "registration_skipped": "no valid clustering model was available",
        }
    expected_names = {
        model["model_category"]: f"{MODEL_PREFIX}-{model['model_category'].lower()}"
        for model in trained_models
    }
    prior_runs = client.search_runs(
        [experiment.experiment_id],
        filter_string=f"tags.model_version = '{model_version}'",
        order_by=["attributes.start_time DESC"],
    )
    for prior_run in prior_runs:
        prior_models: list[dict[str, str]] = []
        complete = True
        for category, registered_name in expected_names.items():
            versions = [
                version
                for version in client.search_model_versions(f"name='{registered_name}'")
                if version.run_id == prior_run.info.run_id
                and version.status == "READY"
            ]
            if not versions:
                complete = False
                break
            latest = max(versions, key=lambda item: int(item.version))
            prior_models.append(
                {
                    "model_category": category,
                    "registered_model_name": registered_name,
                    "version": str(latest.version),
                }
            )
        if complete:
            return {
                "experiment": EXPERIMENT_NAME,
                "run_id": prior_run.info.run_id,
                "models": prior_models,
                "reused_existing_registration": True,
            }
    model_selection = json.loads(
        (settings.output_dir / "model_selection_report.json").read_text()
    )
    feature_report = json.loads(
        (settings.output_dir / "reports" / "feature_generation.json").read_text()
    )
    source_profile = json.loads(
        (settings.output_dir / "reports" / "source_profile.json").read_text()
    )
    source_revision, source_dirty = _source_revision()
    bronze_manifest_path = (
        settings.source_path.expanduser().resolve().parents[1]
        / "metadata"
        / "dataset_versions"
        / "customer_bronze"
        / "latest.json"
    )
    bronze_manifest = (
        json.loads(bronze_manifest_path.read_text(encoding="utf-8"))
        if bronze_manifest_path.is_file()
        else {}
    )
    registered: list[dict[str, str]] = []
    with mlflow.start_run(
        experiment_id=experiment.experiment_id,
        run_name="building-behaviour-segmentation",
    ) as run:
        mlflow.set_tags(
            {
                "capability": "behaviour_based_geospatial_customer_segmentation",
                "persona": "government",
                "observation_start": feature_report["observation_start"],
                "observation_end_exclusive": feature_report["observation_end_exclusive"],
                "source_path": str(settings.source_path.resolve()),
                "source_manifest_version": bronze_manifest.get("dataset_version", "unversioned"),
                "source_code_revision": source_revision or "unavailable",
                "source_code_dirty": str(source_dirty).lower() if source_dirty is not None else "unknown",
                "model_version": metadata["model_version"],
            }
        )
        mlflow.log_params(
            {
                "window_months": settings.window_months,
                "minimum_coverage": settings.minimum_coverage,
                "minimum_category_size": settings.minimum_category_size,
                "minimum_cluster_size": settings.minimum_cluster_size,
                "minimum_cluster_fraction": settings.minimum_cluster_fraction,
                "correlation_threshold": settings.correlation_threshold,
                "random_seed": settings.random_seed,
                "source_row_count": source_profile["row_count"],
                "source_building_count": source_profile["distinct_buildings"],
                "source_timestamp_count": source_profile["distinct_timestamps"],
                "feature_count": sum(len(items) for items in metadata["features"].values()),
                "features": json.dumps(metadata["features"]),
            }
        )
        for category, count in metadata["category_building_counts"].items():
            mlflow.log_metric(f"category.{category.lower()}.building_count", float(count))
        mlflow.log_metric("assignment_count", float(metadata["assignment_count"]))
        mlflow.log_metric(
            "unassigned_feature_buildings",
            float(metadata["unassigned_feature_buildings"]),
        )
        for model_record in trained_models:
            model_category = model_record["model_category"]
            model_selection_key = re.sub(
                r"[^A-Z0-9]+", "_", str(model_category).upper()
            ).strip("_") or "UNKNOWN"
            evaluation = model_selection.get(
                model_selection_key,
                {"selected": None, "candidates": []},
            )
            selected = evaluation["selected"]
            for candidate in evaluation["candidates"]:
                for metric in (
                    "silhouette",
                    "davies_bouldin",
                    "calinski_harabasz",
                    "stability_ari",
                    "smallest_cluster_share",
                ):
                    value = candidate.get(metric)
                    if value is not None and pd.notna(value):
                        mlflow.log_metric(
                            f"{model_category.lower()}.{candidate['algorithm']}.k{candidate['k']}.{metric}",
                            float(value),
                        )
            if selected:
                mlflow.log_metric(
                    f"{model_category.lower()}.selected.cluster_count",
                    float(selected["cluster_count"]),
                )
            bundle_path = settings.output_dir / "models" / f"{model_category.lower()}_model.joblib"
            import joblib

            bundle = joblib.load(bundle_path)
            serving_pipeline = Pipeline(
                [
                    ("preprocessor", bundle["preprocessor"]),
                    ("clusterer", bundle["model"]),
                ]
            )
            input_example = pd.read_parquet(
                settings.output_dir / "building_features.parquet",
                columns=bundle["feature_columns"],
            ).head(3)
            model_info = mlflow.sklearn.log_model(
                serving_pipeline,
                artifact_path=f"{model_category.lower()}_clusterer",
                input_example=input_example,
            )
            registered_name = f"{MODEL_PREFIX}-{model_category.lower()}"
            same_model_version = [
                version
                for version in client.search_model_versions(f"name='{registered_name}'")
                if version.tags.get("segmentation_model_version") == model_version
                and version.status == "READY"
            ]
            if same_model_version:
                registered_model = max(
                    same_model_version, key=lambda item: int(item.version)
                )
            else:
                registered_model = mlflow.register_model(model_info.model_uri, registered_name)
                client.set_model_version_tag(
                    registered_name,
                    registered_model.version,
                    "segmentation_model_version",
                    model_version,
                )
            mlflow.set_tag(f"registered_model.{model_category}", registered_name)
            registered.append(
                {
                    "model_category": model_category,
                    "registered_model_name": registered_name,
                    "version": str(registered_model.version),
                }
            )
        for path in (
            settings.output_dir / "model_metadata.json",
            settings.output_dir / "model_selection_report.json",
            settings.output_dir / "feature_diagnostics.json",
            settings.output_dir / "reports" / "source_profile.json",
            settings.output_dir / "reports" / "feature_generation.json",
            settings.output_dir / "reports" / "geospatial_summary.json",
        ):
            if path.is_file():
                mlflow.log_artifact(str(path), artifact_path="segmentation_reports")
        for filename in (
            "cluster_profiles.parquet",
            "consumer_assignments.parquet",
            "survey_priority.parquet",
            "segment_distribution.parquet",
        ):
            path = settings.output_dir / filename
            if path.is_file():
                mlflow.log_artifact(str(path))
        for path in sorted((settings.output_dir / "models").glob("*_model.joblib")):
            mlflow.log_artifact(str(path), artifact_path="fitted_model_bundles")
        result = {
            "experiment": EXPERIMENT_NAME,
            "run_id": run.info.run_id,
            "models": registered,
        }
        mlflow.log_dict(result, "registration_summary.json")
        return result

