"""Domain-grounded AI assistant service."""

from __future__ import annotations

import hashlib
import importlib
import logging
from pathlib import Path
from typing import Any

from app.providers.data_provider import BaseDataProvider
from ai.anamoly.agents.query_router import route_prompt
from ai.anamoly.memory.conversation_memory import ConversationMemory
from ai.anamoly.agents.orchestrator import AnomalyAssistant

logger = logging.getLogger("gridvision.anomaly.agent")


class AssistantService:
    """Preserve GridVision's existing insights and route anomaly queries to GraphRAG."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        anomaly_service: Any | None = None,
        *,
        route_government_queries: bool = True,
    ) -> None:
        self.data_provider = data_provider
        self.anomaly_service = anomaly_service
        self.route_government_queries = route_government_queries
        self._anomaly_assistant: AnomalyAssistant | None = None

    def _assistant(self) -> AnomalyAssistant:
        if self.anomaly_service is None:
            raise RuntimeError("The GridVision anomaly analysis service is unavailable.")
        if self._anomaly_assistant is None:
            self._anomaly_assistant = AnomalyAssistant(
                self.anomaly_service,
                data_provider=self.data_provider,
                memory=ConversationMemory(),
            )
        return self._anomaly_assistant

    def answer_query(
        self,
        prompt: str,
        persona: str = "household",
        entity_id: str | None = None,
        conversation_id: str | None = None,
        principal: str | None = None,
        authenticated_persona: str | None = None,
        authorized_customer_ids: list[int] | None = None,
        stream_callback: Any | None = None,
    ) -> dict[str, Any]:
        if self.route_government_queries and persona == "government":
            return self._answer_government_routed_query(
                prompt=prompt,
                persona=persona,
                entity_id=entity_id,
                conversation_id=conversation_id,
                principal=principal,
                authenticated_persona=authenticated_persona,
                authorized_customer_ids=authorized_customer_ids,
                stream_callback=stream_callback,
            )
        return self._answer_anomaly_query(
            prompt=prompt,
            persona=persona,
            entity_id=entity_id,
            conversation_id=conversation_id,
            principal=principal,
            authenticated_persona=authenticated_persona,
            authorized_customer_ids=authorized_customer_ids,
            stream_callback=stream_callback,
        )

    def _answer_government_routed_query(
        self,
        *,
        prompt: str,
        persona: str,
        entity_id: str | None,
        conversation_id: str | None,
        principal: str | None,
        authenticated_persona: str | None,
        authorized_customer_ids: list[int] | None,
        stream_callback: Any | None,
    ) -> dict[str, Any]:
        """Route Government UI questions through the Ollama supervisor."""
        from ai.govt.router import route_query

        govt_module = importlib.import_module(
            "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
        )
        identity = f"{principal or 'anonymous'}:{conversation_id or 'one-shot'}"
        history_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        history_path = (
            govt_module.DEFAULT_HISTORY_PATH.parent
            / "conversations"
            / f"{history_key}.json"
        )
        history = govt_module._read_history(history_path)
        prior_turns = history.get("turns", [])[-4:]
        prior_context = "\n".join(
            f"user: {turn.get('user_question', turn.get('content', ''))}"
            for turn in prior_turns
            if isinstance(turn, dict)
        )
        if (
            self._anomaly_assistant is not None
            and self._anomaly_assistant.memory is not None
        ):
            anomaly_turns = self._anomaly_assistant.memory.load(
                principal, conversation_id, persona
            )
            prior_context = "\n".join(
                [prior_context]
                + [
                    f"{turn.get('role', 'unknown')}: {turn.get('content', '')}"
                    for turn in anomaly_turns[-8:]
                    if isinstance(turn, dict)
                ]
            )
        route = route_query(prompt, prior_context=prior_context)
        logger.info(
            "government_assistant_route_selected",
            extra={
                "event": {
                    "assistant": route.assistant,
                    "persona": persona,
                    "reason": route.reason,
                }
            },
        )
        if route.assistant == "clarify":
            return {
                "answer": (
                    "Should I answer this as a question about anomaly events and "
                    "power quality, or about government-grid demand and redistribution?"
                ),
                "persona": persona,
                "entityId": entity_id,
                "conversationId": conversation_id or "",
                "status": "success",
                "citations": [],
                "runReferences": [],
                "downloads": [],
                "artifacts": [],
                "assistantRoute": route.assistant,
            }
        if route.assistant == "anomaly":
            result = self._answer_anomaly_query(
                prompt=prompt,
                persona=persona,
                entity_id=entity_id,
                conversation_id=conversation_id,
                principal=principal,
                authenticated_persona=authenticated_persona,
                authorized_customer_ids=authorized_customer_ids,
                stream_callback=stream_callback,
            )
            result["assistantRoute"] = "anomaly"
            return result

        result = govt_module.handle_user_query(
            prompt,
            provider="ollama",
            history_path=history_path,
        )
        artifact_root = Path(govt_module.DEFAULT_ARTIFACTS_DIR).expanduser().resolve()
        artifacts: list[dict[str, str]] = []
        downloads: list[dict[str, str]] = []
        for path_value, label in (
            (result.image_path, "Government analysis visualization"),
            (result.csv_path, "Government analysis data"),
        ):
            if path_value is None:
                continue
            path = Path(path_value).expanduser().resolve()
            if path.parent != artifact_root or not path.is_file():
                logger.warning("government_assistant_artifact_not_available")
                continue
            file_format = path.suffix.lower().lstrip(".")
            if file_format not in {"png", "csv"}:
                continue
            artifact = {
                "format": file_format,
                "label": label,
                "url": f"/api/v1/assistant/government-artifacts/{path.name}",
            }
            artifacts.append(artifact)
            if file_format == "csv":
                downloads.append(artifact)
        if stream_callback:
            stream_callback(result.text)
        run_references = []
        request = getattr(result, "request", None)
        if request is not None:
            run_id = getattr(request, "run_id", None)
            if run_id:
                run_references.append(str(run_id))
        return {
            "answer": result.text,
            "persona": persona,
            "entityId": entity_id,
            "conversationId": conversation_id or "",
            "status": "success",
            "citations": [],
            "runReferences": run_references,
            "downloads": downloads,
            "artifacts": artifacts,
            "assistantRoute": "government",
        }

    def _answer_anomaly_query(
        self,
        *,
        prompt: str,
        persona: str,
        entity_id: str | None,
        conversation_id: str | None,
        principal: str | None,
        authenticated_persona: str | None,
        authorized_customer_ids: list[int] | None,
        stream_callback: Any | None,
    ) -> dict[str, Any]:
        intent = route_prompt(prompt)["intent"]
        pathway = {
            "technical_explanation": "GENERAL_RAG",
            "general_knowledge": "GENERAL_RAG",
            "general_query": "GENERAL_RAG",
            "historical_anomaly_query": "SAVED_RUN_QUERY",
            "analysis_execution": "MODEL_INFERENCE",
            "customer_impact_query": "EVENT_ANALYSIS",
            "event_query": "EVENT_ANALYSIS",
            "event_detail_followup": "SAVED_RUN_QUERY",
            "rectification_query": "RECTIFICATION_RAG",
            "current_guidance": "EXTERNAL_WEB_SEARCH",
            "export": "EXPORT",
        }.get(intent, "GENERAL_RAG")
        logger.info(
            "assistant_pathway_selected",
            extra={
                "event": {
                    "pathway": pathway,
                    "intent": intent,
                    "persona": persona,
                }
            },
        )
        legacy_domain_query = intent == "general_query" and any(
            term in prompt.lower()
            for term in (
                "bill",
                "tariff",
                "calculate",
                "rupee",
                "inr",
                "peak",
                "reserve",
                "stress",
                "curtail",
            )
        )
        if not legacy_domain_query:
            return self._assistant().ask(
                prompt,
                persona=persona,
                entity_id=entity_id,
                conversation_id=conversation_id,
                principal=principal,
                authenticated_persona=authenticated_persona,
                authorized_customer_ids=authorized_customer_ids,
                stream_callback=stream_callback,
            )

        p = prompt.lower()
        active_entity = entity_id or ("METER-1000" if persona == "household" else ("Panther_office_1" if persona == "commercial" else "North Region"))

        if any(w in p for w in ["bill", "tariff", "calculate", "rupee", "inr"]):
            answer = (
                "**Billing Computation (Prototype Tariff Specification):**\n\n"
                "Your month-end estimated invoice is computed using the baseline equation:\n\n"
                "$$\\text{Estimated Bill (₹)} = (\\text{Month-to-Date kWh} + \\text{Predicted Remaining kWh}) \\times ₹10.00/\\text{kWh}$$\n\n"
                f"- **Active Meter**: `{active_entity}`\n"
                "- **Tariff Rate**: ₹10.00 / kWh (Flat Prototype Tier)\n"
                "- **Cycle Window**: 19 Elapsed Days / 30 Total Days in Billing Cycle.\n\n"
                "To lower your bill, consider shifting heavy induction loads (geysers, washing machines) outside peak hours."
            )
        elif any(w in p for w in ["peak", "reserve", "stress", "curtail"]):
            peak_data = self.data_provider.get_peak_demand_analysis()
            answer = (
                f"**System Peak Demand & Reserve Status:**\n\n"
                f"- **Expected Peak**: **{peak_data['expectedPeakMw']} MW** at `{peak_data['expectedPeakTime']}`\n"
                f"- **Current Active Load**: **{peak_data['currentLoadMw']} MW**\n"
                f"- **Grid Capacity Ceiling**: **{peak_data['peakCapacityLimitMw']} MW**\n"
                f"- **Reserve Margin**: **{peak_data['reserveMarginPct']}%** ({peak_data['riskLevel'].upper()} risk)\n\n"
                "**Recommended Action**: " + peak_data["mitigationStrategy"]
            )
        elif any(w in p for w in ["anomaly", "drift", "spike"]):
            anomalies = self.data_provider.get_anomaly_events()
            active_count = len([a for a in anomalies if a["status"] != "resolved"])
            answer = (
                f"**Active Grid Anomalies Summary:**\n\n"
                f"There are currently **{active_count}** unresolved anomalies being tracked across the regional network:\n\n"
                + "\n".join(
                    f"- **{a['id']}** ({a['entityName']}): {a['anomalyType']} ({a['severity'].upper()}) — *{a['rootCauseDiagnosis']}*"
                    for a in anomalies[:3]
                )
            )
        elif any(w in p for w in ["feature", "influence", "temperature", "degree", "weather"]):
            answer = (
                "**Model Feature Sensitivity & Meteorological Drivers:**\n\n"
                "Inference for commercial facilities is driven by three primary feature groups:\n\n"
                "1. **Thermal Inertia**: Cooling Degree Hours (CDH base 18°C) contributes ~38% of model variance during summer peaks.\n"
                "2. **Autoregressive Lags**: 1-hour and 24-hour lagged electrical draw provide temporal continuity.\n"
                "3. **Occupancy Schedule**: Day-of-week and hour-of-day encodings distinguish operational from night-setback baseloads."
            )
        else:
            answer = (
                f"GridVision telemetry analysis for **{active_entity}** ({persona.capitalize()} scope):\n\n"
                "Historical consumption is tracking normally within confidence bands. "
                "Daily averages and peak window projections are continuously recomputed as new hourly meter intervals stream in."
            )

        return {
            "answer": answer,
            "persona": persona,
            "entityId": active_entity,
            "status": "success",
            "citations": [],
            "runReferences": [],
            "downloads": [],
        }
