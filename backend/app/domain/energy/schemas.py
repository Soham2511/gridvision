"""Standardized Pydantic v2 domain schemas for GridVision energy analytics.

Used across LangChain tools, application services, domain calculators, and API responses
to ensure consistent serialization, validation, unit transparency, and null handling.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.energy.metrics import AggregationGranularity, EnergyUnit


class DatePeriod(BaseModel):
    """Specification of an inclusive temporal query boundary."""

    model_config = ConfigDict(frozen=True)

    start_date: str = Field(
        ...,
        description="Starting date in ISO format (YYYY-MM-DD)",
        examples=["2018-05-01"],
    )
    end_date: str = Field(
        ...,
        description="Ending date in ISO format (YYYY-MM-DD)",
        examples=["2018-05-31"],
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        clean = (v or "").strip()
        try:
            # Accepts YYYY-MM-DD or full ISO timestamp
            if "T" in clean:
                clean = clean.split("T")[0]
            elif " " in clean:
                clean = clean.split(" ")[0]
            datetime.strptime(clean, "%Y-%m-%d")
            return clean
        except ValueError as exc:
            raise ValueError(f"Invalid date format '{v}'. Expected YYYY-MM-DD.") from exc


class ConsumptionQueryRequest(BaseModel):
    """Parameters for querying household consumption history."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    granularity: AggregationGranularity = Field(
        default=AggregationGranularity.DAILY,
        description="Temporal grouping: hourly, daily, weekly, monthly, yearly",
    )
    metric: str = Field(
        default="consumption",
        description="Target metric (e.g. 'consumption', 'daily_average', 'peak_demand')",
    )


class ComparisonQueryRequest(BaseModel):
    """Parameters for comparing two specific consumption periods."""

    period_a: DatePeriod = Field(..., description="First comparison period (e.g. baseline)")
    period_b: DatePeriod = Field(..., description="Second comparison period (e.g. target)")
    metric: str = Field(
        default="consumption",
        description="Metric to compare: 'consumption' or 'daily_average'",
    )


class BreakdownQueryRequest(BaseModel):
    """Parameters for retrieving consumption distributions along a specific dimension."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    dimension: Literal["hour_of_day", "day_of_week", "monthly", "timeline"] = Field(
        default="hour_of_day",
        description="Breakdown dimension: 'hour_of_day', 'day_of_week', 'monthly', 'timeline'",
    )


class PeakAnalysisQueryRequest(BaseModel):
    """Parameters for analyzing peak and low consumption periods."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    granularity: AggregationGranularity = Field(
        default=AggregationGranularity.DAILY,
        description="Aggregation level: 'hourly', 'daily', or 'monthly'",
    )
    top_n: int = Field(default=5, ge=1, le=50, description="Number of extreme periods to return")
    ranking_direction: Literal["highest", "lowest"] = Field(
        default="highest",
        description="Ranking direction: 'highest' or 'lowest'",
    )


class AggregationDataPoint(BaseModel):
    """Single aggregated interval point."""

    period_key: str = Field(..., description="Period identifier (e.g. '2018-05-15' or '14:00')")
    value: float = Field(..., description="Aggregated metric numerical value")
    unit: str = Field(..., description="Unit of measurement (e.g. kWh, kWh/day)")
    observation_count: int = Field(..., description="Number of raw intervals included")
    completeness_pct: float = Field(default=100.0, description="Completeness of expected intervals")


class PeriodSummary(BaseModel):
    """Summary metrics for a single temporal period."""

    period: DatePeriod
    total_consumption_kwh: float
    average_daily_kwh: float
    observed_days: int
    expected_days: int
    completeness_pct: float


class PeriodComparisonResult(BaseModel):
    """Output contract for comparative period analysis."""

    period_a: PeriodSummary
    period_b: PeriodSummary
    absolute_difference_kwh: float
    percentage_change_pct: float | None
    normalized_daily_difference_kwh: float
    is_comparable: bool
    explanation: str


class BreakdownBucket(BaseModel):
    """Single category bucket within a consumption distribution."""

    bucket: str = Field(..., description="Category label (e.g. 'Monday', '18:00', '2018-05')")
    total_kwh: float
    percentage_of_total: float
    average_kwh: float


class PeakPeriodRecord(BaseModel):
    """Identified peak or low interval."""

    rank: int
    period: str
    consumption_kwh: float
    average_daily_kwh: float | None = None


class AnalyticsToolResponse(BaseModel):
    """Standardized output wrapper for all LangChain analytics tools and API endpoints."""

    status: Literal["success", "insufficient_data", "error"] = "success"
    meter_id: str
    tool_name: str
    period: DatePeriod | None = None
    metric: str
    unit: str
    results: Any
    data_provenance: str = "customer_silver_hourly"
    observation_count: int
    completeness_pct: float | None = None
    limitations: list[str] = Field(default_factory=list)


class ForecastQueryRequest(BaseModel):
    """Parameters for forecasting household electricity consumption over a limited period."""

    horizon_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Number of future days to forecast (1 to 30 days maximum)",
    )
    start_date: str | None = Field(
        default=None,
        description="Starting date for the forecast (YYYY-MM-DD). If omitted, starts after the last observed date.",
    )


class ForecastDataPoint(BaseModel):
    """Single daily forecast point in the projected horizon."""

    date: str
    predicted_kwh: float
    lower_bound_kwh: float
    upper_bound_kwh: float


class ForecastResult(BaseModel):
    """Output contract for forward consumption forecast."""

    horizon_days: int
    start_date: str
    end_date: str
    total_predicted_kwh: float
    average_daily_kwh: float
    forecast_points: list[ForecastDataPoint]
    methodology: str
    estimated_bill_inr: float | None = None
    tariff_rate_inr_per_kwh: float | None = None
    confidence_interval_pct: float = 10.0
    caveats: list[str] = Field(default_factory=list)


class BillPredictionQueryRequest(BaseModel):
    """Parameters for ML-based monthly energy consumption and bill prediction."""

    target_month: str = Field(
        ...,
        description="Target calendar month in YYYY-MM or YYYY-MM-DD format (e.g. '2019-02', '2018-12', '2019-01')",
        examples=["2019-02"],
    )
    cutoff_day: int = Field(
        default=14,
        ge=1,
        le=28,
        description="Observed cutoff progress day (e.g. 7, 14, 21, or 28; default is 14)",
    )


class BillPredictionResult(BaseModel):
    """Output contract for ML-based monthly bill and consumption prediction."""

    target_month: str
    cutoff_day: int
    predicted_month_kwh: float
    predicted_bill_inr: float
    tariff_rate_inr_per_kwh: float
    daily_average_kwh: float
    confidence_interval: dict[str, float]
    model_name: str
    model_version: str
    selected_estimator: str
    evaluation_status: str
    features_used: list[str]
    actual_historical_kwh: float | None = None
    actual_historical_bill_inr: float | None = None
    absolute_error_kwh: float | None = None
    caveats: list[str] = Field(default_factory=list)
