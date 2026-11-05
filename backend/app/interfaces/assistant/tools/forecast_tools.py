"""LangChain tool: forecast_consumption."""

from __future__ import annotations

import json
from typing import Any, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from app.application.energy_analytics.generate_forecast import (
    GenerateForecastUseCase,
)
from app.domain.energy.schemas import ForecastQueryRequest


class ForecastConsumptionInput(BaseModel):
    """Input parameters for forecasting household electricity consumption."""

    horizon_days: int = Field(
        default=7,
        description="Number of future days to forecast (between 1 and 30 days; default 7 days). Projections are strictly limited to a maximum of 30 days.",
    )
    start_date: str | None = Field(
        default=None,
        description="Starting date of forecast period in YYYY-MM-DD format (e.g. '2019-01-01'). If omitted, starts immediately following the latest recorded telemetry date.",
    )

    @field_validator("horizon_days", mode="before")
    @classmethod
    def clamp_horizon_days(cls, v: Any) -> int:
        """Clamp requested horizon to allowed domain boundary (1 to 30 days)."""
        try:
            val = int(v)
            return max(1, min(val, 30))
        except (ValueError, TypeError):
            return 7


class ForecastConsumptionTool(BaseTool):
    """Forecasts household electricity consumption for a limited forward horizon (1 to 30 days)."""

    name: str = "forecast_consumption"
    description: str = (
        "Forecast household electricity day by day for a bounded horizon of 1-30 days. "
        "Use for requests such as the next 7 or 14 days, or another short daily forecast, "
        "when a date range and daily points are appropriate. Returns projected daily kWh, "
        "period total, confidence bounds, and an estimated charge. For a prediction of a "
        "named calendar month's complete usage or bill, use predict_usage_and_bill instead; "
        "do not treat this limited daily horizon as a full-month bill prediction."
    )
    args_schema: Type[BaseModel] = ForecastConsumptionInput

    authorized_meter_id: str
    use_case: GenerateForecastUseCase = Field(default_factory=GenerateForecastUseCase)

    def _run(self, horizon_days: int = 7, start_date: str | None = None) -> str:
        clamped_days = max(1, min(int(horizon_days), 30))
        request = ForecastQueryRequest(
            horizon_days=clamped_days,
            start_date=start_date,
        )

        response = self.use_case.execute(
            meter_id=self.authorized_meter_id,
            request=request,
        )
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
