"""Forecasting and inference service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider
from app.providers.model_provider import BaseModelProvider, PredictionOutput


class ForecastService:
    """Handles entity forecasting horizons and on-demand model inference."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        model_provider: BaseModelProvider,
    ) -> None:
        self.data_provider = data_provider
        self.model_provider = model_provider

    def get_commercial_buildings(self) -> list[dict[str, Any]]:
        return self.data_provider.get_commercial_buildings()

    def get_residential_meters(self) -> list[dict[str, Any]]:
        return self.data_provider.get_residential_meters()

    def get_regional_sites(self) -> list[dict[str, Any]]:
        return self.data_provider.get_regional_sites()

    def get_commercial_forecast(self, building_id: str) -> dict[str, Any]:
        bldg = self.data_provider.get_commercial_building(building_id)
        if not bldg:
            bldgs = self.data_provider.get_commercial_buildings()
            bldg = bldgs[0] if bldgs else {"buildingId": building_id}
        horizon = self.model_provider.predict_horizon("commercial", building_id)
        return {
            "building": bldg,
            "horizon": horizon,
        }

    def get_residential_forecast(self, household_id: str) -> dict[str, Any]:
        meter = self.data_provider.get_residential_meter(household_id)
        if not meter:
            meters = self.data_provider.get_residential_meters()
            meter = meters[0] if meters else {"householdId": household_id}
        horizon = self.model_provider.predict_horizon("residential", household_id)
        return {
            "meter": meter,
            "horizon": horizon,
        }

    def get_government_forecast(self, site_id: str) -> dict[str, Any]:
        site = self.data_provider.get_regional_site(site_id)
        if not site:
            sites = self.data_provider.get_regional_sites()
            site = sites[0] if sites else {"siteId": site_id}
        horizon = self.model_provider.predict_horizon("government", site_id)
        return {
            "site": site,
            "horizon": horizon,
        }

    def predict_one(
        self,
        model_name: str,
        entity_id: str,
        features: dict[str, Any],
        actual_kwh_so_far: float | None = None,
        context: str = "future_forecast",
    ) -> PredictionOutput:
        return self.model_provider.predict(
            model_name=model_name,
            entity_id=entity_id,
            features=features,
            actual_kwh_so_far=actual_kwh_so_far,
            context=context,
        )
