"""LangGraph tool selection, bounded retrieval, validation and response flow."""

from __future__ import annotations

import re
from typing import Any, TypedDict

from .context import AuthenticatedRequestContext
from .providers.llm_provider import ChatModelProvider
from .tools.base import ToolError, ToolRegistry


class State(TypedDict, total=False):
    message: str
    history: list[dict[str, str]]
    calls: list[dict]
    attempted: list[str]
    results: list[dict]
    errors: list[dict]
    rounds: int
    answer: str
    clarification: bool
    unavailable: bool


class RunContext(TypedDict):
    context: AuthenticatedRequestContext
    available_sources: set[str]


def _unsupported(message: str) -> str | None:
    if any(term in message.casefold() for term in ("company profile", "company information", "equipment", "operating hours", "business hours")):
        return "GridVision has no authoritative company profile, equipment inventory, or operating-hours source configured, so I cannot retrieve that information."
    return None


def _intent(message: str) -> set[str]:
    text, names = message.casefold(), set()
    if any(x in text for x in ("profile", "details", "building information")):
        names.update({"get_consumer_profile", "get_building_details", "get_regional_information"})
    if any(x in text for x in ("consumption", "consumed", "usage", "history", "historical", "how much", "energy", "kwh")):
        names.add("get_historical_consumption")
    if any(x in text for x in ("forecast", "predict", "prediction", "future")):
        names.add("get_energy_forecast")
    if any(x in text for x in ("anomaly", "anomalies", "abnormal", "outlier")):
        names.add("get_anomaly_predictions")
    if any(x in text for x in ("segment", "segmentation", "cluster")):
        names.add("get_segmentation_results")
    if any(x in text for x in ("model metadata", "model version", "model status", "model information", "what model", "model details")):
        names.add("get_model_metadata")
    if any(x in text for x in ("region", "regional", "grid", "government")):
        names.add("get_regional_information")
    return names


def _numbers(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_numbers(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(_numbers(v) for v in value)) if value else set()
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {str(value)}
    if isinstance(value, str):
        return set(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?%?", value))
    return set()


def _numeric_fidelity(answer: str, results: list[dict]) -> bool:
    evidence = _numbers(results)
    return all(token.replace(",", "") in evidence or token.rstrip("%") in evidence for token in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?%?", answer))


def build_graph(*, registry: ToolRegistry, llm: ChatModelProvider, max_tool_calls: int, max_graph_steps: int, checkpointer: Any):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("LangGraph is required to execute the agent.") from exc

    def plan(state: State, runtime):
        if _unsupported(state["message"]):
            return {"calls": [], "rounds": state.get("rounds", 0) + 1, "unavailable": True}
        trusted = runtime.context["context"]
        available_sources = runtime.context["available_sources"]
        allowed = registry.available_tools(trusted, available_sources)
        relevant = _intent(state["message"])
        if relevant:
            allowed = [t for t in allowed if t.name in relevant]
            if not allowed:
                return {"calls": [], "rounds": state.get("rounds", 0) + 1, "unavailable": True}
        history = list(state.get("history", []))
        scopes = {k: next(iter(v)) for k, v in trusted.entity_scopes.items() if len(v) == 1 and next(iter(v)) not in {"*", "system"}}
        if scopes:
            history.append({"role": "assistant", "content": "Server-authorized single entity IDs for resolving this turn: " + repr(scopes)})
        if state.get("results"):
            import json
            history.append({"role": "assistant", "content": "Evidence already retrieved; do not repeat tools unless more is needed: " + json.dumps(state["results"], default=str)})
        calls = llm.plan(state["message"], history, allowed)
        attempted = set(state.get("attempted", []))
        calls = [c for c in calls if f"{c.get('name')}:{c.get('arguments', {})}" not in attempted]
        calls = calls[:max(0, max_tool_calls - len(attempted))]
        return {"calls": calls, "rounds": state.get("rounds", 0) + 1}

    def execute(state: State, runtime):
        import concurrent.futures
        trusted = runtime.context["context"]
        available_sources = runtime.context["available_sources"]
        allowed = {t.name for t in registry.available_tools(trusted, available_sources)}
        calls, attempted = state.get("calls", []), list(state.get("attempted", []))
        results, errors = list(state.get("results", [])), list(state.get("errors", []))
        def run(call):
            if call.get("name") not in allowed:
                raise ToolError("FORBIDDEN", "Tool is not authorized or available.")
            return registry.execute(call["name"], call.get("arguments", {}), context=trusted, available_sources=available_sources).model_dump(mode="json")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(calls)))) as pool:
            futures = {pool.submit(run, call): call for call in calls}
            for future in concurrent.futures.as_completed(futures):
                call = futures[future]
                attempted.append(f"{call.get('name')}:{call.get('arguments', {})}")
                try:
                    results.append(future.result())
                except ToolError as exc:
                    errors.append({"tool": str(call.get("name", "")), "code": exc.code})
                except Exception:
                    errors.append({"tool": str(call.get("name", "")), "code": "TOOL_FAILED"})
        return {"calls": [], "attempted": attempted, "results": results, "errors": errors}

    def route(state: State):
        return "plan" if state.get("rounds", 0) < min(2, max_graph_steps) and state.get("results") else "respond"

    def respond(state: State):
        if not state.get("results"):
            if state.get("errors"):
                return {"answer": "I could not retrieve the requested GridVision information because the required tool failed or was unavailable.", "clarification": False}
            unavailable = _unsupported(state["message"])
            if state.get("unavailable"):
                return {"answer": unavailable or "The GridVision source or authorized retrieval tool needed for this request is unavailable.", "clarification": False}
            return {"answer": unavailable or "Which consumer, building, or region and time period should I look up?", "clarification": unavailable is None}
        answer = llm.answer(state["message"], state.get("history", []), state["results"])
        if not _numeric_fidelity(answer, state["results"]):
            import json
            answer = "Retrieved values are shown exactly as returned by GridVision:\n" + json.dumps(state["results"], ensure_ascii=False, indent=2, default=str)
        if state.get("errors"):
            failed = ", ".join(sorted({x["tool"] for x in state["errors"]}))
            answer += f"\n\nSome requested information could not be retrieved ({failed}); these results are partial."
        return {"answer": answer, "clarification": False}

    graph = StateGraph(State, context_schema=RunContext)
    graph.add_node("plan", plan)
    graph.add_node("execute", execute)
    graph.add_node("respond", respond)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges("execute", route, {"plan": "plan", "respond": "respond"})
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)
