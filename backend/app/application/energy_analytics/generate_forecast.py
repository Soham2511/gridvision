"""Use case: Generate forward consumption forecast for household."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.domain.energy.metrics import EnergyUnit
from app.domain.energy.schemas import (
    AnalyticsToolResponse,
    DatePeriod,
    ForecastQueryRequest,
    ForecastResult,
)
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.energy_analytics.generate_forecast")


class GenerateForecastUseCase:
    """Computes bounded consumption projections for an authorized household."""

    def __init__(
        self,
        repository: BaseHouseholdEnergyRepository | None = None,
        analytics_engine: EnergyAnalyticsEngine | None = None,
        tariff_rate: float = 10.0,
    ) -> None:
        self.repository = repository or HouseholdEnergyRepository()
        self.analytics = analytics_engine or EnergyAnalyticsEngine()
        self.tariff_rate = tariff_rate

    def execute(
        self, meter_id: str, request: ForecastQueryRequest
    ) -> AnalyticsToolResponse:
        """Execute forecast projection for authorized meter."""
        clamped_horizon = max(1, min(int(request.horizon_days), 30))
        min_date, max_date = self.repository.get_available_date_range(meter_id)

        # 1. Determine anchor start date
        if request.start_date:
            clean_start = request.start_date.strip().split("T")[0].split(" ")[0]
            start_date_str = clean_start
        elif max_date:
            try:
                dt_max = datetime.strptime(max_date, "%Y-%m-%d")
                start_date_str = (dt_max + timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                start_date_str = datetime.now().strftime("%Y-%m-%d")
        else:
            start_date_str = datetime.now().strftime("%Y-%m-%d")

        # 2. Fetch trailing 30 days of telemetry to establish empirical baseline
        baseline_records: list[dict[str, Any]] = []
        if max_date:
            try:
                req_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                max_dt = datetime.strptime(max_date, "%Y-%m-%d")

                anchor_dt = min(req_dt, max_dt)
                trailing_start = (anchor_dt - timedelta(days=30)).strftime("%Y-%m-%d")
                trailing_end = anchor_dt.strftime("%Y-%m-%d")

                baseline_records = self.repository.get_meter_intervals(
                    meter_id=meter_id,
                    start_date=trailing_start,
                    end_date=trailing_end,
                )
            except Exception as exc:
                logger.warning("Failed to retrieve trailing baseline for meter %s: %s", meter_id, exc)

        # 3. Generate forward projection
        forecast_result: ForecastResult = self.analytics.project_consumption_forecast(
            records=baseline_records,
            horizon_days=clamped_horizon,
            start_date=start_date_str,
            tariff_rate_inr_per_kwh=self.tariff_rate,
        )

        period = DatePeriod(
            start_date=forecast_result.start_date,
            end_date=forecast_result.end_date,
        )

        return AnalyticsToolResponse(
            status="success" if baseline_records else "insufficient_data",
            meter_id=meter_id,
            tool_name="forecast_consumption",
            period=period,
            metric="forecast_consumption",
            unit=EnergyUnit.KWH.value,
            results=forecast_result.model_dump(),
            observation_count=len(baseline_records),
            completeness_pct=100.0 if baseline_records else 0.0,
            limitations=forecast_result.caveats if not baseline_records else [],
        )
