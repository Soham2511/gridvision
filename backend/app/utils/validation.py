"""Request validation models using Pydantic."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class PredictionRequestModel(BaseModel):
    """Schema for unified inference requests."""

    model_config = ConfigDict(extra="ignore")

    entity_id: str = Field(..., min_length=1, max_length=200)
    features: dict[str, Any] = Field(default_factory=dict)
    forecast_timestamp: datetime | None = None
    context: Literal["unspecified", "retrospective_gold_replay", "future_forecast"] = (
        "unspecified"
    )
    actual_kwh_so_far: float | None = Field(default=None, ge=0)


class CurtailmentRequestModel(BaseModel):
    """Schema for peak demand ADR curtailment dispatch."""

    model_config = ConfigDict(extra="ignore")

    curtailment_mw: float = Field(..., gt=0, le=200)
    duration_hours: float = Field(default=2.0, gt=0, le=24)


class AnomalyStatusUpdateModel(BaseModel):
    """Schema for updating anomaly status."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["investigating", "confirmed", "resolved", "dismissed"]


class AssistantChatRequestModel(BaseModel):
    """Schema for AI assistant prompts."""

    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(..., min_length=1, max_length=2000)
    persona: Literal["household", "commercial", "government"] = "household"
    entity_id: str | None = None
