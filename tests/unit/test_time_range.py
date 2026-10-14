"""Unit tests for time-range filtering utilities."""

from __future__ import annotations

import pandas as pd
from dashboard.utils.time_range import TIME_RANGE_OPTIONS, filter_by_time_range


def test_time_range_options_complete() -> None:
    """Verify all 6 required time ranges are defined."""
    assert TIME_RANGE_OPTIONS == ("1D", "1W", "1M", "3M", "6M", "1Y")


def test_filter_by_time_range_empty() -> None:
    """Empty dataframe handles time range gracefully without error."""
    df = pd.DataFrame()
    res = filter_by_time_range(df, "timestamp", "1M")
    assert res.total_records == 0
    assert res.filtered_df.empty


def test_filter_by_time_range_anchored_at_max() -> None:
    """Filtering is anchored strictly at the maximum observed timestamp in data."""
    dates = pd.date_range("2017-01-01", periods=100, freq="D")
    df = pd.DataFrame({"timestamp": dates, "val": range(100)})

    res_1w = filter_by_time_range(df, "timestamp", "1W")
    assert res_1w.end_timestamp == dates.max()
    assert (res_1w.end_timestamp - res_1w.start_timestamp).days <= 7
    assert res_1w.total_records <= 8

    res_1m = filter_by_time_range(df, "timestamp", "1M")
    assert (res_1m.end_timestamp - res_1m.start_timestamp).days <= 30


def test_filter_by_time_range_truncation_detection() -> None:
    """When requested range exceeds available data, truncation is flagged honestly."""
    dates = pd.date_range("2017-01-01", periods=10, freq="D")
    df = pd.DataFrame({"timestamp": dates, "val": range(10)})

    res_1y = filter_by_time_range(df, "timestamp", "1Y")
    assert res_1y.is_partially_truncated is True
    assert "extends beyond the earliest available record" in res_1y.explanation
    assert res_1y.total_records == 10
