"""Narrow interfaces available to Commercial specialist agents."""

from __future__ import annotations

from typing import Any, Protocol

from ai.commercial.schemas.communication import ToolObservation


class CommercialTools(Protocol):
    """Read-only-by-default tools injected into the workflow."""

    def get_peak_forecast(
        self,
        factory_id: str | None,
        goal: str,
        building_id: str | None = None,
    ) -> ToolObservation:
        """Return a Commercial building forecast, or explicit unavailability."""

    def get_commercial_buildings(self, limit: int = 20) -> ToolObservation:
        """List real Commercial buildings for forecast selection."""

    def retrieve_operational_context(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        """Return operational graph/document evidence, or explicit unavailability."""

    def get_renewable_scenarios(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        """Return renewable scenario inputs, or explicit unavailability."""

    def optimize(
        self, factory_id: str | None, inputs: dict[str, Any]
    ) -> ToolObservation:
        """Return a validated optimization result, or explicit unavailability."""
