"""Unit tests for the multi-step autoregressive forecasting engine."""

from __future__ import annotations

import pandas as pd
from dashboard.utils.data import (
    load_commercial_history,
    load_commercial_latest,
    load_government_history,
    load_government_latest,
    load_residential_history,
    load_residential_latest,
)
from dashboard.utils.forecasting import (
    forecast_commercial_next_10h,
    forecast_government_aggregate_next_10h,
    forecast_government_next_10h,
    forecast_household_next_10_days,
)


def test_forecast_commercial_next_10h_autoregressive() -> None:
    history = load_commercial_history()
    latest = load_commercial_latest()
    bldg_id = str(latest["building_id"].iloc[0])
    row = latest.iloc[0]

    fc = forecast_commercial_next_10h(bldg_id, history, row)
    assert len(fc) == 10
    assert list(fc.columns) == ["timestamp", "forecast_kwh"]

    # Timestamps must start exactly 1 hour after the dataset boundary
    start_ts = pd.Timestamp(fc["timestamp"].iloc[0])
    end_ts = pd.Timestamp(fc["timestamp"].iloc[-1])
    assert str(start_ts) == "2018-01-01 00:00:00"
    assert str(end_ts) == "2018-01-01 09:00:00"

    # All forecasted values must be positive numbers
    for val in fc["forecast_kwh"]:
        assert isinstance(val, (int, float))
        assert val > 0.0


def test_forecast_government_next_10h_autoregressive() -> None:
    history = load_government_history()
    latest = load_government_latest()
    site_id = str(latest["site_id"].iloc[0])
    row = latest.iloc[0]

    fc = forecast_government_next_10h(site_id, history, row)
    assert len(fc) == 10
    assert list(fc.columns) == ["timestamp", "forecast_kwh"]
    assert str(fc["timestamp"].iloc[0]) == "2018-01-01 00:00:00"
    assert str(fc["timestamp"].iloc[-1]) == "2018-01-01 09:00:00"
    assert all(val > 0.0 for val in fc["forecast_kwh"])


def test_forecast_government_aggregate_next_10h() -> None:
    history = load_government_history()
    latest = load_government_latest()

    agg_fc = forecast_government_aggregate_next_10h(history, latest)
    assert len(agg_fc) == 10
    assert "total_aggregate_demand_kwh" in agg_fc.columns
    assert str(agg_fc["timestamp"].iloc[0]) == "2018-01-01 00:00:00"
    assert str(agg_fc["timestamp"].iloc[-1]) == "2018-01-01 09:00:00"
    # Aggregate demand across 17 sites is on the order of 100k+ kWh/hr
    assert agg_fc["total_aggregate_demand_kwh"].iloc[0] > 50_000


def test_forecast_household_next_10_days() -> None:
    history = load_residential_history()
    latest = load_residential_latest()
    hh_id = str(latest["household_id"].iloc[0])
    row = latest.iloc[0]

    fc = forecast_household_next_10_days(hh_id, history, row)
    assert len(fc) == 10
    assert list(fc.columns) == ["date", "forecast_kwh"]
    assert all(val > 0.0 for val in fc["forecast_kwh"])
