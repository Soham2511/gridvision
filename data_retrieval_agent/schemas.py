"""Strict agent API schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StartSessionRequest(StrictSchema):
    label: str | None = Field(default=None, min_length=1, max_length=80)


class MessageRequest(StrictSchema):
    message: str = Field(min_length=1, max_length=4000)


class SessionInfoResponse(StrictSchema):
    session_id: str
    created_at: datetime
    expires_at: datetime
    status: Literal["active", "expired", "ended"]


class SourceReference(StrictSchema):
    source_id: str
    record_type: str
    period_start: str | None = None
    period_end: str | None = None
    units: str | None = None
    dataset_version: str | None = None
    data_class: Literal["historical", "observed", "predicted", "synthetic"]


class AgentMessageResponse(StrictSchema):
    session_id: str
    answer: str
    needs_clarification: bool = False
    clarification_question: str | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    availability: Literal["available", "partial", "unavailable"]
