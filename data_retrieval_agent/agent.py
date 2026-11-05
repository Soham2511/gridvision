"""Data retrieval agent service and source availability checks."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Any

from .config import AgentSettings
from .context import AuthenticatedRequestContext
from .graph import build_graph
from .memory.checkpointer import create_checkpointer
from .memory.session_manager import SessionManager
from .providers.llm_provider import ChatModelProvider
from .tools.registered import build_tool_registry


class DataRetrievalAgent:
    def __init__(self, *, settings: AgentSettings, services: dict[str, Any], approved_sources: set[str], session_manager=None, llm=None, checkpointer=None):
        self.settings, self.services = settings, services
        self.approved_sources = set(approved_sources)
        self.registry = build_tool_registry(services, self.approved_sources)
        self._checkpointer = checkpointer
        self._graph = None
        self.sessions = session_manager or SessionManager(settings.session_ttl_seconds, on_delete=self._delete_checkpoint)
        self.llm = llm or ChatModelProvider(settings.llm_provider, settings.model_name, settings.timeout_seconds, settings.langsmith_tracing)

    def _delete_checkpoint(self, session_id: str):
        delete = getattr(self._checkpointer, "delete_thread", None)
        if callable(delete):
            delete(session_id)

    @property
    def ready(self) -> bool:
        return self.settings.enabled and self.settings.llm_provider != "none" and bool(self.settings.model_name)

    def available_sources(self) -> set[str]:
        mapping = {
            "customer_gold": ("customer_gold_path",),
            "customer_silver": ("customer_silver_path",),
            "commercial_silver": ("commercial_silver_path",),
            "commercial_gold": ("commercial_gold_path",),
            "government_2018": ("government_data_path",),
            "segmentation_2018": ("segmentation_output_dir",),
            "anomaly_synthetic_2019": ("anomaly_dataset_path", "anomaly_model_path"),
        }
        sources = set()
        for source, keys in mapping.items():
            if source not in self.approved_sources or not all(self.services.get(key) and Path(self.services[key]).exists() for key in keys):
                continue
            if source == "segmentation_2018":
                root = Path(self.services[keys[0]])
                if not all((root / name).is_file() for name in ("consumer_assignments.parquet", "model_metadata.json")):
                    continue
            extras = {
                "customer_gold": "customer_metadata_path",
                "customer_silver": "customer_silver_metadata_path",
                "commercial_silver": "commercial_silver_metadata_path",
                "commercial_gold": "commercial_metadata_path",
            }
            if extras.get(source) and self.services.get(extras[source]) and not Path(self.services[extras[source]]).is_file():
                continue
            sources.add(source)
        provider = self.services.get("model_provider")
        if provider and hasattr(provider, "get_horizon_model_status"):
            try:
                status = provider.get_horizon_model_status()
                for persona in ("commercial", "government"):
                    source = "commercial_gold" if persona == "commercial" else "government_2018"
                    if source in sources and status.get(persona, {}).get("status") == "ready":
                        sources.add(f"forecast_{persona}")
            except Exception:
                pass
        customer = self.services.get("customer_bill_prediction_service")
        if customer and "customer_gold" in sources:
            try:
                if customer.get_summary().get("status") == "configured":
                    sources.add("forecast_residential")
            except Exception:
                pass
        return sources

    def _compiled_graph(self):
        if self._graph is None:
            if self._checkpointer is None:
                self._checkpointer = create_checkpointer()
            self._graph = build_graph(registry=self.registry, llm=self.llm, max_tool_calls=self.settings.max_tool_calls, max_graph_steps=self.settings.max_graph_steps, checkpointer=self._checkpointer)
        return self._graph

    def respond(self, session_id: str, message: str, context: AuthenticatedRequestContext) -> dict:
        if not self.ready:
            raise RuntimeError("The data retrieval agent is disabled or unconfigured.")
        if len(message) > self.settings.max_message_chars:
            raise ValueError("Message exceeds configured maximum length.")
        session = self.sessions.get(session_id, context)
        if session is None:
            raise KeyError("Session does not exist or is not owned by this user.")
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._compiled_graph().invoke, {
            "message": message, "history": session.turns,
            "results": [], "errors": [], "rounds": 0,
        }, {"configurable": {"thread_id": session_id}, "recursion_limit": self.settings.max_graph_steps}, context={
            "context": context,
            "available_sources": self.available_sources(),
        })
        try:
            result = future.result(timeout=self.settings.timeout_seconds * (self.settings.max_graph_steps + 1))
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            future.add_done_callback(lambda _completed: self._delete_checkpoint(session_id))
            executor.shutdown(wait=False, cancel_futures=True)
            raise TimeoutError("Agent workflow exceeded its time limit.") from exc
        except Exception:
            executor.shutdown(wait=True)
            raise
        else:
            executor.shutdown(wait=True)
        answer = str(result.get("answer", ""))
        try:
            self.sessions.append_turns(session_id, context, message, answer)
        except KeyError:
            # An in-flight request may finish after session end/expiry.
            self._delete_checkpoint(session_id)
            raise
        sources = []
        for item in result.get("results", []):
            source, provenance = item.get("source", {}), item.get("source", {}).get("provenance", {})
            provenance = provenance if isinstance(provenance, dict) else {}
            period = provenance.get("period", {}) if isinstance(provenance.get("period", {}), dict) else {}
            sources.append({
                "source_id": source.get("source_id", "unknown"),
                "record_type": source.get("record_type", "retrieved_data"),
                "units": source.get("units", provenance.get("units")),
                "data_class": source.get("data_class", "historical"),
                "dataset_version": provenance.get("datasetVersion", provenance.get("version")),
                "period_start": period.get("start", period.get("startMonth", source.get("startDate"))),
                "period_end": period.get("end", period.get("endMonth", source.get("endDate"))),
            })
        partial_data = any(item.get("status") == "partial" for item in result.get("results", []))
        availability = (
            "unavailable" if result.get("unavailable") or (not sources and result.get("errors"))
            else "partial" if result.get("errors") or partial_data or (not sources and result.get("clarification"))
            else "available" if sources
            else "unavailable"
        )
        return {"session_id": session_id, "answer": answer, "needs_clarification": bool(result.get("clarification")), "clarification_question": answer if result.get("clarification") else None, "sources": sources, "availability": availability}
