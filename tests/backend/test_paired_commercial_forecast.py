"""API coverage for paired commercial and mapped government forecasts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask.testing import FlaskClient


class PairForecastProvider:
    def __init__(self, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls: list[tuple[str, str]] = []

    def predict_horizon(self, sector: str, entity_id: str, horizon_count: int = 24):
        self.calls.append((sector, entity_id))
        if self.unavailable and sector == "government":
            raise RuntimeError("government model artifact is not loaded")
        factor = 10.0 if sector == "commercial" else 100.0
        return [
            {
                "timestamp": "2025-02-01T01:00:00Z",
                "horizonHours": 1,
                "forecastDemand": factor,
            },
            {
                "timestamp": "2025-02-01T02:00:00Z",
                "horizonHours": 2,
                "forecastDemand": factor + 1,
            },
        ][:horizon_count]

    def get_forecast_model_info(self, sector: str) -> dict[str, Any]:
        return {
            "model_name": f"{sector}-registered-model",
            "model_version": "v17",
            "provider": "test-provider",
            "is_demo": False,
        }


def _configure_building(client: FlaskClient, *, mapped: bool = True) -> PairForecastProvider:
    data_provider = client.application.extensions["data_provider"]
    building = data_provider._commercial_buildings[0]
    building["buildingId"] = "101"
    if mapped:
        building["id.grid.coarse"] = 7
    else:
        building.pop("id.grid.coarse", None)
    provider = PairForecastProvider()
    client.application.extensions["model_provider"] = provider
    client.application.extensions["forecast_service"].model_provider = provider
    return provider


def test_paired_forecast_returns_distinct_model_sources_and_aligned_horizons(
    client: FlaskClient,
) -> None:
    provider = _configure_building(client)
    response = client.get("/api/v1/forecast/commercial/101/paired")
    assert response.status_code == 200
    data = response.get_json()["data"]
    datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    assert provider.calls == [("commercial", "101"), ("government", "7")]
    assert data["building"] == {"building_id": "101", "id.grid.coarse": 7}
    assert data["commercial_forecast"]["source"] == "commercial_building_model"
    assert data["commercial_forecast"]["model"]["model_version"] == "v17"
    assert data["government_forecast"]["source"] == "government_grid_model"
    assert data["government_forecast"]["scope"] == "total_grid_demand"
    assert data["government_forecast"]["model"]["model_version"] == "v17"
    assert [point["horizon_hours"] for point in data["paired_horizon"]] == [1, 2]
    assert data["paired_horizon"][0]["timestamp"] == "2025-02-01T01:00:00Z"
    assert data["paired_horizon"][0]["commercial_prediction"] == 10.0
    assert data["paired_horizon"][0]["total_grid_demand_prediction"] == 100.0
    assert all(
        point["commercial_prediction"] >= 0
        and point["total_grid_demand_prediction"] >= 0
        for point in data["paired_horizon"]
    )


def test_paired_forecast_missing_building_returns_404(client: FlaskClient) -> None:
    _configure_building(client)
    response = client.get("/api/v1/forecast/commercial/not-a-building/paired")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"


def test_paired_forecast_missing_region_mapping_returns_conflict(client: FlaskClient) -> None:
    _configure_building(client, mapped=False)
    response = client.get("/api/v1/forecast/commercial/101/paired")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "REGION_MAPPING_NOT_FOUND"


def test_sample_site_name_is_not_used_as_a_grid_mapping(client: FlaskClient) -> None:
    provider = PairForecastProvider()
    client.application.extensions["model_provider"] = provider
    client.application.extensions["forecast_service"].model_provider = provider
    response = client.get("/api/v1/forecast/commercial/Panther_office_1/paired")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "REGION_MAPPING_NOT_FOUND"
    assert provider.calls == []


def test_paired_forecast_unavailable_model_returns_503(client: FlaskClient) -> None:
    _configure_building(client)
    provider = PairForecastProvider(unavailable=True)
    client.application.extensions["model_provider"] = provider
    client.application.extensions["forecast_service"].model_provider = provider
    response = client.get("/api/v1/forecast/commercial/101/paired")
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_paired_forecast_rejects_negative_energy_predictions(client: FlaskClient) -> None:
    _configure_building(client)
    provider = PairForecastProvider()
    provider.predict_horizon = lambda sector, entity_id, horizon_count=24: [
        {"timestamp": "2025-02-01T01:00:00Z", "horizonHours": 1, "forecastDemand": -3.0}
    ]
    client.application.extensions["model_provider"] = provider
    client.application.extensions["forecast_service"].model_provider = provider
    response = client.get("/api/v1/forecast/commercial/101/paired")
    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "INVALID_MODEL_OUTPUT"
