"""Aggregate customer intervals and build the residential model's Gold features."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from app.data_engineering.transformations.bronze_to_silver import INTERVALS_PER_DAY

FEATURE_COLUMNS = [
    "lag_1d",
    "lag_7d",
    "lag_14d",
    "rolling_mean_3d",
    "rolling_mean_7d",
    "rolling_mean_14d",
    "rolling_std_7d",
    "rolling_mean_30d",
    "rolling_std_30d",
    "recent_vs_month_mean",
    "recent_vs_prior_week",
    "history_mean",
    "history_median",
    "history_p90",
    "actual_cycle_kwh_so_far",
    "elapsed_days",
    "days_remaining",
    "day_of_week",
    "is_weekend",
    "month_num",
    "day_of_year",
    "year",
    "sin_doy",
    "cos_doy",
    "coverage_today",
    "coverage_7d_mean",
    "valid_intervals_7d",
]


def aggregate_customer_daily(
    partial_daily: Iterable[pd.DataFrame],
) -> pd.DataFrame:
    """Combine chunk-level daily aggregates without imputing missing readings."""
    parts = list(partial_daily)
    if not parts:
        raise ValueError("No Silver interval batches were available for aggregation.")
    partial = pd.concat(parts, ignore_index=True)
    daily = partial.groupby(
        ["household_id", "date"],
        as_index=False,
        observed=True,
        sort=False,
    ).agg(
        daily_kwh=("daily_kwh", lambda values: values.sum(min_count=1)),
        valid_intervals=("valid_intervals", "sum"),
        rows_seen=("rows_seen", "sum"),
        missing_flags=("missing_flags", "sum"),
        negative_flags=("negative_flags", "sum"),
        extreme_flags=("extreme_flags", "sum"),
    )
    daily["date"] = pd.to_datetime(daily["date"])
    daily["coverage_ratio"] = daily["valid_intervals"] / INTERVALS_PER_DAY
    daily["is_complete_day"] = daily["coverage_ratio"] >= 0.90
    daily.loc[daily["daily_kwh"] < 0, "daily_kwh"] = np.nan
    return daily


def _build_household_features(group: pd.DataFrame) -> pd.DataFrame:
    """Calculate notebook-compatible daily features using history to each origin."""
    group = group.sort_values("date").copy()
    series = group["daily_kwh"]
    group["lag_1d"] = series.shift(1)
    group["lag_7d"] = series.shift(7)
    group["lag_14d"] = series.shift(14)
    group["rolling_mean_3d"] = series.rolling(3, min_periods=2).mean()
    group["rolling_mean_7d"] = series.rolling(7, min_periods=5).mean()
    group["rolling_mean_14d"] = series.rolling(14, min_periods=8).mean()
    group["rolling_std_7d"] = series.rolling(7, min_periods=5).std()
    group["rolling_mean_30d"] = series.rolling(30, min_periods=10).mean()
    group["rolling_std_30d"] = series.rolling(30, min_periods=10).std()
    group["recent_vs_month_mean"] = group["rolling_mean_7d"] - group["rolling_mean_30d"]
    group["recent_vs_prior_week"] = (
        group["rolling_mean_7d"] - series.shift(7).rolling(7, min_periods=4).mean()
    )

    group["history_mean"] = series.expanding(min_periods=7).mean()
    group["history_median"] = series.expanding(min_periods=7).median()
    group["history_p90"] = series.expanding(min_periods=7).quantile(0.90)
    group["actual_cycle_kwh_so_far"] = series.groupby(
        group["month_start"], sort=False
    ).cumsum()

    group["elapsed_days"] = group["day_of_month"]
    group["days_remaining"] = (group["month_end"] - group["date"]).dt.days
    group["day_of_year"] = group["date"].dt.dayofyear
    group["year"] = group["date"].dt.year
    group["sin_doy"] = np.sin(2 * np.pi * group["day_of_year"] / 365.25)
    group["cos_doy"] = np.cos(2 * np.pi * group["day_of_year"] / 365.25)
    group["coverage_today"] = group["coverage_ratio"]
    group["coverage_7d_mean"] = group["coverage_ratio"].rolling(7, min_periods=1).mean()
    group["valid_intervals_7d"] = (
        group["valid_intervals"].rolling(7, min_periods=1).sum()
    )
    return group


def build_customer_gold(
    partial_daily: Iterable[pd.DataFrame],
    minimum_coverage: float = 0.90,
    minimum_elapsed_days: int = 7,
) -> pd.DataFrame:
    """Create customer-day data, causal model features, targets, and eligibility."""
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be between 0 and 1.")
    if minimum_elapsed_days < 1:
        raise ValueError("minimum_elapsed_days must be positive.")

    daily = aggregate_customer_daily(partial_daily)
    if daily.empty:
        raise ValueError("No customer-day records were produced.")
    daily["household_id"] = daily["household_id"].astype(str)

    all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    households = sorted(daily["household_id"].unique().tolist())
    full_index = pd.MultiIndex.from_product(
        [households, all_dates], names=["household_id", "date"]
    )
    daily_full = daily.set_index(["household_id", "date"]).reindex(full_index)
    daily_full = daily_full.reset_index()
    daily_full["date"] = pd.to_datetime(daily_full["date"])
    daily_full["month_start"] = daily_full["date"].dt.to_period("M").dt.start_time
    daily_full["month_end"] = (
        daily_full["date"].dt.to_period("M").dt.end_time.dt.floor("D")
    )
    daily_full["day_of_month"] = daily_full["date"].dt.day
    daily_full["day_of_week"] = daily_full["date"].dt.dayofweek
    daily_full["month_num"] = daily_full["date"].dt.month
    daily_full["is_weekend"] = daily_full["day_of_week"].isin([5, 6]).astype("int8")
    daily_full["coverage_ratio"] = daily_full["coverage_ratio"].fillna(0.0)
    daily_full["valid_intervals"] = (
        daily_full["valid_intervals"].fillna(0).astype("int16")
    )
    daily_full["rows_seen"] = daily_full["rows_seen"].fillna(0).astype("int16")
    for flag_column in ("missing_flags", "negative_flags", "extreme_flags"):
        daily_full[flag_column] = daily_full[flag_column].fillna(0).astype("int16")
    daily_full["is_complete_day"] = daily_full["coverage_ratio"] >= minimum_coverage

    groups = daily_full.groupby("household_id", sort=False, observed=True)
    featured = pd.concat(
        [_build_household_features(group) for _, group in groups],
        ignore_index=True,
    )

    month_groups = featured.groupby(
        ["household_id", "month_start"], sort=False, observed=True
    )
    monthly_total = month_groups["daily_kwh"].transform(
        lambda values: values.sum(min_count=1)
    )
    cumulative = month_groups["daily_kwh"].cumsum()
    featured["target_remaining_kwh"] = monthly_total - cumulative
    bad_day = (
        ~featured["is_complete_day"].fillna(False) | featured["daily_kwh"].isna()
    ).astype("int8")
    featured["future_bad_days"] = (
        bad_day.groupby(
            [featured["household_id"], featured["month_start"]],
            sort=False,
            observed=True,
        ).transform("sum")
        - bad_day.groupby(
            [featured["household_id"], featured["month_start"]],
            sort=False,
            observed=True,
        ).cumsum()
    )
    featured["future_target_complete"] = featured["future_bad_days"].eq(0)

    first_seen = daily.groupby("household_id")["date"].min()
    featured["first_seen_date"] = featured["household_id"].map(first_seen)
    featured["elapsed_since_first_seen"] = (
        featured["date"] - featured["first_seen_date"]
    ).dt.days + 1
    featured["is_prediction_eligible"] = (
        featured["day_of_month"].ge(minimum_elapsed_days)
        & featured["elapsed_since_first_seen"].ge(minimum_elapsed_days)
        & featured["is_complete_day"]
        & featured["days_remaining"].gt(0)
    )
    featured["is_training_example"] = (
        featured["is_prediction_eligible"]
        & featured["future_target_complete"]
        & featured["target_remaining_kwh"].notna()
    )
    featured[FEATURE_COLUMNS] = featured[FEATURE_COLUMNS].replace(
        [np.inf, -np.inf], np.nan
    )
    return featured.sort_values(["household_id", "date"]).reset_index(drop=True)
