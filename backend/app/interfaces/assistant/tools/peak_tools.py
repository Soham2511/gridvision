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

    start_date: str = Field(..., description="Inclusive first date to rank, YYYY-MM-DD.")
    end_date: str = Field(..., description="Inclusive last date to rank, YYYY-MM-DD.")
    granularity: str = Field(
        default="daily",
        description="Unit to rank: hourly intervals, daily totals, or monthly totals.",
    )
    top_n: int = Field(default=5, ge=1, le=20, description="How many highest/lowest periods to return (1-20).")
    ranking_direction: Literal["highest", "lowest"] = Field(
        default="highest",
        description="Return largest usage periods ('highest') or smallest usage periods ('lowest').",
    )


class GetPeakConsumptionPeriodsTool(BaseTool):
    """Identifies and ranks highest or lowest consumption periods for the household."""

    name: str = "get_peak_consumption_periods"
    description: str = (
        "Rank a household's actual consumption within a date range to find its highest-use "
        "peaks or lowest-use troughs, by hour, day, or month. Use for questions like 'which "
        "day used the most power?' or 'what are my peak hours?'. Set ranking_direction to "
        "'highest' or 'lowest' and top_n to the requested count. This does not predict future usage."
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
