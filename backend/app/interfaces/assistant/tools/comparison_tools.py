"""LangChain tool: compare_consumption_periods."""

from __future__ import annotations

import json
from typing import Any, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.application.energy_analytics.compare_periods import ComparePeriodsUseCase
from app.domain.energy.schemas import ComparisonQueryRequest, DatePeriod


class CompareConsumptionPeriodsInput(BaseModel):
    """Input parameters for comparing two specific consumption periods."""

    start_date_a: str = Field(..., description="Start date of Period A (YYYY-MM-DD)")
    end_date_a: str = Field(..., description="End date of Period A (YYYY-MM-DD)")
    start_date_b: str = Field(..., description="Start date of Period B (YYYY-MM-DD)")
    end_date_b: str = Field(..., description="End date of Period B (YYYY-MM-DD)")
    metric: str = Field(default="consumption", description="Metric to compare: 'consumption' or 'daily_average'")


class CompareConsumptionPeriodsTool(BaseTool):
    """Compares household electricity consumption between two specific periods."""

    name: str = "compare_consumption_periods"
    description: str = (
        "Compare electricity consumption and average daily usage between two user-specified periods. "
        "Returns absolute kWh differences, normalized daily changes, percentage changes, and comparability status. "
        "Use this tool when the customer asks to compare two months, two weeks, or custom date ranges."
    )
    args_schema: Type[BaseModel] = CompareConsumptionPeriodsInput

    authorized_meter_id: str
    use_case: ComparePeriodsUseCase = Field(default_factory=ComparePeriodsUseCase)

    def _run(
        self,
        start_date_a: str,
        end_date_a: str,
        start_date_b: str,
        end_date_b: str,
        metric: str = "consumption",
    ) -> str:
        request = ComparisonQueryRequest(
            period_a=DatePeriod(start_date=start_date_a, end_date=end_date_a),
            period_b=DatePeriod(start_date=start_date_b, end_date=end_date_b),
            metric=metric,
        )

        response = self.use_case.execute(
            meter_id=self.authorized_meter_id,
            request=request,
        )
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
