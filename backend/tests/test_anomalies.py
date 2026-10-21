"""Tests for anomaly detection and triage workflow."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_get_anomalies_all(client: FlaskClient):
    """Test retrieving all anomaly events."""
    response = client.get("/api/v1/anomalies")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 4
    for a in data:
        assert "id" in a
        assert "severity" in a
        assert "status" in a


def test_get_anomalies_filtered(client: FlaskClient):
    """Test filtering by severity and status."""
    res_crit = client.get("/api/v1/anomalies?severity=critical")
    assert res_crit.status_code == 200
    for a in res_crit.get_json()["data"]:
        assert a["severity"] == "critical"

    res_search = client.get("/api/v1/anomalies?search=Panther")
    assert res_search.status_code == 200
    for a in res_search.get_json()["data"]:
        assert "panther" in a["entityName"].lower() or "panther" in a["entityId"].lower()


def test_update_anomaly_status(client: FlaskClient):
    """Test updating anomaly status."""
    update_payload = {"status": "confirmed"}
    response = client.patch("/api/v1/anomalies/ANOM-2026-001", json=update_payload)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "confirmed"


def test_update_anomaly_not_found(client: FlaskClient):
    """Test updating unknown anomaly returns 404."""
    response = client.patch("/api/v1/anomalies/UNKNOWN-ID-999", json={"status": "confirmed"})
    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_update_anomaly_invalid_status(client: FlaskClient):
    """Test updating with invalid status value returns 422."""
    response = client.patch("/api/v1/anomalies/ANOM-2026-001", json={"status": "invalid_status_xyz"})
    assert response.status_code == 422
