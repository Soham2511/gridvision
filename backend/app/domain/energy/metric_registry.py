"""Centralized Energy Metric Registry for GridVision.

Authoritative source of truth for all metric calculations, units, and definitions.
Eliminates duplicated calculations, naming ambiguities, and inconsistent formulas across
the assistant, dashboard, and background pipelines.
"""

from __future__ import annotations

from app.domain.energy.metrics import (
    AggregationGranularity,
    EnergyUnit,
    MetricDefinition,
    MetricType,
)

_REGISTRY: dict[str, MetricDefinition] = {
    "consumption": MetricDefinition(
        key="consumption",
        name="Energy Consumption",
        description="Total active electrical energy consumed over a specified period.",
        unit=EnergyUnit.KWH,
        metric_type=MetricType.OBSERVED,
        supported_granularities=(
            AggregationGranularity.HOURLY,
            AggregationGranularity.DAILY,
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="sum(interval_kwh)",
        missing_value_treatment="exclude_missing_from_sum",
        minimum_valid_observations=1,
    ),
    "daily_average": MetricDefinition(
        key="daily_average",
        name="Average Daily Consumption",
        description="Mean energy consumed per day across valid observed days.",
        unit=EnergyUnit.KWH_PER_DAY,
        metric_type=MetricType.DERIVED,
        supported_granularities=(
            AggregationGranularity.DAILY,
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="total_kwh / valid_observed_days",
        missing_value_treatment="normalize_by_observed_days_only",
        minimum_valid_observations=1,
    ),
    "peak_demand": MetricDefinition(
        key="peak_demand",
        name="Peak Interval Demand",
        description="Maximum measured consumption observed during any single interval/hour within the period.",
        unit=EnergyUnit.KWH,
        metric_type=MetricType.OBSERVED,
        supported_granularities=(
            AggregationGranularity.DAILY,
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="max(interval_kwh)",
        missing_value_treatment="ignore_nulls",
        minimum_valid_observations=1,
    ),
    "median_daily": MetricDefinition(
        key="median_daily",
        name="Median Daily Consumption",
        description="The 50th percentile of valid daily consumption totals.",
        unit=EnergyUnit.KWH_PER_DAY,
        metric_type=MetricType.DERIVED,
        supported_granularities=(
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="percentile(daily_kwh, 50)",
        missing_value_treatment="omit_unobserved_days",
        minimum_valid_observations=3,
    ),
    "p90_daily": MetricDefinition(
        key="p90_daily",
        name="90th Percentile Daily Consumption",
        description="Daily consumption level exceeded on only 10% of observed days.",
        unit=EnergyUnit.KWH_PER_DAY,
        metric_type=MetricType.DERIVED,
        supported_granularities=(
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="percentile(daily_kwh, 90)",
        missing_value_treatment="omit_unobserved_days",
        minimum_valid_observations=10,
    ),
    "relative_change": MetricDefinition(
        key="relative_change",
        name="Relative Period Change",
        description="Percentage difference in consumption or daily average relative to a reference baseline.",
        unit=EnergyUnit.PERCENT,
        metric_type=MetricType.DERIVED,
        supported_granularities=(
            AggregationGranularity.DAILY,
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="((current - baseline) / baseline) * 100",
        missing_value_treatment="return_null_if_baseline_zero_or_incomparable",
        minimum_valid_observations=2,
    ),
    "coverage_ratio": MetricDefinition(
        key="coverage_ratio",
        name="Telemetry Coverage Ratio",
        description="Percentage of expected interval readings successfully recorded.",
        unit=EnergyUnit.PERCENT,
        metric_type=MetricType.DERIVED,
        supported_granularities=(
            AggregationGranularity.DAILY,
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
            AggregationGranularity.YEARLY,
        ),
        aggregation_method="(valid_intervals / expected_intervals) * 100",
        missing_value_treatment="strict_temporal_cadence",
        minimum_valid_observations=0,
    ),
    "estimated_bill": MetricDefinition(
        key="estimated_bill",
        name="Estimated Bill Invoice",
        description="Projected household billing cost computed from observed and predicted cycle energy.",
        unit=EnergyUnit.INR,
        metric_type=MetricType.DERIVED,
        supported_granularities=(
            AggregationGranularity.MONTHLY,
        ),
        aggregation_method="(cycle_kwh_so_far + predicted_remaining_kwh) * tariff_rate",
        missing_value_treatment="return_null_if_tariff_missing",
        minimum_valid_observations=1,
    ),
    "forecast_consumption": MetricDefinition(
        key="forecast_consumption",
        name="Forecast Energy Consumption",
        description="Projected household electricity consumption across a bounded forward horizon (1 to 30 days).",
        unit=EnergyUnit.KWH,
        metric_type=MetricType.PREDICTED,
        supported_granularities=(
            AggregationGranularity.DAILY,
            AggregationGranularity.WEEKLY,
            AggregationGranularity.MONTHLY,
        ),
        aggregation_method="sum(daily_predicted_kwh)",
        missing_value_treatment="require_baseline_or_model",
        minimum_valid_observations=1,
    ),
}


class EnergyMetricRegistry:
    """Registry interface providing access to validated metric definitions."""

    @classmethod
    def get(cls, key: str) -> MetricDefinition:
        """Retrieve definition for a registered metric key or raise KeyError."""
        clean_key = (key or "").strip().lower()
        if clean_key not in _REGISTRY:
            valid_keys = ", ".join(_REGISTRY.keys())
            raise KeyError(
                f"Unknown energy metric '{key}'. Valid registered metrics: {valid_keys}"
            )
        return _REGISTRY[clean_key]

    @classmethod
    def exists(cls, key: str) -> bool:
        """Check if metric key is registered."""
        return (key or "").strip().lower() in _REGISTRY

    @classmethod
    def list_all(cls) -> list[MetricDefinition]:
        """Return list of all registered metric definitions."""
        return list(_REGISTRY.values())
