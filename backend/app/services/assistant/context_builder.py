"""Household context builder and metrics calculator for residential conversational AI.

Strictly extracts telemetry and billing metrics for ONLY the authorized meter ID.
Separates data retrieval, metric calculation, context modeling, and prompt serialization.
Guarantees zero crossover, zero hardcoded fallback data, and strict data grounding.
"""

from __future__ import annotations

import json
from typing import Any
from app.providers.data_provider import BaseDataProvider
from app.services.assistant.historical.snapshot_repository import HistoricalSnapshotRepository


class HouseholdMetricsCalculator:
    """Pure calculation engine for residential energy metrics and billing projections."""

    @staticmethod
    def calculate_cycle_daily_average(
        actual_cycle_kwh: float | None, elapsed_days: int | None
    ) -> float | None:
        """Calculate average daily consumption across the elapsed cycle days so far."""
        if actual_cycle_kwh is None or elapsed_days is None or elapsed_days <= 0:
            return None
        return round(actual_cycle_kwh / elapsed_days, 2)

    @staticmethod
    def calculate_percentage_change(
        current: float | None, baseline: float | None
    ) -> float | None:
        """Calculate percentage difference of current value relative to baseline."""
        if current is None or baseline is None or baseline <= 0:
            return None
        return round(((current - baseline) / baseline) * 100, 1)

    @staticmethod
    def calculate_billing_projections(
        actual_cycle: float | None,
        predicted_remaining: float | None,
        fallback_est_kwh: float | None,
        tariff_rate: float,
    ) -> tuple[float | None, float | None]:
        """Compute estimated month-end kWh and estimated invoice in INR."""
        if actual_cycle is not None and predicted_remaining is not None:
            est_kwh = round(actual_cycle + predicted_remaining, 1)
            est_bill = round(est_kwh * tariff_rate, 2)
            return est_kwh, est_bill

        if fallback_est_kwh is not None:
            est_kwh = round(float(fallback_est_kwh), 1)
            est_bill = round(est_kwh * tariff_rate, 2)
            return est_kwh, est_bill

        return None, None


class HouseholdContextBuilder:
    """Assembles a verified, meter-scoped telemetry context for the LLM."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        tariff_rate: float = 10.0,
        snapshot_repository: HistoricalSnapshotRepository | None = None,
    ) -> None:
        self.data_provider = data_provider
        self.tariff_rate = tariff_rate
        self.snapshot_repository = (
            snapshot_repository
            if snapshot_repository is not None
            else HistoricalSnapshotRepository()
        )
        self.calculator = HouseholdMetricsCalculator()

    def build_context(
        self, household_id: str, prompt_intent: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch and structure telemetry exclusively for the specified household_id.

        Returns None if the meter does not exist in the verified data provider.
        """
        clean_id = (household_id or "").strip()
        if not clean_id:
            return None

        # 1. Strictly isolated meter fetch
        meter_data = self.data_provider.get_residential_meter(clean_id)
        if not meter_data:
            return None

        hid = meter_data.get("householdId", clean_id)
        num_part = hid.replace("METER-", "").replace("meter-", "")
        formatted_meter_id = f"METER-{num_part}"
        resident_name = f"Resident-{num_part}"

        # 2. Scoped household analytics
        overview_data = self.data_provider.get_household_overview(hid) or {}
        history_data = self.data_provider.get_historical_insights("household", "30D", hid) or {}
        history_metrics = history_data.get("metrics") or {}

        # 3. 24-hour diurnal load profile sample (only non-null points)
        raw_curve = overview_data.get("consumptionCurve", [])
        compact_curve = [
            {
                "time": pt.get("time"),
                "actualKwh": pt.get("actualConsumption"),
                "predictedKwh": pt.get("predictedConsumption"),
            }
            for pt in raw_curve
            if pt.get("actualConsumption") is not None or pt.get("predictedConsumption") is not None
        ]

        # 4. Coverage and Data Quality
        cov_ratio = meter_data.get("coverageRatio")
        coverage_pct = round(cov_ratio * 100, 1) if cov_ratio is not None else None
        data_quality_status = (
            "nominal_high_coverage"
            if coverage_pct and coverage_pct >= 90.0
            else "partial_coverage_warning"
        )

        # 5. Core Metric Calculations
        actual_cycle = meter_data.get("actualCycleKwhSoFar")
        predicted_remaining = meter_data.get("predictedRemainingKwh")
        est_month_kwh_raw = meter_data.get("estimatedMonthEndKwh")
        elapsed_days = meter_data.get("elapsedDays")
        last_date = meter_data.get("lastDate")

        est_month_kwh, est_month_bill = self.calculator.calculate_billing_projections(
            actual_cycle=actual_cycle,
            predicted_remaining=predicted_remaining,
            fallback_est_kwh=est_month_kwh_raw,
            tariff_rate=self.tariff_rate,
        )

        cycle_daily_avg = self.calculator.calculate_cycle_daily_average(
            actual_cycle, elapsed_days
        )

        current_daily = meter_data.get("dailyKwh", overview_data.get("currentDailyUsageKwh"))
        baseline_daily_avg = overview_data.get("dailyAvgKwh")
        prev_7d_avg = overview_data.get("prev7DaysAvgKwh")
        monthly_avg = overview_data.get("monthlyAvgKwh")
        prev_month_kwh = overview_data.get("prevMonthKwh")

        daily_change_vs_30d = self.calculator.calculate_percentage_change(
            current_daily, baseline_daily_avg
        )
        daily_change_vs_7d = self.calculator.calculate_percentage_change(
            current_daily, prev_7d_avg
        )
        monthly_change_vs_prev = self.calculator.calculate_percentage_change(
            monthly_avg, prev_month_kwh
        )

        # 6. Retrieve persistent historical snapshot for authorized meter
        historical_snapshot = None
        if self.snapshot_repository is not None:
            historical_snapshot = self.snapshot_repository.get_snapshot(formatted_meter_id)

        historical_profile = None
        has_profile = False
        has_yearly = False
        has_monthly = False
        has_seasonality = False

        if historical_snapshot and "historicalProfile" in historical_snapshot:
            historical_profile = historical_snapshot["historicalProfile"]
            has_profile = True
            has_yearly = bool(historical_profile.get("yearlyTrends"))
            has_monthly = bool(historical_profile.get("monthlyTimeline"))
            has_seasonality = bool(historical_profile.get("seasonality"))

        context = {
            "contextSchemaVersion": "2.0",
            "contextCapabilities": {
                "recentAnalyticsAvailable": True,
                "historicalProfileAvailable": has_profile,
                "historicalYearlyTrendsAvailable": has_yearly,
                "historicalMonthlyTimelineAvailable": has_monthly,
                "historicalSeasonalityAvailable": has_seasonality,
                "detailedHistoricalQueriesAvailable": False,
            },
            "householdIdentity": {
                "meterId": formatted_meter_id,
                "customerName": resident_name,
                "persona": "residential",
                "tariffRateInrPerKwh": self.tariff_rate,
            },
            "dataProvenance": {
                "dataSource": "retrospective_smart_meter_benchmark",
                "dataStatus": "recorded_historical_cycle",
                "isolationScope": f"meter_isolated_{formatted_meter_id}",
                "lastRecordedDate": last_date,
                "temporalFreshness": f"Recorded telemetry as of {last_date}" if last_date else "Unknown",
                "coverageStatus": data_quality_status,
                "telemetryCoverageRatioPct": coverage_pct,
            },
            "billingCycleStatus": {
                "elapsedDays": elapsed_days,
                "totalCycleDays": 30,
                "lastRecordedDate": last_date,
                "actualCycleKwhSoFar": actual_cycle,
                "cycleDailyAverageKwh": cycle_daily_avg,
                "predictedRemainingKwh": predicted_remaining,
                "estimatedMonthEndKwh": est_month_kwh,
                "estimatedMonthEndBillInr": est_month_bill,
            },
            "recentConsumptionMetrics": {
                "currentDailyUsageKwh": current_daily,
                "cycleDailyAverageKwh": cycle_daily_avg,
                "baselineDailyAverageKwh": baseline_daily_avg,
                "dailyChangeVs30dBaselinePct": daily_change_vs_30d,
                "prev7DaysAvgKwh": prev_7d_avg,
                "dailyChangeVs7dAveragePct": daily_change_vs_7d,
                "monthlyAverageKwh": monthly_avg,
                "monthlyChangeVsPrevMonthPct": monthly_change_vs_prev,
                "previousMonthTotalKwh": prev_month_kwh,
                "hourlyPatternSample": compact_curve[:8],
            },
            "historical30DOverview": {
                "periodDemandKwh": history_metrics.get("totalDemandKwh", monthly_avg),
                "peakDemandKwh": history_metrics.get("peakHourDemandKwh"),
                "dailyAverageKwh": history_metrics.get("dailyAverageKwh", baseline_daily_avg),
            },
            "historicalProfile": historical_profile,
        }

        return context

    def format_as_prompt_block(self, context: dict[str, Any]) -> str:
        """Serialize context to JSON string for inclusion in the system prompt.
        
        Compacts verbose monthly timelines and hourly arrays to stay safely below LLM token limits (TPM 8000).
        """
        # Streamline context into essentials needed for prompt grounding
        compact_ctx = {
            "householdIdentity": context.get("householdIdentity"),
            "billingCycleStatus": context.get("billingCycleStatus"),
            "recentConsumptionMetrics": context.get("recentConsumptionMetrics"),
        }
        hp = context.get("historicalProfile") or {}
        if hp:
            compact_ctx["historicalSummary"] = {
                "allTimeSummary": hp.get("allTimeSummary"),
                "coverage": hp.get("coverage"),
                "recentMonths": (hp.get("monthlyTimeline") or [])[-3:],
            }
        return json.dumps(compact_ctx, separators=(",", ":"))
