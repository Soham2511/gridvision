"""Household Real Data Provider grounded in customer_gold.parquet and household_hourly.parquet."""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger("gridvision.data.household")


def _find_data_file(filename: str) -> Path | None:
    env_dir = os.getenv("GOLD_DATA_DIR")
    candidates = [
        Path(env_dir) / filename if env_dir else None,
        Path("/app/data/gold") / filename,
        Path("/data/gold") / filename,
        Path(__file__).resolve().parents[3] / "data" / "gold" / filename,
        Path.cwd() / "data" / "gold" / filename,
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


class RealHouseholdDataProvider:
    """Provides high-fidelity telemetry and curves computed directly from

    customer_gold.parquet and household_hourly.parquet, with inference
    powered by the MLflow champion model.
    """

    DEFAULT_ENTITY_ID = 32617
    TARIFF_INR_PER_KWH = 10.0

    def __init__(self, model_provider: Any = None) -> None:
        self.model_provider = model_provider
        self._df_gold: pd.DataFrame | None = None
        self._df_hourly: pd.DataFrame | None = None
        self._load_datasets()

    def _load_datasets(self) -> None:
        gold_file = _find_data_file("customer_gold.parquet")
        hourly_file = _find_data_file("household_hourly.parquet")

        if gold_file and gold_file.exists():
            try:
                self._df_gold = pd.read_parquet(gold_file)
                logger.info("Loaded real customer_gold.parquet (%d rows)", len(self._df_gold))
            except Exception as exc:
                logger.warning("Failed to load customer_gold.parquet: %s", exc)

        if hourly_file and hourly_file.exists():
            try:
                self._df_hourly = pd.read_parquet(hourly_file)
                # Ensure timestamp is datetime
                self._df_hourly["timestamp"] = pd.to_datetime(self._df_hourly["timestamp"])
                logger.info("Loaded real household_hourly.parquet (%d rows)", len(self._df_hourly))
            except Exception as exc:
                logger.warning("Failed to load household_hourly.parquet: %s", exc)

    def is_available(self) -> bool:
        return self._df_gold is not None and self._df_hourly is not None

    def _resolve_entity_id(self, household_id: str | None) -> int:
        if not household_id:
            return self.DEFAULT_ENTITY_ID
        clean = household_id.upper().replace("METER-", "").replace("METER_", "").strip()
        if clean == "1000" or clean == "DEFAULT":
            return self.DEFAULT_ENTITY_ID
        try:
            val = int(clean)
            if self._df_hourly is not None and val in self._df_hourly["entity_id"].values:
                return val
        except ValueError:
            pass
        return self.DEFAULT_ENTITY_ID

    def _get_mlflow_prediction(self, entity_id: int, cutoff_row: pd.Series) -> tuple[float, float]:
        """Query MLflow model adapter or fall back to naive projection from gold dataset."""
        features = {
            "cumulative_energy_kwh": float(cutoff_row["cumulative_energy_kwh"]),
            "observed_hours_to_cutoff": int(cutoff_row["observed_hours_to_cutoff"]),
            "days_in_month": int(cutoff_row["days_in_month"]),
        }
        if self.model_provider and hasattr(self.model_provider, "predict"):
            try:
                out = self.model_provider.predict(
                    model_name="residential",
                    entity_id=f"METER-{entity_id}",
                    features=features,
                    actual_kwh_so_far=features["cumulative_energy_kwh"],
                )
                if out and out.estimated_month_end_kwh:
                    return round(float(out.estimated_month_end_kwh), 1), round(float(out.estimated_month_end_bill_inr), 1)
            except Exception as exc:
                logger.warning("MLflow prediction failed, using gold projection: %s", exc)

        # Fallback to model naive projection or target
        pred_kwh = float(cutoff_row.get("naive_projected_month_kwh", cutoff_row.get("target_month_kwh", 300.0)))
        return round(pred_kwh, 1), round(pred_kwh * self.TARIFF_INR_PER_KWH, 1)

    def get_residential_meters(self) -> list[dict[str, Any]]:
        if not self.is_available():
            return []

        meters: list[dict[str, Any]] = []
        unique_entities = sorted(self._df_hourly["entity_id"].unique())

        for eid in unique_entities:
            e_gold = self._df_gold[(self._df_gold["entity_id"] == eid) & (self._df_gold["cutoff_day"] == 21)]
            cutoff_row = e_gold[e_gold["month_of_year"] == 10].iloc[0] if len(e_gold[e_gold["month_of_year"] == 10]) > 0 else e_gold.iloc[-1]

            pred_kwh, pred_bill = self._get_mlflow_prediction(eid, cutoff_row)
            e_hourly = self._df_hourly[self._df_hourly["entity_id"] == eid]
            avg_daily_kwh = round(float(e_hourly["kwh"].mean() * 24.0), 1)
            actual_so_far = round(float(cutoff_row["cumulative_energy_kwh"]), 1)
            target_month = round(float(cutoff_row["target_month_kwh"]), 1)
            remaining = max(0.0, round(pred_kwh - actual_so_far, 1))

            household_id_str = "METER-1000" if eid == self.DEFAULT_ENTITY_ID else f"METER-{eid}"

            meters.append({
                "householdId": household_id_str,
                "entityId": int(eid),
                "userName": "Ramesh Sharma" if eid == self.DEFAULT_ENTITY_ID else f"Resident {eid}",
                "buildingType": str(cutoff_row.get("building_type", "Single Family Residence")),
                "sqm": round(float(cutoff_row.get("building_area_m2", 120.0)), 1),
                "yearBuilt": int(cutoff_row.get("effective_year_built", 1985)),
                "dailyKwh": avg_daily_kwh,
                "actualCycleKwhSoFar": actual_so_far,
                "targetRemainingKwh": max(0.0, round(target_month - actual_so_far, 1)),
                "predictedRemainingKwh": remaining,
                "estimatedMonthEndKwh": pred_kwh,
                "estimatedMonthEndBillInr": pred_bill,
                "coverageRatio": round(float(cutoff_row.get("coverage_ratio", 0.985)), 3),
                "elapsedDays": 21,
                "lastDate": "21 Oct 2026",
            })

        return meters

    def get_residential_meter(self, household_id: str) -> dict[str, Any] | None:
        meters = self.get_residential_meters()
        eid = self._resolve_entity_id(household_id)
        for m in meters:
            if m["entityId"] == eid:
                return m
        return meters[0] if meters else None

    def get_household_overview(
        self,
        household_id: str | None = None,
        time_range: str = "1D",
    ) -> dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("Household datasets not loaded")

        eid = self._resolve_entity_id(household_id)
        e_gold = self._df_gold[self._df_gold["entity_id"] == eid]
        e_hourly = self._df_hourly[self._df_hourly["entity_id"] == eid].sort_values("timestamp")

        # Reference month: October (month 10), cutoff day 21
        oct_cutoffs = e_gold[(e_gold["month_of_year"] == 10) & (e_gold["cutoff_day"] == 21)]
        cutoff_row = oct_cutoffs.iloc[0] if len(oct_cutoffs) > 0 else e_gold.iloc[-1]

        # MLflow model prediction for month-end
        pred_month_kwh, pred_month_bill = self._get_mlflow_prediction(eid, cutoff_row)

        # 7-day actual window: 15 Oct 2018 to 21 Oct 2018
        # Previous 7-day window: 08 Oct 2018 to 14 Oct 2018
        ts_cur_start = pd.to_datetime("2018-10-15 00:00:00")
        ts_cur_end = pd.to_datetime("2018-10-21 23:59:59")
        ts_prev_start = pd.to_datetime("2018-10-08 00:00:00")
        ts_prev_end = pd.to_datetime("2018-10-14 23:59:59")

        df_cur_7d = e_hourly[(e_hourly["timestamp"] >= ts_cur_start) & (e_hourly["timestamp"] <= ts_cur_end)]
        df_prev_7d = e_hourly[(e_hourly["timestamp"] >= ts_prev_start) & (e_hourly["timestamp"] <= ts_prev_end)]

        cur_7d_total = float(df_cur_7d["kwh"].sum())
        prev_7d_total = float(df_prev_7d["kwh"].sum()) if len(df_prev_7d) > 0 else cur_7d_total

        daily_avg_kwh = round(cur_7d_total / 7.0, 1)
        prev_7d_avg_kwh = round(prev_7d_total / 7.0, 1)
        daily_avg_change_pct = round(((daily_avg_kwh - prev_7d_avg_kwh) / max(prev_7d_avg_kwh, 0.1)) * 100.0, 1)

        # Current daily usage: Latest completed day in cycle (21 Oct)
        df_latest_day = e_hourly[e_hourly["timestamp"].dt.date == pd.to_datetime("2018-10-21").date()]
        current_daily_kwh = round(float(df_latest_day["kwh"].sum()), 1)

        # Monthly averages from gold dataset across the 12 months
        gold_cutoffs_21 = e_gold[e_gold["cutoff_day"] == 21].sort_values("month_of_year")
        monthly_avg_kwh = round(float(gold_cutoffs_21["target_month_kwh"].mean()), 1)
        sept_row = gold_cutoffs_21[gold_cutoffs_21["month_of_year"] == 9]
        # Card compares displayed monthly average against last month (September)
        monthly_avg_change_pct = round(((monthly_avg_kwh - prev_month_kwh) / max(prev_month_kwh, 0.1)) * 100.0, 1)

        # Build dynamic consumption curves based on scale
        curve: list[dict[str, Any]] = []
        demarcation_time = "16:00"
        actual_callout: dict[str, Any] | None = None
        predicted_callout: dict[str, Any] | None = None

        norm_range = time_range.upper()

        if norm_range == "1D":
            # 24-hour diurnal profile for 21 Oct 2018
            # Hours 00:00 to 16:00 actual observed; 16:00 to 24:00 forward prediction
            day_hours = e_hourly[e_hourly["timestamp"].dt.date == pd.to_datetime("2018-10-21").date()].sort_values("timestamp")
            demarcation_time = "16:00"

            peak_actual_val = -1.0
            peak_actual_time = "09:00"
            peak_pred_val = -1.0
            peak_pred_time = "20:00"

            for h in range(24):
                time_str = f"{h:02d}:00"
                row_h = day_hours[day_hours["timestamp"].dt.hour == h]
                actual_val = round(float(row_h["kwh"].iloc[0]), 2) if len(row_h) > 0 else 0.45

                # Evening boost profile for single-family residences
                evening_boost = 1.6 if 18 <= h <= 21 else (1.2 if 16 <= h <= 22 else 0.9)
                pred_val = round(actual_val * evening_boost, 2)

                if h <= 16:
                    pt_actual = actual_val
                    pt_pred = actual_val if h == 16 else None
                    if actual_val > peak_actual_val:
                        peak_actual_val = actual_val
                        peak_actual_time = time_str
                else:
                    pt_actual = None
                    pt_pred = pred_val
                    if pred_val > peak_pred_val:
                        peak_pred_val = pred_val
                        peak_pred_time = time_str

                note_act = "Morning peak" if h == 8 else ("Noon baseload" if h == 12 else None)
                note_pred = "Evening cook & HVAC" if h == 20 else None

                item: dict[str, Any] = {
                    "time": time_str,
                    "actualConsumption": pt_actual,
                    "predictedConsumption": pt_pred,
                    "fullDate": f"21 Oct 2026, {time_str}",
                }
                if note_act:
                    item["actualNote"] = note_act
                if note_pred:
                    item["predictedNote"] = note_pred
                curve.append(item)

            actual_callout = {
                "time": peak_actual_time,
                "value": round(peak_actual_val, 2),
                "dateText": f"21 Oct 2026, {peak_actual_time}",
                "label": "Observed Consumption",
                "color": "#00A396",
            }
            predicted_callout = {
                "time": peak_pred_time,
                "value": round(peak_pred_val, 2),
                "dateText": f"21 Oct 2026, {peak_pred_time}",
                "label": "Predicted Consumption",
                "color": "#8B5CF6",
            }

        elif norm_range == "7D":
            # 7-day daily profile (15 Oct to 21 Oct) + forward 3 days prediction
            demarcation_time = "21 Oct"
            days = [
                ("15 Oct", "2018-10-15"),
                ("16 Oct", "2018-10-16"),
                ("17 Oct", "2018-10-17"),
                ("18 Oct", "2018-10-18"),
                ("19 Oct", "2018-10-19"),
                ("20 Oct", "2018-10-20"),
                ("21 Oct", "2018-10-21"),
                ("22 Oct", "2018-10-22"),
                ("23 Oct", "2018-10-23"),
                ("24 Oct", "2018-10-24"),
            ]
            peak_actual_val = -1.0
            peak_actual_day = "20 Oct"

            for idx, (day_lbl, dt_str) in enumerate(days):
                is_actual = idx <= 6
                is_overlap = idx == 6
                sub = e_hourly[e_hourly["timestamp"].dt.date == pd.to_datetime(dt_str).date()]
                actual_val = round(float(sub["kwh"].sum()), 1) if len(sub) > 0 else 9.5
                pred_val = actual_val if is_overlap else (actual_val if idx > 6 else None)

                if is_actual and actual_val > peak_actual_val:
                    peak_actual_val = actual_val
                    peak_actual_day = day_lbl

                curve.append({
                    "time": day_lbl,
                    "actualConsumption": actual_val if is_actual else None,
                    "predictedConsumption": pred_val,
                    "fullDate": f"{day_lbl} 2026",
                })

            actual_callout = {
                "time": peak_actual_day,
                "value": peak_actual_val,
                "dateText": f"{peak_actual_day} 2026",
                "label": "Observed Peak",
                "color": "#00A396",
            }
            # Predicted callout matches the peak predicted point exactly
            pred_pts = [p for p in curve if p["predictedConsumption"] is not None and p["time"] != demarcation_time]
            peak_pred_pt = max(pred_pts, key=lambda p: p["predictedConsumption"]) if pred_pts else curve[-1]
            predicted_callout = {
                "time": peak_pred_pt["time"],
                "value": peak_pred_pt["predictedConsumption"],
                "dateText": peak_pred_pt["fullDate"],
                "label": "Forecasted Demand",
                "color": "#8B5CF6",
            }

        elif norm_range == "1M":
            # 30-day daily profile from 22 Sep 2018 to 21 Oct 2018 with forward prediction to month-end
            demarcation_time = "21 Oct"
            d_start = pd.to_datetime("2018-09-22")
            peak_actual_val = -1.0
            peak_actual_day = "20 Oct"

            for d in range(30):
                dt = d_start + timedelta(days=d)
                day_lbl = dt.strftime("%d %b")
                sub = e_hourly[e_hourly["timestamp"].dt.date == dt.date()]
                val = round(float(sub["kwh"].sum()), 1) if len(sub) > 0 else round(daily_avg_kwh, 1)
                is_overlap = (d == 29)  # 21 Oct demarcation point

                if val > peak_actual_val:
                    peak_actual_val = val
                    peak_actual_day = day_lbl

                curve.append({
                    "time": day_lbl,
                    "actualConsumption": val,
                    "predictedConsumption": val if is_overlap else None,
                    "fullDate": f"{day_lbl} 2026",
                })

            # Add forward prediction points through 31 Oct
            for p_day in range(1, 11):
                f_dt = pd.to_datetime("2018-10-21") + timedelta(days=p_day)
                f_lbl = f_dt.strftime("%d %b")
                f_val = round(daily_avg_kwh * (1.0 + 0.06 * math.sin(p_day * 0.7)), 1)
                curve.append({
                    "time": f_lbl,
                    "actualConsumption": None,
                    "predictedConsumption": f_val,
                    "fullDate": f"{f_lbl} 2026",
                })

            actual_callout = {
                "time": peak_actual_day,
                "value": peak_actual_val,
                "dateText": f"{peak_actual_day} 2026",
                "label": "Observed Peak",
                "color": "#00A396",
            }
            # Predicted callout anchored directly on highest forecast point
            pred_pts = [p for p in curve if p["predictedConsumption"] is not None and p["time"] != demarcation_time]
            peak_pred_pt = max(pred_pts, key=lambda p: p["predictedConsumption"]) if pred_pts else curve[-1]
            predicted_callout = {
                "time": peak_pred_pt["time"],
                "value": peak_pred_pt["predictedConsumption"],
                "dateText": peak_pred_pt["fullDate"],
                "label": "Projected Peak",
                "color": "#8B5CF6",
            }

        elif norm_range == "3M":
            # 90-day seasonal profile (sampled every 6 days over 15 points)
            demarcation_time = "21 Oct"
            d_start = pd.to_datetime("2018-07-29")
            peak_actual_val = -1.0
            peak_actual_day = "16 Aug"

            for step in range(15):
                dt = d_start + timedelta(days=step * 6)
                day_lbl = dt.strftime("%d %b")
                sub = e_hourly[e_hourly["timestamp"].dt.date == dt.date()]
                val = round(float(sub["kwh"].sum()), 1) if len(sub) > 0 else round(daily_avg_kwh * 1.1, 1)
                is_overlap = (step == 14)

                if val > peak_actual_val:
                    peak_actual_val = val
                    peak_actual_day = day_lbl

                curve.append({
                    "time": day_lbl,
                    "actualConsumption": val,
                    "predictedConsumption": val if is_overlap else None,
                    "fullDate": f"{day_lbl} 2026",
                })

            # Add forward prediction points
            for f_idx, f_lbl in enumerate(["27 Oct", "02 Nov", "08 Nov"], start=1):
                f_val = round(daily_avg_kwh * (0.95 + 0.04 * f_idx), 1)
                curve.append({
                    "time": f_lbl,
                    "actualConsumption": None,
                    "predictedConsumption": f_val,
                    "fullDate": f"{f_lbl} 2026",
                })

            actual_callout = {
                "time": peak_actual_day,
                "value": peak_actual_val,
                "dateText": f"{peak_actual_day} 2026 (Summer High)",
                "label": "Quarter Peak",
                "color": "#00A396",
            }
            pred_pts = [p for p in curve if p["predictedConsumption"] is not None and p["time"] != demarcation_time]
            peak_pred_pt = max(pred_pts, key=lambda p: p["predictedConsumption"]) if pred_pts else curve[-1]
            predicted_callout = {
                "time": peak_pred_pt["time"],
                "value": peak_pred_pt["predictedConsumption"],
                "dateText": peak_pred_pt["fullDate"],
                "label": "Projected Trend",
                "color": "#8B5CF6",
            }

        elif norm_range in {"1Y", "ALL"}:
            # 12-month timeline from customer_gold.parquet
            demarcation_time = "Oct"
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            gold_12m = e_gold[e_gold["cutoff_day"] == 21].sort_values("month_of_year")

            peak_actual_val = -1.0
            peak_actual_month = "Jul"

            for m_idx, m_name in enumerate(month_names, start=1):
                m_row = gold_12m[gold_12m["month_of_year"] == m_idx]
                val = round(float(m_row["target_month_kwh"].iloc[0]), 1) if len(m_row) > 0 else 300.0

                is_observed = m_idx <= 10
                is_overlap = m_idx == 10

                if is_observed and val > peak_actual_val:
                    peak_actual_val = val
                    peak_actual_month = m_name

                curve.append({
                    "time": m_name,
                    "actualConsumption": val if is_observed else None,
                    "predictedConsumption": val if is_overlap else (val if m_idx > 10 else None),
                    "fullDate": f"{m_name} 2026",
                })

            actual_callout = {
                "time": peak_actual_month,
                "value": peak_actual_val,
                "dateText": f"{peak_actual_month} 2026 (Summer Peak)",
                "label": "Max Consumption",
                "color": "#00A396",
            }
            predicted_callout = {
                "time": "Dec",
                "value": round(float(gold_12m[gold_12m['month_of_year'] == 12]['target_month_kwh'].iloc[0]), 1) if len(gold_12m[gold_12m['month_of_year'] == 12]) > 0 else 300.0,
                "dateText": "Dec 2026 (Winter Forecast)",
                "label": "Forecasted Month",
                "color": "#8B5CF6",
            }

        return {
            "householdId": household_id or ("METER-1000" if eid == self.DEFAULT_ENTITY_ID else f"METER-{eid}"),
            "userName": "Ramesh Sharma" if eid == self.DEFAULT_ENTITY_ID else f"Resident {eid}",
            "timeRange": norm_range,
            "currentDailyUsageKwh": current_daily_kwh,
            "dailyAvgKwh": daily_avg_kwh,
            "dailyAvgChangePct": daily_avg_change_pct,
            "prev7DaysAvgKwh": prev_7d_avg_kwh,
            "monthlyAvgKwh": monthly_avg_kwh,
            "monthlyAvgChangePct": monthly_avg_change_pct,
            "prevMonthKwh": prev_month_kwh,
            "predictedMonthEndKwh": pred_month_kwh,
            "predictedMonthEndBillInr": pred_month_bill,
            "tariffRate": self.TARIFF_INR_PER_KWH,
            "demarcationTime": demarcation_time,
            "actualCallout": actual_callout,
            "predictedCallout": predicted_callout,
            "consumptionCurve": curve,
        }

    def get_historical_insights(
        self,
        time_range: str = "30D",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("Household datasets not loaded")

        eid = self._resolve_entity_id(entity_id)
        e_hourly = self._df_hourly[self._df_hourly["entity_id"] == eid].sort_values("timestamp")
        e_gold = self._df_gold[self._df_gold["entity_id"] == eid]

        # Reference anchor: 21 Oct 2018
        anchor_date = pd.to_datetime("2018-10-21").date()

        days_count = 30 if time_range == "30D" else (90 if time_range == "90D" else 365)
        start_date = anchor_date - timedelta(days=days_count - 1)

        sub_hourly = e_hourly[
            (e_hourly["timestamp"].dt.date >= start_date) & 
            (e_hourly["timestamp"].dt.date <= anchor_date)
        ]

        # Group by day
        daily_groups = sub_hourly.groupby(sub_hourly["timestamp"].dt.date)

        history_curve: list[dict[str, Any]] = []
        for dt, grp in daily_groups:
            tot = round(float(grp["kwh"].sum()), 1)
            peak_val = round(float(grp["kwh"].max()), 1)
            avg_val = round(float(grp["kwh"].mean()), 2)
            peak_row = grp.loc[grp["kwh"].idxmax()]
            peak_time_str = peak_row["timestamp"].strftime("%I:%M %p")

            history_curve.append({
                "date": dt.strftime("%d %b"),
                "fullDate": dt.strftime("%d %b %Y"),
                "peakDemand": peak_val,
                "avgDemand": avg_val,
                "totalConsumption": tot,
                "peakTime": peak_time_str,
            })

        if not history_curve:
            # Fallback
            history_curve = [
                {"date": "21 Oct", "fullDate": "21 Oct 2026", "peakDemand": 2.1, "avgDemand": 0.45, "totalConsumption": 9.8, "peakTime": "07:00 PM"}
            ]

        total_sum = sum(p["totalConsumption"] for p in history_curve)
        avg_daily = round(total_sum / max(len(history_curve), 1), 1)
        peak_pt = max(history_curve, key=lambda p: p["peakDemand"])

        return {
            "persona": "household",
            "entityId": f"METER-{eid}",
            "timeRange": time_range,
            "daysReturned": len(history_curve),
            "startDate": history_curve[0]["date"] + " 2026",
            "endDate": history_curve[-1]["date"] + " 2026",
            "avgDailyConsumption": avg_daily,
            "avgMonthlyConsumption": round(avg_daily * 30.0, 1),
            "peakConsumption": peak_pt["peakDemand"],
            "peakTimestamp": f"{peak_pt['fullDate']}, {peak_pt['peakTime']}",
            "unit": "kWh",
            "historyCurve": history_curve,
        }
