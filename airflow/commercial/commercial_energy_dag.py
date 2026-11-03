"""Airflow DAG for source validation and commercial Silver/Gold generation."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

DAG_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = DAG_DIRECTORY.parents[1]
for import_path in (PROJECT_ROOT, DAG_DIRECTORY):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from commercial.data_pipeline import (
    BRONZE_PATH,
    GOLD_PATH,
    SILVER_PATH,
    build_commercial_gold,
    create_commercial_silver,
    validate_source,
)

DAG_ID = "commercial_building_forecasting_data_pipeline"


def _validate_bronze(**_: object) -> dict[str, object]:
    return validate_source(BRONZE_PATH)


def _create_silver(**_: object) -> dict[str, object]:
    # The upstream validation task already checked the source schema and keys.
    return create_commercial_silver(BRONZE_PATH, SILVER_PATH, source_validated=True)


def _create_gold(**_: object) -> dict[str, object]:
    return build_commercial_gold(SILVER_PATH, GOLD_PATH)


with DAG(
    dag_id=DAG_ID,
    description="Validate shared Bronze and build commercial building Silver and Gold datasets.",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["gridvision", "commercial", "energy", "data-engineering"],
) as dag:
    bronze = PythonOperator(
        task_id="validate_commercial_bronze",
        python_callable=_validate_bronze,
    )
    silver = PythonOperator(
        task_id="create_commercial_silver",
        python_callable=_create_silver,
    )
    gold = PythonOperator(
        task_id="create_commercial_gold",
        python_callable=_create_gold,
    )
    bronze >> silver >> gold
