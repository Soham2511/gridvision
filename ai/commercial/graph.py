"""LangGraph composition for the bounded Commercial multi-agent workflow."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ai.commercial.agents.cost_optimization import run_cost_optimization
from ai.commercial.agents.finalizer import finalize_response
from ai.commercial.agents.operations import run_operations
from ai.commercial.agents.peak_prediction import run_peak_prediction
from ai.commercial.agents.planner import (
    CommercialPlanner,
    GroqPlanner,
    GroqPlannerError,
)
from ai.commercial.agents.renewable import run_renewable
from ai.commercial.agents.supervisor import plan_request
from ai.commercial.agents.validator import validate_results
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.schemas.communication import CommercialRequest
from ai.commercial.schemas.state import CommercialState
from ai.commercial.tools.document_rag_tools import DocumentRAGCommercialTools
from ai.commercial.tools.protocol import CommercialTools
from ai.commercial.tools.registry import (
    RegistryCommercialTools,
    build_commercial_tool_registry,
)

SPECIALIST_NODES = (
    "peak_prediction",
    "operations",
    "renewable",
)
MAX_TRACE_MESSAGE_LENGTH = 500
logger = logging.getLogger("gridvision.commercial.workflow")
GREETING_PATTERN = re.compile(
    r"(?:hi+|hello+|hey+|howdy|good (?:morning|afternoon|evening))[.!?,\s]*",
    re.IGNORECASE,
)


class _NodeExecutionError(RuntimeError):
    def __init__(
        self,
        node_id: str,
        error_type: str,
        duration_ms: float,
    ) -> None:
        super().__init__(f"Workflow node {node_id!r} failed ({error_type}).")
        self.node_id = node_id
        self.error_type = error_type
        self.duration_ms = duration_ms


class WorkflowExecutionError(RuntimeError):
    """Safe workflow failure details for the local UI."""

    def __init__(
        self,
        *,
        failed_node: str,
        error_type: str,
        execution_trace: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            f"Workflow node {failed_node!r} failed ({error_type})."
        )
        self.failed_node = failed_node
        self.error_type = error_type
        self.execution_trace = execution_trace


def _trace_summary(result: dict[str, Any]) -> tuple[str, str | None]:
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        return "error", str(errors[0])[:MAX_TRACE_MESSAGE_LENGTH]

    specialist_results = result.get("specialist_results")
    if isinstance(specialist_results, dict):
        for specialist_result in specialist_results.values():
            status = getattr(specialist_result, "status", None)
            error = getattr(specialist_result, "error", None)
            if status == "failed":
                message = getattr(error, "message", None)
                return (
                    "error",
                    str(message or "The specialist failed.")[
                        :MAX_TRACE_MESSAGE_LENGTH
                    ],
                )
            if status == "unavailable":
                message = getattr(error, "message", None)
                return (
                    "warning",
                    str(message or "Required evidence or data is unavailable.")[
                        :MAX_TRACE_MESSAGE_LENGTH
                    ],
                )

    report = result.get("validation_status")
    status = getattr(report, "status", None)
    if status in {"incomplete", "needs_rework", "escalated"}:
        issues = getattr(report, "issues", ())
        return (
            "warning" if status != "escalated" else "error",
            str(issues[0])[:MAX_TRACE_MESSAGE_LENGTH]
            if issues
            else f"Workflow validation status: {status}.",
        )
    return "completed", None


def _traced_node(
    node_name: str,
    handler: Callable[[CommercialState], dict[str, Any]],
) -> Callable[[CommercialState], dict[str, Any]]:
    """Log bounded node lifecycle metadata without logging prompts or evidence."""
    def invoke(state: CommercialState) -> dict[str, Any]:
        started = time.perf_counter()
        request_id = state.get("request_id")
        logger.info(
            "commercial_node_started",
            extra={
                "event": {
                    "request_id": request_id,
                    "node_id": node_name,
                }
            },
        )
        try:
            result = handler(state)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            logger.error(
                "commercial_node_failed",
                extra={
                    "event": {
                        "request_id": request_id,
                        "node_id": node_name,
                        "error_type": type(exc).__name__,
                        "duration_ms": duration_ms,
                    }
                },
            )
            raise _NodeExecutionError(
                node_id=node_name,
                error_type=type(exc).__name__,
                duration_ms=duration_ms,
            ) from exc
        status, message = _trace_summary(result)
        logger.info(
            "commercial_node_completed",
            extra={
                "event": {
                    "request_id": request_id,
                    "node_id": node_name,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                    "step_count": result.get("step_count", 0),
                    "tool_call_count": result.get("tool_call_count", 0),
                    "llm_call_count": result.get("llm_call_count", 0),
                }
            },
        )
        return {
            **result,
            "execution_trace": [
                {
                    "node_id": node_name,
                    "status": status,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                    **({"message": message} if message else {}),
                }
            ],
        }

    return invoke


class CommercialWorkflow:
    """Compiled workflow that applies its configured recursion bound by default."""

    def __init__(self, compiled_graph, settings: CommercialSettings) -> None:
        self._compiled_graph = compiled_graph
        self._settings = settings

    def invoke(self, input: dict, config: dict | None = None) -> dict:
        request = CommercialRequest.model_validate(input)
        invoke_config = dict(config or {})
        requested_limit = invoke_config.get(
            "recursion_limit", self._settings.max_graph_steps
        )
        invoke_config["recursion_limit"] = min(
            requested_limit,
            self._settings.max_graph_steps,
        )
        latest_state: dict[str, Any] = {}
        try:
            for value in self._compiled_graph.stream(
                request.model_dump(),
                config=invoke_config,
                stream_mode="values",
            ):
                if isinstance(value, dict):
                    latest_state = value
        except _NodeExecutionError as exc:
            trace = list(latest_state.get("execution_trace", []))
            trace.append(
                {
                    "node_id": exc.node_id,
                    "status": "error",
                    "duration_ms": exc.duration_ms,
                    "message": f"Node failed with {exc.error_type}.",
                }
            )
            raise WorkflowExecutionError(
                failed_node=exc.node_id,
                error_type=exc.error_type,
                execution_trace=trace,
            ) from exc
        return latest_state


def _validate_request(state: CommercialState) -> dict:
    request_fields = {
        key: state[key]
        for key in (
            "request_id",
            "factory_id",
            "building_id",
            "user_goal",
            "optimization_inputs",
            "conversation_history",
        )
        if key in state
    }
    request = CommercialRequest.model_validate(request_fields)
    return {
        "request_id": request.request_id,
        "factory_id": request.factory_id,
        "building_id": request.building_id,
        "user_goal": request.user_goal,
        "conversation_history": list(request.conversation_history),
        "optimization_inputs": (
            request.optimization_inputs.model_dump(mode="python")
            if request.optimization_inputs is not None
            else None
        ),
        "rework_count": 0,
        "step_count": 1,
        "llm_call_count": 0,
    }


def _route_specialists(state: CommercialState) -> list[str]:
    if GREETING_PATTERN.fullmatch(state.get("user_goal", "").strip()):
        return ["greeting"]
    if state.get("errors"):
        return ["aggregate"]
    selected = [
        assignment.specialist
        for assignment in state.get("assignments", [])
        if assignment.specialist in SPECIALIST_NODES
    ]
    return selected or ["aggregate"]


def _respond_to_greeting(state: CommercialState) -> dict:
    response = {
        "request_id": state.get("request_id"),
        "factory_id": state.get("factory_id"),
        "status": "passed",
        "summary": (
            "Hi! I can help with factory operations, uploaded documents, "
            "energy forecasts, renewable scenarios, or schedule optimization."
        ),
        "findings": [],
        "evidence_refs": [],
        "assumptions": [],
        "conflicts": [],
        "validation": {
            "status": "passed",
            "issues": [],
            "evidence_count": 0,
        },
        "errors": [],
    }
    return {"final_response": response, "step_count": 1}


def _aggregate(state: CommercialState) -> dict:
    optimizer_input = state.get("optimization_inputs")
    return {
        "optimization_input": optimizer_input or {},
        "step_count": 1,
    }


def _route_optimizer(state: CommercialState) -> Literal["cost_optimization", "validator"]:
    selected = any(
        assignment.specialist == "cost_optimization"
        for assignment in state.get("assignments", [])
    )
    return "cost_optimization" if selected else "validator"


def _route_after_validation(
    state: CommercialState,
    settings: CommercialSettings,
) -> list[str]:
    report = state.get("validation_status")
    if (
        report is None
        or report.status != "needs_rework"
        or state.get("rework_count", 0) > settings.max_rework_attempts
    ):
        return ["finalizer"]

    failed_specialists = {
        result.specialist
        for result in state.get("specialist_results", {}).values()
        if result.status == "failed" and result.specialist in SPECIALIST_NODES
    }
    return sorted(failed_specialists) or ["finalizer"]


def build_commercial_graph(
    tools: CommercialTools | None = None,
    settings: CommercialSettings | None = None,
) -> CommercialWorkflow:
    """Build a compiled graph with injected tools and validated execution limits."""
    resolved_settings = settings or CommercialSettings.from_env()
    provider_tools = tools or DocumentRAGCommercialTools(
        resolved_settings.rag_documents,
        settings=resolved_settings,
    )
    resolved_tools = RegistryCommercialTools(
        build_commercial_tool_registry(provider_tools)
    )
    planner = None
    if resolved_settings.llm_provider == "groq":
        planner = GroqPlanner(
            api_key_file=resolved_settings.groq_api_key_file,
            base_url=resolved_settings.groq_base_url,
            model=resolved_settings.groq_model,
            timeout_seconds=resolved_settings.groq_timeout_seconds,
        )

    workflow = StateGraph(
        CommercialState,
        input_schema=CommercialRequest,
    )
    workflow.add_node(
        "validate_request",
        _traced_node("validate_request", _validate_request),
    )
    workflow.add_node(
        "supervisor",
        _traced_node(
            "supervisor",
            lambda state: _plan_with_provider(
                state,
                resolved_settings,
                planner,
            ),
        ),
    )
    workflow.add_node(
        "greeting",
        _traced_node("greeting", _respond_to_greeting),
    )
    workflow.add_node(
        "peak_prediction",
        _traced_node(
            "peak_prediction",
            lambda state: run_peak_prediction(state, resolved_tools),
        ),
    )
    workflow.add_node(
        "operations",
        _traced_node(
            "operations",
            lambda state: run_operations(state, resolved_tools),
        ),
    )
    workflow.add_node(
        "renewable",
        _traced_node(
            "renewable",
            lambda state: run_renewable(state, resolved_tools),
        ),
    )
    workflow.add_node("aggregate", _traced_node("aggregate", _aggregate))
    workflow.add_node(
        "cost_optimization",
        _traced_node(
            "cost_optimization",
            lambda state: run_cost_optimization(state, resolved_tools),
        ),
    )
    workflow.add_node(
        "validator",
        _traced_node(
            "validator",
            lambda state: validate_results(state, resolved_settings),
        ),
    )
    workflow.add_node(
        "finalizer",
        _traced_node(
            "finalizer",
            lambda state: finalize_response(state, planner),
        ),
    )

    workflow.add_edge(START, "validate_request")
    workflow.add_edge("validate_request", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        _route_specialists,
        {
            "peak_prediction": "peak_prediction",
            "operations": "operations",
            "renewable": "renewable",
            "aggregate": "aggregate",
            "greeting": "greeting",
        },
    )
    workflow.add_edge("greeting", END)
    for specialist in SPECIALIST_NODES:
        workflow.add_edge(specialist, "aggregate")
    workflow.add_conditional_edges(
        "aggregate",
        _route_optimizer,
        {
            "cost_optimization": "cost_optimization",
            "validator": "validator",
        },
    )
    workflow.add_edge("cost_optimization", "validator")
    workflow.add_conditional_edges(
        "validator",
        lambda state: _route_after_validation(state, resolved_settings),
        {
            "peak_prediction": "peak_prediction",
            "operations": "operations",
            "renewable": "renewable",
            "finalizer": "finalizer",
        },
    )
    workflow.add_edge("finalizer", END)

    return CommercialWorkflow(workflow.compile(), resolved_settings)


def _plan_with_provider(
    state: CommercialState,
    settings: CommercialSettings,
    planner: CommercialPlanner | None,
) -> dict:
    if GREETING_PATTERN.fullmatch(state.get("user_goal", "").strip()):
        return {
            "plan": ["Respond with supported assistant capabilities."],
            "assignments": [],
            "step_count": 1,
        }
    if planner is None:
        return plan_request(state, settings)
    try:
        result = plan_request(state, settings, planner)
    except Exception as exc:
        provider = settings.llm_provider.upper()
        error = f"{provider}_PLANNING_FAILED: {type(exc).__name__}"
        if isinstance(exc, GroqPlannerError):
            error = f"{error}: {exc}"
        return {
            "plan": [f"Escalate: {provider} planning failed."],
            "assignments": [],
            "errors": [error],
            "llm_call_count": 1,
            "step_count": 1,
        }
    return {**result, "llm_call_count": 1}
