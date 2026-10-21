"""Tests for forecasting, entity catalog, and model inference."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_entities_commercial(client: FlaskClient):
    """Test commercial buildings list and single building."""
    response = client.get("/api/v1/entities/commercial")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 5
    assert data[0]["buildingId"] == "Panther_office_1"

    single_res = client.get("/api/v1/entities/commercial/Panther_office_1")
    assert single_res.status_code == 200
    assert single_res.get_json()["data"]["sqm"] == 14250


def test_entities_residential(client: FlaskClient):
    """Test residential meters list and single meter."""
    response = client.get("/api/v1/entities/residential")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 4
    assert data[0]["householdId"] == "METER-1000"


def test_entities_government(client: FlaskClient):
    """Test regional government sites list."""
    response = client.get("/api/v1/entities/government")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 6


def test_commercial_forecast(client: FlaskClient):
    """Test multi-horizon commercial forecast."""
    response = client.get("/api/v1/forecast/commercial/Panther_office_1")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "building" in data
    assert "horizon" in data
    assert len(data["horizon"]) >= 10
    point = data["horizon"][0]
    assert "formattedTime" in point
    assert "peakThreshold" in point


def test_residential_forecast(client: FlaskClient):
    """Test residential month-end forecast."""
    response = client.get("/api/v1/forecast/residential/METER-1000")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "meter" in data
    assert "horizon" in data
    assert len(data["horizon"]) >= 10


def test_unified_prediction_endpoint(client: FlaskClient):
    """Test POST /api/v1/forecast/predict with valid features."""
    payload = {
        "model_name": "residential",
        "entity_id": "METER-1000",
        "features": {
            "elapsed_days": 19,
            "daily_avg_kwh": 14.8,
        },
        "actual_kwh_so_far": 284.5,
        "context": "future_forecast",
    }
    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["entity_id"] == "METER-1000"
    assert data["is_demo"] is True
    assert data["provider"] == "development_mock_v1"
    assert data["prediction"] > 0
    assert data["estimated_month_end_kwh"] > 0
    assert data["estimated_month_end_bill_inr"] > 0
    assert any("DEMO PREDICTION" in c for c in data["caveats"])


def test_prediction_validation_failure(client: FlaskClient):
    """Test prediction fails gracefully on empty entity_id."""
    payload = {
        "entity_id": "",
        "features": {},
    }
    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 422
    assert response.get_json()["success"] is False


def test_persona_predict_endpoints(client: FlaskClient):
    """Test persona-specific prediction routes."""
    # Commercial
    comm_res = client.post("/api/v1/commercial/predict", json={
        "entity_id": "Panther_office_1",
        "features": {"sqm": 14250},
    })
    assert comm_res.status_code == 200
    assert comm_res.get_json()["data"]["prediction"] > 0

    # Residential
    res_res = client.post("/api/v1/residential/predict", json={
        "entity_id": "METER-1000",
        "features": {"elapsed_days": 19, "daily_avg_kwh": 14.8},
        "actual_kwh_so_far": 284.5,
    })
    assert res_res.status_code == 200
    assert res_res.get_json()["data"]["estimated_month_end_kwh"] > 0

    # Government
    gov_res = client.post("/api/v1/government/predict", json={
        "entity_id": "Bear",
        "features": {"season": 2},
    })
    assert gov_res.status_code == 200
    assert gov_res.get_json()["data"]["prediction"] > 0


def test_government_forecast(client: FlaskClient):
    """Test regional government forecast horizon."""
    response = client.get("/api/v1/forecast/government/Bear")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "site" in data
    assert "horizon" in data
    assert len(data["horizon"]) > 5


def test_overview_endpoint(client: FlaskClient):
    """Test overview executive summary KPIs."""
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "kpis" in data
    assert len(data["kpis"]) == 4
    assert "peakAnalysis" in data

