"""Paired single-agent and multi-agent evaluation for annotated test cases."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai.commercial.agents.supervisor import plan_request
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.graph import build_commercial_graph
from ai.commercial.schemas.communication import (
    CommercialRequest,
    SpecialistName,
    ToolObservation,
)
from ai.commercial.tools.protocol import CommercialTools
from ai.commercial.tools.registry import (
    RegistryCommercialTools,
    build_commercial_tool_registry,
)


class EvaluationCase(BaseModel):
    """A test query with optional human-authored expected behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=128)
    request: CommercialRequest
    expected_specialists: tuple[SpecialistName, ...] = ()
    expected_source_ids: tuple[str, ...] = ()
    expected_conflict: bool | None = None
    expected_recovery: bool = False
    require_feasible_schedule: bool = False


class RunMetrics(BaseModel):
    """Measured values for one execution of one annotated case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    task_completed: bool
    specialist_precision: float | None = None
    specialist_recall: float | None = None
    evidence_support_rate: float | None = None
    graph_source_recall: float | None = None
    tool_success_rate: float | None = None
    conflict_expectation_met: bool | None = None
    constraint_satisfied: bool | None = None
    recovery_succeeded: bool | None = None
    loop_detected: bool
    tool_calls: int
    llm_calls: int
    latency_ms: float
    estimated_model_cost: float | None = None


class CaseComparison(BaseModel):
    """Paired measurements for the same query and provider fixtures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    single_agent: RunMetrics
    multi_agent: RunMetrics


def _specialist_observation(
    specialist: SpecialistName,
    request: CommercialRequest,
    tools: CommercialTools,
) -> ToolObservation:
    if specialist == "peak_prediction":
        return tools.get_peak_forecast(
            request.factory_id,
            request.user_goal,
            request.building_id,
        )
    if specialist == "operations":
        return tools.retrieve_operational_context(
            request.factory_id,
            request.user_goal,
        )
    if specialist == "renewable":
        return tools.get_renewable_scenarios(
            request.factory_id,
            request.user_goal,
        )
    if request.optimization_inputs is None:
        return ToolObservation(
            status="unavailable",
            error={
                "code": "OPTIMIZATION_INPUT_UNAVAILABLE",
                "message": "No explicit optimization schedule was supplied.",
            },
        )
    return tools.optimize(
        request.factory_id,
        request.optimization_inputs.model_dump(mode="python"),
    )


def _single_agent_baseline(
    request: CommercialRequest,
    settings: CommercialSettings,
    tools: CommercialTools,
) -> dict[str, Any]:
    """Run the same deterministic plan and providers sequentially, without handoffs."""
    plan = plan_request(request.model_dump(mode="python"), settings)
    observations: list[ToolObservation] = []
    for assignment in plan.get("assignments", []):
        observations.append(
            _specialist_observation(assignment.specialist, request, tools)
        )
    used = {
        assignment.specialist
        for assignment in plan.get("assignments", [])
    }
    tool_calls = sum(
        not (
            assignment.specialist == "cost_optimization"
            and request.optimization_inputs is None
        )
        for assignment in plan.get("assignments", [])
    )
    tool_success_count = sum(
        observation.status == "available"
        for assignment, observation in zip(
            plan.get("assignments", []),
            observations,
        )
        if not (
            assignment.specialist == "cost_optimization"
            and request.optimization_inputs is None
        )
    )
    return {
        "status": (
            "passed"
            if observations and all(item.status == "available" for item in observations)
            else "incomplete"
        ),
        "assignments": list(used),
        "observations": observations,
        "tool_call_count": tool_calls,
        "tool_success_count": tool_success_count,
        "llm_call_count": 0,
        "step_count": len(observations) + 1,
        "rework_count": 0,
        "conflicts": [
            conflict
            for item in observations
            for conflict in item.conflicts
        ],
        "specialist_results": {},
        "optimization_result": next(
            (
                item
                for item in observations
                if item.status == "available"
                and "schedule" in item.data
            ),
            None,
        ),
    }


def _metrics(
    run: dict[str, Any],
    case: EvaluationCase,
    settings: CommercialSettings,
    *,
    duration_ms: float,
    multi_agent: bool,
) -> RunMetrics:
    actual_specialists = (
        {
            assignment.specialist
            for assignment in run.get("assignments", [])
        }
        if multi_agent
        else set(run.get("assignments", []))
    )
    expected_specialists = set(case.expected_specialists)
    if expected_specialists:
        true_positives = len(actual_specialists & expected_specialists)
        precision = true_positives / len(actual_specialists) if actual_specialists else 0.0
        recall = true_positives / len(expected_specialists)
    else:
        precision = None
        recall = None

    if multi_agent:
        specialist_results = list(
            run.get("specialist_results", {}).values()
        )
        status = str(run["final_response"]["status"])
        evidence_refs = run["final_response"]["evidence_refs"]
        conflicts = run["final_response"]["conflicts"]
        optimizer = run.get("optimization_result")
    else:
        specialist_results = []
        status = str(run["status"])
        evidence_refs = [
            reference.model_dump(mode="json")
            for observation in run["observations"]
            for reference in observation.evidence_refs
        ]
        conflicts = run["conflicts"]
        optimizer = run.get("optimization_result")

    findings_count = sum(
        len(result.findings) for result in specialist_results
    ) if multi_agent else sum(
        len(observation.findings) for observation in run["observations"]
    )
    supported_count = sum(
        len(result.findings) for result in specialist_results
        if result.evidence_refs
    ) if multi_agent else sum(
        len(observation.findings)
        for observation in run["observations"]
        if observation.evidence_refs
    )
    evidence_support = (
        supported_count / findings_count if findings_count else None
    )

    graph_source_recall = None
    if case.expected_source_ids:
        actual_sources = {
            reference.get("source_id")
            for reference in evidence_refs
        }
        graph_source_recall = (
            len(actual_sources & set(case.expected_source_ids))
            / len(set(case.expected_source_ids))
        )

    if case.expected_conflict is None:
        conflict_expectation_met = None
    else:
        conflict_expectation_met = bool(conflicts) == case.expected_conflict

    optimizer_available = (
        optimizer is not None
        and (
            optimizer.status == "completed"
            if multi_agent
            else optimizer.status == "available"
        )
    )
    if case.require_feasible_schedule:
        constraint_satisfied = bool(
            optimizer_available
            and "schedule" in optimizer.data
        )
    else:
        constraint_satisfied = None

    rework_count = run.get("rework_count", 0)
    recovery_succeeded = (
        rework_count > 0 and status == "passed"
        if case.expected_recovery
        else None
    )
    tool_calls = int(run.get("tool_call_count", 0))
    llm_calls = int(run.get("llm_call_count", 0))
    step_count = int(run.get("step_count", 0))
    return RunMetrics(
        status=status,
        task_completed=status == "passed",
        specialist_precision=precision,
        specialist_recall=recall,
        evidence_support_rate=evidence_support,
        graph_source_recall=graph_source_recall,
        tool_success_rate=(
            sum(result.status == "completed" for result in specialist_results)
            / tool_calls
            if multi_agent and tool_calls
            else (
                run["tool_success_count"] / tool_calls
                if not multi_agent and tool_calls
                else None
            )
        ),
        conflict_expectation_met=conflict_expectation_met,
        constraint_satisfied=constraint_satisfied,
        recovery_succeeded=recovery_succeeded,
        loop_detected=(
            tool_calls > settings.max_tool_calls
            or step_count > settings.max_graph_steps
        ),
        tool_calls=tool_calls,
        llm_calls=llm_calls,
        latency_ms=duration_ms,
        estimated_model_cost=None,
    )


def evaluate_cases(
    cases: tuple[EvaluationCase, ...],
    *,
    tools: CommercialTools,
    settings: CommercialSettings | None = None,
) -> tuple[CaseComparison, ...]:
    """Run annotated cases through sequential baseline and multi-agent graph."""
    resolved_settings = settings or CommercialSettings.from_env()
    registry_tools = RegistryCommercialTools(
        build_commercial_tool_registry(tools)
    )
    workflow = build_commercial_graph(
        tools=tools,
        settings=resolved_settings,
    )
    comparisons: list[CaseComparison] = []
    for case in cases:
        baseline_started = time.perf_counter()
        baseline = _single_agent_baseline(
            case.request,
            resolved_settings,
            registry_tools,
        )
        baseline_duration = (time.perf_counter() - baseline_started) * 1000
        multi_started = time.perf_counter()
        multi = workflow.invoke(case.request.model_dump(mode="python"))
        multi_duration = (time.perf_counter() - multi_started) * 1000
        comparisons.append(
            CaseComparison(
                case_id=case.case_id,
                single_agent=_metrics(
                    baseline,
                    case,
                    resolved_settings,
                    duration_ms=baseline_duration,
                    multi_agent=False,
                ),
                multi_agent=_metrics(
                    multi,
                    case,
                    resolved_settings,
                    duration_ms=multi_duration,
                    multi_agent=True,
                ),
            )
        )
    return tuple(comparisons)
