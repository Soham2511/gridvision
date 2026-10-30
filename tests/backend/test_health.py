"""Tests for health, readiness, and platform telemetry endpoints."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_root_index(client: FlaskClient):
    """Test the root endpoint returns service directory."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["service"] == "GridVision REST API"
    assert "endpoints" in data


def test_health_live(client: FlaskClient):
    """Test the liveness check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["status"] == "alive"

    response_alias = client.get("/api/v1/health/live")
    assert response_alias.status_code == 200
    assert response_alias.get_json()["data"]["status"] == "alive"


def test_health_ready(client: FlaskClient):
    """Test the readiness probe."""
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["status"] == "ready"
    assert "providers" in data["data"]
    assert data["data"]["providers"]["is_demo_mode"] is True


def test_platform_health_summary(client: FlaskClient):
    """Test platform health telemetry used by DataModelHealthPage."""
    response = client.get("/api/v1/platform/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    payload = data["data"]
    assert payload["totalBuildings"] == 124
    assert payload["totalRegions"] == 8
    assert len(payload["models"]) >= 5
    for m in payload["models"]:
        assert "id" in m
        assert "modelName" in m
        assert "mse" in m
        assert "r2" in m
