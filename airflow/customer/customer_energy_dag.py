"""Airflow DAG for bronze, silver, and customer-model gold data."""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from customer.data_pipeline import (
    BRONZE_PATH,
    GOLD_PATH,
    SILVER_PATH,
    SOURCE_PATH,
    build_customer_bill_gold,
    create_bronze,
    create_customer_silver,
)

DAG_ID = "customer_energy_data_pipeline"


def _create_bronze(**_: object) -> dict[str, object]:
    return create_bronze(SOURCE_PATH, BRONZE_PATH)


def _create_silver(**_: object) -> dict[str, object]:
    return create_customer_silver(BRONZE_PATH, SILVER_PATH)


def _create_gold(**_: object) -> dict[str, object]:
    return build_customer_bill_gold(SILVER_PATH, GOLD_PATH)


with DAG(
    dag_id=DAG_ID,
    description="Build bronze, residential silver, and customer bill prediction gold Parquet data.",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["gridvision", "customer", "energy", "data-engineering"],
) as dag:
    bronze = PythonOperator(
        task_id="create_bronze",
        python_callable=_create_bronze,
    )
    silver = PythonOperator(
        task_id="create_customer_silver",
        python_callable=_create_silver,
    )
    gold = PythonOperator(
        task_id="create_customer_bill_gold",
        python_callable=_create_gold,
    )

    bronze >> silver >> gold
