"""Use case: Breakdown household consumption along categorical dimensions."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.domain.energy.metrics import EnergyUnit
from app.domain.energy.schemas import (
    AnalyticsToolResponse,
    BreakdownQueryRequest,
    DatePeriod,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.energy_analytics.breakdown")


class BreakdownConsumptionUseCase:
    """Computes distribution of consumption across hours of day, days of week, or months."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        analytics_engine: EnergyAnalyticsEngine | None = None,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.analytics = analytics_engine or EnergyAnalyticsEngine()

    def execute(
        self, meter_id: str, request: BreakdownQueryRequest
    ) -> AnalyticsToolResponse:
        """Execute consumption breakdown for authorized meter."""
        period = DatePeriod(start_date=request.start_date, end_date=request.end_date)
        records = self.repository.get_meter_intervals(
            meter_id=meter_id,
            start_date=period.start_date,
            end_date=period.end_date,
        )

        if not records:
            return AnalyticsToolResponse(
                status="insufficient_data",
                meter_id=meter_id,
                tool_name="get_consumption_breakdown",
                period=period,
                metric="breakdown",
                unit=EnergyUnit.KWH.value,
                results=[],
                observation_count=0,
                completeness_pct=0.0,
                limitations=[
                    f"No recorded telemetry for {meter_id} between {period.start_date} and {period.end_date}."
                ],
            )

        buckets = self.analytics.breakdown_consumption(
            records=records,
            dimension=request.dimension,
        )

        total_kwh = round(sum(b.total_kwh for b in buckets), 2)

        return AnalyticsToolResponse(
            status="success",
            meter_id=meter_id,
            tool_name="get_consumption_breakdown",
            period=period,
            metric=f"breakdown_by_{request.dimension}",
            unit=EnergyUnit.KWH.value,
            results={
                "dimension": request.dimension,
                "totalConsumptionKwh": total_kwh,
                "buckets": [b.model_dump() for b in buckets],
            },
            observation_count=len(records),
            completeness_pct=100.0,
            limitations=[],
        )
