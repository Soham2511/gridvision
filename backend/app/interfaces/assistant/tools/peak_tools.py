"""LangChain tool: get_peak_consumption_periods."""

from __future__ import annotations

import json
from typing import Any, Literal, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.application.energy_analytics.analyze_peaks import AnalyzePeaksUseCase
from app.domain.energy.metrics import AggregationGranularity
from app.domain.energy.schemas import PeakAnalysisQueryRequest


class GetPeakConsumptionPeriodsInput(BaseModel):
    """Input parameters for analyzing peak and low consumption periods."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    granularity: str = Field(
        default="daily",
        description="Granularity of periods to rank: 'hourly', 'daily', or 'monthly'",
    )
    top_n: int = Field(default=5, ge=1, le=20, description="Number of extreme periods to return (1-20)")
    ranking_direction: Literal["highest", "lowest"] = Field(
        default="highest",
        description="Ranking direction: 'highest' (peaks) or 'lowest' (troughs)",
    )


class GetPeakConsumptionPeriodsTool(BaseTool):
    """Identifies and ranks highest or lowest consumption periods for the household."""

    name: str = "get_peak_consumption_periods"
    description: str = (
        "Find the highest (peak) or lowest (trough) consumption periods for the household within a date range. "
        "Allows ranking by hourly intervals, days, or months. "
        "Use this tool when the customer asks for their highest-usage days, lowest days, or peak consumption hours."
    )
    args_schema: Type[BaseModel] = GetPeakConsumptionPeriodsInput

    authorized_meter_id: str
    use_case: AnalyzePeaksUseCase = Field(default_factory=AnalyzePeaksUseCase)

    def _run(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "daily",
        top_n: int = 5,
        ranking_direction: Literal["highest", "lowest"] = "highest",
    ) -> str:
        try:
            gran_enum = AggregationGranularity(granularity.lower().strip())
        except ValueError:
            gran_enum = AggregationGranularity.DAILY

        request = PeakAnalysisQueryRequest(
            start_date=start_date,
            end_date=end_date,
            granularity=gran_enum,
            top_n=top_n,
            ranking_direction=ranking_direction,
        )

        response = self.use_case.execute(
            meter_id=self.authorized_meter_id,
            request=request,
        )
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
