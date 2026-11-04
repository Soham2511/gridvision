"""Cost optimization specialist node."""

from __future__ import annotations

from ai.commercial.agents.common import result_from_observation
from ai.commercial.schemas.communication import AgentError, ToolObservation
from ai.commercial.schemas.state import CommercialState
from ai.commercial.tools.protocol import CommercialTools


def run_cost_optimization(
    state: CommercialState,
    tools: CommercialTools,
) -> dict:
    assignment = next(
        (
            item
            for item in state.get("assignments", [])
            if item.specialist == "cost_optimization"
        ),
        None,
    )
    if assignment is None:
        return {"step_count": 1}
    if "cost_optimizer" not in assignment.allowed_tools:
        raise PermissionError(
            "Tool 'cost_optimizer' is not allowed for "
            f"task {assignment.task_id!r}."
        )

    optimization_input = state.get("optimization_input") or {}
    if optimization_input:
        observation = tools.optimize(
            state.get("factory_id"),
            optimization_input,
        )
        tool_call_count = 1
    else:
        observation = ToolObservation(
            status="unavailable",
            error=AgentError(
                code="OPTIMIZATION_INPUT_UNAVAILABLE",
                message=(
                    "Required structured inputs are unavailable; the optimizer "
                    "was not called."
                ),
            ),
        )
        tool_call_count = 0

    result = result_from_observation(assignment, observation)
    return {
        "specialist_results": {assignment.task_id: result},
        "optimization_result": result,
        "evidence_refs": list(result.evidence_refs),
        "assumptions": list(result.assumptions),
        "conflicts": list(result.conflicts),
        "step_count": 1,
        "tool_call_count": tool_call_count,
    }
