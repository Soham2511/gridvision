"""LangGraph orchestration using only registered GridVision tools."""

from __future__ import annotations

import json
import logging
import queue
import re
import urllib.parse
import urllib.error
import urllib.request
from datetime import date
from typing import Any, TypedDict
from uuid import uuid4

from ai.anamoly.agents.query_router import classify_query, route_prompt
from ai.anamoly.date_guardrails import dataset_date_bounds, validate_requested_dates
from ai.anamoly.agents.recommendation_agent import (
    RECOMMENDATION_SYSTEM_PROMPT,
    recommendation_context,
)
from ai.anamoly.config import get_settings
from ai.anamoly.evaluation.groundedness import evaluate_grounding
from ai.anamoly.tools.gridvision_tools import build_registry
from ai.anamoly.tools.registry import (
    ToolConfirmationRequired,
    ToolPermissionError,
)
from ai.anamoly.tools.web_search_tools import register_web_search_tool
from ai.anamoly.tools.export_tools import register_export_tools

logger = logging.getLogger("gridvision.anomaly.agent")


class AssistantState(TypedDict, total=False):
    prompt: str
    persona: str
    conversation_id: str
    principal: str | None
    context: dict[str, Any]
    route: dict[str, Any]
    tool_result: Any
    references: list[dict[str, Any]]
    answer: str
    run_id: str | None
    event_id: str | None
    conversation_state: dict[str, Any]
    status: str
    citations: list[dict[str, Any]]
    downloads: list[dict[str, str]]
    grounding: dict[str, Any]


def _ollama_chat(
    messages: list[dict[str, str]], on_token: Any | None = None
) -> str:
    settings = get_settings()
    payload = json.dumps(
        {
            "model": settings.chat_model,
            "messages": messages,
            "stream": on_token is not None,
            "options": {"temperature": 0.15},
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.ollama_api_key and urllib.parse.urlparse(settings.ollama_base_url).scheme == "https":
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    request = urllib.request.Request(
        f"{settings.ollama_base_url}/api/chat",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.request_timeout_seconds
        ) as response:
            if on_token is None:
                result = json.loads(response.read().decode("utf-8"))
                answer = result.get("message", {}).get("content")
            else:
                parts: list[str] = []
                for line in response:
                    if not line.strip():
                        continue
                    result = json.loads(line.decode("utf-8"))
                    token = result.get("message", {}).get("content", "")
                    if token:
                        parts.append(token)
                        on_token(token)
                    if result.get("done"):
                        break
                answer = "".join(parts)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ollama chat request failed: {exc}") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Ollama returned an empty chat response.")
    return answer.strip()


class AnomalyAssistant:
    """Run a bounded LangGraph workflow over existing GridVision services."""

    def __init__(
        self,
        anomaly_service: Any,
        *,
        data_provider: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError("The assistant requires the langgraph dependency.") from exc
        self.anomaly_service = anomaly_service
        self.data_provider = data_provider
        self.memory = memory
        self.registry = build_registry()
        register_web_search_tool(self.registry)
        register_export_tools(self.registry)
        graph = StateGraph(AssistantState)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("respond", self._respond)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "respond")
        graph.add_edge("respond", END)
        self.graph = graph.compile()

    def ask(
        self,
        prompt: str,
        *,
        persona: str,
        entity_id: str | None = None,
        conversation_id: str | None = None,
        principal: str | None = None,
        authenticated_persona: str | None = None,
        authorized_customer_ids: list[int] | None = None,
        stream_callback: Any | None = None,
    ) -> dict[str, Any]:
        conversation_id = conversation_id or uuid4().hex
        context = {
            "anomaly_service": self.anomaly_service,
            "data_provider": self.data_provider,
            "entity_id": entity_id,
            "persona": persona,
            "authorized_customer_ids": authorized_customer_ids or [],
            "principal": principal,
            "authenticated_persona": authenticated_persona,
            "stream_callback": stream_callback,
        }
        prior_messages = (
            self.memory.load(principal, conversation_id, persona)
            if self.memory is not None
            else []
        )
        structured_context_loader = getattr(
            self.memory, "latest_structured_context", None
        )
        conversation_state = (
            structured_context_loader(principal, conversation_id, persona)
            if callable(structured_context_loader)
            else {}
        )
        state = self.graph.invoke(
            {
                "prompt": prompt,
                "persona": persona,
                "conversation_id": conversation_id,
                "principal": principal,
                "context": {
                    **context,
                    "prior_messages": prior_messages[-8:],
                    "conversation_state": conversation_state,
                },
                "status": "success",
            }
        )
        if self.memory is not None:
            tool_result = state.get("tool_result") or {}
            self.memory.append(
                principal,
                conversation_id,
                persona,
                prompt,
                state["answer"],
                current_run_id=state.get("run_id"),
                selected_event_id=state.get("event_id"),
                run_ids=tool_result.get("run_ids", []),
                start_date=tool_result.get("start_date"),
                end_date=tool_result.get("end_date"),
                structured_context=state.get("conversation_state", conversation_state),
            )
        self._trace(state, persona)
        return {
            "answer": state["answer"],
            "persona": persona,
            "entityId": entity_id,
            "conversationId": conversation_id,
            "status": state.get("status", "success"),
            "citations": state.get("citations", []),
            "runReferences": ([state["run_id"]] if state.get("run_id") else []),
            "downloads": state.get("downloads", []),
            "grounding": state.get("grounding", {}),
            "charts": state.get("charts", []),
        }

    def _retrieve(self, state: AssistantState) -> dict[str, Any]:
        context = state["context"]
        route = classify_query(
            state["prompt"],
            context.get("prior_messages", []),
            conversation_state=context.get("conversation_state", {}),
        )
        if route["intent"] == "confirmation_response":
            pending_dates = self._pending_analysis_confirmation(context)
            if pending_dates is not None:
                route = {
                    "intent": "analysis_execution",
                    **pending_dates,
                    "confirmed_by_user": True,
                }
        persona = state["persona"]
        result: Any = None
        references: list[dict[str, Any]] = []
        run_id: str | None = None
        event_id = route.get("event_id")
        status = "success"
        try:
            if route["intent"] == "confirmation_response":
                result = {
                    "message": (
                        "There is no pending analysis request in this conversation "
                        "to confirm. Please provide a supported date range."
                    )
                }
            elif route["intent"] == "confirmation_declined":
                result = {"message": "Okay. I will not start a new analysis."}
            elif route["intent"] == "historical_anomaly_query":
                if not route.get("start_date"):
                    result = {
                        "message": (
                            "Please specify a date or period within the available "
                            "anomaly dataset to look up historical results."
                        )
                    }
                else:
                    requested_start, requested_end = validate_requested_dates(
                        self.anomaly_service,
                        route["start_date"],
                        route["end_date"],
                    )
                    period = self.registry.execute(
                        "find_runs_for_period",
                        {
                            "start_date": requested_start.isoformat(),
                            "end_date": requested_end.isoformat(),
                        },
                        persona=persona,
                        context=context,
                    )
                    if not period["available"]:
                        result = {
                            "message": (
                                f"The period {requested_start.isoformat()} through "
                                f"{requested_end.isoformat()} has not yet been fully "
                                "analysed. Would you like me to run a new analysis "
                                "using the existing defaults?"
                            ),
                            "available": False,
                        }
                    else:
                        # A period can be covered by several runs. Bind the active
                        # run to the newest single run that covers the whole
                        # requested interval, instead of whichever run starts first.
                        run_summaries = {
                            str(item.get("analysis_id")): item
                            for item in self.anomaly_service.list_runs(limit=1000)
                            if item.get("analysis_id") in period["run_ids"]
                        }
                        full_period_runs = []
                        for candidate_id in period["run_ids"]:
                            summary = run_summaries.get(str(candidate_id), {})
                            request = summary.get("request", {})
                            try:
                                candidate_start = date.fromisoformat(request["start_date"])
                                candidate_end = date.fromisoformat(request["end_date"])
                            except (KeyError, TypeError, ValueError):
                                continue
                            if candidate_start <= requested_start and candidate_end >= requested_end:
                                full_period_runs.append(summary)
                        if full_period_runs:
                            active_summary = max(
                                full_period_runs,
                                key=lambda item: str(item.get("created_at", "")),
                            )
                            run_id = str(active_summary["analysis_id"])
                        else:
                            run_id = (
                                str(period["run_ids"][0])
                                if len(period["run_ids"]) == 1 else None
                            )
                        result = self.registry.execute(
                            "query_events",
                            {
                                "start_date": requested_start.isoformat(),
                                "end_date": requested_end.isoformat(),
                                "limit": 100,
                            },
                            persona=persona,
                            context=context,
                        )
                        anomalies = self.registry.execute(
                            "query_anomalies",
                            {
                                "start_date": requested_start.isoformat(),
                                "end_date": requested_end.isoformat(),
                                "limit": 1000,
                            },
                            persona=persona,
                            context=context,
                        )
                        result["anomaly_windows"] = anomalies["items"]
                        result["run_ids"] = period["run_ids"]
                        run_id = run_id or (result.get("run_ids") or [None])[0]
                        if len(result.get("items", [])) == 1:
                            event_id = result["items"][0].get(
                                "event_id", result["items"][0].get("id")
                            )
            elif route["intent"] == "event_detail_followup":
                start, end = validate_requested_dates(
                    self.anomaly_service, route["start_date"], route["end_date"]
                )
                result = self.registry.execute(
                    "query_events",
                    {"start_date": start.isoformat(), "end_date": end.isoformat(), "limit": 1000},
                    persona=persona,
                    context=context,
                )
                anomalies = self.registry.execute(
                    "query_anomalies",
                    {"start_date": start.isoformat(), "end_date": end.isoformat(), "limit": 1000},
                    persona=persona,
                    context=context,
                )
                result["anomaly_windows"] = anomalies["items"]
                result["start_date"] = start.isoformat()
                result["end_date"] = end.isoformat()
                run_id = (result.get("run_ids") or [None])[0]
            elif route["intent"] == "event_selection":
                candidates = route.get("candidates", [])
                lines = [
                    f"I found {len(candidates)} events in the active conversation context. "
                    "Which event should I use?"
                ]
                for item in candidates:
                    lines.append(
                        f"- {item.get('event_id', item.get('id', 'unknown'))}: "
                        f"{item.get('event_start', 'time not recorded')} "
                        f"({item.get('event_scope', 'scope not recorded')}); "
                        f"run {item.get('run_id', 'not recorded')}"
                    )
                result = {"message": "\n".join(lines)}
            elif route["intent"] == "run_summary":
                summary_run_id = route.get("run_id")
                if not summary_run_id:
                    result = {
                        "message": (
                            "I don't have an active saved run in this conversation yet. "
                            "Ask for a date range or provide a saved run ID."
                        )
                    }
                else:
                    result = self.registry.execute(
                        "get_run_details",
                        {"run_id": summary_run_id},
                        persona=persona,
                        context=context,
                    )
                    result["run_id"] = summary_run_id
                    run_id = summary_run_id
            elif route["intent"] in {"event_filter_query", "event_visualization"}:
                active_run_id = route.get("run_id")
                if active_run_id:
                    run = self.registry.execute(
                        "get_run_details",
                        {"run_id": active_run_id},
                        persona=persona,
                        context=context,
                    )
                    items = run.get("events", [])
                    windows = run.get("anomaly_windows", [])
                    run_ids = [active_run_id]
                    result_start = run.get("request", {}).get("start_date")
                    result_end = run.get("request", {}).get("end_date")
                    run_id = active_run_id
                else:
                    items = context.get("conversation_state", {}).get("events", [])
                    windows = []
                    run_ids = context.get("conversation_state", {}).get("run_ids", [])
                    result_start = context.get("conversation_state", {}).get("start_date")
                    result_end = context.get("conversation_state", {}).get("end_date")
                if not items and result_start and result_end:
                    result = self.registry.execute(
                        "query_events",
                        {"start_date": result_start, "end_date": result_end, "limit": 1000},
                        persona=persona,
                        context=context,
                    )
                    items = result.get("items", [])
                    run_ids = result.get("run_ids", run_ids)
                if route["intent"] == "event_filter_query":
                    items = [
                        item for item in items
                        if str(item.get("event_scope", "")).upper() == route["scope"]
                    ]
                    message = (
                        f"Found {len(items)} {route['scope'].replace('_', ' ').lower()} "
                        f"events in the saved run/period."
                        if items else
                        f"No {route['scope'].replace('_', ' ').lower()} events were found "
                        "in the saved run/period; the available prediction data was checked."
                    )
                    result = {
                        "message": message,
                        "items": items,
                        "start_date": result_start,
                        "end_date": result_end,
                        "run_ids": run_ids,
                        "anomaly_windows": windows,
                        "scope": route["scope"],
                    }
                else:
                    result = {
                        "items": items,
                        "start_date": result_start,
                        "end_date": result_end,
                        "run_ids": run_ids,
                        "anomaly_windows": windows,
                        "visualization": True,
                    }
            elif route["intent"] == "analysis_execution":
                if not route.get("start_date"):
                    result = {
                        "message": (
                            "Please provide an explicit date or date range within "
                            "the anomaly dataset before I start an analysis."
                        )
                    }
                else:
                    start, end = validate_requested_dates(
                        self.anomaly_service,
                        route["start_date"],
                        route["end_date"],
                    )
                    result = self.registry.execute(
                        "execute_anomaly_analysis",
                        {
                            "start_date": start.isoformat(),
                            "end_date": end.isoformat(),
                        },
                        persona=persona,
                        context=context,
                        confirmed=True,
                    )
                    run_id = result.get("run_id")
            elif route["intent"] == "customer_impact_query":
                if route.get("needs_context"):
                    result = {
                        "message": (
                            "Please provide a customer ID, a saved run ID, or a "
                            "supported date period for the customer-impact lookup."
                        )
                    }
                elif route.get("start_date"):
                    start, end = validate_requested_dates(
                        self.anomaly_service,
                        route["start_date"],
                        route["end_date"],
                    )
                    period = self.registry.execute(
                        "find_runs_for_period",
                        {
                            "start_date": start.isoformat(),
                            "end_date": end.isoformat(),
                        },
                        persona=persona,
                        context=context,
                    )
                    if not period["available"]:
                        result = {
                            "message": (
                                f"No completed saved analysis covers {start.isoformat()} "
                                f"through {end.isoformat()}. Would you like me to run "
                                "a new analysis using the existing defaults?"
                            )
                        }
                    elif route.get("customer_id") is None:
                        result = self.registry.execute(
                            "query_events",
                            {
                                "start_date": start.isoformat(),
                                "end_date": end.isoformat(),
                                "limit": 1000,
                            },
                            persona=persona,
                            context=context,
                        )
                        result["affected_customer_ids"] = sorted({
                            int(customer_id)
                            for event in result.get("items", [])
                            for customer_id in event.get("customer_ids", [])
                        })
                        affected_ids = ", ".join(
                            str(customer_id)
                            for customer_id in result["affected_customer_ids"]
                        )
                        result["message"] = (
                            "The saved analysis found "
                            f"{len(result['affected_customer_ids'])} affected "
                            "customers in the requested period."
                            + (f" Customer IDs: {affected_ids}." if affected_ids else "")
                        )
                        run_id = period["run_ids"][0] if period["run_ids"] else None
                    else:
                        run_id = period["run_ids"][0]
                        result = self.registry.execute(
                            "query_customer_impact",
                            {
                                "run_id": run_id,
                                "customer_id": route["customer_id"],
                            },
                            persona=persona,
                            context=context,
                        )
                elif route.get("customer_id") is not None and route.get("run_id"):
                    run_id = route["run_id"]
                    result = self.registry.execute(
                        "query_customer_impact",
                        {
                            "run_id": run_id,
                            "customer_id": route["customer_id"],
                        },
                        persona=persona,
                        context=context,
                    )
                else:
                    result = {
                        "message": (
                            "Customer-impact lookups require an authorized customer "
                            "ID and a completed run ID, or a supported date period."
                        )
                    }
            elif route["intent"] == "event_query":
                run_id_value = route.get("run_id")
                if run_id_value:
                    run_id = run_id_value
                    result = self.registry.execute(
                        "get_event_details",
                        {"run_id": run_id_value, "event_id": route["event_id"]},
                        persona=persona,
                        context=context,
                    )
                    result["run_id"] = run_id_value
                else:
                    prior_period = self._prior_historical_period(context)
                    if prior_period:
                        matches = self._resolve_events_in_period(
                            route["event_id"], prior_period
                        )
                        result = {
                            "event_id": route["event_id"],
                            "items": matches,
                            **prior_period,
                        }
                    else:
                        result = self.registry.execute(
                            "find_event_by_id",
                            {"event_id": route["event_id"]},
                            persona=persona,
                            context=context,
                        )
                    run_id = result.get("run_id") or next(
                        (item.get("run_id") for item in result.get("items", []) if item.get("run_id")),
                        None,
                    )
            elif route["intent"] == "export":
                tool_name = (
                    "export_events"
                    if route["dataset"] == "events"
                    else "export_anomaly_records"
                )
                result = self.registry.execute(
                    tool_name,
                    {"run_id": route["run_id"], "format": route["format"]},
                    persona=persona,
                    context=context,
                    confirmed=True,
                )
                run_id = route["run_id"]
            elif route["intent"] == "current_guidance":
                local = self.registry.execute(
                    "search_knowledge_base",
                    {"query": state["prompt"], "limit": 5},
                    persona=persona,
                    context=context,
                )
                references = local
                external: list[dict[str, Any]] = []
                tavily_configured = bool(get_settings().tavily_api_key)
                if tavily_configured:
                    web_result = self.registry.execute(
                        "tavily_web_search",
                        {"query": state["prompt"]},
                        persona=persona,
                        context=context,
                    )
                    external = self._external_references(web_result)
                references = references + external
                result = {
                    "source": "mixed_sources" if external else "local_knowledge_base",
                    "items": references,
                }
                if not tavily_configured:
                    result["message"] = (
                        "Current external search is not configured; this answer can "
                        "use local indexed sources only."
                    )
            elif route["intent"] in {
                "technical_explanation",
                "general_knowledge",
                "general_query",
            }:
                references = self.registry.execute(
                    "retrieve_graph_context",
                    {"query": state["prompt"], "limit": 5},
                    persona=persona,
                    context=context,
                )
            elif route["intent"] == "rectification_query":
                prior_period = self._prior_historical_period(context)
                if not route.get("start_date") and prior_period:
                    route["start_date"] = prior_period["start_date"]
                    route["end_date"] = prior_period["end_date"]
                prior_event = self._prior_event_reference(context)
                selected_event_id = route.get("event_id") or (
                    prior_event.get("event_id") if prior_event else None
                )
                selected_run_id = route.get("run_id") or (
                    prior_event.get("run_id") if prior_event else None
                )
                event_context: dict[str, Any] | None = None
                if selected_event_id:
                    if selected_run_id:
                        event_context = self.registry.execute(
                            "get_event_details",
                            {
                                "run_id": selected_run_id,
                                "event_id": selected_event_id,
                            },
                            persona=persona,
                            context=context,
                        )
                        event_context["run_id"] = selected_run_id
                    elif prior_period:
                        event_context = self._resolve_events_in_period(
                            selected_event_id, prior_period
                        )
                    else:
                        event_context = self.registry.execute(
                            "find_event_by_id",
                            {"event_id": selected_event_id},
                            persona=persona,
                            context=context,
                        )
                    if isinstance(event_context, list):
                        event_context = {"items": event_context}
                    run_id = event_context.get("run_id") or next(
                        (item.get("run_id") for item in event_context.get("items", []) if item.get("run_id")),
                        None,
                    )
                elif route.get("start_date"):
                    requested_start, requested_end = validate_requested_dates(
                        self.anomaly_service,
                        route["start_date"],
                        route["end_date"],
                    )
                    period = self.registry.execute(
                        "find_runs_for_period",
                        {
                            "start_date": requested_start.isoformat(),
                            "end_date": requested_end.isoformat(),
                        },
                        persona=persona,
                        context=context,
                    )
                    if not period["available"]:
                        result = {
                            "message": (
                                f"No completed prediction run covers "
                                f"{requested_start.isoformat()} through "
                                f"{requested_end.isoformat()}. Would you like me to "
                                "run the trained model using the existing defaults?"
                            )
                        }
                    else:
                        run_id = period["run_ids"][0]
                        event_context = self.registry.execute(
                            "query_events",
                            {
                                "start_date": requested_start.isoformat(),
                                "end_date": requested_end.isoformat(),
                                "limit": 100,
                            },
                            persona=persona,
                            context=context,
                        )
                        event_context["run_ids"] = period["run_ids"]
                        event_context["anomaly_windows"] = self.registry.execute(
                            "query_anomalies",
                            {
                                "start_date": requested_start.isoformat(),
                                "end_date": requested_end.isoformat(),
                                "limit": 1000,
                            },
                            persona=persona,
                            context=context,
                        )["items"]
                else:
                    result = {
                        "message": (
                            "I can explain general rectification guidance, but need "
                            "an event ID, saved run ID, or supported date range to "
                            "ground recommendations in a specific prediction."
                        )
                    }
                if event_context:
                    event_records = (
                        event_context.get("items", [])
                        if isinstance(event_context.get("items"), list)
                        else [event_context]
                    )
                    if selected_event_id:
                        event_records = [
                            item for item in event_records
                            if str(item.get("event_id", item.get("id", "")))
                            == str(selected_event_id)
                        ]
                    kinds = sorted({
                        str(kind).replace("_", " ")
                        for item in event_records
                        for kind in (item.get("anomaly_types") or [item.get("dominant_anomaly_type", "anomaly")])
                    })
                    scopes = sorted({
                        str(item.get("event_scope", "grid event")).replace("_", " ").lower()
                        for item in event_records
                    })
                    topic = ", ".join(kinds) or "electricity anomaly"
                    scope_text = ", ".join(scopes) or "grid event"
                    guidance_query = (
                        f"Electric utility troubleshooting: possible causes and diagnostic "
                        f"steps for a {topic} anomaly in a {scope_text}; meter telemetry, "
                        "distribution feeder, switching, and rectification guidance"
                    )
                    run_for_retrieval = run_id or selected_run_id
                    try:
                        retrieved = self.registry.execute(
                            "retrieve_graph_context",
                            {
                                "query": guidance_query,
                                "limit": 8,
                                **({"run_id": run_for_retrieval} if run_for_retrieval else {}),
                            },
                            persona=persona,
                            context=context,
                        )
                        local_hits = (
                            retrieved.get("documents", [])
                            if isinstance(retrieved, dict)
                            else retrieved
                        )
                        references = [
                            item for item in local_hits
                            if self._is_relevant_grid_source(item)
                        ]
                    except RuntimeError as exc:
                        logger.warning("Vector guidance retrieval failed: %s", exc)
                        references = []
                    if get_settings().tavily_api_key:
                        try:
                            web_result = self.registry.execute(
                                "tavily_web_search",
                                {"query": guidance_query},
                                persona=persona,
                                context=context,
                            )
                            external_hits = [
                                item for item in web_result.get("items", [])
                                if self._is_relevant_grid_source(item)
                            ]
                            references.extend(
                                self._external_references({"items": external_hits})
                            )
                        except RuntimeError as exc:
                            logger.warning("Tavily guidance search failed: %s", exc)
                if result is None:
                    result = {
                        "event_context": event_context,
                        "guidance_note": "Cause is not recorded as an established physical fault.",
                    }
                else:
                    result["event_context"] = event_context
                    result["guidance_note"] = "Cause is not recorded as an established physical fault."
            elif route["intent"] == "invalid_date":
                dataset_start, dataset_end = dataset_date_bounds(self.anomaly_service)
                result = {
                    "message": (
                        f"I couldn't interpret that date. Use DD/MM/YYYY or "
                        f"YYYY-MM-DD and choose dates between {dataset_start.isoformat()} "
                        f"and {dataset_end.isoformat()}."
                    )
                }
            elif route["intent"] == "historical_query":
                # Compatibility for callers that still send the former route name.
                result = {"message": "Please specify a supported date or period."}
            else:
                result = self._legacy_context(state["prompt"], persona, context)
        except ToolConfirmationRequired as exc:
            result = {"confirmation_required": str(exc)}
            status = "confirmation_required"
        except ToolPermissionError as exc:
            result = {"error": str(exc)}
            status = "forbidden"
        except ValueError as exc:
            result = {"error": str(exc)}
            status = "success"
        except RuntimeError as exc:
            result = {"error": str(exc)}
            status = "error"
        if isinstance(result, dict):
            run_id = run_id or result.get("run_id")
        logger.info(
            "assistant_pathway_completed",
            extra={
                "event": {
                    "pathway": self._pathway_for_intent(route["intent"]),
                    "intent": route["intent"],
                    "persona": persona,
                    "status": status,
                    "has_run_reference": bool(run_id),
                }
            },
        )
        return {
            "route": route,
            "tool_result": result,
            "references": references,
            "run_id": run_id,
            "event_id": event_id,
            "run_ids": result.get("run_ids", []) if isinstance(result, dict) else [],
            "start_date": result.get("start_date") if isinstance(result, dict) else None,
            "end_date": result.get("end_date") if isinstance(result, dict) else None,
            "conversation_state": self._update_conversation_state(
                context.get("conversation_state", {}), route, result, run_id, event_id
            ),
            "status": status,
        }

    @staticmethod
    def _pathway_for_intent(intent: str) -> str:
        return {
            "technical_explanation": "GENERAL_RAG",
            "general_knowledge": "GENERAL_RAG",
            "general_query": "GENERAL_RAG",
            "historical_anomaly_query": "SAVED_RUN_QUERY",
            "event_detail_followup": "SAVED_RUN_QUERY",
            "event_selection": "EVENT_ANALYSIS",
            "analysis_execution": "MODEL_INFERENCE",
            "customer_impact_query": "EVENT_ANALYSIS",
            "event_query": "EVENT_ANALYSIS",
            "event_filter_query": "SAVED_RUN_QUERY",
            "event_visualization": "SAVED_RUN_QUERY",
            "run_summary": "SAVED_RUN_QUERY",
            "rectification_query": "RECTIFICATION_RAG",
            "current_guidance": "EXTERNAL_WEB_SEARCH",
            "export": "EXPORT",
        }.get(intent, "GENERAL_RAG")

    @staticmethod
    def _update_conversation_state(
        previous: dict[str, Any],
        route: dict[str, Any],
        result: Any,
        run_id: str | None,
        event_id: str | None,
    ) -> dict[str, Any]:
        """Keep compact, structured references to the active saved analysis/events."""
        state = dict(previous or {})
        if not isinstance(result, dict):
            return state
        event_context = result.get("event_context")
        if isinstance(event_context, dict):
            if isinstance(event_context.get("items"), list):
                items = event_context["items"]
            elif event_context.get("event_id") or event_context.get("id"):
                items = [event_context]
            else:
                items = []
        else:
            items = []
        if not items and isinstance(result.get("items"), list):
            items = result["items"]
        if not items and isinstance(result.get("events"), list):
            items = result["events"]
        elif not items and (result.get("event_id") or result.get("id")):
            items = [result]

        records = [
            {
                **dict(item),
                **({"run_id": str(run_id)} if run_id and not item.get("run_id") else {}),
            }
            for item in items
            if isinstance(item, dict) and (item.get("event_id") or item.get("id"))
        ]
        # Keep the run's full event list when answering a single-event or filtered
        # follow-up. Otherwise the next “this run” request would silently inherit
        # only the last displayed event/filter result.
        if records and route.get("intent") not in {
            "event_query", "event_filter_query", "event_selection",
        }:
            state["events"] = records[:100]
        elif records and route.get("intent") == "event_query":
            state["selected_event"] = records[0]
            state["selected_event_id"] = str(
                records[0].get("event_id", records[0].get("id"))
            )
        if route.get("intent") == "event_filter_query" and records:
            state["last_filtered_events"] = records[:100]
        if result.get("start_date"):
            state["start_date"] = result["start_date"]
        if result.get("end_date"):
            state["end_date"] = result["end_date"]
        request = result.get("request", {})
        if request.get("start_date"):
            state["start_date"] = request["start_date"]
        if request.get("end_date"):
            state["end_date"] = request["end_date"]
        run_ids = result.get("run_ids")
        if isinstance(run_ids, list) and run_ids:
            state["run_ids"] = [str(value) for value in run_ids]
        record_run_ids = [str(item["run_id"]) for item in records if item.get("run_id")]
        if record_run_ids and not (isinstance(run_ids, list) and run_ids):
            state["run_ids"] = list(dict.fromkeys(record_run_ids))
        if run_id:
            if state.get("active_run_id") and str(state["active_run_id"]) != str(run_id):
                state.pop("selected_event", None)
                state.pop("selected_event_id", None)
                state.pop("selected_run_id", None)
            state["active_run_id"] = str(run_id)
            if not state.get("run_ids"):
                state["run_ids"] = [str(run_id)]
        elif record_run_ids and not state.get("active_run_id"):
            state["active_run_id"] = record_run_ids[0]
        selected_id = event_id or route.get("event_id")
        matching = [
            item for item in records
            if selected_id
            and str(item.get("event_id", item.get("id", ""))) == str(selected_id)
        ]
        if len(matching) == 1:
            selected = matching[0]
            state["selected_event"] = selected
            state["selected_event_id"] = str(
                selected.get("event_id", selected.get("id"))
            )
            if selected.get("run_id"):
                state["selected_run_id"] = str(selected["run_id"])
        elif len(records) == 1:
            selected = records[0]
            state["selected_event"] = selected
            state["selected_event_id"] = str(
                selected.get("event_id", selected.get("id"))
            )
            if selected.get("run_id"):
                state["selected_run_id"] = str(selected["run_id"])
        elif records:
            state.pop("selected_event", None)
            state.pop("selected_event_id", None)
            state.pop("selected_run_id", None)
        elif run_id:
            state["selected_run_id"] = str(run_id)
        state["last_intent"] = route.get("intent")
        return state

    @staticmethod
    def _external_references(result: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                **item,
                "citation": {
                    "title": item.get("title", "External webpage"),
                    "sourceUrl": item.get("url"),
                    "page": None,
                    "publisher": None,
                },
            }
            for item in result.get("items", [])
        ]

    @staticmethod
    def _is_relevant_grid_source(item: dict[str, Any]) -> bool:
        metadata = item.get("metadata", {})
        searchable = " ".join(
            str(value) for value in (
                item.get("title", metadata.get("title", "")),
                item.get("text", item.get("content", "")),
                item.get("url", metadata.get("source_url", "")),
            )
        ).lower()
        strong_terms = (
            "smart meter", "electric meter", "meter reading", "meter data",
            "meter interval", "meter telemetry", "load profile", "energy consumption",
            "anomaly detection", "power quality", "voltage sag", "switching transient",
            "distribution feeder", "feeder fault", "electrical fault",
        )
        return any(term in searchable for term in strong_terms)

    @staticmethod
    def _prior_event_reference(
        context: dict[str, Any]
    ) -> dict[str, str] | None:
        for item in reversed(context.get("prior_messages", [])):
            if item.get("role") == "assistant" and item.get("event_id"):
                return {
                    "event_id": str(item["event_id"]),
                    "run_id": str(item["run_id"]) if item.get("run_id") else "",
                }
        return None

    @staticmethod
    def _historical_event_followup(
        prompt: str, context: dict[str, Any]
    ) -> dict[str, str] | None:
        lowered = prompt.lower()
        detail_terms = (
            "those events", "these events", "the events", "event details",
            "in detail", "which events", "severity", "event type", "event scope",
            "breakdown of events", "tell me about those", "tell me about these",
        )
        if not any(term in lowered for term in detail_terms):
            return None
        return AnomalyAssistant._prior_historical_period(context)

    @staticmethod
    def _prior_historical_period(context: dict[str, Any]) -> dict[str, str] | None:
        conversation_state = context.get("conversation_state", {})
        if (
            conversation_state.get("start_date")
            and conversation_state.get("end_date")
        ):
            return {
                "start_date": str(conversation_state["start_date"]),
                "end_date": str(conversation_state["end_date"]),
            }
        for message in reversed(context.get("prior_messages", [])):
            if (
                message.get("role") == "assistant"
                and message.get("start_date")
                and message.get("end_date")
            ):
                return {
                    "start_date": str(message["start_date"]),
                    "end_date": str(message["end_date"]),
                }
            if message.get("role") != "user":
                continue
            prior_route = route_prompt(message.get("content", ""))
            if (
                prior_route.get("intent") == "historical_anomaly_query"
                and prior_route.get("start_date")
                and prior_route.get("end_date")
            ):
                return {
                    "start_date": prior_route["start_date"],
                    "end_date": prior_route["end_date"],
                }
        return None

    def _resolve_events_in_period(
        self, event_id: str, period: dict[str, str]
    ) -> list[dict[str, Any]]:
        start, end = validate_requested_dates(
            self.anomaly_service, period["start_date"], period["end_date"]
        )
        matches: dict[tuple[str, ...], tuple[str, dict[str, Any], str]] = {}
        summaries = sorted(
            self.anomaly_service.list_runs(limit=1000),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )
        selected_created_at: str | None = None
        for summary in summaries:
            if summary.get("status") != "completed":
                continue
            request = summary.get("request", {})
            try:
                run_start = date.fromisoformat(request["start_date"])
                run_end = date.fromisoformat(request["end_date"])
            except (KeyError, TypeError, ValueError):
                continue
            if run_start > end or run_end < start:
                continue
            created_at = str(summary.get("created_at", ""))
            if selected_created_at is not None and created_at != selected_created_at:
                break
            run_id = str(summary.get("analysis_id", ""))
            run = self.anomaly_service.get_run(run_id)
            if not run:
                continue
            event = next(
                (
                    item for item in run.get("events", [])
                    if str(item.get("event_id", item.get("id", ""))) == event_id
                ),
                None,
            )
            if event is not None:
                if selected_created_at is None:
                    selected_created_at = created_at
                identity = (
                    str(event.get("event_id", event.get("id", ""))),
                    str(event.get("event_start", "")),
                    str(event.get("event_end", "")),
                    str(event.get("event_scope", "")),
                    str(event.get("latitude_center", "")),
                    str(event.get("longitude_center", "")),
                )
                candidate = (created_at, event, run_id)
                current = matches.get(identity)
                if current is None or candidate[0] > current[0]:
                    matches[identity] = candidate
        if not matches:
            raise ValueError(
                f"Event '{event_id}' was not found in the saved runs covering "
                f"{start.isoformat()} through {end.isoformat()}."
            )
        # IDs are reused across runs. Follow the newest saved run that defines this
        # ID within the active period; within it, preserve distinct time occurrences.
        return [
            {**event, "run_id": run_id}
            for _, event, run_id in sorted(
                matches.values(), key=lambda match: str(match[1].get("event_start", ""))
            )
        ]

    @staticmethod
    def _pending_analysis_confirmation(
        context: dict[str, Any]
    ) -> dict[str, str] | None:
        messages = context.get("prior_messages", [])
        if len(messages) < 2:
            return None
        previous_user, previous_assistant = messages[-2:]
        if (
            previous_user.get("role") != "user"
            or previous_assistant.get("role") != "assistant"
            or "would you like me to run a new analysis" not in
            previous_assistant.get("content", "").lower()
        ):
            return None
        previous_route = route_prompt(previous_user.get("content", ""))
        if previous_route.get("intent") != "historical_anomaly_query":
            return None
        if not previous_route.get("start_date") or not previous_route.get("end_date"):
            return None
        return {
            "start_date": previous_route["start_date"],
            "end_date": previous_route["end_date"],
        }

    def _legacy_context(
        self, prompt: str, persona: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        provider = context.get("data_provider")
        lowered = prompt.lower()
        if provider and any(term in lowered for term in ("peak", "reserve", "stress")):
            return {"source": "GridVision peak demand service", "result": provider.get_peak_demand_analysis()}
        return {
            "message": "No stored anomaly result was queried. Use the existing GridVision tools for numerical results.",
            "persona": persona,
        }

    def _respond(self, state: AssistantState) -> dict[str, Any]:
        route = state["route"]
        references = state.get("references", [])
        result = state.get("tool_result")
        if route["intent"] == "export" and isinstance(result, dict):
            downloads = [
                {
                    "format": result["format"].upper(),
                    "label": "Download exported records",
                    "url": result["download_url"],
                }
            ]
        elif route["intent"] == "analysis_execution" and isinstance(result, dict):
            run_id = result.get("run_id")
            downloads = (
                [
                    {
                        "format": "CSV",
                        "label": "Download anomaly events",
                        "url": f"/api/v1/models/anomaly-prediction/runs/{run_id}/download/events.csv",
                    },
                    {
                        "format": "GeoJSON",
                        "label": "Download localized events",
                        "url": f"/api/v1/models/anomaly-prediction/runs/{run_id}/download/events.geojson",
                    },
                ]
                if run_id
                else []
            )
        elif (
            route["intent"] == "historical_anomaly_query"
            and isinstance(result, dict)
            and len(result.get("run_ids", [])) == 1
        ):
            run_id = result["run_ids"][0]
            downloads = [
                {
                    "format": "CSV",
                    "label": "Download anomaly events",
                    "url": (
                        f"/api/v1/models/anomaly-prediction/runs/{run_id}/"
                        "download/events.csv"
                    ),
                }
            ]
        else:
            downloads = []
        charts = (
            (
                [self._event_map_chart(result), self._severity_comparison_chart(result)]
                if route["intent"] == "event_visualization"
                else [self._event_breakdown_chart(result)]
            )
            if route["intent"] in {
                "event_detail_followup", "event_query", "event_filter_query",
                "event_visualization", "run_summary",
            }
            and isinstance(result, dict)
            else []
        )
        if state.get("status") in {"error", "forbidden", "confirmation_required"}:
            if isinstance(result, dict):
                answer = str(
                    result.get("error")
                    or result.get("confirmation_required")
                    or "The requested operation is not available."
                )
            else:
                answer = "The requested operation is not available."
            return {
                "answer": answer,
                "status": state["status"],
                "run_id": state.get("run_id"),
                "event_id": state.get("event_id"),
                "citations": [],
                "downloads": [],
                "grounding": {},
                "charts": [],
            }
        model_references = references or (
            result.get("items", [])
            if isinstance(result, dict)
            and result.get("source") in {"local_knowledge_base", "external_web"}
            else []
        )
        if isinstance(result, dict) and result.get("source") == "external_web":
            model_references = [
                {
                    **item,
                    "citation": {
                        "title": item.get("title", "External webpage"),
                        "sourceUrl": item.get("url"),
                        "page": None,
                        "publisher": None,
                    },
                }
                for item in model_references
            ]
        if (
            route["intent"] == "rectification_query"
            and isinstance(result, dict)
            and result.get("message")
        ):
            answer = str(result["message"])
        elif (
            route["intent"] == "rectification_query"
            and isinstance(result, dict)
            and isinstance(result.get("event_context"), dict)
        ):
            answer = self._rectification_summary(
                result["event_context"], route.get("event_id")
            )
            if not model_references:
                answer += (
                    "\n\nNo directly relevant indexed or web guidance was found. "
                    "The cause remains a hypothesis from the saved anomaly signature."
                )
        elif route["intent"] == "run_summary" and isinstance(result, dict):
            answer = self._run_summary(result)
        elif route["intent"] == "event_filter_query" and isinstance(result, dict):
            answer = str(result.get("message", ""))
            if result.get("items"):
                answer += "\n" + self._event_detail_summary(result)
        elif route["intent"] == "event_visualization" and isinstance(result, dict):
            answer = (
                f"Prepared a geospatial cluster view and severity comparison for "
                f"{len(result.get('items', []))} events from the selected saved "
                f"run/period ({result.get('start_date')} through {result.get('end_date')})."
            )
        elif route["intent"] in {
            "historical_anomaly_query",
            "customer_impact_query",
            "event_query",
            "event_selection",
            "invalid_date",
            "analysis_execution",
            "confirmation_response",
            "confirmation_declined",
        } and isinstance(result, dict) and result.get("message") and not (
            route["intent"] == "event_query"
            and re.search(
                r"\b(why|how)\b.{0,50}\b(classif(?:ied|ication)|scope|multi.area)\b",
                state["prompt"],
                flags=re.IGNORECASE,
            )
        ):
            answer = str(result["message"])
        elif (
            route["intent"] == "analysis_execution"
            and isinstance(result, dict)
            and isinstance(result.get("metrics"), dict)
        ):
            answer = self._analysis_summary(result)
        elif (
            route["intent"] == "event_detail_followup"
            and isinstance(result, dict)
        ):
            answer = self._event_detail_summary(result)
        elif (
            route["intent"] == "event_query"
            and isinstance(result, dict)
            and isinstance(result.get("items"), list)
            and not re.search(
                r"\b(why|how)\b.{0,50}\b(classif(?:ied|ication)|scope|multi.area)\b",
                state["prompt"],
                flags=re.IGNORECASE,
            )
        ):
            requested_event_id = route.get("event_id") or result.get("event_id")
            event_items = [
                item for item in result["items"]
                if not requested_event_id
                or str(item.get("event_id", item.get("id", "")))
                == str(requested_event_id)
            ]
            answer = self._event_detail_summary(
                {
                    "start_date": result.get("start_date"),
                    "end_date": result.get("end_date"),
                    "items": event_items,
                    "anomaly_windows": result.get("anomaly_windows", []),
                }
            )
        elif (
            route["intent"] == "event_query"
            and isinstance(result, dict)
            and result.get("event_id", result.get("id"))
            and not re.search(
                r"\b(why|how)\b.{0,50}\b(classif(?:ied|ication)|scope|multi.area)\b",
                state["prompt"],
                flags=re.IGNORECASE,
            )
        ):
            start = str(result.get("event_start", ""))[:10]
            end = str(result.get("event_end", ""))[:10]
            answer = self._event_detail_summary(
                {
                    "start_date": start,
                    "end_date": end,
                    "items": [result],
                    "anomaly_windows": [],
                }
            )
        elif (
            route["intent"] == "historical_anomaly_query"
            and isinstance(result, dict)
            and isinstance(result.get("items"), list)
            and "count" in result
        ):
            answer = self._historical_summary(result)
        elif isinstance(result, dict) and "error" in result:
            answer = str(result["error"])
        elif (
            route["intent"] in {"historical_anomaly_query", "historical_query"}
            and isinstance(result, dict)
            and result.get("message")
            and "available" not in result
        ):
            answer = str(result["message"])
        elif route["intent"] in {"historical_anomaly_query", "historical_query"} and isinstance(result, dict) and not result.get("run_ids"):
            answer = (
                "No completed saved analysis covers that full period. "
                "Would you like me to run a new analysis using the existing defaults?"
            )
        else:
            system = (
                "You are GridVision's anomaly cause and rectification assistant. Use "
                "event_context as the authoritative facts for event ID, source run, "
                "time, type, scope, severity, customers, clusters, and coordinates. "
                "Use only relevant technical references in references; ignore unrelated "
                "documents. Explain possible causes consistent with the recorded anomaly "
                "type, but state clearly that the model signature is not a confirmed "
                "physical root cause. Give practical verification and rectification steps "
                "that differ for single-customer versus local-area events. Do not invent "
                "measurements, fault codes, locations, or affected equipment. Cite only "
                "the relevant provided sources. If none are relevant, say the guidance is "
                "general and no relevant indexed/web source was found."
                if route["intent"] == "rectification_query"
                else RECOMMENDATION_SYSTEM_PROMPT if (
                route["intent"] in {"historical_anomaly_query", "analysis_execution"}
                and "recommend" in state["prompt"].lower()
                ) else (
                "You are GridVision's anomaly intelligence assistant. Answer from the "
                "provided saved GridVision results or cited source excerpts for "
                "GridVision records. Always answer in concise natural-language prose; "
                "never return JSON. For general technical questions, give a concise "
                "standard explanation when retrieval has no relevant source and say "
                "when it is not confirmed by an indexed reference. Never invent "
                "numerical records. Clearly distinguish local saved results from "
                "external web guidance. Explain uncertainty and cite sources by title "
                "and page where available. If evidence is insufficient, say so. For "
                "residential users, never recommend dangerous electrical work."
                )
            )
            bounded_context = {
                "intent": route["intent"],
                "result": result,
                "conversation_context": state["context"].get("conversation_state", {}),
                "references": recommendation_context(result or {}, model_references),
                "history": state["context"].get("prior_messages", []),
            }
            answer = _ollama_chat(
                [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": (
                            f"Question: {state['prompt']}\n\n"
                            f"Verified context (JSON): "
                            f"{json.dumps(bounded_context, ensure_ascii=False, default=str)[:24000]}"
                        ),
                    },
                ],
                on_token=state["context"].get("stream_callback"),
            )
        citations = [
            item.get("citation", {})
            for item in model_references
            if isinstance(item, dict) and item.get("citation")
        ]
        return {
            "answer": answer,
            "status": state.get("status", "success"),
            "run_id": state.get("run_id"),
            "event_id": state.get("event_id"),
            "citations": citations,
            "downloads": downloads,
            "grounding": evaluate_grounding(answer, model_references),
            "charts": charts,
        }

    @staticmethod
    def _event_detail_summary(result: dict[str, Any]) -> str:
        items = result.get("items", [])
        windows = result.get("anomaly_windows", [])
        by_event: dict[str, list[dict[str, Any]]] = {}
        for window in windows:
            by_event.setdefault(str(window.get("event_id", "")), []).append(window)
        lines = [
            f"Event details for {result.get('start_date')} through {result.get('end_date')}: "
            f"{len(items)} saved localized events."
        ]
        for event in items[:50]:
            event_id = str(event.get("event_id", event.get("id", "Unknown event")))
            event_start = str(event.get("event_start", ""))
            event_end = str(event.get("event_end", ""))
            scores = [
                float(item["severity"])
                for item in by_event.get(event_id, [])
                if isinstance(item.get("severity"), (int, float))
                and event_start <= str(item.get("anomaly_start", item.get("start_time", ""))) <= event_end
            ]
            if not scores:
                scores = [
                    float(event[key]) for key in ("mean_anomaly_score", "max_anomaly_score")
                    if isinstance(event.get(key), (int, float))
                ]
            types = event.get("anomaly_type_distribution") or {
                str(kind): 1 for kind in event.get("anomaly_types", [])
            }
            type_text = ", ".join(
                f"{kind.replace('_', ' ')} ({count})"
                for kind, count in sorted(types.items())
            ) or "not recorded"
            duration_hours = (
                float(event["event_duration"]) / 3600
                if isinstance(event.get("event_duration"), (int, float))
                else None
            )
            duration_text = (
                f"{duration_hours:.1f} hr" if duration_hours is not None else "not recorded"
            )
            customer_ids = event.get("customer_ids", [])
            cluster_ids = event.get("spatial_cluster_ids", [])
            severity_mean = event.get("mean_anomaly_score")
            severity_max = event.get("max_anomaly_score")
            score_text = (
                f"severity score {min(scores):.2f}–{max(scores):.2f}"
                if scores else "severity score not recorded"
            )
            lines.append(
                f"- {event_id}: {event.get('event_start', 'time not recorded')} to "
                f"{event.get('event_end', 'time not recorded')} (source time; timezone unspecified); "
                f"{event.get('event_scope', 'scope not recorded').replace('_', ' ').lower()}; "
                f"types: {type_text}; {score_text}; "
                f"duration: {duration_text}; "
                f"{event.get('affected_customer_count', 0)} affected customers; "
                f"center: {event.get('latitude_center', 'not recorded')}, "
                f"{event.get('longitude_center', 'not recorded')}; "
                f"impact diameter/spatial extent: {event.get('spatial_extent_km', 'not recorded')} km; "
                f"clusters: {event.get('spatial_cluster_count', 0)} "
                f"({', '.join(str(value) for value in cluster_ids) or 'IDs not recorded'}); "
                f"customer IDs: {', '.join(str(value) for value in customer_ids) or 'not recorded'}; "
                f"mean/max severity: {severity_mean if severity_mean is not None else 'not recorded'}/"
                f"{severity_max if severity_max is not None else 'not recorded'}; "
                f"probable cause: model signature {event.get('dominant_anomaly_type', 'not recorded')} "
                f"(not a confirmed physical cause); "
                f"source run: {event.get('run_id', 'not recorded')}."
            )
        if len(items) > 50:
            lines.append(f"Showing the first 50 of {len(items)} events.")
        return "\n".join(lines)

    @staticmethod
    def _rectification_summary(
        context: dict[str, Any], event_id: str | None
    ) -> str:
        records = context.get("items") if isinstance(context.get("items"), list) else [context]
        if event_id:
            records = [
                event for event in records
                if str(event.get("event_id", event.get("id", ""))) == event_id
            ]
        if not records:
            return "I couldn't find that event in the previous saved period. Please check the event ID."
        lines = []
        event_types: set[str] = set()
        for event in records:
            event_id_value = str(event.get("event_id", event.get("id", "Unknown event")))
            kinds = event.get("anomaly_types") or [event.get("dominant_anomaly_type", "unknown")]
            if isinstance(kinds, str):
                kinds = [kinds]
            event_types.update(str(kind).lower() for kind in kinds)
            customer_ids = event.get("customer_ids") or []
            severity = event.get("max_anomaly_score", event.get("mean_anomaly_score"))
            lines.append(
                f"- {event_id_value} (run {event.get('run_id', 'from the selected period')}), "
                f"{event.get('event_start', 'time not recorded')} to {event.get('event_end', 'time not recorded')}: "
                f"type {', '.join(str(kind).replace('_', ' ') for kind in kinds)}; "
                f"{event.get('event_scope', 'scope not recorded').replace('_', ' ').lower()}; "
                f"center {event.get('latitude_center', 'not recorded')}, "
                f"{event.get('longitude_center', 'not recorded')}; "
                f"severity {severity if severity is not None else 'not recorded'}; "
                f"{event.get('affected_customer_count', len(customer_ids))} affected customer(s) "
                f"({', '.join(str(value) for value in customer_ids) or 'IDs not recorded'})."
            )
        possible_causes = []
        if "spike" in event_types:
            possible_causes.append(
                "a short-lived measured-load increase, a switching transient, or a meter/telemetry artifact"
            )
        if "drop" in event_types:
            possible_causes.append(
                "a real reduction in load, a service interruption, or weak/missing telemetry"
            )
        if "flatline" in event_types or "zero_block" in event_types:
            possible_causes.append(
                "repeated or zero readings caused by an interruption, meter communications, or a data-pipeline issue"
            )
        likely = (
            "Possible explanations include " + "; or ".join(possible_causes) + "."
            if possible_causes else
            "The saved telemetry does not establish a physical cause for this event."
        )
        scopes = {str(event.get("event_scope", "")).upper() for event in records}
        if "LOCAL_AREA" in scopes or "MULTI_AREA" in scopes:
            checks = (
                "Compare the original interval readings for the affected customers and nearby meters; check "
                "meter communications and data-quality flags for the event window. If readings are valid and "
                "the affected customers share network infrastructure, review relevant outage, switching, and "
                "protection logs. Escalate verified network issues to utility operations."
            )
        else:
            checks = (
                "Check the affected meter's original interval readings, adjacent intervals, and communications "
                "or data-quality flags. Compare with that customer's recent load pattern. If the spike is "
                "present in validated readings, have the utility operations team investigate the meter/service "
                "and relevant event logs."
            )
        actions = (
            checks + " The model signature is not proof of a physical fault; confirm the signal before taking corrective action."
        )
        opening = (
            f"I found {len(records)} distinct saved records for {event_id}; the event ID is reused "
            "across records, so these are shown separately:\n"
            if len(records) > 1 else "Saved event context:\n"
        )
        return opening + "\n".join(lines) + f"\n\nPossible cause: {likely}\n\nRectification checks: {actions}"

    @staticmethod
    def _event_breakdown_chart(result: dict[str, Any]) -> dict[str, Any]:
        scope_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        score_counts = {"0.00–0.25": 0, "0.25–0.50": 0, "0.50–0.75": 0, "0.75–1.00": 0}
        events = result.get("items", result.get("events", []))
        if not events and result.get("event_id"):
            events = [result]
        for event in events:
            scope = str(event.get("event_scope", "unknown")).replace("_", " ").title()
            scope_counts[scope] = scope_counts.get(scope, 0) + 1
            distribution = event.get("anomaly_type_distribution", {})
            if distribution:
                for kind, count in distribution.items():
                    label = str(kind).replace("_", " ").title()
                    type_counts[label] = type_counts.get(label, 0) + int(count)
            else:
                for kind in event.get("anomaly_types", []):
                    label = str(kind).replace("_", " ").title()
                    type_counts[label] = type_counts.get(label, 0) + 1
        for window in result.get("anomaly_windows", []):
            score = window.get("severity", window.get("anomaly_score"))
            if isinstance(score, (int, float)):
                bucket = (
                    "0.00–0.25" if score < 0.25 else
                    "0.25–0.50" if score < 0.50 else
                    "0.50–0.75" if score < 0.75 else
                    "0.75–1.00"
                )
                score_counts[bucket] += 1
        if not result.get("anomaly_windows"):
            for event in events:
                score = event.get("max_anomaly_score", event.get("mean_anomaly_score"))
                if isinstance(score, (int, float)):
                    bucket = (
                        "0.00–0.25" if score < 0.25 else
                        "0.25–0.50" if score < 0.50 else
                        "0.50–0.75" if score < 0.75 else
                        "0.75–1.00"
                    )
                    score_counts[bucket] += 1
        return {
            "title": "Saved event breakdown",
            "series": [
                {"label": "Event scope", "items": scope_counts},
                {"label": "Anomaly type", "items": type_counts},
                {"label": "Severity score range", "items": score_counts},
            ],
        }

    @staticmethod
    def _event_map_chart(result: dict[str, Any]) -> dict[str, Any]:
        points = []
        for event in result.get("items", []):
            latitude = event.get("latitude_center")
            longitude = event.get("longitude_center")
            if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                continue
            points.append({
                "id": str(event.get("event_id", event.get("id", "event"))),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "severity": float(event.get("max_anomaly_score", event.get("mean_anomaly_score", 0))),
                "scope": str(event.get("event_scope", "unknown")),
            })
        return {"title": "Event cluster centers", "kind": "map", "points": points}

    @staticmethod
    def _severity_comparison_chart(result: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, float] = {}
        for event in result.get("items", []):
            event_id = str(event.get("event_id", event.get("id", "event")))
            event_time = str(event.get("event_start", ""))
            key = f"{event_id} {event_time[5:16]}" if event_time else event_id
            score = event.get("max_anomaly_score", event.get("mean_anomaly_score"))
            if isinstance(score, (int, float)):
                values[key] = float(score)
        return {
            "title": "Severity score by event",
            "series": [{"label": "Maximum anomaly score", "items": values}],
        }

    @staticmethod
    def _run_summary(result: dict[str, Any]) -> str:
        request = result.get("request", {})
        start = request.get("start_date", "unknown start")
        end = request.get("end_date", start)
        run_id = result.get("run_id", result.get("analysis_id", "unknown run"))
        events = result.get("events", [])
        windows = result.get("anomaly_windows", [])
        scope_counts: dict[str, int] = {}
        for event in events:
            scope = str(event.get("event_scope", "unknown")).replace("_", " ").lower()
            scope_counts[scope] = scope_counts.get(scope, 0) + 1
        type_counts: dict[str, int] = {}
        for window in windows:
            kind = str(window.get("anomaly_type", "unknown")).replace("_", " ")
            type_counts[kind] = type_counts.get(kind, 0) + 1
        summary = (
            f"Saved run {run_id} covers {start} through {end} and contains "
            f"{len(events)} localized events from this run only."
        )
        if scope_counts:
            summary += " Scope counts: " + ", ".join(
                f"{count} {scope}" for scope, count in sorted(scope_counts.items())
            ) + "."
        if type_counts:
            summary += " Anomaly windows by type: " + ", ".join(
                f"{count} {kind}" for kind, count in sorted(type_counts.items())
            ) + "."
        if events:
            summary += "\n" + AnomalyAssistant._event_detail_summary({
                "start_date": start,
                "end_date": end,
                "items": events,
                "anomaly_windows": windows,
            })
        return summary

    @staticmethod
    def _analysis_summary(result: dict[str, Any]) -> str:
        metrics = result["metrics"]
        request = result.get("request", {})
        start = request.get("start_date", "the requested date range")
        end = request.get("end_date")
        period = f"{start} through {end}" if end and end != start else str(start)
        customer_count = metrics.get("selected_customer_count", 0)
        anomaly_count = metrics.get("anomaly_window_count", 0)
        event_count = metrics.get("localized_event_count", 0)
        type_counts = metrics.get("anomaly_type_counts", {})
        counts = ", ".join(
            f"{count} {kind.replace('_', ' ')}"
            for kind, count in sorted(type_counts.items())
        )
        scope_counts = metrics.get("event_scope_counts", {})
        scopes = ", ".join(
            f"{count} {scope.lower().replace('_', ' ')}"
            for scope, count in sorted(scope_counts.items())
        )
        answer = (
            f"Analysis for {period} is complete. It checked {customer_count:,} "
            f"customer{'s' if customer_count != 1 else ''} and found "
            f"{anomaly_count:,} anomaly window{'s' if anomaly_count != 1 else ''} "
            f"across {event_count:,} localized event{'s' if event_count != 1 else ''}."
        )
        if counts:
            answer += f" By anomaly type: {counts}."
        if scopes:
            answer += f" Event scopes: {scopes}."
        batch_count = result.get("metadata", {}).get("customer_batch_count", 1)
        if batch_count > 1:
            answer += f" The full customer set was processed in {batch_count} batches."
        return answer

    @staticmethod
    def _historical_summary(result: dict[str, Any]) -> str:
        items = result["items"]
        start = result.get("start_date", "the requested period")
        end = result.get("end_date")
        period = f"{start} through {end}" if end and end != start else str(start)
        run_ids = result.get("run_ids", [])
        run_reference = (
            f" Saved runs covering this period: {', '.join(run_ids)}." if run_ids else ""
        )
        if not items:
            return f"The completed saved prediction covers {period} and found no anomaly events.{run_reference}"
        type_counts: dict[str, int] = {}
        scope_counts: dict[str, int] = {}
        for event in items:
            scope = event.get("event_scope")
            if scope:
                scope_counts[str(scope)] = scope_counts.get(str(scope), 0) + 1
        anomaly_windows = result.get("anomaly_windows", [])
        for event in anomaly_windows or items:
            distribution = event.get("anomaly_type_distribution", {})
            if isinstance(distribution, dict):
                for kind, count in distribution.items():
                    type_counts[str(kind)] = type_counts.get(str(kind), 0) + int(count)
            elif event.get("dominant_anomaly_type"):
                kind = str(event["dominant_anomaly_type"])
                type_counts[kind] = type_counts.get(kind, 0) + 1
        answer = (
            f"The completed saved prediction for {period} found "
            f"{len(items):,} localized events"
        )
        if type_counts:
            counts = ", ".join(
                f"{count} {kind.replace('_', ' ')}"
                for kind, count in sorted(type_counts.items())
            )
            answer += f" and {sum(type_counts.values()):,} anomaly windows by type: {counts}"
        if scope_counts:
            scopes = ", ".join(
                f"{count} {scope.lower().replace('_', ' ')}"
                for scope, count in sorted(scope_counts.items())
            )
            answer += f". Event scopes: {scopes}"
        return answer + "." + run_reference

    @staticmethod
    def _trace(state: AssistantState, persona: str) -> None:
        settings = get_settings()
        if not settings.langsmith_tracing or not settings.langsmith_api_key:
            return
        from datetime import datetime, timezone

        try:
            from langsmith import Client
        except ImportError:
            logger.error("LangSmith tracing is enabled but langsmith is not installed.")
            return
        try:
            client = Client(api_key=settings.langsmith_api_key)
            run = client.create_run(
                name="gridvision-anomaly-assistant",
                run_type="chain",
                inputs={
                    "persona": persona,
                    "intent": state.get("route", {}).get("intent"),
                    "prompt_length": len(state.get("prompt", "")),
                    "tool_status": state.get("status"),
                },
                extra={"metadata": {"conversation_id": state.get("conversation_id")}},
                project_name="gridvision-anomaly-assistant",
            )
            client.update_run(
                run.id,
                outputs={
                    "status": state.get("status"),
                    "citation_count": len(state.get("citations", [])),
                    "has_run_reference": bool(state.get("run_id")),
                },
                end_time=datetime.now(timezone.utc),
            )
        except Exception:
            logger.exception("LangSmith metadata trace failed.")
