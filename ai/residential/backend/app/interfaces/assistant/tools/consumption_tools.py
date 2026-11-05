"""LangChain tool: query_consumption_history."""

from __future__ import annotations

import json
from typing import Any, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.application.energy_analytics.query_consumption import QueryConsumptionUseCase
from app.domain.energy.metrics import AggregationGranularity
from app.domain.energy.schemas import ConsumptionQueryRequest


class QueryConsumptionHistoryInput(BaseModel):
    """Input parameters for querying household consumption history."""

    start_date: str = Field(
        ...,
        description="Starting date of the period in YYYY-MM-DD format (e.g. '2018-05-01')",
    )
    end_date: str = Field(
        ...,
        description="Ending date of the period in YYYY-MM-DD format (e.g. '2018-05-15')",
    )
    granularity: str = Field(
        default="daily",
        description="Aggregation granularity: 'hourly', 'daily', 'weekly', 'monthly', or 'yearly'",
    )


class QueryConsumptionHistoryTool(BaseTool):
    """Retrieves household electricity consumption for a specific date range and granularity."""

    name: str = "query_consumption_history"
    description: str = (
        "Retrieve actual recorded household electricity use for a date range, aggregated hourly, "
        "daily, weekly, monthly, or yearly. Use for historical or current-period usage, and for "
        "actual consumption in a completed named month; set start_date and end_date to the "
        "inclusive calendar range and choose monthly granularity for a month total. This returns "
        "meter records, not a future prediction. For a future named month's predicted bill, use "
        "predict_usage_and_bill instead. The authorized meter is injected by the server."
    )
    args_schema: Type[BaseModel] = QueryConsumptionHistoryInput

    authorized_meter_id: str
    use_case: QueryConsumptionUseCase = Field(default_factory=QueryConsumptionUseCase)

    def _run(self, start_date: str, end_date: str, granularity: str = "daily") -> str:
        try:
            gran_enum = AggregationGranularity(granularity.lower().strip())
        except ValueError:
            gran_enum = AggregationGranularity.DAILY

        request = ConsumptionQueryRequest(
            start_date=start_date,
            end_date=end_date,
            granularity=gran_enum,
        )

        response = self.use_case.execute(
            meter_id=self.authorized_meter_id,
            request=request,
        )
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
