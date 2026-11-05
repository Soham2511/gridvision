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
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description=(
            "Target future calendar month in YYYY-MM format (for example 2019-02 for "
            "February 2019). Convert a month name and stated year to this format exactly; "
            "do not change or infer the year. Use the user's exact requested month, even "
            "when the date is far ahead, and let the prediction service report if it cannot "
            "produce a supported forecast."
        ),
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
        "Use this tool for a prediction of a specific upcoming calendar month's total household "
        "electricity consumption or bill, including requests such as 'what will my February "
        "2019 bill be?' or 'predict usage for 2027-02'. Provide target_month as YYYY-MM and "
        "preserve the year the customer stated. It runs the trained customer-bill prediction "
        "model and returns predicted monthly kWh, estimated bill in INR, daily average, "
        "confidence bounds, and model status. This is the correct tool for a monthly bill "
        "estimate; do not use forecast_consumption for a full-month invoice. For actual "
        "recorded consumption or completed-month bills, use query_consumption_history."
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
