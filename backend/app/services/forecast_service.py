"""Forecasting and inference service."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from numbers import Integral
from typing import Any

from app.api.error_handlers import (
    InvalidModelOutputError,
    ModelUnavailableError,
    RegionMappingNotFoundError,
    ResourceNotFoundError,
)
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
        if hasattr(self.model_provider, "get_commercial_buildings"):
            return self.model_provider.get_commercial_buildings()
        return self.data_provider.get_commercial_buildings()

    def get_residential_meters(self) -> list[dict[str, Any]]:
        return self.data_provider.get_residential_meters()

    def get_regional_sites(self) -> list[dict[str, Any]]:
        if hasattr(self.model_provider, "get_regional_sites"):
            return self.model_provider.get_regional_sites()
        return self.data_provider.get_regional_sites()

    def get_commercial_building(self, building_id: str) -> dict[str, Any] | None:
        return next((row for row in self.get_commercial_buildings() if row["buildingId"] == building_id), None)

    def get_regional_site(self, site_id: str) -> dict[str, Any] | None:
        return next((row for row in self.get_regional_sites() if row["siteId"] == site_id), None)

    def get_commercial_forecast(self, building_id: str) -> dict[str, Any]:
        bldg = self.get_commercial_building(building_id)
        if not bldg:
            raise ResourceNotFoundError(f"Commercial building '{building_id}' not found.")
        horizon = self.model_provider.predict_horizon("commercial", building_id)
        return {
            "building": bldg,
            "horizon": horizon,
        }

    def get_commercial_region_forecast(self, building_id: str) -> dict[str, Any]:
        """Return separately sourced commercial and total-grid forecast horizons."""
        building = self.get_commercial_building(building_id)
        if building is None:
            raise ResourceNotFoundError(f"Commercial building '{building_id}' not found.")
        grid_id = building.get("id.grid.coarse")
        if grid_id is None or str(grid_id).strip() == "":
            raise RegionMappingNotFoundError(
                f"Commercial building '{building_id}' has no verified id.grid.coarse mapping."
            )
        if isinstance(grid_id, bool) or not isinstance(grid_id, Integral):
            raise RegionMappingNotFoundError(
                f"Commercial building '{building_id}' has a non-integer id.grid.coarse mapping."
            )
        grid_id = int(grid_id)

        try:
            # Keep the calls separate: the commercial model receives the building ID;
            # the government model receives only the verified coarse-grid ID.
            commercial_raw = self.model_provider.predict_horizon(
                "commercial", building_id
            )
            government_raw = self.model_provider.predict_horizon(
                "government", str(grid_id)
            )
            commercial_model = self.model_provider.get_forecast_model_info("commercial")
            government_model = self.model_provider.get_forecast_model_info("government")
        except Exception as exc:
            raise ModelUnavailableError(
                f"Commercial and regional forecasts require both horizon models: {exc}"
            ) from exc

        commercial_points = self._normalize_horizon(commercial_raw, "commercial")
        government_points = self._normalize_horizon(government_raw, "government")
        government_by_key = {
            (point["timestamp"], point["horizon_hours"]): point
            for point in government_points
        }
        paired = []
        for point in commercial_points:
            key = (point["timestamp"], point["horizon_hours"])
            regional = government_by_key.get(key)
            if regional is None:
                continue
            paired.append(
                {
                    "timestamp": point["timestamp"],
                    "horizon_hours": point["horizon_hours"],
                    "commercial_prediction": point["prediction"],
                    "total_grid_demand_prediction": regional["prediction"],
                    "commercial_actual": point.get("actual"),
                    "total_grid_demand_actual": regional.get("actual"),
                }
            )
        if not paired:
            raise ModelUnavailableError(
                "The commercial and government models returned no shared timestamp/horizon pairs."
            )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "building": {
                "building_id": building_id,
                "id.grid.coarse": grid_id,
            },
            "commercial_forecast": {
                "source": "commercial_building_model",
                "model": commercial_model,
                "horizon": commercial_points,
            },
            "government_forecast": {
                "source": "government_grid_model",
                "scope": "total_grid_demand",
                "grid_id": grid_id,
                "model": government_model,
                "horizon": government_points,
            },
            "paired_horizon": paired,
        }

    @staticmethod
    def _normalize_horizon(points: list[dict[str, Any]], model_label: str) -> list[dict[str, Any]]:
        """Validate model horizon timestamps, step numbers, and energy predictions."""
        normalized = []
        for point in points:
            timestamp = point.get("timestamp")
            hours = point.get("horizon_hours", point.get("horizonHours"))
            prediction = point.get(
                "prediction", point.get("forecastDemand", point.get("forecast_demand"))
            )
            if timestamp is None or hours is None or prediction is None:
                continue
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                horizon_hours = int(hours)
                value = float(prediction)
            except (TypeError, ValueError, OverflowError) as exc:
                raise InvalidModelOutputError(
                    f"{model_label} forecast has an invalid timestamp, horizon, or prediction."
                ) from exc
            if horizon_hours < 1 or not math.isfinite(value) or value < 0:
                raise InvalidModelOutputError(
                    f"{model_label} forecast predictions must be finite and non-negative with positive horizons."
                )
            normalized.append(
                {
                    "timestamp": parsed.isoformat().replace("+00:00", "Z"),
                    "horizon_hours": horizon_hours,
                    "prediction": value,
                    "actual": float(point["actual"]) if point.get("actual") is not None else None,
                }
            )
        if not normalized:
            raise ModelUnavailableError(f"{model_label} model returned no valid forecast points.")
        keys = [(point["timestamp"], point["horizon_hours"]) for point in normalized]
        if len(keys) != len(set(keys)):
            raise InvalidModelOutputError(f"{model_label} model returned duplicate timestamp/horizon points.")
        return normalized

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
        site = self.get_regional_site(site_id)
        if not site:
            raise ResourceNotFoundError(f"Government grid '{site_id}' not found.")
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
