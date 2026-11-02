"""Dashboard and historical analytics service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class DashboardService:
    """Provides aggregated dashboard telemetry across personas."""

    def __init__(self, data_provider: BaseDataProvider, model_provider: Any | None = None) -> None:
        self.data_provider = data_provider
        self.model_provider = model_provider

    def get_commercial_dashboard(
        self,
        tab: str = "building",
        time_range: str = "1D",
        building_id: str = "Panther_office_1",
    ) -> dict[str, Any]:
        if tab in {"building", "regional"} and self.model_provider is not None:
            get_real_dashboard = getattr(
                self.model_provider, "get_commercial_dashboard", None
            )
            if callable(get_real_dashboard):
                entity_id = "regional" if tab == "regional" else building_id
                return get_real_dashboard(entity_id, time_range)
        return self.data_provider.get_commercial_dashboard(
            tab=tab,
            time_range=time_range,
            building_id=building_id,
        )

    def get_household_overview(self, household_id: str | None = None) -> dict[str, Any]:
        return self.data_provider.get_household_overview(household_id=household_id)

    def get_government_regions(self, time_range: str = "1D") -> list[dict[str, Any]]:
        if self.model_provider is not None:
            get_real_regions = getattr(
                self.model_provider, "get_government_regions", None
            )
            if callable(get_real_regions):
                return get_real_regions(time_range)
        return self.data_provider.get_government_regions()

    def get_government_dashboard(
        self,
        view_type: str = "overall",
        region_id: str | None = None,
        time_range: str = "1D",
    ) -> dict[str, Any]:
        if self.model_provider is not None:
            get_real_dashboard = getattr(
                self.model_provider, "get_government_dashboard", None
            )
            if callable(get_real_dashboard):
                return get_real_dashboard(view_type, region_id, time_range)
        return self.data_provider.get_government_dashboard(
            view_type=view_type,
            region_id=region_id,
            time_range=time_range,
        )

    def get_historical_insights(
        self,
        persona: str = "household",
        time_range: str = "30D",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        if persona.lower() == "commercial" and self.model_provider is not None:
            get_commercial_history = getattr(
                self.model_provider, "get_commercial_historical_insights", None
            )
            if callable(get_commercial_history):
                return get_commercial_history(time_range, entity_id)
        if persona.lower() == "government" and self.model_provider is not None:
            get_government_history = getattr(
                self.model_provider, "get_government_historical_insights", None
            )
            if callable(get_government_history):
                return get_government_history(time_range, entity_id)
        return self.data_provider.get_historical_insights(
            persona=persona,
            time_range=time_range,
            entity_id=entity_id,
        )
