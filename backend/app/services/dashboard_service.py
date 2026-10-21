"""Dashboard and historical analytics service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class DashboardService:
    """Provides aggregated dashboard telemetry across personas."""

    def __init__(self, data_provider: BaseDataProvider) -> None:
        self.data_provider = data_provider

    def get_commercial_dashboard(
        self,
        tab: str = "building",
        time_range: str = "1D",
        building_id: str = "Panther_office_1",
    ) -> dict[str, Any]:
        return self.data_provider.get_commercial_dashboard(
            tab=tab,
            time_range=time_range,
            building_id=building_id,
        )

    def get_household_overview(self, household_id: str | None = None) -> dict[str, Any]:
        return self.data_provider.get_household_overview(household_id=household_id)

    def get_government_regions(self) -> list[dict[str, Any]]:
        return self.data_provider.get_government_regions()

    def get_government_dashboard(
        self,
        view_type: str = "overall",
        region_id: str | None = None,
        time_range: str = "1D",
    ) -> dict[str, Any]:
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
        return self.data_provider.get_historical_insights(
            persona=persona,
            time_range=time_range,
            entity_id=entity_id,
        )
