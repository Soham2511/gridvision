"""Request validation models using Pydantic."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai.commercial.schemas.communication import CommercialConversationMessage
from ai.commercial.schemas.optimization import ScheduleInput


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


class ChatHistoryMessage(BaseModel):
    """Single message in conversational session history."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant", "system"]
    content: str = Field(..., max_length=4000)


class AssistantChatRequestModel(BaseModel):
    """Schema for AI assistant prompts."""

    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(..., min_length=1, max_length=2000)
    persona: Literal["household", "commercial", "government"] = "household"
    entity_id: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list)
    conversation_id: str | None = None
    session_id: str | None = None


class CommercialWorkflowRequestModel(BaseModel):
    """Public request contract for the Commercial multi-agent workflow."""

    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    factory_id: str | None = Field(default=None, min_length=1, max_length=128)
    building_id: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]{0,15}$",
    )
    user_goal: str = Field(min_length=1, max_length=2000)
    optimization_inputs: ScheduleInput | None = None
    conversation_history: list[CommercialConversationMessage] = Field(
        default_factory=list,
        max_length=8,
    )


class CommercialWebSearchRequestModel(BaseModel):
    """Explicitly confirmed user request for a general web lookup."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)


class ScheduleApprovalRequestModel(BaseModel):
    """Demo-user decision for an immutable optimized schedule proposal."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)
