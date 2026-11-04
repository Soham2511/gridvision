"""Deterministic request planner and specialist assignment node."""

from __future__ import annotations

import re

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.schemas.communication import (
    CommercialRequest,
    SpecialistName,
    TaskAssignment,
)
from ai.commercial.schemas.state import CommercialState
from ai.commercial.agents.planner import CommercialPlanner

SPECIALIST_TOOLS: dict[SpecialistName, tuple[str, ...]] = {
    "peak_prediction": ("peak_forecast",),
    "operations": ("operational_context_read",),
    "renewable": ("renewable_scenario_read",),
    "cost_optimization": ("cost_optimizer",),
}

SPECIALIST_OUTPUTS: dict[SpecialistName, str] = {
    "peak_prediction": "Evidence-backed Commercial building forecast and provenance",
    "operations": "Evidence-backed operational findings and constraints",
    "renewable": "Parameterized renewable scenarios and assumptions",
    "cost_optimization": "Feasible schedule and validated cost comparison",
}

OPTIMIZATION_TERMS = (
    "optimize",
    "optimise",
    "optimization",
    "optimisation",
    "schedule",
    "reschedule",
    "minimize",
    "minimise",
    "lowest cost",
    "cost minimization",
    "cost minimisation",
    "cost-minimization",
    "cost-minimisation",
    "dispatch",
    "cost savings",
    "energy cost",
)


def _contains_any_term(goal: str, terms: tuple[str, ...]) -> bool:
    normalized_goal = " ".join(goal.casefold().split())
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized_goal)
        for term in terms
    )


def plan_request(
    state: CommercialState,
    settings: CommercialSettings,
    planner: CommercialPlanner | None = None,
) -> dict:
    """Classify a request deterministically and produce bounded assignments."""
    request_fields = {
        key: state[key]
        for key in ("request_id", "factory_id", "building_id", "user_goal")
        if key in state
    }
    request = CommercialRequest.model_validate(request_fields)
    goal = request.user_goal.casefold()
    selected: list[SpecialistName]

    if planner is None:
        selected = []
        if _contains_any_term(
            goal,
            ("peak", "forecast", "forecasts", "demand", "demands", "load", "loads"),
        ):
            selected.append("peak_prediction")

        if _contains_any_term(
            goal,
            (
                "process",
                "processes",
                "machine",
                "machines",
                "factory",
                "factories",
                "production",
                "maintenance",
                "constraint",
                "constraints",
                "production line",
                "production lines",
                "sop",
                "shift",
                "shifts",
            ),
        ):
            selected.append("operations")

        if _contains_any_term(
            goal,
            ("solar", "wind", "battery", "batteries", "renewable", "renewables"),
        ):
            selected.append("renewable")

        if _contains_any_term(goal, OPTIMIZATION_TERMS):
            selected.append("cost_optimization")

        if not selected:
            selected.append("operations")
    else:
        selected = planner.select_specialists(request.user_goal)

    selected = list(dict.fromkeys(selected))
    retryable_agents = sum(
        specialist != "cost_optimization" for specialist in selected
    )
    worst_case_tool_calls = len(selected) + (
        retryable_agents * settings.max_rework_attempts
    )
    assignments = [
        TaskAssignment(
            task_id=f"{request.request_id}:{specialist}",
            specialist=specialist,
            goal=request.user_goal,
            scope=(
                request.building_id
                if specialist == "peak_prediction" and request.building_id
                else request.factory_id or "factory not specified"
            ),
            allowed_tools=SPECIALIST_TOOLS[specialist],
            constraints=(
                "Use only allow-listed tools.",
                "Do not invent factory data, evidence, or savings.",
            ),
            expected_output=SPECIALIST_OUTPUTS[specialist],
        )
        for specialist in selected
    ]

    if worst_case_tool_calls > settings.max_tool_calls:
        return {
            "plan": [
                "Escalate without tool calls: the requested plan exceeds the configured tool budget."
            ],
            "assignments": [],
            "errors": [
                "PLAN_EXCEEDS_TOOL_BUDGET: "
                f"up to {worst_case_tool_calls} calls may be required; "
                f"limit is {settings.max_tool_calls}."
            ],
            "step_count": 1,
        }

    return {
        "plan": [f"Run {specialist}." for specialist in selected],
        "assignments": assignments,
        "step_count": 1,
    }
