"""Shared execution helper for independently testable specialist nodes."""

from __future__ import annotations

from collections.abc import Callable

from ai.commercial.schemas.communication import (
    AgentResult,
    SpecialistName,
    TaskAssignment,
    ToolObservation,
)
from ai.commercial.schemas.state import CommercialState
from ai.commercial.tools.protocol import CommercialTools

ToolCall = Callable[
    [CommercialTools, str | None, str, str | None],
    ToolObservation,
]
TOOL_NAMES = {
    "peak_prediction": "peak_forecast",
    "operations": "operational_context_read",
    "renewable": "renewable_scenario_read",
}


def execute_specialist(
    state: CommercialState,
    tools: CommercialTools,
    specialist: SpecialistName,
    call_tool: ToolCall,
) -> dict:
    """Execute one assigned, allow-listed tool and return owned state updates."""
    assignment = next(
        (
            item
            for item in state.get("assignments", [])
            if item.specialist == specialist
        ),
        None,
    )
    if assignment is None:
        return {"step_count": 1}

    tool_name = TOOL_NAMES[specialist]
    if tool_name not in assignment.allowed_tools:
        raise PermissionError(
            f"Tool {tool_name!r} is not allowed for task {assignment.task_id!r}."
        )

    observation = call_tool(
        tools,
        state.get("factory_id"),
        assignment.goal,
        state.get("building_id"),
    )
    result = result_from_observation(assignment, observation)
    return {
        "specialist_results": {assignment.task_id: result},
        "evidence_refs": list(result.evidence_refs),
        "assumptions": list(result.assumptions),
        "conflicts": list(result.conflicts),
        "step_count": 1,
        "tool_call_count": 1,
    }


def result_from_observation(
    assignment: TaskAssignment,
    observation: ToolObservation,
) -> AgentResult:
    status = {
        "available": "completed",
        "unavailable": "unavailable",
        "failed": "failed",
    }[observation.status]
    return AgentResult(
        task_id=assignment.task_id,
        specialist=assignment.specialist,
        status=status,
        findings=observation.findings,
        evidence_refs=observation.evidence_refs,
        assumptions=observation.assumptions,
        conflicts=observation.conflicts,
        data=observation.data,
        error=observation.error,
    )
