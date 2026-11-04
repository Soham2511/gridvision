"""Deterministic calculation engine for GridVision Monthly Energy Consumption Reports.

Computes exact metrics for the 7 required report sections from raw Silver observations:
1. Monthly Consumption Overview
2. Average Hourly Consumption Pattern
3. Daily Consumption Trend
4. Weekday vs Weekend Comparison
5. Weekly Consumption Summary
6. Consumption Consistency
7. Electricity Bill Breakdown
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class PeakLowestObservation:
    value_kwh: float
    timestamp_or_date: str
    unit: str = "kWh"


@dataclass(frozen=True)
class HourlyPatternPoint:
    hour: int  # 0 to 23
    hour_label: str  # "00:00", "01:00", ...
    average_kwh: float | None
    valid_days_count: int
    is_peak: bool = False
    is_lowest: bool = False


@dataclass(frozen=True)
class DailyTrendPoint:
    date_str: str  # "YYYY-MM-DD"
    day_number: int  # 1 to 31
    total_kwh: float
    readings_count: int
    is_complete: bool  # 24 readings
    is_peak: bool = False
    is_lowest: bool = False


@dataclass(frozen=True)
class WeekdayWeekendMetric:
    total_kwh: float
    avg_daily_kwh: float
    peak_daily_kwh: float
    peak_date: str | None
    days_count: int


@dataclass(frozen=True)
class WeekdayWeekendComparison:
    weekday: WeekdayWeekendMetric
    weekend: WeekdayWeekendMetric
    diff_pct: float | None  # percentage difference between weekend and weekday daily average


@dataclass(frozen=True)
class CalendarWeekSummary:
    week_index: int  # 1..5
    week_label: str  # "Week 1", "Week 2", ...
    start_date: str
    end_date: str
    days_count: int
    is_partial: bool
    total_kwh: float
    avg_daily_kwh: float


@dataclass(frozen=True)
class ConsistencyMetrics:
    mean_daily_kwh: float
    std_dev_daily_kwh: float
    cv_percent: float  # (std_dev / mean) * 100
    variability_range_kwh: float  # max - min daily
    variability_category: str  # "Low", "Moderate", "High"
    explanations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BillBreakdown:
    total_consumption_kwh: float
    tariff_inr_per_kwh: float | None
    energy_charges_inr: float | None
    fixed_charges_inr: float | None
    taxes_and_surcharges_inr: float | None
    estimated_total_bill_inr: float | None
    is_available: bool
    tariff_notes: str


@dataclass(frozen=True)
class MonthlyConsumptionAnalysis:
    # Identifiers & Metadata
    entity_id: str | int | None
    persona: str
    period_start: str
    period_end: str
    unit: str
    observation_count: int
    days_returned: int

    # Section 1: Monthly Consumption Overview
    total_monthly_kwh: float
    avg_daily_kwh: float
    peak_hourly: PeakLowestObservation | None
    lowest_hourly: PeakLowestObservation | None
    peak_daily: PeakLowestObservation
    lowest_daily: PeakLowestObservation
    estimated_monthly_bill_inr: float | None

    # Section 2: Average Hourly Consumption Pattern
    hourly_pattern: list[HourlyPatternPoint]
    peak_hour: HourlyPatternPoint | None
    lowest_hour: HourlyPatternPoint | None

    # Section 3: Daily Consumption Trend
    daily_trend: list[DailyTrendPoint]
    highest_day: DailyTrendPoint
    lowest_day: DailyTrendPoint

    # Section 4: Weekday vs Weekend Comparison
    weekday_weekend: WeekdayWeekendComparison

    # Section 5: Weekly Consumption Summary
    weekly_summary: list[CalendarWeekSummary]

    # Section 6: Consumption Consistency
    consistency: ConsistencyMetrics

    # Section 7: Electricity Bill Breakdown
    bill: BillBreakdown


def _parse_timestamp(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        # Handle 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS'
        val = val.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val.split(".")[0], fmt)
            except ValueError:
                continue
    return None


def is_consumption_report(data: Any) -> bool:
    """Check whether a given dataset represents a monthly consumption report."""
    if not isinstance(data, dict):
        return False
    has_daily = "dailyConsumption" in data and isinstance(data["dailyConsumption"], list)
    has_hourly = "hourlyReadings" in data and isinstance(data["hourlyReadings"], list)
    has_period = "period" in data and isinstance(data["period"], dict)
    persona = data.get("persona") in {"household", "commercial", "residential"}
    return (has_daily or has_hourly) and (has_period or persona)


class ConsumptionReportCalculator:
    """Performs deterministic calculations for all seven sections of the report."""

    @classmethod
    def calculate(cls, data: dict[str, Any]) -> MonthlyConsumptionAnalysis:
        entity_id = data.get("entityId")
        persona = str(data.get("persona", "household")).casefold()
        period = data.get("period", {})
        period_start = str(period.get("start", ""))
        period_end = str(period.get("end", ""))
        unit = str(data.get("unit", "kWh"))

        # 1. Parse and deduplicate hourly readings
        raw_hourly = data.get("hourlyReadings") or []
        seen_timestamps: set[str] = set()
        valid_hourly: list[tuple[datetime, float]] = []

        for item in raw_hourly:
            if not isinstance(item, dict):
                continue
            ts = _parse_timestamp(item.get("timestamp"))
            val = item.get("consumptionKwh", item.get("normalized_building_energy_kwh", item.get("kwh")))
            if ts is None or val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
                continue
            fval = float(val)
            if not math.isfinite(fval) or fval < 0:
                continue
            ts_key = ts.isoformat()
            if ts_key in seen_timestamps:
                continue  # deduplicate
            seen_timestamps.add(ts_key)
            valid_hourly.append((ts, fval))

        # Sort hourly readings chronologically
        valid_hourly.sort(key=lambda x: x[0])

        # 2. Daily aggregation from hourly (or fallback to provided dailyConsumption)
        hourly_by_day: dict[str, list[float]] = defaultdict(list)
        for ts, kwh in valid_hourly:
            hourly_by_day[ts.date().isoformat()].append(kwh)

        daily_trend: list[DailyTrendPoint] = []
        raw_daily = data.get("dailyConsumption") or []

        if hourly_by_day:
            # Reconstruct daily from hourly readings for 100% mathematical consistency
            sorted_day_keys = sorted(hourly_by_day.keys())
            for idx, day_str in enumerate(sorted_day_keys, 1):
                readings = hourly_by_day[day_str]
                day_total = sum(readings)
                day_num = int(day_str.split("-")[-1])
                daily_trend.append(
                    DailyTrendPoint(
                        date_str=day_str,
                        day_number=day_num,
                        total_kwh=round(day_total, 3),
                        readings_count=len(readings),
                        is_complete=(len(readings) >= 24),
                    )
                )
        elif raw_daily:
            # Fallback to pre-aggregated daily records if hourly not supplied
            for idx, item in enumerate(raw_daily, 1):
                if not isinstance(item, dict):
                    continue
                day_str = str(item.get("date", ""))
                val = item.get("totalConsumptionKwh", item.get("kwh", item.get("total_kwh", 0.0)))
                fval = float(val) if val is not None and math.isfinite(float(val)) else 0.0
                day_num = int(day_str.split("-")[-1]) if "-" in day_str else idx
                daily_trend.append(
                    DailyTrendPoint(
                        date_str=day_str,
                        day_number=day_num,
                        total_kwh=round(fval, 3),
                        readings_count=int(item.get("readingCount", item.get("observationCount", 24))),
                        is_complete=bool(item.get("readingCount", item.get("observationCount", 24)) >= 24),
                    )
                )

        if not daily_trend:
            raise ValueError("No valid consumption observations found in input data.")

        # Ensure period_start and period_end match data if missing
        if not period_start:
            period_start = daily_trend[0].date_str
        if not period_end:
            period_end = daily_trend[-1].date_str

        # Section 1: Overview calculations
        total_monthly_kwh = round(sum(d.total_kwh for d in daily_trend), 3)
        days_returned = len(daily_trend)
        avg_daily_kwh = round(total_monthly_kwh / days_returned, 3) if days_returned > 0 else 0.0

        # Hourly peak and lowest (clearly distinguished)
        peak_hourly: PeakLowestObservation | None = None
        lowest_hourly: PeakLowestObservation | None = None
        if valid_hourly:
            peak_reading = max(valid_hourly, key=lambda x: x[1])
            lowest_reading = min(valid_hourly, key=lambda x: x[1])
            peak_hourly = PeakLowestObservation(
                value_kwh=round(peak_reading[1], 4),
                timestamp_or_date=peak_reading[0].strftime("%Y-%m-%d %H:%M"),
            )
            lowest_hourly = PeakLowestObservation(
                value_kwh=round(lowest_reading[1], 4),
                timestamp_or_date=lowest_reading[0].strftime("%Y-%m-%d %H:%M"),
            )

        # Daily peak and lowest
        max_day = max(daily_trend, key=lambda d: d.total_kwh)
        min_day = min(daily_trend, key=lambda d: d.total_kwh)
        peak_daily = PeakLowestObservation(value_kwh=max_day.total_kwh, timestamp_or_date=max_day.date_str)
        lowest_daily = PeakLowestObservation(value_kwh=min_day.total_kwh, timestamp_or_date=min_day.date_str)

        # Mark peak and lowest in daily trend
        daily_trend_marked: list[DailyTrendPoint] = []
        for d in daily_trend:
            daily_trend_marked.append(
                DailyTrendPoint(
                    date_str=d.date_str,
                    day_number=d.day_number,
                    total_kwh=d.total_kwh,
                    readings_count=d.readings_count,
                    is_complete=d.is_complete,
                    is_peak=(d.date_str == max_day.date_str),
                    is_lowest=(d.date_str == min_day.date_str),
                )
            )
        daily_trend = daily_trend_marked
        highest_day = next(d for d in daily_trend if d.is_peak)
        lowest_day = next(d for d in daily_trend if d.is_lowest)

        # Section 2: Average Hourly Consumption Pattern (0..23)
        hourly_pattern: list[HourlyPatternPoint] = []
        hourly_sums: dict[int, list[float]] = defaultdict(list)
        for ts, kwh in valid_hourly:
            hourly_sums[ts.hour].append(kwh)

        valid_pattern_points: list[HourlyPatternPoint] = []
        for h in range(24):
            hour_readings = hourly_sums.get(h, [])
            valid_days = len(hour_readings)
            avg_h = round(sum(hour_readings) / valid_days, 4) if valid_days > 0 else None
            point = HourlyPatternPoint(
                hour=h,
                hour_label=f"{h:02d}:00",
                average_kwh=avg_h,
                valid_days_count=valid_days,
            )
            hourly_pattern.append(point)
            if avg_h is not None:
                valid_pattern_points.append(point)

        peak_hour: HourlyPatternPoint | None = None
        lowest_hour: HourlyPatternPoint | None = None
        if valid_pattern_points:
            p_max = max(valid_pattern_points, key=lambda p: p.average_kwh or 0.0)
            p_min = min(valid_pattern_points, key=lambda p: p.average_kwh or 0.0)
            # Re-create pattern with peak/lowest flags
            hourly_pattern = [
                HourlyPatternPoint(
                    hour=p.hour,
                    hour_label=p.hour_label,
                    average_kwh=p.average_kwh,
                    valid_days_count=p.valid_days_count,
                    is_peak=(p.hour == p_max.hour),
                    is_lowest=(p.hour == p_min.hour),
                )
                for p in hourly_pattern
            ]
            peak_hour = next((p for p in hourly_pattern if p.is_peak), None)
            lowest_hour = next((p for p in hourly_pattern if p.is_lowest), None)

        # Section 4: Weekday vs Weekend Comparison
        weekday_days: list[DailyTrendPoint] = []
        weekend_days: list[DailyTrendPoint] = []
        for d in daily_trend:
            try:
                dt = date.fromisoformat(d.date_str)
                if dt.weekday() < 5:  # 0=Monday, 4=Friday
                    weekday_days.append(d)
                else:  # 5=Saturday, 6=Sunday
                    weekend_days.append(d)
            except ValueError:
                weekday_days.append(d)

        wd_total = sum(d.total_kwh for d in weekday_days)
        wd_count = len(weekday_days)
        wd_avg = round(wd_total / wd_count, 3) if wd_count > 0 else 0.0
        wd_peak_pt = max(weekday_days, key=lambda d: d.total_kwh) if weekday_days else None
        wd_metric = WeekdayWeekendMetric(
            total_kwh=round(wd_total, 3),
            avg_daily_kwh=wd_avg,
            peak_daily_kwh=wd_peak_pt.total_kwh if wd_peak_pt else 0.0,
            peak_date=wd_peak_pt.date_str if wd_peak_pt else None,
            days_count=wd_count,
        )

        we_total = sum(d.total_kwh for d in weekend_days)
        we_count = len(weekend_days)
        we_avg = round(we_total / we_count, 3) if we_count > 0 else 0.0
        we_peak_pt = max(weekend_days, key=lambda d: d.total_kwh) if weekend_days else None
        we_metric = WeekdayWeekendMetric(
            total_kwh=round(we_total, 3),
            avg_daily_kwh=we_avg,
            peak_daily_kwh=we_peak_pt.total_kwh if we_peak_pt else 0.0,
            peak_date=we_peak_pt.date_str if we_peak_pt else None,
            days_count=we_count,
        )

        diff_pct: float | None = None
        if wd_avg > 0:
            diff_pct = round(((we_avg - wd_avg) / wd_avg) * 100.0, 2)

        weekday_weekend = WeekdayWeekendComparison(
            weekday=wd_metric,
            weekend=we_metric,
            diff_pct=diff_pct,
        )

        # Section 5: Weekly Consumption Summary (Calendar Weeks)
        # Groups days into calendar weeks ending on Sunday (or month end)
        weekly_summary: list[CalendarWeekSummary] = []
        current_week_days: list[DailyTrendPoint] = []
        week_idx = 1

        for d in daily_trend:
            current_week_days.append(d)
            dt = date.fromisoformat(d.date_str) if "-" in d.date_str else None
            # Week boundary: Sunday (weekday == 6) or end of month
            is_sunday = dt is not None and dt.weekday() == 6
            is_month_end = d == daily_trend[-1]

            if is_sunday or is_month_end:
                w_count = len(current_week_days)
                w_total = sum(item.total_kwh for item in current_week_days)
                w_avg = round(w_total / w_count, 3) if w_count > 0 else 0.0
                weekly_summary.append(
                    CalendarWeekSummary(
                        week_index=week_idx,
                        week_label=f"Week {week_idx}",
                        start_date=current_week_days[0].date_str,
                        end_date=current_week_days[-1].date_str,
                        days_count=w_count,
                        is_partial=(w_count < 7),
                        total_kwh=round(w_total, 3),
                        avg_daily_kwh=w_avg,
                    )
                )
                current_week_days = []
                week_idx += 1

        # Section 6: Consumption Consistency
        daily_values = [d.total_kwh for d in daily_trend]
        mean_daily = statistics.mean(daily_values)
        std_dev = statistics.stdev(daily_values) if len(daily_values) > 1 else 0.0
        cv_pct = round((std_dev / mean_daily) * 100.0, 2) if mean_daily > 0 else 0.0
        var_range = round(max(daily_values) - min(daily_values), 3)

        if cv_pct < 15.0:
            var_category = "Low Variability"
        elif cv_pct <= 30.0:
            var_category = "Moderate Variability"
        else:
            var_category = "High Variability"

        consistency = ConsistencyMetrics(
            mean_daily_kwh=round(mean_daily, 3),
            std_dev_daily_kwh=round(std_dev, 3),
            cv_percent=cv_pct,
            variability_range_kwh=var_range,
            variability_category=var_category,
            explanations=[
                "Mean Daily Consumption represents the average energy usage per day over the reporting period.",
                "Standard Deviation measures how much daily consumption deviates from the monthly average. Lower values signify steady routines.",
                "Coefficient of Variation (CV) expresses standard deviation as a percentage of the mean (CV = std_dev / mean × 100%), allowing scale-independent comparison across billing cycles.",
                "Consumption Range shows the span between the single highest and lowest daily consumption during the month.",
            ],
        )

        # Section 7: Electricity Bill Breakdown
        tariff_inr = data.get("tariffInrPerKwh")
        if tariff_inr is not None and isinstance(tariff_inr, (int, float)) and math.isfinite(float(tariff_inr)):
            rate = float(tariff_inr)
            energy_charges = round(total_monthly_kwh * rate, 2)
            fixed_charges = 0.0
            taxes_and_fees = 0.0
            estimated_bill = round(energy_charges + fixed_charges + taxes_and_fees, 2)
            bill = BillBreakdown(
                total_consumption_kwh=total_monthly_kwh,
                tariff_inr_per_kwh=rate,
                energy_charges_inr=energy_charges,
                fixed_charges_inr=fixed_charges,
                taxes_and_surcharges_inr=taxes_and_fees,
                estimated_total_bill_inr=estimated_bill,
                is_available=True,
                tariff_notes=(
                    f"Estimated bill calculated using the configured tariff rate of ₹{rate:.2f}/kWh. "
                    "The source dataset does not include customer-specific slab structures, fixed monthly charges, "
                    "or applicable regulatory taxes. This estimate is provided for budgetary guidance only."
                ),
            )
            estimated_monthly_bill_inr = estimated_bill
        else:
            bill = BillBreakdown(
                total_consumption_kwh=total_monthly_kwh,
                tariff_inr_per_kwh=None,
                energy_charges_inr=None,
                fixed_charges_inr=None,
                taxes_and_surcharges_inr=None,
                estimated_total_bill_inr=None,
                is_available=False,
                tariff_notes="An accurate electricity bill cannot be calculated because no tariff configuration or billing data is available for this consumer.",
            )
            estimated_monthly_bill_inr = None

        obs_count = len(valid_hourly) if valid_hourly else sum(d.readings_count for d in daily_trend)

        return MonthlyConsumptionAnalysis(
            entity_id=entity_id,
            persona=persona,
            period_start=period_start,
            period_end=period_end,
            unit=unit,
            observation_count=obs_count,
            days_returned=days_returned,
            total_monthly_kwh=total_monthly_kwh,
            avg_daily_kwh=avg_daily_kwh,
            peak_hourly=peak_hourly,
            lowest_hourly=lowest_hourly,
            peak_daily=peak_daily,
            lowest_daily=lowest_daily,
            estimated_monthly_bill_inr=estimated_monthly_bill_inr,
            hourly_pattern=hourly_pattern,
            peak_hour=peak_hour,
            lowest_hour=lowest_hour,
            daily_trend=daily_trend,
            highest_day=highest_day,
            lowest_day=lowest_day,
            weekday_weekend=weekday_weekend,
            weekly_summary=weekly_summary,
            consistency=consistency,
            bill=bill,
        )

