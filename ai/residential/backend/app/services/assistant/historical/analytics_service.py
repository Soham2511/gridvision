"""Historical Analytics Service for GridVision Residential Assistant.

Performs deterministic, mathematically grounded aggregations and statistical analysis
over the entire available historical consumption record for an authorized household.
Separates data retrieval from calculation logic for maximum reusability.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DailyConsumptionRecord:
    """Aggregated daily consumption measurement."""

    date_str: str  # YYYY-MM-DD
    year: int
    month: int
    day: int
    total_kwh: float
    observed_intervals: int
    expected_intervals: int
    completeness_pct: float
    is_complete_day: bool


class HistoricalAnalyticsService:
    """Pure analytics engine for long-term household energy consumption patterns."""

    @staticmethod
    def aggregate_daily_consumption(
        observations: list[dict[str, Any]],
        expected_intervals_per_day: int = 24,
    ) -> list[DailyConsumptionRecord]:
        """Aggregate interval observations into daily consumption records.

        Handles:
        - Duplicate timestamps (deduplicated by keeping unique or averaging)
        - Invalid / negative readings (filtered out)
        - Actual vs predicted separation (predicted discarded)
        - Missing observations (never treated as zero consumption)
        """
        if not observations:
            return []

        # Convert to pandas DataFrame for vectorized cleansing
        rows = []
        for obs in observations:
            if obs.get("is_predicted", False):
                continue

            ts = obs.get("timestamp")
            val = obs.get("consumption_kwh")

            if ts is None or val is None:
                continue

            try:
                val_float = float(val)
                if math.isnan(val_float) or math.isinf(val_float) or val_float < 0:
                    continue
            except (ValueError, TypeError):
                continue

            if isinstance(ts, str):
                try:
                    ts_dt = pd.to_datetime(ts).to_pydatetime()
                except Exception:
                    continue
            elif hasattr(ts, "to_pydatetime"):
                ts_dt = ts.to_pydatetime()
            elif isinstance(ts, datetime):
                ts_dt = ts
            else:
                continue

            rows.append({"timestamp": ts_dt, "kwh": val_float})

        if not rows:
            return []

        df = pd.DataFrame(rows)
        # Deduplicate exact timestamps
        df = df.drop_duplicates(subset=["timestamp"], keep="last")
        df["date"] = df["timestamp"].dt.date

        daily_records: list[DailyConsumptionRecord] = []
        grouped = df.groupby("date")

        for dt_val, group in sorted(grouped, key=lambda x: x[0]):
            count = len(group)
            total_kwh = float(group["kwh"].sum())
            completeness = round((count / expected_intervals_per_day) * 100, 1) if expected_intervals_per_day > 0 else 100.0
            # A day is considered complete if it has >= 75% expected intervals (e.g. 18 of 24 hours)
            is_complete = completeness >= 75.0

            daily_records.append(
                DailyConsumptionRecord(
                    date_str=dt_val.strftime("%Y-%m-%d"),
                    year=dt_val.year,
                    month=dt_val.month,
                    day=dt_val.day,
                    total_kwh=round(total_kwh, 2),
                    observed_intervals=count,
                    expected_intervals=expected_intervals_per_day,
                    completeness_pct=min(completeness, 100.0),
                    is_complete_day=is_complete,
                )
            )

        return daily_records

    @staticmethod
    def calculate_all_time_summary(
        daily_records: list[DailyConsumptionRecord],
    ) -> dict[str, Any]:
        """Compute all-time statistical metrics across observed days."""
        if not daily_records:
            return {
                "totalConsumptionKwh": None,
                "averageDailyConsumptionKwh": None,
                "medianDailyConsumptionKwh": None,
                "p90DailyConsumptionKwh": None,
                "highestConsumptionDay": None,
                "lowestConsumptionDay": None,
                "validObservationDays": 0,
            }

        kwh_values = [r.total_kwh for r in daily_records]
        total_kwh = round(float(sum(kwh_values)), 2)
        avg_kwh = round(float(np.mean(kwh_values)), 2)
        med_kwh = round(float(np.median(kwh_values)), 2)
        p90_kwh = round(float(np.percentile(kwh_values, 90)), 2)

        highest_record = max(daily_records, key=lambda r: r.total_kwh)
        lowest_record = min(daily_records, key=lambda r: r.total_kwh)

        return {
            "totalConsumptionKwh": total_kwh,
            "averageDailyConsumptionKwh": avg_kwh,
            "medianDailyConsumptionKwh": med_kwh,
            "p90DailyConsumptionKwh": p90_kwh,
            "highestConsumptionDay": {
                "date": highest_record.date_str,
                "consumptionKwh": highest_record.total_kwh,
            },
            "lowestConsumptionDay": {
                "date": lowest_record.date_str,
                "consumptionKwh": lowest_record.total_kwh,
            },
            "validObservationDays": len(daily_records),
        }

    @staticmethod
    def calculate_yearly_trends(
        daily_records: list[DailyConsumptionRecord],
    ) -> list[dict[str, Any]]:
        """Calculate yearly totals, daily averages, and valid year-over-year changes."""
        if not daily_records:
            return []

        years_map: dict[int, list[DailyConsumptionRecord]] = {}
        for r in daily_records:
            years_map.setdefault(r.year, []).append(r)

        yearly_results: list[dict[str, Any]] = []
        sorted_years = sorted(years_map.keys())

        for idx, yr in enumerate(sorted_years):
            records = years_map[yr]
            kwh_vals = [r.total_kwh for r in records]
            total_yr_kwh = round(float(sum(kwh_vals)), 2)
            avg_daily_kwh = round(float(np.mean(kwh_vals)), 2)

            # Determine days in year (leap year aware)
            days_in_yr = 366 if calendar.isleap(yr) else 365
            obs_days = len(records)
            completeness = round((obs_days / days_in_yr) * 100, 1)
            is_complete = obs_days >= 330 or completeness >= 90.0

            # Find peak month in this year
            month_sums: dict[str, float] = {}
            for r in records:
                m_key = f"{yr}-{r.month:02d}"
                month_sums[m_key] = month_sums.get(m_key, 0.0) + r.total_kwh
            peak_month = max(month_sums.items(), key=lambda x: x[1])[0] if month_sums else None

            # Calculate year-over-year change ONLY for comparable valid periods
            yoy_change_pct = None
            if idx > 0:
                prev_yr = sorted_years[idx - 1]
                if prev_yr == yr - 1:
                    prev_records = years_map[prev_yr]
                    prev_days_in_yr = 366 if calendar.isleap(prev_yr) else 365
                    prev_completeness = (len(prev_records) / prev_days_in_yr) * 100
                    prev_is_complete = len(prev_records) >= 330 or prev_completeness >= 90.0

                    # Only compare if both are complete, OR if both have comparable day counts
                    if (is_complete and prev_is_complete) or abs(len(records) - len(prev_records)) <= 15:
                        prev_total = sum(r.total_kwh for r in prev_records)
                        if prev_total > 0:
                            yoy_change_pct = round(((total_yr_kwh - prev_total) / prev_total) * 100, 1)

            yearly_results.append({
                "year": yr,
                "totalConsumptionKwh": total_yr_kwh,
                "averageDailyConsumptionKwh": avg_daily_kwh,
                "highestConsumptionMonth": peak_month,
                "validObservationCount": obs_days,
                "dataCompletenessPct": completeness,
                "isCompletePeriod": is_complete,
                "yearOverYearChangePct": yoy_change_pct,
            })

        return yearly_results

    @staticmethod
    def calculate_monthly_timeline(
        daily_records: list[DailyConsumptionRecord],
    ) -> list[dict[str, Any]]:
        """Generate chronological monthly timeline across entire historical span."""
        if not daily_records:
            return []

        months_map: dict[str, list[DailyConsumptionRecord]] = {}
        for r in daily_records:
            m_key = f"{r.year}-{r.month:02d}"
            months_map.setdefault(m_key, []).append(r)

        monthly_timeline: list[dict[str, Any]] = []

        for m_key in sorted(months_map.keys()):
            records = months_map[m_key]
            yr, mo = (int(p) for p in m_key.split("-"))
            _, expected_days = calendar.monthrange(yr, mo)
            observed_days = len(records)
            kwh_vals = [r.total_kwh for r in records]
            total_kwh = round(float(sum(kwh_vals)), 2)
            avg_daily_kwh = round(float(np.mean(kwh_vals)), 2)
            completeness = round((observed_days / expected_days) * 100, 1)
            is_complete = completeness >= 90.0

            monthly_timeline.append({
                "month": m_key,
                "totalConsumptionKwh": total_kwh,
                "averageDailyConsumptionKwh": avg_daily_kwh,
                "observedDayCount": observed_days,
                "expectedDayCount": expected_days,
                "completenessPct": completeness,
                "isCompletePeriod": is_complete,
            })

        return monthly_timeline

    @staticmethod
    def calculate_seasonality(
        daily_records: list[DailyConsumptionRecord],
    ) -> list[dict[str, Any]]:
        """Calculate monthly seasonality patterns across all available years (Jan-Dec)."""
        month_records: dict[int, list[DailyConsumptionRecord]] = {m: [] for m in range(1, 13)}
        for r in daily_records:
            month_records[r.month].append(r)

        seasonality_list: list[dict[str, Any]] = []
        for mo in range(1, 13):
            records = month_records[mo]
            month_name = calendar.month_name[mo]

            if not records:
                seasonality_list.append({
                    "monthIndex": mo,
                    "monthName": month_name,
                    "averageDailyConsumptionKwh": None,
                    "medianDailyConsumptionKwh": None,
                    "yearsObservedCount": 0,
                    "validObservationCount": 0,
                    "completenessPct": 0.0,
                    "isEstablishedPattern": False,
                })
                continue

            kwh_vals = [r.total_kwh for r in records]
            distinct_years = len(set(r.year for r in records))
            avg_daily = round(float(np.mean(kwh_vals)), 2)
            med_daily = round(float(np.median(kwh_vals)), 2)
            obs_count = len(records)
            # A pattern is considered established only if multiple years of observations exist
            is_established = distinct_years >= 2 and obs_count >= 50

            seasonality_list.append({
                "monthIndex": mo,
                "monthName": month_name,
                "averageDailyConsumptionKwh": avg_daily,
                "medianDailyConsumptionKwh": med_daily,
                "yearsObservedCount": distinct_years,
                "validObservationCount": obs_count,
                "completenessPct": 100.0 if obs_count >= 28 * distinct_years else round((obs_count / (30 * distinct_years)) * 100, 1),
                "isEstablishedPattern": is_established,
            })

        return seasonality_list

    @staticmethod
    def calculate_historical_extremes(
        monthly_timeline: list[dict[str, Any]],
        yearly_trends: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute highest/lowest consumption periods and valid annual step changes."""
        if not monthly_timeline:
            return {
                "topConsumptionMonths": [],
                "highestConsumptionYear": None,
                "largestAnnualIncrease": None,
                "largestAnnualDecrease": None,
            }

        # Top 5 highest months by total consumption
        sorted_months = sorted(
            monthly_timeline,
            key=lambda m: m["totalConsumptionKwh"],
            reverse=True,
        )
        top_months = [
            {
                "month": m["month"],
                "consumptionKwh": m["totalConsumptionKwh"],
                "averageDailyKwh": m["averageDailyConsumptionKwh"],
            }
            for m in sorted_months[:5]
        ]

        # Highest consumption year
        highest_year = None
        if yearly_trends:
            best_yr = max(yearly_trends, key=lambda y: y["totalConsumptionKwh"])
            highest_year = {
                "year": best_yr["year"],
                "totalConsumptionKwh": best_yr["totalConsumptionKwh"],
            }

        # Largest annual increase and decrease
        largest_inc = None
        largest_dec = None

        for idx in range(1, len(yearly_trends)):
            cur = yearly_trends[idx]
            prev = yearly_trends[idx - 1]
            pct = cur.get("yearOverYearChangePct")
            if pct is not None:
                diff_kwh = round(cur["totalConsumptionKwh"] - prev["totalConsumptionKwh"], 2)
                item = {
                    "fromYear": prev["year"],
                    "toYear": cur["year"],
                    "changePct": pct,
                    "changeKwh": diff_kwh,
                }
                if pct > 0:
                    if largest_inc is None or pct > largest_inc["changePct"]:
                        largest_inc = item
                elif pct < 0:
                    if largest_dec is None or pct < largest_dec["changePct"]:
                        largest_dec = item

        return {
            "topConsumptionMonths": top_months,
            "highestConsumptionYear": highest_year,
            "largestAnnualIncrease": largest_inc,
            "largestAnnualDecrease": largest_dec,
        }

    @staticmethod
    def calculate_long_term_behaviour(
        daily_records: list[DailyConsumptionRecord],
        monthly_timeline: list[dict[str, Any]],
        yearly_trends: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Determine long-term consumption trends, variability, and typical range."""
        if not daily_records or len(daily_records) < 30:
            return {
                "overallTrend": "insufficient_data",
                "variability": None,
                "typicalDailyConsumptionRangeKwh": None,
            }

        kwh_vals = [r.total_kwh for r in daily_records]
        mean_val = float(np.mean(kwh_vals))
        std_val = float(np.std(kwh_vals))

        # Variability via Coefficient of Variation (CV = std / mean)
        variability = "insufficient_data"
        if mean_val > 0:
            cv = std_val / mean_val
            if cv < 0.25:
                variability = "low"
            elif cv <= 0.50:
                variability = "moderate"
            else:
                variability = "high"

        # Typical consumption range (10th to 90th percentile)
        p10 = round(float(np.percentile(kwh_vals, 10)), 2)
        p90 = round(float(np.percentile(kwh_vals, 90)), 2)
        typical_range = {"min": p10, "max": p90}

        # Trend determination:
        # If we have 2+ valid yearly trends with YoY changes, use annual direction
        valid_yoy = [y["yearOverYearChangePct"] for y in yearly_trends if y.get("yearOverYearChangePct") is not None]
        if valid_yoy:
            avg_yoy = sum(valid_yoy) / len(valid_yoy)
            if avg_yoy > 5.0:
                overall_trend = "increasing"
            elif avg_yoy < -5.0:
                overall_trend = "decreasing"
            else:
                overall_trend = "stable"
        elif len(monthly_timeline) >= 6:
            # If 6+ months exist within a single year, compare first half to second half
            mid = len(monthly_timeline) // 2
            first_half = [m["averageDailyConsumptionKwh"] for m in monthly_timeline[:mid]]
            second_half = [m["averageDailyConsumptionKwh"] for m in monthly_timeline[mid:]]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)

            if avg_first > 0:
                half_diff_pct = ((avg_second - avg_first) / avg_first) * 100
                if half_diff_pct > 8.0:
                    overall_trend = "increasing"
                elif half_diff_pct < -8.0:
                    overall_trend = "decreasing"
                else:
                    overall_trend = "stable"
            else:
                overall_trend = "insufficient_data"
        else:
            overall_trend = "insufficient_data"

        return {
            "overallTrend": overall_trend,
            "variability": variability,
            "typicalDailyConsumptionRangeKwh": typical_range,
        }

    @staticmethod
    def calculate_coverage_metadata(
        daily_records: list[DailyConsumptionRecord],
        total_observations_count: int,
        data_source: str = "customer_silver_hourly",
    ) -> dict[str, Any]:
        """Compute coverage boundaries, missing periods, and telemetry status."""
        if not daily_records:
            return {
                "startDate": None,
                "endDate": None,
                "dataSource": data_source,
                "dataStatus": "unavailable",
                "observationGranularity": "hourly_interval",
                "validObservationCount": 0,
                "expectedObservationCount": None,
                "completenessPct": 0.0,
                "missingPeriods": [],
            }

        start_date = daily_records[0].date_str
        end_date = daily_records[-1].date_str

        # Calculate expected days between start and end date
        d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        span_days = (d_end - d_start).days + 1
        expected_intervals = span_days * 24

        observed_dates = set(r.date_str for r in daily_records)
        missing_periods: list[dict[str, str]] = []

        # Find continuous missing periods (> 2 consecutive missing days)
        current_gap_start = None
        for i in range(span_days):
            cur_d = d_start + timedelta(days=i)
            cur_str = cur_d.strftime("%Y-%m-%d")
            if cur_str not in observed_dates:
                if current_gap_start is None:
                    current_gap_start = cur_str
            else:
                if current_gap_start is not None:
                    gap_end = (cur_d - timedelta(days=1)).strftime("%Y-%m-%d")
                    missing_periods.append({
                        "gapStart": current_gap_start,
                        "gapEnd": gap_end,
                    })
                    current_gap_start = None

        if current_gap_start is not None:
            missing_periods.append({
                "gapStart": current_gap_start,
                "gapEnd": end_date,
            })

        completeness_pct = (
            round((total_observations_count / expected_intervals) * 100, 1)
            if expected_intervals > 0
            else 0.0
        )

        return {
            "startDate": start_date,
            "endDate": end_date,
            "dataSource": data_source,
            "dataStatus": "recorded_historical",
            "observationGranularity": "hourly_interval",
            "validObservationCount": total_observations_count,
            "expectedObservationCount": expected_intervals,
            "completenessPct": min(completeness_pct, 100.0),
            "missingPeriods": missing_periods,
        }
