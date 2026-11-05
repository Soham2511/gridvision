"""LangGraph shared state and deterministic concurrent merge rules."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from ai.commercial.schemas.communication import (
    AgentResult,
    CommercialConversationMessage,
    EvidenceRef,
    TaskAssignment,
    ValidationReport,
)
from ai.commercial.schemas.optimization import ScheduleInput


def merge_results(
    current: dict[str, AgentResult],
    update: dict[str, AgentResult],
) -> dict[str, AgentResult]:
    """Merge task-keyed results, allowing a bounded retry to replace its result."""
    return {**current, **update}


def merge_evidence(
    current: list[EvidenceRef],
    update: list[EvidenceRef],
) -> list[EvidenceRef]:
    """Append evidence in stable order while removing duplicate references."""
    merged = list(current)
    seen = {
        (item.source_id, item.locator, item.excerpt, item.synthetic)
        for item in current
    }
    for item in update:
        key = (item.source_id, item.locator, item.excerpt, item.synthetic)
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def merge_strings(current: list[str], update: list[str]) -> list[str]:
    """Append strings once, preserving first-seen order."""
    merged = list(current)
    seen = set(current)
    for item in update:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


class CommercialState(TypedDict, total=False):
    """Shared graph state; node ownership is documented in the package README."""

    request_id: str
    factory_id: str | None
    building_id: str | None
    user_goal: str
    conversation_history: list[CommercialConversationMessage]
    plan: list[str]
    assignments: list[TaskAssignment]
    specialist_results: Annotated[
        dict[str, AgentResult], merge_results
    ]
    evidence_refs: Annotated[list[EvidenceRef], merge_evidence]
    assumptions: Annotated[list[str], merge_strings]
    conflicts: Annotated[list[str], merge_strings]
    optimization_input: dict[str, Any] | None
    optimization_inputs: ScheduleInput | None
    optimization_result: AgentResult | None
    validation_status: ValidationReport | None
    step_count: Annotated[int, operator.add]
    llm_call_count: Annotated[int, operator.add]
    tool_call_count: Annotated[int, operator.add]
    rework_count: int
    errors: Annotated[list[str], merge_strings]
    final_response: dict[str, Any] | None
    execution_trace: Annotated[list[dict[str, Any]], operator.add]
