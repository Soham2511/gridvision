"""Unified Energy Analytics Engine for GridVision.

Pure, deterministic, framework-agnostic mathematical operations engine.
Owns all calculations for aggregation, statistical distribution, period comparison,
breakdown analysis, peak rankings, and billing projections.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.domain.energy.metrics import AggregationGranularity, EnergyUnit
from app.domain.energy.schemas import (
    AggregationDataPoint,
    BreakdownBucket,
    DatePeriod,
    ForecastDataPoint,
    ForecastResult,
    PeakPeriodRecord,
    PeriodComparisonResult,
    PeriodSummary,
)


class EnergyAnalyticsEngine:
    """Pure domain analytics engine for household energy computations."""

    # --- 1. Aggregation Operations ---

    @staticmethod
    def aggregate_intervals(
        records: list[dict[str, Any]],
        granularity: AggregationGranularity = AggregationGranularity.DAILY,
    ) -> list[AggregationDataPoint]:
        """Aggregate raw interval readings according to requested temporal granularity.

        records item format: {"timestamp": datetime, "kwh": float}
        """
        if not records:
            return []

        df = pd.DataFrame(records)
        df = df.dropna(subset=["timestamp", "kwh"])
        df = df[df["kwh"] >= 0]
        if df.empty:
            return []

        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        df = df.sort_values("timestamp")

        if granularity == AggregationGranularity.HOURLY:
            df["key"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:00")
            expected_per_bucket = 1
            unit = EnergyUnit.KWH
        elif granularity == AggregationGranularity.DAILY:
            df["key"] = df["timestamp"].dt.strftime("%Y-%m-%d")
            expected_per_bucket = 24
            unit = EnergyUnit.KWH
        elif granularity == AggregationGranularity.WEEKLY:
            df["key"] = df["timestamp"].dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
            expected_per_bucket = 24 * 7
            unit = EnergyUnit.KWH
        elif granularity == AggregationGranularity.MONTHLY:
            df["key"] = df["timestamp"].dt.strftime("%Y-%m")
            expected_per_bucket = 24 * 30
            unit = EnergyUnit.KWH
        elif granularity == AggregationGranularity.YEARLY:
            df["key"] = df["timestamp"].dt.strftime("%Y")
            expected_per_bucket = 24 * 365
            unit = EnergyUnit.KWH
        else:
            df["key"] = df["timestamp"].dt.strftime("%Y-%m-%d")
            expected_per_bucket = 24
            unit = EnergyUnit.KWH

        results: list[AggregationDataPoint] = []
        for key_val, group in df.groupby("key", sort=True):
            total_val = round(float(group["kwh"].sum()), 2)
            count = len(group)
            comp_pct = round((count / expected_per_bucket) * 100, 1) if expected_per_bucket > 0 else 100.0

            results.append(
                AggregationDataPoint(
                    period_key=str(key_val),
                    value=total_val,
                    unit=unit.value,
                    observation_count=count,
                    completeness_pct=min(comp_pct, 100.0),
                )
            )

        return results

    # --- 2. Statistical Calculations ---

    @staticmethod
    def calculate_statistics(values: list[float]) -> dict[str, float | None]:
        """Compute basic distribution statistics over a list of numerical values."""
        clean = [v for v in values if v is not None and not math.isnan(v)]
        if not clean:
            return {
                "mean": None,
                "median": None,
                "p10": None,
                "p90": None,
                "min": None,
                "max": None,
                "std": None,
                "cv": None,
            }

        arr = np.array(clean, dtype=float)
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr))
        cv = (std_val / mean_val) if mean_val > 0 else None

        return {
            "mean": round(mean_val, 2),
            "median": round(float(np.median(arr)), 2),
            "p10": round(float(np.percentile(arr, 10)), 2),
            "p90": round(float(np.percentile(arr, 90)), 2),
            "min": round(float(np.min(arr)), 2),
            "max": round(float(np.max(arr)), 2),
            "std": round(std_val, 2),
            "cv": round(cv, 3) if cv is not None else None,
        }

    # --- 3. Period Comparison Operations ---

    @classmethod
    def compare_periods(
        cls,
        records_a: list[dict[str, Any]],
        period_a: DatePeriod,
        records_b: list[dict[str, Any]],
        period_b: DatePeriod,
    ) -> PeriodComparisonResult:
        """Compare two periods cleanly using normalized daily rates and total energy."""
        summary_a = cls._summarize_period(records_a, period_a)
        summary_b = cls._summarize_period(records_b, period_b)

        abs_diff = round(summary_b.total_consumption_kwh - summary_a.total_consumption_kwh, 2)
        norm_diff = round(summary_b.average_daily_kwh - summary_a.average_daily_kwh, 2)

        # Check comparability: periods must both have sufficient observed days
        # and not have wild day length disparities unless comparing daily averages
        is_comparable = True
        explanation_parts = []

        if summary_a.observed_days == 0:
            is_comparable = False
            explanation_parts.append(f"Period A ({period_a.start_date} to {period_a.end_date}) has no recorded data.")
        if summary_b.observed_days == 0:
            is_comparable = False
            explanation_parts.append(f"Period B ({period_b.start_date} to {period_b.end_date}) has no recorded data.")

        pct_change = None
        if is_comparable:
            # Use daily average as the primary comparison base to handle differing calendar day lengths
            base_rate = summary_a.average_daily_kwh
            if base_rate > 0:
                pct_change = round(((summary_b.average_daily_kwh - base_rate) / base_rate) * 100, 1)
                direction = "higher" if pct_change > 0 else "lower"
                explanation_parts.append(
                    f"Average daily consumption in Period B ({summary_b.average_daily_kwh} kWh/day) "
                    f"is {abs(pct_change):.1f}% {direction} than Period A ({summary_a.average_daily_kwh} kWh/day)."
                )
            else:
                pct_change = None
                explanation_parts.append("Baseline average daily consumption is zero; percentage change cannot be computed.")

        return PeriodComparisonResult(
            period_a=summary_a,
            period_b=summary_b,
            absolute_difference_kwh=abs_diff,
            percentage_change_pct=pct_change,
            normalized_daily_difference_kwh=norm_diff,
            is_comparable=is_comparable,
            explanation=" ".join(explanation_parts),
        )

    @classmethod
    def _summarize_period(
        cls, records: list[dict[str, Any]], period: DatePeriod
    ) -> PeriodSummary:
        daily_points = cls.aggregate_intervals(records, AggregationGranularity.DAILY)
        d_start = datetime.strptime(period.start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(period.end_date, "%Y-%m-%d").date()
        expected_days = (d_end - d_start).days + 1

        total_kwh = round(sum(p.value for p in daily_points), 2)
        observed_days = len(daily_points)
        avg_daily = round(total_kwh / observed_days, 2) if observed_days > 0 else 0.0
        comp_pct = round((observed_days / expected_days) * 100, 1) if expected_days > 0 else 0.0

        return PeriodSummary(
            period=period,
            total_consumption_kwh=total_kwh,
            average_daily_kwh=avg_daily,
            observed_days=observed_days,
            expected_days=expected_days,
            completeness_pct=min(comp_pct, 100.0),
        )

    # --- 4. Breakdown Distributions ---

    @staticmethod
    def breakdown_consumption(
        records: list[dict[str, Any]],
        dimension: str = "hour_of_day",
    ) -> list[BreakdownBucket]:
        """Compute consumption distribution across categorical dimensions."""
        if not records:
            return []

        df = pd.DataFrame(records)
        df = df.dropna(subset=["timestamp", "kwh"])
        df = df[df["kwh"] >= 0]
        if df.empty:
            return []

        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        total_all_kwh = float(df["kwh"].sum())

        if dimension == "hour_of_day":
            df["bucket"] = df["timestamp"].dt.strftime("%H:00")
            order_keys = [f"{h:02d}:00" for h in range(24)]
        elif dimension == "day_of_week":
            df["bucket"] = df["timestamp"].dt.day_name()
            order_keys = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        elif dimension == "monthly":
            df["bucket"] = df["timestamp"].dt.strftime("%Y-%m")
            order_keys = sorted(df["bucket"].unique())
        else:
            df["bucket"] = df["timestamp"].dt.strftime("%Y-%m-%d")
            order_keys = sorted(df["bucket"].unique())

        grouped = df.groupby("bucket")["kwh"].agg(["sum", "mean"]).to_dict("index")
        buckets: list[BreakdownBucket] = []

        for b_name in order_keys:
            if b_name in grouped:
                b_sum = round(float(grouped[b_name]["sum"]), 2)
                b_mean = round(float(grouped[b_name]["mean"]), 2)
                pct = round((b_sum / total_all_kwh) * 100, 1) if total_all_kwh > 0 else 0.0
                buckets.append(
                    BreakdownBucket(
                        bucket=b_name,
                        total_kwh=b_sum,
                        percentage_of_total=pct,
                        average_kwh=b_mean,
                    )
                )

        return buckets

    # --- 5. Peak and Low Analysis ---

    @classmethod
    def get_peak_periods(
        cls,
        records: list[dict[str, Any]],
        granularity: AggregationGranularity = AggregationGranularity.DAILY,
        top_n: int = 5,
        ranking_direction: str = "highest",
    ) -> list[PeakPeriodRecord]:
        """Identify extreme consumption periods (peaks or lows)."""
        aggregated = cls.aggregate_intervals(records, granularity)
        if not aggregated:
            return []

        reverse = (ranking_direction == "highest")
        sorted_points = sorted(aggregated, key=lambda p: p.value, reverse=reverse)

        results: list[PeakPeriodRecord] = []
        for idx, pt in enumerate(sorted_points[:top_n]):
            results.append(
                PeakPeriodRecord(
                    rank=idx + 1,
                    period=pt.period_key,
                    consumption_kwh=pt.value,
                    average_daily_kwh=pt.value if granularity == AggregationGranularity.DAILY else None,
                )
            )

        return results

    # --- 6. Billing Calculations ---

    @staticmethod
    def calculate_bill_projection(
        actual_cycle_kwh: float | None,
        predicted_remaining_kwh: float | None,
        tariff_rate_inr_per_kwh: float,
    ) -> tuple[float | None, float | None]:
        """Compute estimated month-end kWh and estimated invoice in INR."""
        if actual_cycle_kwh is None or tariff_rate_inr_per_kwh <= 0:
            return None, None

        pred = predicted_remaining_kwh if predicted_remaining_kwh is not None else 0.0
        est_kwh = round(actual_cycle_kwh + pred, 1)
        est_bill = round(est_kwh * tariff_rate_inr_per_kwh, 2)
        return est_kwh, est_bill

    @staticmethod
    def calculate_bill_amount(
        consumption_kwh: float | None,
        tariff_rate_inr_per_kwh: float,
    ) -> float | None:
        """Calculate bill cost in INR from kWh and tariff rate."""
        if consumption_kwh is None or tariff_rate_inr_per_kwh <= 0:
            return None
        return round(float(consumption_kwh) * float(tariff_rate_inr_per_kwh), 2)

    @staticmethod
    def calculate_daily_rate(
        total_kwh: float | None,
        days: int | None,
    ) -> float | None:
        """Calculate average daily consumption rate from total consumption and day count."""
        if total_kwh is None or days is None or days <= 0:
            return None
        return round(float(total_kwh) / int(days), 2)

    @staticmethod
    def calculate_confidence_bounds(
        predicted_kwh: float,
        margin_kwh: float | None = None,
        margin_pct: float | None = None,
    ) -> dict[str, float]:
        """Compute lower and upper confidence bounds cleanly avoiding negative values."""
        if margin_kwh is not None:
            err = abs(float(margin_kwh))
        elif margin_pct is not None:
            err = abs(float(predicted_kwh) * (float(margin_pct) / 100.0))
        else:
            err = abs(float(predicted_kwh) * 0.10)

        lower = max(0.0, round(float(predicted_kwh) - err, 2))
        upper = round(float(predicted_kwh) + err, 2)
        return {
            "lower_kwh": lower,
            "upper_kwh": upper,
            "margin_kwh": round(err, 2),
        }

    # --- 7. Bounded Forecasting Engine ---

    @classmethod
    def project_consumption_forecast(
        cls,
        records: list[dict[str, Any]],
        horizon_days: int = 7,
        start_date: str | None = None,
        tariff_rate_inr_per_kwh: float = 10.0,
        confidence_interval_pct: float = 10.0,
    ) -> ForecastResult:
        """Project forward household electricity consumption for a bounded horizon (1 to 30 days).

        Employs an autoregressive daily baseline with empirical day-of-week demand weighting
        derived from recent observed telemetry intervals.
        """
        horizon_days = max(1, min(int(horizon_days), 30))

        # 1. Determine anchor start date
        if start_date:
            try:
                clean_start = start_date.strip().split("T")[0].split(" ")[0]
                start_dt = datetime.strptime(clean_start, "%Y-%m-%d").date()
            except ValueError:
                start_dt = date.today()
        elif records:
            max_rec_dt = max(
                (r["timestamp"] if isinstance(r["timestamp"], (datetime, date)) else pd.to_datetime(r["timestamp"]))
                for r in records
                if r.get("timestamp")
            )
            rec_date = max_rec_dt.date() if isinstance(max_rec_dt, datetime) else max_rec_dt
            start_dt = rec_date + timedelta(days=1)
        else:
            start_dt = date.today()

        # 2. Derive daily baseline and day-of-week weights from records
        daily_points = cls.aggregate_intervals(records, AggregationGranularity.DAILY) if records else []

        if daily_points:
            daily_vals = [p.value for p in daily_points if p.value > 0]
            baseline_mean = float(np.mean(daily_vals)) if daily_vals else 10.0

            dow_totals: dict[int, list[float]] = {i: [] for i in range(7)}
            for p in daily_points:
                try:
                    p_dt = datetime.strptime(p.period_key, "%Y-%m-%d").date()
                    dow_totals[p_dt.weekday()].append(p.value)
                except ValueError:
                    pass

            dow_weights: dict[int, float] = {}
            for dow, vals in dow_totals.items():
                if vals and baseline_mean > 0:
                    ratio = float(np.mean(vals)) / baseline_mean
                    dow_weights[dow] = max(0.8, min(ratio, 1.25))
                else:
                    dow_weights[dow] = 1.0
        else:
            baseline_mean = 12.0
            dow_weights = {i: 1.0 for i in range(7)}

        # 3. Generate bounded forward daily projection points
        forecast_points: list[ForecastDataPoint] = []
        for i in range(horizon_days):
            cur_date = start_dt + timedelta(days=i)
            cur_dow = cur_date.weekday()
            weight = dow_weights.get(cur_dow, 1.0)

            pred_kwh = round(max(0.1, baseline_mean * weight), 2)
            margin = round(pred_kwh * (confidence_interval_pct / 100.0), 2)
            lower_kwh = round(max(0.0, pred_kwh - margin), 2)
            upper_kwh = round(pred_kwh + margin, 2)

            forecast_points.append(
                ForecastDataPoint(
                    date=cur_date.strftime("%Y-%m-%d"),
                    predicted_kwh=pred_kwh,
                    lower_bound_kwh=lower_kwh,
                    upper_bound_kwh=upper_kwh,
                )
            )

        end_dt = start_dt + timedelta(days=horizon_days - 1)
        total_pred = round(sum(p.predicted_kwh for p in forecast_points), 2)
        avg_daily = round(total_pred / horizon_days, 2)
        est_bill = round(total_pred * tariff_rate_inr_per_kwh, 2) if tariff_rate_inr_per_kwh > 0 else None

        caveats = [
            f"Forecast is strictly bounded to {horizon_days} days (maximum 30 days allowed by safety guardrails).",
            "Projection uses trailing telemetry baseline with day-of-week demand pattern adjustment.",
            f"Expected variance is estimated at \u00b1{confidence_interval_pct:.0f}% under normal operating conditions.",
            "Unforeseen appliance usage, extreme weather anomalies, or prolonged vacancies will alter actual consumption.",
        ]

        return ForecastResult(
            horizon_days=horizon_days,
            start_date=start_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
            total_predicted_kwh=total_pred,
            average_daily_kwh=avg_daily,
            forecast_points=forecast_points,
            methodology="trailing_baseline_with_day_weighting",
            estimated_bill_inr=est_bill,
            tariff_rate_inr_per_kwh=tariff_rate_inr_per_kwh,
            confidence_interval_pct=confidence_interval_pct,
            caveats=caveats,
        )

