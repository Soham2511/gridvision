"""LangChain tool: get_consumption_breakdown."""

from __future__ import annotations

import json
from typing import Any, Literal, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.application.energy_analytics.breakdown_consumption import (
    BreakdownConsumptionUseCase,
)
from app.domain.energy.schemas import BreakdownQueryRequest


class GetConsumptionBreakdownInput(BaseModel):
    """Input parameters for retrieving consumption breakdown."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    dimension: Literal["hour_of_day", "day_of_week", "monthly", "timeline"] = Field(
        default="hour_of_day",
        description="Categorical dimension: 'hour_of_day', 'day_of_week', 'monthly', or 'timeline'",
    )


class GetConsumptionBreakdownTool(BaseTool):
    """Retrieves consumption distribution across hours of day, days of week, or months."""

    name: str = "get_consumption_breakdown"
    description: str = (
        "Retrieve detailed distribution of household electricity consumption along a specific dimension: "
        "'hour_of_day' (diurnal hourly pattern), 'day_of_week' (weekday vs weekend pattern), or 'monthly'. "
        "Returns kWh totals, average values, and percentage shares for each bucket."
    )
    args_schema: Type[BaseModel] = GetConsumptionBreakdownInput

    authorized_meter_id: str
    use_case: BreakdownConsumptionUseCase = Field(default_factory=BreakdownConsumptionUseCase)

    def _run(
        self,
        start_date: str,
        end_date: str,
        dimension: Literal["hour_of_day", "day_of_week", "monthly", "timeline"] = "hour_of_day",
    ) -> str:
        request = BreakdownQueryRequest(
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
        )

        response = self.use_case.execute(
            meter_id=self.authorized_meter_id,
            request=request,
        )
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
