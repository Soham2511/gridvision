"""Tests for energy insights and AI domain assistant."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_energy_insights(client: FlaskClient):
    """Test retrieving energy insights and filtering."""
    response = client.get("/api/v1/energy-insights")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 4

    res_peak = client.get("/api/v1/energy-insights?category=peak_shaving")
    assert res_peak.status_code == 200
    for ins in res_peak.get_json()["data"]:
        assert ins["category"] == "peak_shaving"

    res_sector = client.get("/api/v1/energy-insights?sector=commercial")
    assert res_sector.status_code == 200
    for ins in res_sector.get_json()["data"]:
        assert ins["sector"] in ("commercial", "all")


def test_assistant_chat(client: FlaskClient):
    """Test AI assistant prompt answering."""
    tariff_prompt = {"prompt": "How is my month-end bill calculated?", "persona": "household"}
    res_tariff = client.post("/api/v1/assistant/chat", json=tariff_prompt)
    assert res_tariff.status_code == 200
    assert "Billing Computation" in res_tariff.get_json()["data"]["answer"]

    peak_prompt = {"prompt": "What is our current reserve margin?", "persona": "government"}
    res_peak = client.post("/api/v1/assistant/chat", json=peak_prompt)
    assert res_peak.status_code == 200
    assert "Reserve Status" in res_peak.get_json()["data"]["answer"]
