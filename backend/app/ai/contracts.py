"""Typed, provenance-carrying contracts for later AI workflows."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceReference(FrozenContract):
    source_id: str = Field(min_length=1, max_length=120)
    dataset: str = Field(min_length=1, max_length=240)
    dataset_version: str = Field(min_length=1, max_length=160)
    provenance: Literal[
        "project_historical",
        "model_prediction",
        "detector_output",
        "synthetic",
        "user_supplied",
        "retrieved_guidance",
    ]
    period_start: str | None = Field(default=None, max_length=80)
    period_end: str | None = Field(default=None, max_length=80)
    units: str | None = Field(default=None, max_length=80)
    is_live_telemetry: bool = False


class EvidenceFact(FrozenContract):
    fact_id: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    value: str | int | float | bool
    units: str | None = Field(default=None, max_length=80)
    value_kind: Literal[
        "observation", "prediction", "detector_output", "derived_aggregate", "user_input"
    ]

    @field_validator("value")
    @classmethod
    def finite_numeric_values(cls, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Evidence values must be finite.")
        return value


class EvidenceEnvelope(FrozenContract):
    schema_version: Literal["evidence.v1"] = "evidence.v1"
    snapshot_id: str = Field(min_length=1, max_length=160)
    created_at: datetime
    persona: Literal["household", "commercial", "government", "system"]
    entity_ref: str | None = Field(default=None, max_length=160)
    sources: list[SourceReference] = Field(max_length=100)
    facts: list[EvidenceFact] = Field(max_length=1000)

    @model_validator(mode="after")
    def validate_lineage(self) -> "EvidenceEnvelope":
        source_ids = [source.source_id for source in self.sources]
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Evidence source identifiers must be unique.")
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("Evidence fact identifiers must be unique.")
        known_sources = set(source_ids)
        if any(fact.source_id not in known_sources for fact in self.facts):
            raise ValueError("Every fact must reference a source in the envelope.")
        return self


class GroundedClaim(FrozenContract):
    text: str = Field(min_length=1, max_length=1000)
    kind: Literal["observation", "possible_cause", "recommendation"]
    evidence_fact_ids: list[str] = Field(min_length=1, max_length=30)


class Citation(FrozenContract):
    source_id: str = Field(min_length=1, max_length=120)
    fact_ids: list[str] = Field(min_length=1, max_length=30)


class AIOutput(FrozenContract):
    schema_version: Literal["ai_output.v1"] = "ai_output.v1"
    narrative: str = Field(min_length=1, max_length=5000)
    claims: list[GroundedClaim] = Field(max_length=50)
    citations: list[Citation] = Field(max_length=50)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    confirmed_fault: Literal[False] = False


class GenerationRequest(FrozenContract):
    request_id: str = Field(min_length=1, max_length=160)
    prompt_key: str = Field(min_length=1, max_length=100)
    evidence: EvidenceEnvelope
    variables: dict[str, str] = Field(default_factory=dict, max_length=30)
    idempotency_key: str | None = Field(default=None, max_length=160)


class GenerationAuditEvent(FrozenContract):
    request_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str | None = Field(default=None, max_length=160)
    workflow: str = Field(min_length=1, max_length=120)
    prompt_key: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=120)
    outcome: Literal["succeeded", "failed", "rejected", "timed_out"]
    source_ids: list[str] = Field(max_length=100)
    duration_ms: float = Field(ge=0, le=3_600_000)
    output_chars: int = Field(ge=0, le=5000)
    error_code: str | None = Field(default=None, max_length=120)

