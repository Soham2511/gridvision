"""Global time-range selector and filtering logic anchored to dataset boundaries."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TimeRangeFilterResult:
    """Result of filtering a dataframe by a relative time range."""
    filtered_df: pd.DataFrame
    requested_range: str
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp
    available_start: pd.Timestamp
    available_end: pd.Timestamp
    total_records: int
    is_partially_truncated: bool
    explanation: str


TIME_RANGE_OPTIONS: tuple[str, ...] = ("1D", "1W", "1M", "3M", "6M", "1Y")


def filter_by_time_range(
    df: pd.DataFrame,
    timestamp_col: str,
    range_option: str,
) -> TimeRangeFilterResult:
    """
    Filter dataframe based on the requested relative range anchored at max available timestamp.
    
    Never uses machine clock; always anchors at df[timestamp_col].max().
    """
    if df.empty or timestamp_col not in df.columns:
        now = pd.Timestamp.now()
        return TimeRangeFilterResult(
            filtered_df=df,
            requested_range=range_option,
            start_timestamp=now,
            end_timestamp=now,
            available_start=now,
            available_end=now,
            total_records=0,
            is_partially_truncated=False,
            explanation="No data available to filter.",
        )

    series = pd.to_datetime(df[timestamp_col])
    available_start = series.min()
    available_end = series.max()

    delta_map = {
        "1D": pd.Timedelta(days=1),
        "1W": pd.Timedelta(days=7),
        "1M": pd.Timedelta(days=30),
        "3M": pd.Timedelta(days=90),
        "6M": pd.Timedelta(days=180),
        "1Y": pd.Timedelta(days=365),
    }

    delta = delta_map.get(range_option, pd.Timedelta(days=30))
    target_start = available_end - delta

    is_truncated = target_start < available_start
    actual_start = max(target_start, available_start)

    mask = (series >= actual_start) & (series <= available_end)
    filtered = df.loc[mask].copy()

    explanation = ""
    if is_truncated:
        explanation = (
            f"The selected interval ({range_option}) extends beyond the earliest available record "
            f"({available_start.strftime('%Y-%m-%d')}). Displaying all available records from "
            f"{available_start.strftime('%Y-%m-%d')} to {available_end.strftime('%Y-%m-%d')}."
        )

    return TimeRangeFilterResult(
        filtered_df=filtered,
        requested_range=range_option,
        start_timestamp=actual_start,
        end_timestamp=available_end,
        available_start=available_start,
        available_end=available_end,
        total_records=len(filtered),
        is_partially_truncated=is_truncated,
        explanation=explanation,
    )
