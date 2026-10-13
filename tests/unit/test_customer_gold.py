"""Focused tests for residential Gold features and eligibility rules."""

from __future__ import annotations

import pandas as pd
from app.data_engineering.transformations.silver_to_gold import build_customer_gold


def test_gold_target_uses_future_cycle_readings_and_respects_coverage() -> None:
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    partial = pd.DataFrame(
        {
            "household_id": ["meter-1"] * len(dates),
            "date": dates,
            "daily_kwh": [float(day) for day in range(1, 11)],
            "valid_intervals": [96] * len(dates),
            "rows_seen": [96] * len(dates),
            "missing_flags": [0] * len(dates),
            "negative_flags": [0] * len(dates),
            "extreme_flags": [0] * len(dates),
        }
    )

    gold = build_customer_gold([partial])
    day_seven = gold.loc[gold["date"].eq(pd.Timestamp("2024-01-07"))].iloc[0]
    day_six = gold.loc[gold["date"].eq(pd.Timestamp("2024-01-06"))].iloc[0]

    assert bool(day_six["is_prediction_eligible"]) is False
    assert bool(day_seven["is_prediction_eligible"]) is True
    assert bool(day_seven["is_training_example"]) is True
    assert day_seven["actual_cycle_kwh_so_far"] == 28.0
    assert day_seven["target_remaining_kwh"] == 27.0


def test_gold_marks_missing_calendar_dates_ineligible() -> None:
    dates = pd.date_range("2024-01-01", periods=9, freq="D").delete(7)
    partial = pd.DataFrame(
        {
            "household_id": ["meter-1"] * len(dates),
            "date": dates,
            "daily_kwh": [100.0] * len(dates),
            "valid_intervals": [96] * len(dates),
            "rows_seen": [96] * len(dates),
            "missing_flags": [0] * len(dates),
            "negative_flags": [0] * len(dates),
            "extreme_flags": [0] * len(dates),
        }
    )

    gold = build_customer_gold([partial])
    missing_day = gold.loc[gold["date"].eq(pd.Timestamp("2024-01-08"))].iloc[0]

    assert pd.isna(missing_day["daily_kwh"])
    assert missing_day["coverage_ratio"] == 0
    assert not bool(missing_day["is_prediction_eligible"])
