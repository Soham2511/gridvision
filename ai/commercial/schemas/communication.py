"""Pydantic contracts for requests, agent handoffs, evidence, and validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai.commercial.schemas.optimization import ScheduleInput

SpecialistName = Literal[
    "peak_prediction",
    "operations",
    "renewable",
    "cost_optimization",
]


class ContractModel(BaseModel):
    """Base contract that rejects undeclared fields and mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CommercialRequest(ContractModel):
    """User request accepted by the Commercial workflow."""

    request_id: str = Field(min_length=1, max_length=128)
    factory_id: str | None = Field(default=None, min_length=1, max_length=128)
    building_id: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]{0,15}$",
    )
    user_goal: str = Field(min_length=1, max_length=2000)
    optimization_inputs: ScheduleInput | None = None


class TaskAssignment(ContractModel):
    """Bounded, typed handoff from the supervisor to one specialist."""

    task_id: str = Field(min_length=1, max_length=160)
    specialist: SpecialistName
    goal: str = Field(min_length=1, max_length=2000)
    scope: str = Field(min_length=1, max_length=1000)
    allowed_tools: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    expected_output: str = Field(min_length=1, max_length=500)
    status: Literal["pending", "completed", "failed"] = "pending"


class EvidenceRef(ContractModel):
    """Provenance reference attached to an agent finding."""

    source_id: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=80)
    locator: str | None = Field(default=None, max_length=500)
    excerpt: str | None = Field(default=None, max_length=4000)
    observed_at: datetime | None = None
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    synthetic: bool = False


class AgentError(ContractModel):
    """Structured failure or unavailability reported by a tool or agent."""

    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False


class ToolObservation(ContractModel):
    """Validated response from an injected specialist tool."""

    status: Literal["available", "unavailable", "failed"]
    findings: tuple[str, ...] = ()
    data: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    assumptions: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    error: AgentError | None = None


class AgentResult(ContractModel):
    """Structured result returned by a specialist node."""

    task_id: str
    specialist: SpecialistName
    status: Literal["completed", "unavailable", "failed"]
    findings: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    assumptions: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    data: dict[str, Any] = Field(default_factory=dict)
    error: AgentError | None = None


class ValidationReport(ContractModel):
    """Critic outcome and unresolved validation issues."""

    status: Literal["passed", "incomplete", "needs_rework", "escalated"]
    issues: tuple[str, ...] = ()
    evidence_count: int = Field(default=0, ge=0)


class FinalResponse(ContractModel):
    """Validated shape of the user-facing workflow response."""

    request_id: str | None
    factory_id: str | None
    status: Literal["passed", "incomplete", "needs_rework", "escalated"]
    summary: str
    findings: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    assumptions: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    validation: ValidationReport
    errors: tuple[str, ...] = ()
