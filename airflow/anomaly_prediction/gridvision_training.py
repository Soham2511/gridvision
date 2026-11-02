"""Airflow DAG for GridVision bronze, silver, gold, and model training."""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from airflow.decorators import dag, task

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = (
    ROOT
    / "backend"
    / "app"
    / "models"
    / "anomaly_prediction"
    / "runtime"
)
sys.path.insert(0, str(RUNTIME_PATH))

from gridvision_data import (  # noqa: E402
    build_gold_features,
    parse_bronze_to_silver,
)
from gridvision_logging import configure_logging  # noqa: E402
from gridvision_mlflow import (  # noqa: E402
    run_tracked_existing_model,
    run_tracked_training,
)

SOURCE_DATA = Path(
    os.environ.get(
        "GRIDVISION_SOURCE_DATA",
        ROOT / "data" / "anomaly_prediction" / "synthetic_2019_normal.parquet",
    )
)
SILVER_DATA = Path(
    os.environ.get(
        "GRIDVISION_SILVER_DATA",
        ROOT / "data" / "anomaly_prediction" / "silver" / "synthetic_2019_silver.parquet",
    )
)
GOLD_DATA = Path(
    os.environ.get(
        "GRIDVISION_GOLD_DATA",
        ROOT / "data" / "anomaly_prediction" / "gold" / "gridvision_model_features.parquet",
    )
)
MODEL_PATH = Path(
    os.environ.get(
        "GRIDVISION_MODEL_PATH",
        ROOT / "models" / "anomaly_prediction" / "gridvision_anomaly_model.joblib",
    )
)
REPORT_DIRECTORY = Path(
    os.environ.get(
        "GRIDVISION_REPORT_DIR", ROOT / "reports" / "anomaly_prediction" / "training"
    )
)


@dag(
    dag_id="gridvision_anomaly_training",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["gridvision", "anomaly-detection", "mlflow"],
)
def gridvision_anomaly_training() -> None:
    @task
    def parse_to_silver() -> dict[str, Any]:
        logger_path = configure_logging()
        if SILVER_DATA.is_file():
            from gridvision_pipeline import inspect_parquet

            result = inspect_parquet(SILVER_DATA)
            result["path"] = str(SILVER_DATA)
            logging.getLogger(__name__).info(
                "Reusing prepared Silver anomaly data at %s", SILVER_DATA
            )
            return result
        logging.getLogger(__name__).info(
            "Parsing bronze parquet into silver: %s", SOURCE_DATA
        )
        result = parse_bronze_to_silver(SOURCE_DATA, SILVER_DATA)
        logging.getLogger(__name__).info(
            "Silver layer parsed %s rows and %s columns to %s; project log file: %s",
            result["rows"],
            len(result["columns"]),
            result["path"],
            logger_path,
        )
        return result

    @task
    def engineer_gold(silver: dict[str, Any]) -> dict[str, Any]:
        configure_logging()
        if GOLD_DATA.is_file():
            from gridvision_pipeline import inspect_parquet

            result = inspect_parquet(GOLD_DATA)
            result["path"] = str(GOLD_DATA)
            logging.getLogger(__name__).info(
                "Reusing generated Gold anomaly features at %s", GOLD_DATA
            )
            return result
        result = build_gold_features(silver["path"], GOLD_DATA)
        logging.getLogger(__name__).info(
            "Gold layer engineered %s rows with %s model features at %s",
            result["rows"],
            len(result["feature_columns"]),
            result["path"],
        )
        return result

    @task
    def train_model(
        silver: dict[str, Any], gold: dict[str, Any]
    ) -> dict[str, Any]:
        configure_logging()
        if (
            os.environ.get("ANOMALY_FORCE_RETRAIN", "").lower()
            not in {"1", "true", "yes"}
            and MODEL_PATH.is_file()
            and (REPORT_DIRECTORY / "evaluation_metrics.json").is_file()
        ):
            return run_tracked_existing_model(MODEL_PATH, REPORT_DIRECTORY)
        return run_tracked_training(
            prepared_data_path=silver["path"],
            model_path=MODEL_PATH,
            report_dir=REPORT_DIRECTORY,
            gold_features_path=gold["path"],
        )

    silver = parse_to_silver()
    gold = engineer_gold(silver)
    train_model(silver, gold)


gridvision_anomaly_training()
