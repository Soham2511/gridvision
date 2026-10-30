from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from airflow.decorators import dag, task

DAG_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DAG_DIRECTORY.parents[1]
for import_path in (PROJECT_ROOT, DAG_DIRECTORY):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from training.government_load.config import PipelineSettings  # noqa: E402
from grid_forecasting_pipeline.etl import prepare_training_data  # noqa: E402
from training.government_load.modeling import train_hybrid_model  # noqa: E402


@dag(
    dag_id="government_load_forecasting",
    description=(
        "Prepare shared GridVision data and train the government load forecaster"
    ),
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    tags=["gridvision", "government", "energy", "forecasting"],
)
def government_load_forecasting():
    @task
    def prepare() -> dict[str, str]:
        settings = PipelineSettings.from_environment()
        reuse_prepared = (
            os.getenv("GOVERNMENT_PIPELINE_REUSE_PREPARED", "").strip().lower()
            in {"1", "true", "yes"}
        )
        if reuse_prepared:
            ready_path = settings.output_path.expanduser().resolve()
            if not ready_path.is_file():
                raise FileNotFoundError(
                    "Prepared government training data was requested for reuse, "
                    f"but the file does not exist: {ready_path}"
                )
            print(f"Reusing prepared government data at {ready_path}")
        else:
            ready_path = prepare_training_data(settings)
        result = {"training_data_path": str(ready_path)}
        print(f"Government preparation result: {result}")
        return result

    @task
    def train(preparation: dict[str, str]) -> dict[str, object]:
        settings = PipelineSettings.from_environment()
        training_settings = PipelineSettings(
            **{
                **settings.model_dump(),
                "input_path": preparation["training_data_path"],
            }
        )
        result = train_hybrid_model(training_settings)
        print(f"Government DAG training summary: {json.dumps(result, sort_keys=True)}")
        return result

    train(prepare())


government_load_forecasting()
