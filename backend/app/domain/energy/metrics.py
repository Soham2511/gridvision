"""Core energy metric definitions and taxonomy for GridVision.

Provides standardized enums and data structures for metric categorization, units,
and aggregation semantics, completely independent of AI or web frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MetricType(str, Enum):
    """Classification of how a metric value is produced."""

    OBSERVED = "observed"      # Directly measured from smart meter intervals
    DERIVED = "derived"        # Mathematically aggregated or transformed from observations
    PREDICTED = "predicted"    # Inferred by ML forecasting or billing models


class EnergyUnit(str, Enum):
    """Standardized physical and financial measurement units."""

    KWH = "kWh"
    KWH_PER_DAY = "kWh/day"
    KW = "kW"
    MW = "MW"
    PERCENT = "%"
    INR = "₹"
    HOURS = "hours"
    DAYS = "days"
    COUNT = "count"


class AggregationGranularity(str, Enum):
    """Supported temporal aggregation granularities."""

    INTERVAL = "interval"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass(frozen=True)
class MetricDefinition:
    """Authoritative semantic specification for a GridVision energy metric."""

    key: str
    name: str
    description: str
    unit: EnergyUnit
    metric_type: MetricType
    supported_granularities: tuple[AggregationGranularity, ...]
    aggregation_method: str
    missing_value_treatment: str
    minimum_valid_observations: int = 1
