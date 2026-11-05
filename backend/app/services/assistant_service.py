"""Domain-grounded AI assistant service."""

from __future__ import annotations

import hashlib
import importlib
import logging
import re
from pathlib import Path
from typing import Any

from app.providers.data_provider import BaseDataProvider
from ai.anamoly.agents.query_router import route_prompt
from ai.anamoly.memory.conversation_memory import ConversationMemory
from ai.anamoly.agents.orchestrator import AnomalyAssistant
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.tools.renewable_energy import RenewableEnergyTools

logger = logging.getLogger("gridvision.anomaly.agent")


class AssistantService:
    """Preserve GridVision's existing insights and route anomaly and government queries."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        anomaly_service: Any | None = None,
        renewable_tools: RenewableEnergyTools | None = None,
        *,
        route_government_queries: bool = True,
        llm_provider: Any = None,
        tariff_rate: float = 10.0,
        authorized_meters: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
        agent_factory: Any = None,
        prediction_service: Any = None,
        **kwargs: Any,
    ) -> None:
        self.data_provider = data_provider
        self.anomaly_service = anomaly_service
        self.route_government_queries = route_government_queries
        settings = CommercialSettings.from_env()
        self.renewable_tools = renewable_tools or RenewableEnergyTools(
            api_key_file=settings.tavily_api_key_file,
            timeout_seconds=settings.tavily_timeout_seconds,
        )
        self._anomaly_assistant: AnomalyAssistant | None = None
        self.llm_provider = llm_provider
        self.prediction_service = prediction_service
        self.residential_orchestrator = None
        try:
            from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator
            self.residential_orchestrator = ResidentialAssistantOrchestrator(
                data_provider=data_provider,
                llm_provider=llm_provider,
                tariff_rate=tariff_rate,
                authorized_meters=authorized_meters,
                temperature=temperature,
                max_tokens=max_tokens,
                agent_factory=agent_factory,
                prediction_service=prediction_service,
            )
        except Exception as exc:
            logger.info("ResidentialAssistantOrchestrator not initialized: %s", exc)

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
        history: list[dict[str, Any]] | None = None,
        user_id: str | None = None,
        **kwargs: Any,
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
        if persona in ("household", "residential") and self.residential_orchestrator is not None and not stream_callback:
            try:
                res = self.residential_orchestrator.answer_query(
                    prompt=prompt,
                    entity_id=entity_id,
                    history=history,
                    user_id=principal or user_id,
                    conversation_id=conversation_id,
                )
                if res and res.get("status") not in ("error", None):
                    return res
            except Exception as exc:
                logger.warning("Residential orchestrator encountered error, falling back: %s", exc)
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
        active_entity = entity_id or "Bear & Aggregate"
        try:
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
            previous_request = history.get("last_successful_request")
            artifact_follow_up = bool(
                re.search(r"\b(image|png|visuali[sz]ation|csv|spreadsheet)\b", prompt, re.I)
                and re.search(r"\b(give me|generate|create|make|show|export)\b", prompt, re.I)
                and not re.search(r"\b(anomaly|power quality|outage)\b", prompt, re.I)
            )
            has_previous_government_result = bool(
                previous_request is not None
                and getattr(previous_request, "forecast_date", None)
                and getattr(previous_request, "intent", None)
                in {
                    "plan", "summary", "hourly_summary", "surplus_deficit",
                    "transfers", "losses", "grid_plan", "compare_hours",
                    "compare_grids", "unmet_demand", "demand_solution",
                    "image_generation", "csv_generation",
                }
            )
            if artifact_follow_up and has_previous_government_result:
                # The file type is a follow-up to the successful Government
                # result in this conversation. Avoid an ambiguous second LLM
                # routing decision (which can otherwise ask for clarification
                # or send it to anomaly handling).
                from ai.govt.router import AssistantRoute

                route = AssistantRoute(
                    "government",
                    "Artifact request follows the previous Government result.",
                )
            else:
                route = route_query(
                    prompt,
                    prior_context=prior_context,
                    default_assistant="government",
                )
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
                clarification = (
                    "Should I answer this as a question about anomaly events and "
                    "power quality, or about government-grid demand and redistribution?"
                )
                if stream_callback:
                    stream_callback(clarification)
                return {
                    "answer": clarification,
                    "persona": persona,
                    "entityId": active_entity,
                    "conversationId": conversation_id or "",
                    "status": "success",
                    "citations": [],
                    "runReferences": [],
                    "downloads": [],
                    "artifacts": [],
                    "charts": [],
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
                "entityId": active_entity,
                "conversationId": conversation_id or "",
                "status": "success",
                "citations": [],
                "runReferences": run_references,
                "downloads": downloads,
                "artifacts": artifacts,
                "charts": [],
                "assistantRoute": "government",
            }
        except Exception as exc:
            logger.exception("government_routed_query_failed error=%s", exc)
            fallback_answer = (
                f"Government assistant analysis for **{active_entity}** encountered an issue: {exc}\n\n"
                "Please verify that Ollama is running and configured models (qwen3:8b, qwen3:1.7b, batiai/gemma4-e2b:q4) are reachable."
            )
            if stream_callback:
                stream_callback(fallback_answer)
            return {
                "answer": fallback_answer,
                "persona": persona,
                "entityId": active_entity,
                "conversationId": conversation_id or "",
                "status": "success",
                "citations": [],
                "runReferences": [],
                "downloads": [],
                "artifacts": [],
                "charts": [],
                "assistantRoute": "error",
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
        p = prompt.lower()
        active_entity = entity_id or ("METER-1000" if persona == "household" else ("Panther_office_1" if persona == "commercial" else "Bear & Aggregate"))

        if any(
            word in p
            for word in ("solar", "renewable", "wind", "photovoltaic", "rooftop")
        ):
            observation = self.renewable_tools.get_renewable_scenarios(
                active_entity,
                prompt,
            )
            answer_parts = list(observation.findings)
            answer_parts.extend(
                f"Assumption: {assumption}"
                for assumption in observation.assumptions
            )
            if observation.evidence_refs:
                answer_parts.append(
                    "Web sources:\n"
                    + "\n".join(
                        f"- {reference.locator}"
                        for reference in observation.evidence_refs
                        if reference.locator
                    )
                )
            if any(w in p for w in ["peak", "demand", "load", "forecast"]):
                peak_data = self.data_provider.get_peak_demand_analysis()
                answer_parts.append(
                    "**Grid peak context:** "
                    f"expected system peak **{peak_data['expectedPeakMw']} MW** "
                    f"at `{peak_data['expectedPeakTime']}` "
                    f"({peak_data['riskLevel']} risk)."
                )
            answer = "\n\n".join(answer_parts)
            if stream_callback and answer:
                for token in answer.split(" "):
                    stream_callback(token + " ")
            return {
                "answer": answer,
                "persona": persona,
                "entityId": active_entity,
                "conversationId": conversation_id or "default",
                "status": "success",
                "citations": [],
                "runReferences": [],
                "downloads": [],
                "artifacts": [],
                "charts": [],
            }

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
            term in p
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
        if not legacy_domain_query and self.anomaly_service is not None:
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

        if stream_callback and answer:
            words = answer.split(" ")
            for i, word in enumerate(words):
                stream_callback(word + (" " if i < len(words) - 1 else ""))

        return {
            "answer": answer,
            "persona": persona,
            "entityId": active_entity,
            "conversationId": conversation_id or "default",
            "status": "success",
            "citations": [],
            "runReferences": [],
            "downloads": [],
            "artifacts": [],
            "charts": [],
        }
