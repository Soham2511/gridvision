"""Use case: Analyze household peak and low consumption periods."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.domain.energy.metrics import EnergyUnit
from app.domain.energy.schemas import (
    AnalyticsToolResponse,
    DatePeriod,
    PeakAnalysisQueryRequest,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.energy_analytics.analyze_peaks")


class AnalyzePeaksUseCase:
    """Ranks and extracts highest or lowest consumption periods for an authorized household."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        analytics_engine: EnergyAnalyticsEngine | None = None,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.analytics = analytics_engine or EnergyAnalyticsEngine()

    def execute(
        self, meter_id: str, request: PeakAnalysisQueryRequest
    ) -> AnalyticsToolResponse:
        """Execute peak analysis query for authorized meter."""
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
                tool_name="get_peak_consumption_periods",
                period=period,
                metric="peak_demand",
                unit=EnergyUnit.KWH.value,
                results=[],
                observation_count=0,
                completeness_pct=0.0,
                limitations=[
                    f"No recorded telemetry for {meter_id} between {period.start_date} and {period.end_date}."
                ],
            )

        peaks = self.analytics.get_peak_periods(
            records=records,
            granularity=request.granularity,
            top_n=request.top_n,
            ranking_direction=request.ranking_direction,
        )

        return AnalyticsToolResponse(
            status="success",
            meter_id=meter_id,
            tool_name="get_peak_consumption_periods",
            period=period,
            metric=f"{request.ranking_direction}_{request.granularity.value}_consumption",
            unit=EnergyUnit.KWH.value,
            results={
                "granularity": request.granularity.value,
                "direction": request.ranking_direction,
                "topPeriods": [p.model_dump() for p in peaks],
            },
            observation_count=len(records),
            completeness_pct=100.0,
            limitations=[],
        )
