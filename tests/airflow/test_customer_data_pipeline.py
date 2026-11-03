"""Tests for the customer bronze-to-silver transform."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

AIRFLOW_CUSTOMER_PATH = (
    Path(__file__).resolve().parents[2] / "airflow" / "customer"
)
if str(AIRFLOW_CUSTOMER_PATH) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_CUSTOMER_PATH))

import data_pipeline  # noqa: E402


def test_silver_transform_aggregates_sampled_residential_rows(
    tmp_path: Path, monkeypatch
):
    source_path = tmp_path / "source.parquet"
    silver_path = tmp_path / "silver.parquet"
    rows = [
        {
            "OBJECTID": entity_id,
            "building.type": building_type,
            "SpecificUseType": "Single Family",
            "GeneralUseType": (
                "Commercial" if building_type == "commercial" else "Residential"
            ),
            "normalized_building_energy_kwh": energy,
            "FootprintArea.m2": 80.0,
            "EffectiveYearBuilt": 1990,
            "vintage": "1990s",
            "usetype": "single_family",
            "id.grid.finer": 10,
            "id.tract": "tract-1",
            "latitude": 34.0,
            "longitude": -118.0,
            "timestamp": timestamp,
            "idf.kw": "Residential",
            "id.grid.coarse": 1,
            "building.area.m2": 100.0,
        }
        for entity_id, building_type, timestamp, energy in [
            (1, "single-family", "2018-01-01 00:00:00", 1.0),
            (1, "single-family", "2018-01-01 00:00:00", 3.0),
            (1, "single-family", "2018-01-01 01:00:00", 2.0),
            (2, "multi-family", "2018-01-01 00:00:00", 4.0),
            (3, "commercial", "2018-01-01 00:00:00", 50.0),
        ]
    ]
    pd.DataFrame(rows).to_parquet(source_path, index=False)
    monkeypatch.setattr(data_pipeline, "DUCKDB_MEMORY_LIMIT", "256MB")
    monkeypatch.setattr(data_pipeline, "DUCKDB_THREADS", 1)
    monkeypatch.setattr(data_pipeline, "PROFILE_SCAN_BATCH_SIZE", 2)
    monkeypatch.setattr(data_pipeline, "DUCKDB_TEMP_DIR", tmp_path / "spill")
    monkeypatch.setattr(
        data_pipeline, "DATASET_VERSIONS_DIR", tmp_path / "versions"
    )
    monkeypatch.setattr(
        data_pipeline, "QUALITY_REPORTS_DIR", tmp_path / "quality_reports"
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")

    result = data_pipeline.create_customer_silver(
        source_path=source_path,
        silver_path=silver_path,
        buildings_per_use=10,
    )

    silver = pd.read_parquet(silver_path)
    assert result["quality_passed"] is True
    assert result["unique_buildings"] == 2
    assert result["rows"] == 3
    assert len(silver) == 3
    duplicate_timestamp = silver[
        (silver["OBJECTID"] == 1)
        & (silver["timestamp"] == pd.Timestamp("2018-01-01 00:00:00"))
    ]
    assert len(duplicate_timestamp) == 1
    assert duplicate_timestamp.iloc[0]["normalized_building_energy_kwh"] == 2.0
    assert set(silver["GeneralUseType"]) == {"Residential"}
