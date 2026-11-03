"""Domain energy module providing metrics, schemas, and analytics engine."""

from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.domain.energy.metric_registry import EnergyMetricRegistry
from app.domain.energy.metrics import (
    AggregationGranularity,
    EnergyUnit,
    MetricDefinition,
    MetricType,
)
from app.domain.energy.schemas import (
    AggregationDataPoint,
    AnalyticsToolResponse,
    BreakdownBucket,
    BreakdownQueryRequest,
    ComparisonQueryRequest,
    ConsumptionQueryRequest,
    DatePeriod,
    PeakAnalysisQueryRequest,
    PeakPeriodRecord,
    PeriodComparisonResult,
    PeriodSummary,
)

__all__ = [
    "AggregationDataPoint",
    "AggregationGranularity",
    "AnalyticsToolResponse",
    "BreakdownBucket",
    "BreakdownQueryRequest",
    "ComparisonQueryRequest",
    "ConsumptionQueryRequest",
    "DatePeriod",
    "EnergyAnalyticsEngine",
    "EnergyMetricRegistry",
    "EnergyUnit",
    "MetricDefinition",
    "MetricType",
    "PeakAnalysisQueryRequest",
    "PeakPeriodRecord",
    "PeriodComparisonResult",
    "PeriodSummary",
]
