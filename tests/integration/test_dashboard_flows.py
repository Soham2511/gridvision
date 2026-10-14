"""Integration tests verifying full data pipeline and dashboard view flows."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from app.main import create_app
from dashboard.clients.api_client import _to_json_value
from dashboard.utils.data import (
    load_commercial_history,
    load_commercial_latest,
    load_government_aggregate_history,
    load_government_history,
    load_government_latest,
    load_model_metadata,
    load_residential_history,
    load_residential_latest,
)
from dashboard.utils.time_range import filter_by_time_range
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def api_client() -> Iterator[TestClient]:
    with TestClient(create_app(PROJECT_ROOT)) as client:
        yield client


def test_residential_flow(api_client: TestClient) -> None:
    latest = load_residential_latest()
    assert not latest.empty
    row = latest.iloc[0]
    meta = load_model_metadata("residential")
    
    payload = {
        "entity_id": str(row["household_id"]),
        "forecast_timestamp": pd.Timestamp(row["date"]).isoformat(),
        "features": {col: row[col] for col in meta["features"]},
        "context": "retrospective_gold_replay",
        "actual_kwh_so_far": float(row["actual_cycle_kwh_so_far"]),
    }
    resp = api_client.post("/api/v1/residential/predict", json=_to_json_value(payload))
    assert resp.status_code == 200
    data = resp.json()
    assert data["prediction_status"] in {"valid", "invalid_negative_energy"}
    if data["prediction_status"] == "valid":
        assert data["estimated_month_end_kwh"] is not None
        assert data["estimated_month_end_bill_inr"] is not None
    else:
        assert data["estimated_month_end_kwh"] is None
        assert data["estimated_month_end_bill_inr"] is None


def test_commercial_flow(api_client: TestClient) -> None:
    latest = load_commercial_latest()
    assert not latest.empty
    row = latest.iloc[0]
    meta = load_model_metadata("commercial")

    payload = {
        "entity_id": str(row["building_id"]),
        "forecast_timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
        "features": {col: row[col] for col in meta["features"]},
        "context": "retrospective_gold_replay",
    }
    resp = api_client.post("/api/v1/commercial/predict", json=_to_json_value(payload))
    assert resp.status_code == 200
    data = resp.json()
    assert data["prediction_status"] in {"valid", "invalid_negative_energy"}
    assert isinstance(data["prediction"], float)


def test_government_flow(api_client: TestClient) -> None:
    latest = load_government_latest()
    assert not latest.empty
    row = latest.iloc[0]
    meta = load_model_metadata("government")

    payload = {
        "entity_id": str(row["site_id"]),
        "forecast_timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
        "features": {col: row[col] for col in meta["features"]},
        "context": "retrospective_gold_replay",
    }
    resp = api_client.post("/api/v1/government/predict", json=_to_json_value(payload))
    assert resp.status_code == 200
    data = resp.json()
    assert data["prediction_status"] in {"valid", "invalid_negative_energy"}
    assert isinstance(data["prediction"], float)


def test_historical_datasets_and_filters() -> None:
    res_hist = load_residential_history()
    assert len(res_hist) > 0
    f_res = filter_by_time_range(res_hist, "date", "1M")
    assert not f_res.filtered_df.empty

    comm_hist = load_commercial_history()
    assert len(comm_hist) > 0
    f_comm = filter_by_time_range(comm_hist, "timestamp", "1W")
    assert not f_comm.filtered_df.empty

    gov_hist = load_government_history()
    assert len(gov_hist) > 0
    f_gov = filter_by_time_range(gov_hist, "timestamp", "3M")
    assert not f_gov.filtered_df.empty

    gov_agg = load_government_aggregate_history()
    assert len(gov_agg) == 17544
    assert (gov_agg["site_count"] == 17).all()


def test_persona_metadata_mapping() -> None:
    # Verify all 3 personas have verified model metadata
    res_meta = load_model_metadata("residential")
    assert res_meta["model_name"] == "residential"
    assert res_meta["target_name"] == "target_remaining_kwh"
    assert "XGBRegressor" in str(res_meta["artifact_type"])

    comm_meta = load_model_metadata("commercial")
    assert comm_meta["model_name"] == "commercial"
    assert comm_meta["target_name"] == "hourly_demand_kwh"
    assert "LightGBM" in str(comm_meta["artifact_type"])

    gov_meta = load_model_metadata("government")
    assert gov_meta["model_name"] == "government"
    assert gov_meta["target_name"] == "total_demand_kwh"
    assert "LightGBM" in str(gov_meta["artifact_type"])

