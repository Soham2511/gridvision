"""Dedicated government behavioural segmentation DAG."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from training.customer_segmentation.clustering import fit_and_publish
from training.customer_segmentation.config import SegmentationSettings
from training.customer_segmentation.data_pipeline import (
    generate_building_features,
    load_or_validate_source_profile,
)
from training.customer_segmentation.geospatial import publish_geospatial_outputs
from training.customer_segmentation.pipeline import (
    validate_outputs,
    write_execution_summary,
)
from training.customer_segmentation.registration import register_models

logger = logging.getLogger("gridvision.segmentation.airflow")


@dag(
    dag_id="government_customer_segmentation",
    description="Profile clean Bronze data, train building behaviour clusters and publish geospatial outputs.",
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},
    tags=["gridvision", "government", "segmentation", "energy"],
)
def government_customer_segmentation():
    @task
    def profile_source() -> dict[str, object]:
        settings = SegmentationSettings.from_environment()
        result = load_or_validate_source_profile(settings)
        compact = {
            "profile_path": str(settings.reports_dir / "source_profile.json"),
            "row_count": result["row_count"],
            "distinct_buildings": result["distinct_buildings"],
            "distinct_timestamps": result["distinct_timestamps"],
            "duplicate_building_timestamp_rows": result[
                "duplicate_building_timestamp_rows"
            ],
            "timestamp_min": str(result["timestamp_min"]),
            "timestamp_max": str(result["timestamp_max"]),
        }
        logger.info("Segmentation source profile: %s", json.dumps(compact, default=str))
        return compact

    @task
    def generate_features(profile: dict[str, object]) -> dict[str, object]:
        del profile
        result = generate_building_features(SegmentationSettings.from_environment())
        return {
            "feature_path": result["feature_path"],
            "feature_rows": result["feature_rows"],
            "eligible_buildings": result["eligible_buildings"],
            "excluded_low_coverage_buildings": result[
                "excluded_low_coverage_buildings"
            ],
            "minimum_observed_coverage": result["minimum_observed_coverage"],
            "observation_start": result["observation_start"],
            "observation_end_exclusive": result["observation_end_exclusive"],
        }

    @task
    def train_models(features: dict[str, object]) -> dict[str, object]:
        settings = SegmentationSettings.from_environment()
        result = fit_and_publish(Path(str(features["feature_path"])), settings)
        return {
            "model_version": result["model_version"],
            "assignment_count": result["assignment_count"],
            "model_count": len(result["trained_models"]),
            "models": [
                {
                    "model_category": model["model_category"],
                    "algorithm": model["algorithm"],
                    "evaluation": model["evaluation"],
                }
                for model in result["trained_models"]
            ],
        }

    @task
    def publish_profiles(model_result: dict[str, object]) -> dict[str, object]:
        del model_result
        return publish_geospatial_outputs(SegmentationSettings.from_environment())

    @task
    def register_and_validate(
        profile: dict[str, object],
        features: dict[str, object],
        models: dict[str, object],
        geospatial: dict[str, object],
    ) -> dict[str, object]:
        settings = SegmentationSettings.from_environment()
        validation = validate_outputs(settings)
        registration = register_models(settings)
        context = get_current_context()
        execution_summary = {
            "status": "complete",
            "trigger": "airflow",
            "dag_id": context["dag"].dag_id,
            "airflow_run_id": context["run_id"],
            "logical_date": str(context.get("logical_date")),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_profile": profile,
            "feature_generation": features,
            "models": models,
            "geospatial": geospatial,
            "mlflow": registration,
            "output_validation": validation,
        }
        summary_path = write_execution_summary(settings, execution_summary)
        return {
            "registration": registration,
            "validation": validation,
            "execution_summary_path": str(summary_path),
        }

    source_profile = profile_source()
    features = generate_features(source_profile)
    models = train_models(features)
    geospatial = publish_profiles(models)
    register_and_validate(source_profile, features, models, geospatial)


government_customer_segmentation()
