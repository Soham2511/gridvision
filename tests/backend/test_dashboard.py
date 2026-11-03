"""Tests for persona dashboards and historical analysis endpoints."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_commercial_dashboard(client: FlaskClient):
    """Test commercial dashboard data retrieval across time ranges."""
    res_1d = client.get("/api/v1/dashboard/commercial?time_range=1D&building_id=Panther_office_1")
    assert res_1d.status_code == 200
    data_1d = res_1d.get_json()["data"]
    assert data_1d["timeRange"] == "1D"
    assert len(data_1d["curve"]) > 10
    assert "actualCallout" in data_1d

    res_7d = client.get("/api/v1/dashboard/commercial?time_range=7D&building_id=Panther_office_1")
    assert res_7d.status_code == 200
    assert len(res_7d.get_json()["data"]["curve"]) >= 7


def test_household_dashboard(client: FlaskClient):
    """Test household dashboard overview."""
    res = client.get("/api/v1/dashboard/household?household_id=METER-1000")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["householdId"] == "METER-1000"
    assert "consumptionCurve" in data
    assert len(data["consumptionCurve"]) > 5


def test_government_regions_and_dashboard(client: FlaskClient):
    """Test government regions list and regional dashboard."""
    regions_res = client.get("/api/v1/dashboard/government/regions")
    assert regions_res.status_code == 200
    regions = regions_res.get_json()["data"]
    assert len(regions) == 6

    dash_overall = client.get("/api/v1/dashboard/government?view_type=overall&time_range=1D")
    assert dash_overall.status_code == 200
    assert dash_overall.get_json()["data"]["regionName"] == "System-Wide"

    dash_region = client.get("/api/v1/dashboard/government?view_type=region&region_id=north&time_range=1D")
    assert dash_region.status_code == 200
    assert dash_region.get_json()["data"]["regionName"] == "North Region"


def test_historical_analysis(client: FlaskClient):
    """Test historical demand analysis endpoint across personas."""
    res_hh = client.get("/api/v1/historical?persona=household&time_range=30D")
    assert res_hh.status_code == 200
    data_hh = res_hh.get_json()["data"]
    assert data_hh["persona"] == "household"
    assert len(data_hh["historyCurve"]) == 30

    res_comm = client.get("/api/v1/historical?persona=commercial&time_range=30D")
    assert res_comm.status_code == 200
    assert res_comm.get_json()["data"]["persona"] == "commercial"

    res_gov = client.get("/api/v1/historical?persona=government&time_range=30D")
    assert res_gov.status_code == 200
    assert res_gov.get_json()["data"]["unit"] == "MW"
