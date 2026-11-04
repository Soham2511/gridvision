"""Use case: Query household consumption history."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.domain.energy.metrics import AggregationGranularity, EnergyUnit
from app.domain.energy.schemas import (
    AnalyticsToolResponse,
    ConsumptionQueryRequest,
    DatePeriod,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.energy_analytics.query_consumption")


class QueryConsumptionUseCase:
    """Retrieves and aggregates household consumption for a specified date period."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        analytics_engine: EnergyAnalyticsEngine | None = None,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.analytics = analytics_engine or EnergyAnalyticsEngine()

    def execute(
        self, meter_id: str, request: ConsumptionQueryRequest
    ) -> AnalyticsToolResponse:
        """Execute consumption query for authorized meter."""
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
                tool_name="query_consumption_history",
                period=period,
                metric=request.metric,
                unit=EnergyUnit.KWH.value,
                results=[],
                observation_count=0,
                completeness_pct=0.0,
                limitations=[
                    f"No recorded meter intervals found for {meter_id} between {period.start_date} and {period.end_date}."
                ],
            )

        aggregated_points = self.analytics.aggregate_intervals(
            records=records,
            granularity=request.granularity,
        )

        total_kwh = round(sum(p.value for p in aggregated_points), 2)
        avg_comp = (
            round(sum(p.completeness_pct for p in aggregated_points) / len(aggregated_points), 1)
            if aggregated_points
            else 0.0
        )

        return AnalyticsToolResponse(
            status="success",
            meter_id=meter_id,
            tool_name="query_consumption_history",
            period=period,
            metric=request.metric,
            unit=EnergyUnit.KWH.value,
            results={
                "totalConsumptionKwh": total_kwh,
                "granularity": request.granularity.value,
                "dataPoints": [p.model_dump() for p in aggregated_points],
            },
            observation_count=len(records),
            completeness_pct=avg_comp,
            limitations=[],
        )
