"""Tests for the customer bronze-to-silver transform."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

AIRFLOW_CUSTOMER_PATH = (
    Path(__file__).resolve().parents[2] / "airflow" / "customer"
)
if str(AIRFLOW_CUSTOMER_PATH) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_CUSTOMER_PATH))

import data_pipeline  # noqa: E402


def test_silver_transform_only_filters_residential_rows(
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
    rows.extend(
        {
            "OBJECTID": entity_id,
            "building.type": "single-family",
            "SpecificUseType": "Single Family",
            "GeneralUseType": "Residential",
            "normalized_building_energy_kwh": 1.0,
            "FootprintArea.m2": 80.0,
            "EffectiveYearBuilt": 1990,
            "vintage": "1990s",
            "usetype": "single_family",
            "id.grid.finer": 10,
            "id.tract": "tract-1",
            "latitude": 34.0,
            "longitude": -118.0,
            "timestamp": "2018-01-01 00:00:00",
            "idf.kw": "Residential",
            "id.grid.coarse": 1,
            "building.area.m2": 100.0,
        }
        for entity_id in [*range(3, 104), 1398895]
    )
    invalid_energy_row = rows[0].copy()
    invalid_energy_row.update(
        {
            "OBJECTID": 104,
            "normalized_building_energy_kwh": -1.0,
        }
    )
    rows.append(invalid_energy_row)
    pd.DataFrame(rows).to_parquet(source_path, index=False)
    monkeypatch.setattr(data_pipeline, "DUCKDB_MEMORY_LIMIT", "64MB")
    monkeypatch.setattr(data_pipeline, "DUCKDB_THREADS", 1)
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
    )

    silver = pd.read_parquet(silver_path)
    assert result["quality_passed"] is True
    assert result["rows"] == 107
    assert len(silver) == 107
    assert pq.read_schema(silver_path) == pq.read_schema(source_path)
    assert 1398895 in set(silver["OBJECTID"])
    duplicate_timestamp = silver[
        (silver["OBJECTID"] == 1)
        & (silver["timestamp"] == "2018-01-01 00:00:00")
    ]
    assert len(duplicate_timestamp) == 2
    assert set(duplicate_timestamp["normalized_building_energy_kwh"]) == {1.0, 3.0}
    assert -1.0 in set(silver["normalized_building_energy_kwh"])
    assert set(silver["GeneralUseType"]) == {"Residential"}


def test_gold_groups_silver_observations_and_builds_monthly_features(
    tmp_path: Path, monkeypatch
):
    silver_path = tmp_path / "silver.parquet"
    gold_path = tmp_path / "gold.parquet"
    timestamps = pd.date_range(
        "2018-01-01 00:00:00",
        "2018-01-31 23:00:00",
        freq="h",
    )
    rows = [
        {
            "OBJECTID": 1,
            "idf.kw": "Residential",
            "id.grid.coarse": 1,
            "building.area.m2": 100.0,
            "FootprintArea.m2": 80.0,
            "GeneralUseType": "Residential",
            "SpecificUseType": "Single Family",
            "EffectiveYearBuilt": 1990,
            "building.type": "single-family",
            "vintage": "1990s",
            "usetype": "single_family",
            "id.grid.finer": 10.0,
            "id.tract": "tract-1",
            "latitude": 34.0,
            "longitude": -118.0,
            "timestamp": timestamp,
            "normalized_building_energy_kwh": (
                1.0 if timestamp != timestamps[0] else energy
            ),
        }
        for timestamp, energy in [
            (timestamp, 1.0) for timestamp in timestamps
        ] + [(timestamps[0], 3.0)]
    ]
    rows.extend({**row, "OBJECTID": 6} for row in list(rows))
    pd.DataFrame(rows).to_parquet(silver_path, index=False)
    monkeypatch.setattr(data_pipeline, "DUCKDB_MEMORY_LIMIT", "64MB")
    monkeypatch.setattr(data_pipeline, "DUCKDB_THREADS", 1)
    monkeypatch.setattr(data_pipeline, "GOLD_PARTITION_COUNT", 2)
    monkeypatch.setattr(data_pipeline, "DUCKDB_TEMP_DIR", tmp_path / "spill")
    monkeypatch.setattr(
        data_pipeline, "DATASET_VERSIONS_DIR", tmp_path / "versions"
    )
    monkeypatch.setattr(
        data_pipeline, "QUALITY_REPORTS_DIR", tmp_path / "quality_reports"
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")

    result = data_pipeline.build_customer_bill_gold(silver_path, gold_path)

    gold = pd.read_parquet(gold_path)
    assert result["quality_passed"] is True
    assert len(gold) == 6
    assert set(gold["entity_id"]) == {1, 6}
    assert set(gold["cutoff_day"]) == {7, 14, 21}
    assert set(gold["target_month_kwh"]) == {745.0}
    assert (
        gold.loc[gold["cutoff_day"] == 7, "cumulative_energy_kwh"].iloc[0]
        == 169.0
    )


def test_bronze_replaces_stale_same_size_file_with_exact_source_copy(
    tmp_path: Path, monkeypatch
):
    source_path = tmp_path / "sample.parquet"
    bronze_path = tmp_path / "bronze.parquet"
    pd.DataFrame({"value": ["source"]}).to_parquet(
        source_path, index=False, compression=None
    )
    pd.DataFrame({"value": ["stale!"]}).to_parquet(
        bronze_path, index=False, compression=None
    )
    assert source_path.stat().st_size == bronze_path.stat().st_size
    assert source_path.read_bytes() != bronze_path.read_bytes()

    monkeypatch.setattr(
        data_pipeline, "DATASET_VERSIONS_DIR", tmp_path / "versions"
    )
    monkeypatch.setattr(
        data_pipeline, "QUALITY_REPORTS_DIR", tmp_path / "quality_reports"
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")

    result = data_pipeline.create_bronze(source_path, bronze_path)

    assert result["quality_passed"] is True
    assert bronze_path.read_bytes() == source_path.read_bytes()
    assert pq.read_table(bronze_path).to_pydict() == {"value": ["source"]}
