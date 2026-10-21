"""Tests for customer segmentation and diurnal curve endpoints."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_customer_segments(client: FlaskClient):
    """Test retrieving high-level customer segments."""
    response = client.get("/api/v1/customers/segments")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 4
    total_share = sum(s["sharePercentage"] for s in data)
    assert 99.0 <= total_share <= 101.0


def test_customer_segmentation_matrix(client: FlaskClient):
    """Test full customer segmentation matrix used by CustomerAnalyticsPage."""
    response = client.get("/api/v1/customers/segmentation-matrix")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["totalCustomers"] == 12480
    assert len(data["industrySegments"]) == 7
    assert len(data["timeOfDayConsumption"]) == 4
    assert len(data["regionalMonthlyDemand"]) == 6


def test_diurnal_curves(client: FlaskClient):
    """Test diurnal curve points across sectors."""
    response = client.get("/api/v1/customers/diurnal-curves")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 12
    for p in data:
        assert "hour" in p
        assert "commercialLoad" in p
        assert "residentialLoad" in p
