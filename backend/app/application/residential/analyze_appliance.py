"""Application use case: Analyze Appliance Purchase, Sale, or Upgrade Scenario."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.energy.metrics import EnergyUnit
from app.domain.energy.schemas import AnalyticsToolResponse
from app.domain.residential.appliance_engine import ApplianceLifecycleCostEngine
from app.domain.residential.schemas import (
    ApplianceScenarioRequest,
    ApplianceScenarioResult,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.residential.analyze_appliance")


class AnalyzeApplianceScenarioUseCase:
    """Computes lifecycle cost, bill differences, and payback period for appliance purchase/upgrade."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        lifecycle_engine: ApplianceLifecycleCostEngine | None = None,
        tariff_rate: float = 10.0,
        resolver: Any = None,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.resolver = resolver
        self.engine = lifecycle_engine or ApplianceLifecycleCostEngine(resolver=resolver)
        self.tariff_rate = tariff_rate

    def execute(
        self, meter_id: str, request: ApplianceScenarioRequest
    ) -> AnalyticsToolResponse:
        """Execute appliance scenario analysis for authorized customer."""
        if not request.tariff_inr_per_kwh or request.tariff_inr_per_kwh <= 0:
            request.tariff_inr_per_kwh = self.tariff_rate

        result: ApplianceScenarioResult = self.engine.execute_analysis(request)

        return AnalyticsToolResponse(
            status="success",
            meter_id=meter_id,
            tool_name="analyze_appliance_scenario",
            metric="appliance_lifecycle_analysis",
            unit=EnergyUnit.KWH.value,
            results=result.model_dump(),
            data_provenance="appliance_lifecycle_cost_engine",
            observation_count=len(result.cashflows),
            completeness_pct=100.0,
            limitations=[
                "Calculations assume rated power draw and specified daily operating hours.",
                "Actual field performance may vary based on maintenance, seasonal weather, and ambient temperature.",
            ],
        )

