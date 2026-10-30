"""Validation tests for the commercial Bronze-to-Gold data pipeline."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMERCIAL_AIRFLOW_PATH = PROJECT_ROOT / "airflow" / "commercial"
for import_path in (PROJECT_ROOT,):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

_PIPELINE_SPEC = importlib.util.spec_from_file_location(
    "commercial_data_pipeline", COMMERCIAL_AIRFLOW_PATH / "data_pipeline.py"
)
assert _PIPELINE_SPEC and _PIPELINE_SPEC.loader
data_pipeline = importlib.util.module_from_spec(_PIPELINE_SPEC)
sys.modules[_PIPELINE_SPEC.name] = data_pipeline
_PIPELINE_SPEC.loader.exec_module(data_pipeline)
from training.commercial_forecast.features import FEATURE_COLUMNS  # noqa: E402


def _fixture_source(path: Path) -> Path:
    start = datetime(2020, 1, 1)
    rows = []
    for entity, use_type, base in [(101, "Commercial", 10.0), (202, "Residential", 1.0)]:
        for hour in range(5):
            rows.append(
                {
                    "OBJECTID": entity,
                    "timestamp": start + timedelta(hours=hour),
                    "normalized_building_energy_kwh": base + hour,
                    "GeneralUseType": use_type,
                    "SpecificUseType": "Office" if entity == 101 else "Home",
                    "usetype": "office" if entity == 101 else "residential",
                    "building.type": "Office" if entity == 101 else "House",
                    "idf.kw": "small",
                    "building.area.m2": 100.0,
                    "FootprintArea.m2": 80.0,
                    "EffectiveYearBuilt": 2000,
                    "id.grid.coarse": 7 if entity == 101 else 9,
                    "latitude": 40.0,
                    "longitude": -73.0,
                }
            )
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture
def pipeline_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(data_pipeline, "MEMORY_LIMIT", "256MB")
    monkeypatch.setattr(data_pipeline, "THREADS", 1)
    monkeypatch.setattr(data_pipeline, "TEMP_DIR", tmp_path / "spill")
    monkeypatch.setattr(data_pipeline, "VERSIONS_DIR", tmp_path / "versions")
    monkeypatch.setattr(
        data_pipeline, "QUALITY_REPORTS_DIR", tmp_path / "logs" / "quality_reports" / "commercial"
    )
    return tmp_path


def test_source_validation_checks_schema_and_region_key(pipeline_dirs: Path) -> None:
    source = _fixture_source(pipeline_dirs / "source.parquet")
    result = data_pipeline.validate_source(source)
    assert result["missing_required_columns"] == []
    assert result["region_key"] == "id.grid.coarse"


def test_source_validation_rejects_building_assigned_to_multiple_grids(
    pipeline_dirs: Path,
) -> None:
    source = _fixture_source(pipeline_dirs / "source.parquet")
    frame = pd.read_parquet(source)
    frame.loc[frame["OBJECTID"] == 101, "id.grid.coarse"] = [7, 7, 7, 8, 8]
    frame.to_parquet(source, index=False)
    with pytest.raises(ValueError, match="multiple coarse grids"):
        data_pipeline.validate_source(source)


def test_source_validation_rejects_missing_columns(pipeline_dirs: Path) -> None:
    source = pipeline_dirs / "incomplete.parquet"
    pd.DataFrame({"OBJECTID": [1], "timestamp": [datetime(2020, 1, 1)]}).to_parquet(
        source, index=False
    )
    with pytest.raises(ValueError, match="missing required columns"):
        data_pipeline.validate_source(source)


def test_silver_filters_residential_and_writes_quality_metadata(
    pipeline_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _fixture_source(pipeline_dirs / "source.parquet")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
    output = pipeline_dirs / "silver.parquet"
    result = data_pipeline.create_commercial_silver(source, output)
    silver = pd.read_parquet(output)
    assert result["quality_passed"] is True
    assert len(silver) == 5
    assert set(silver["GeneralUseType"]) == {"Commercial"}
    assert "id.grid.coarse" in silver.columns
    report = json.loads(Path(result["quality_report"]).read_text(encoding="utf-8"))
    assert report["quality_passed"] is True
    assert report["dataset_name"] == "commercial_silver"


def test_gold_builds_single_horizon_column_and_leakage_safe_labels(
    pipeline_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _fixture_source(pipeline_dirs / "source.parquet")
    silver_path = pipeline_dirs / "silver.parquet"
    gold_path = pipeline_dirs / "gold.parquet"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
    data_pipeline.create_commercial_silver(source, silver_path)

    result = data_pipeline.build_commercial_gold(silver_path, gold_path, horizon_hours=2)
    gold = pd.read_parquet(gold_path)
    assert result["quality_passed"] is True
    assert len(gold) == 7  # 3 horizons from origin 0, 2 from origin 1, 2 from origin 2
    assert gold.columns.tolist().count("forecast_horizon_hours") == 1
    assert set(FEATURE_COLUMNS).issubset(gold.columns)
    assert len(FEATURE_COLUMNS) == 36
    assert set(gold["OBJECTID"]) == {101}
    assert set(gold["id.grid.coarse"]) == {7}
    first = gold.loc[
        (gold["forecast_origin_timestamp"] == pd.Timestamp("2020-01-01 00:00:00"))
        & (gold["forecast_horizon_hours"] == 1)
    ].iloc[0]
    assert first["target_energy"] == 11.0
    assert first["energy_at_origin"] == 10.0
    assert first["target_timestamp"] > first["forecast_origin_timestamp"]
    second_origin = gold.loc[
        (gold["forecast_origin_timestamp"] == pd.Timestamp("2020-01-01 01:00:00"))
        & (gold["forecast_horizon_hours"] == 1)
    ].iloc[0]
    assert second_origin["energy_lag_1"] == 10.0
    report = json.loads(Path(result["quality_report"]).read_text(encoding="utf-8"))
    assert report["quality_passed"] is True


def test_gold_rejects_horizon_outside_supported_range(pipeline_dirs: Path) -> None:
    silver = _fixture_source(pipeline_dirs / "silver.parquet")
    with pytest.raises(ValueError, match="between 1 and 24"):
        data_pipeline.build_commercial_gold(silver, pipeline_dirs / "gold.parquet", 25)


def test_airflow_dag_parses_with_expected_task_order(
    tmp_path: Path,
) -> None:
    airflow_home = tmp_path / "airflow_home"
    env = os.environ.copy()
    env["AIRFLOW_HOME"] = str(airflow_home)
    env["AIRFLOW__LOGGING__BASE_LOG_FOLDER"] = str(airflow_home / "logs")
    dag_path = PROJECT_ROOT / "airflow" / "commercial" / "commercial_energy_dag.py"
    code = (
        "from airflow.models import DagBag; "
        f"bag=DagBag(dag_folder={str(dag_path)!r}, include_examples=False); "
        "assert not bag.import_errors, bag.import_errors; "
        "dag=bag.dags['commercial_building_forecasting_data_pipeline']; "
        "assert dag.task_ids == ['validate_commercial_bronze', "
        "'create_commercial_silver', 'create_commercial_gold']; "
        "assert dag.get_task('validate_commercial_bronze').downstream_task_ids "
        "== {'create_commercial_silver'}; "
        "assert dag.get_task('create_commercial_silver').downstream_task_ids "
        "== {'create_commercial_gold'}"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
