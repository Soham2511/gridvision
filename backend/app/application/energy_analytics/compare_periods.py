"""Use case: Compare two household consumption periods."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.domain.energy.metrics import EnergyUnit
from app.domain.energy.schemas import (
    AnalyticsToolResponse,
    ComparisonQueryRequest,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.energy_analytics.compare_periods")


class ComparePeriodsUseCase:
    """Compares consumption between two user-specified periods for an authorized household."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        analytics_engine: EnergyAnalyticsEngine | None = None,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.analytics = analytics_engine or EnergyAnalyticsEngine()

    def execute(
        self, meter_id: str, request: ComparisonQueryRequest
    ) -> AnalyticsToolResponse:
        """Execute period comparison for authorized meter."""
        records_a = self.repository.get_meter_intervals(
            meter_id=meter_id,
            start_date=request.period_a.start_date,
            end_date=request.period_a.end_date,
        )
        records_b = self.repository.get_meter_intervals(
            meter_id=meter_id,
            start_date=request.period_b.start_date,
            end_date=request.period_b.end_date,
        )

        comparison_result = self.analytics.compare_periods(
            records_a=records_a,
            period_a=request.period_a,
            records_b=records_b,
            period_b=request.period_b,
        )

        limitations = []
        if not comparison_result.is_comparable:
            limitations.append("One or both periods have missing observations, preventing direct comparison.")

        total_obs = len(records_a) + len(records_b)

        return AnalyticsToolResponse(
            status="success" if comparison_result.is_comparable else "insufficient_data",
            meter_id=meter_id,
            tool_name="compare_consumption_periods",
            period=request.period_b,
            metric=request.metric,
            unit=EnergyUnit.KWH.value,
            results=comparison_result.model_dump(),
            observation_count=total_obs,
            completeness_pct=min(
                comparison_result.period_a.completeness_pct,
                comparison_result.period_b.completeness_pct,
            ),
            limitations=limitations,
        )
