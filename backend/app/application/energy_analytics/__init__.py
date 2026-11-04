"""Application use cases for energy analytics."""

from app.application.energy_analytics.analyze_peaks import AnalyzePeaksUseCase
from app.application.energy_analytics.breakdown_consumption import (
    BreakdownConsumptionUseCase,
)
from app.application.energy_analytics.compare_periods import (
    ComparePeriodsUseCase,
)
from app.application.energy_analytics.generate_forecast import (
    GenerateForecastUseCase,
)
from app.application.energy_analytics.query_consumption import (
    QueryConsumptionUseCase,
)

__all__ = [
    "AnalyzePeaksUseCase",
    "BreakdownConsumptionUseCase",
    "ComparePeriodsUseCase",
    "GenerateForecastUseCase",
    "QueryConsumptionUseCase",
]
