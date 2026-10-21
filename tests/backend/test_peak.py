"""Tests for peak demand analysis and ADR curtailment simulation."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_get_peak_demand(client: FlaskClient):
    """Test peak demand analysis endpoint."""
    response = client.get("/api/v1/peak-demand")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["expectedPeakMw"] == 492.6
    assert data["peakCapacityLimitMw"] == 520.0
    assert len(data["hourlyDistribution"]) > 5
    assert len(data["dailyPeakTimeline"]) == 7


def test_simulate_curtailment_success(client: FlaskClient):
    """Test successful curtailment simulation."""
    payload = {"curtailment_mw": 15.0, "duration_hours": 2.0}
    response = client.post("/api/v1/peak-demand/curtail", json=payload)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["curtailmentMw"] == 15.0
    assert data["originalPeakMw"] == 492.6
    assert data["newPeakMw"] == 477.6
    assert data["dispatchConfirmed"] is True
    assert data["newReserveMarginPct"] > data["originalReserveMarginPct"]


def test_simulate_curtailment_invalid_input(client: FlaskClient):
    """Test validation failure for negative or zero curtailment."""
    response = client.post("/api/v1/peak-demand/curtail", json={"curtailment_mw": -5})
    assert response.status_code == 422
    assert response.get_json()["success"] is False
