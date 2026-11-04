"""Application use case: Plan New House Energy & Electrical Layout."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.energy.metrics import EnergyUnit
from app.domain.energy.schemas import AnalyticsToolResponse
from app.domain.residential.building_engine import BuildingEnergyPlanningEngine
from app.domain.residential.schemas import (
    HouseEnergyPlanningRequest,
    HouseEnergyPlanningResult,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.residential.plan_house_energy")


class PlanHouseEnergyUseCase:
    """Computes residential electrical requirements, equipment schedules, and energy plan tiers."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        planning_engine: BuildingEnergyPlanningEngine | None = None,
        tariff_rate: float = 10.0,
        resolver: Any = None,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.engine = planning_engine or BuildingEnergyPlanningEngine()
        self.tariff_rate = tariff_rate
        self.resolver = resolver

    def execute(
        self, meter_id: str, request: HouseEnergyPlanningRequest
    ) -> AnalyticsToolResponse:
        """Execute new house energy planning for authorized customer."""
        # Ensure tariff is synchronized
        if not request.tariff_inr_per_kwh or request.tariff_inr_per_kwh <= 0:
            request.tariff_inr_per_kwh = self.tariff_rate

        result: HouseEnergyPlanningResult = self.engine.execute_planning(request, resolver=self.resolver)

        return AnalyticsToolResponse(
            status="success",
            meter_id=meter_id,
            tool_name="plan_house_energy",
            metric="house_energy_plan",
            unit=EnergyUnit.KWH.value,
            results=result.model_dump(),
            data_provenance="building_energy_planning_engine",
            observation_count=len(result.recommended_plan.equipment_schedule),
            completeness_pct=100.0,
            limitations=[
                "Calculations represent preliminary engineering estimates.",
                "Final wiring sizes and main panel circuit breakers must be verified by a licensed electrical engineer under IS 732.",
            ],
        )

