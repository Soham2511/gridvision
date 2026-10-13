"""Request and response contracts for model predictions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FeatureValue = float | int | str | bool | None


class PredictionRequest(BaseModel):
    """One model row in its verified feature schema."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1, max_length=200)
    forecast_timestamp: datetime
    features: dict[str, FeatureValue]
    context: Literal["unspecified", "retrospective_gold_replay"] = "unspecified"
    actual_kwh_so_far: float | None = Field(default=None, ge=0)


class PredictionResponse(BaseModel):
    """Prediction plus artifact and evaluation context."""

    entity_id: str
    forecast_timestamp: datetime
    prediction: float = Field(allow_inf_nan=False)
    target_name: str
    target_unit: str
    model_name: str
    model_version: str
    evaluation_status: str
    context: str
    prediction_status: Literal["valid", "invalid_negative_energy"]
    actual_kwh_so_far: float | None = None
    estimated_month_end_kwh: float | None = None
    estimated_month_end_bill_inr: float | None = None
    tariff_inr_per_kwh: float | None = None
    data_quality_status: str
    caveats: list[str]
