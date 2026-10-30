"""Tests for error handling, validation, and status codes."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_404_not_found(client: FlaskClient):
    """Test response schema for non-existent endpoint."""
    response = client.get("/api/v1/non-existent-endpoint-12345")
    assert response.status_code == 404
    data = response.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_FOUND"


def test_405_method_not_allowed(client: FlaskClient):
    """Test response schema for unsupported HTTP method."""
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    data = response.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_422_malformed_json_body(client: FlaskClient):
    """Test response schema when request body fails contract validation."""
    response = client.post("/api/v1/forecast/predict", json={"invalid_field": 123})
    assert response.status_code == 422
    data = response.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
