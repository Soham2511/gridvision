"""Abstract base class interface for data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDataProvider(ABC):
    """Abstract data provider interface for GridVision."""

    @abstractmethod
    def get_commercial_buildings(self) -> list[dict[str, Any]]:
        """Return list of commercial buildings."""

    @abstractmethod
    def get_commercial_building(self, building_id: str) -> dict[str, Any] | None:
        """Return details for a single commercial building."""

    @abstractmethod
    def get_residential_meters(self) -> list[dict[str, Any]]:
        """Return list of residential meters."""

    @abstractmethod
    def get_residential_meter(self, household_id: str) -> dict[str, Any] | None:
        """Return details for a single residential meter."""

    @abstractmethod
    def get_regional_sites(self) -> list[dict[str, Any]]:
        """Return list of regional government grid sites."""

    @abstractmethod
    def get_regional_site(self, site_id: str) -> dict[str, Any] | None:
        """Return details for a single regional site."""

    @abstractmethod
    def get_regional_rankings(self) -> list[dict[str, Any]]:
        """Return regional system ranking metrics."""

    @abstractmethod
    def get_commercial_dashboard(
        self,
        tab: str = "building",
        time_range: str = "1D",
        building_id: str = "Panther_office_1",
    ) -> dict[str, Any]:
        """Return commercial dashboard telemetry and curves."""

    @abstractmethod
    def get_household_overview(self, household_id: str | None = None) -> dict[str, Any]:
        """Return household consumption overview and curve."""

    @abstractmethod
    def get_government_regions(self) -> list[dict[str, Any]]:
        """Return government regional items."""

    @abstractmethod
    def get_government_dashboard(
        self,
        view_type: str = "overall",
        region_id: str | None = None,
        time_range: str = "1D",
    ) -> dict[str, Any]:
        """Return government regional grid dashboard telemetry."""

    @abstractmethod
    def get_historical_insights(
        self,
        persona: str = "household",
        time_range: str = "30D",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        """Return aggregated historical demand curves and metrics."""

    @abstractmethod
    def get_peak_demand_analysis(self) -> dict[str, Any]:
        """Return peak demand statistics, reserve margins, and timelines."""

    @abstractmethod
    def get_anomaly_events(
        self,
        severity: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return filtered anomaly detection events."""

    @abstractmethod
    def update_anomaly_status(self, event_id: str, status: str) -> dict[str, Any] | None:
        """Update the status of an anomaly event."""

    @abstractmethod
    def get_customer_segments(self) -> list[dict[str, Any]]:
        """Return high-level customer segments."""

    @abstractmethod
    def get_customer_segmentation_matrix(self) -> dict[str, Any]:
        """Return comprehensive customer segmentation telemetry."""

    @abstractmethod
    def get_diurnal_curves(self) -> list[dict[str, Any]]:
        """Return hourly diurnal load curves."""

    @abstractmethod
    def get_business_insights(
        self,
        category: str | None = None,
        sector: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return algorithmic business insights."""

    @abstractmethod
    def get_platform_health_summary(self) -> dict[str, Any]:
        """Return platform telemetry and model health statistics."""
