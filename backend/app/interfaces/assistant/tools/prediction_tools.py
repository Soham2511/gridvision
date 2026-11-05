"""LangChain tool: predict_usage_and_bill."""

from __future__ import annotations

import json
from typing import Any, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.application.energy_analytics.predict_bill import PredictBillUseCase
from app.domain.energy.schemas import BillPredictionQueryRequest


class PredictUsageAndBillInput(BaseModel):
    """Input parameters for predicting monthly electricity consumption and bill via ML model."""

    target_month: str = Field(
        ...,
        description="Future target calendar month to forecast in YYYY-MM format (e.g. '2027-02')",
        examples=["2027-02"],
    )
    cutoff_day: int = Field(
        default=14,
        description="Cycle progress observation day (between 1 and 28; default is 14)",
    )


class PredictUsageAndBillTool(BaseTool):
    """Predicts monthly electricity consumption (kWh) and bill cost (₹ INR) using the trained ML model."""

    name: str = "predict_usage_and_bill"
    description: str = (
        "Forecast full-month electricity consumption demand (in kWh) and estimated bill cost (in ₹ INR) "
        "for an upcoming calendar month using GridVision's trained Machine Learning model "
        "(customer-bill-prediction champion pipeline). "
        "Returns the ML-predicted monthly kWh, expected invoice in INR, daily average, confidence intervals (±10%), "
        "and model validation metrics. "
        "Use this tool only when the customer explicitly asks to predict future usage or forecast an upcoming month "
        "(e.g. 'predict next month usage' or 'forecast my upcoming bill'). "
        "For completed months or actual historical bills, use query_consumption_history instead."
    )
    args_schema: Type[BaseModel] = PredictUsageAndBillInput

    authorized_meter_id: str
    use_case: PredictBillUseCase = Field(default_factory=PredictBillUseCase)

    def _run(self, target_month: str, cutoff_day: int = 14) -> str:
        request = BillPredictionQueryRequest(
            target_month=target_month,
            cutoff_day=int(cutoff_day),
        )
        response = self.use_case.execute(
            meter_id=self.authorized_meter_id,
            request=request,
        )
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
