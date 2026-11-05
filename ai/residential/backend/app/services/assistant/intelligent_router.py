"""LLM-based intent classification and tool-scope selection."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.services.assistant.dialogue_state import (
    ResolvedDialogueState,
    resolve_dialogue_context,
)
from app.services.assistant.memory_contracts import (
    ActiveConversationState,
    TurnRoutingPlan,
)

logger = logging.getLogger("gridvision.services.assistant.router")


class IntelligentRouter:
    """Classify each request with the configured LLM and expose tools by domain scope."""

    _CLASSIFIABLE_INTENTS = {
        "current_billing_summary",
        "historical_telemetry_query",
        "forward_bill_prediction",
        "consumption_period_comparison",
        "tariff_resolution",
        "regulatory_standards_rag",
        "electricity_knowledge_rag",
        "complaint_center_guidance",
        "house_energy_planning",
        "appliance_lifecycle_analysis",
        "cost_management",
        "general_energy_query",
        "general_chat",
        "irrelevant",
    }

    _TOOL_REQUIRED_INTENTS = {
        "historical_telemetry_query",
        "forward_bill_prediction",
        "consumption_period_comparison",
        "tariff_resolution",
        "regulatory_standards_rag",
        "electricity_knowledge_rag",
        "complaint_center_guidance",
        "house_energy_planning",
        "appliance_lifecycle_analysis",
        "cost_management",
    }

    _INTENT_WORKFLOWS = {
        "house_energy_planning": "house_planning",
        "appliance_lifecycle_analysis": "appliance_lifecycle",
        "cost_management": "cost_management",
    }

    @classmethod
    def classify_intent(
        cls,
        prompt: str,
        llm_provider: Any,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Ask the configured LLM to classify a turn; never substitute keyword routing."""
        if not llm_provider:
            return None

        recent_context = [
            {
                "role": message.get("role"),
                "content": str(message.get("content", ""))[-500:],
            }
            for message in (history or [])[-6:]
            if message.get("role") in {"user", "assistant"}
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    f"Today is {date.today().isoformat()}. Classify the latest user request "
                    "for GridVision's residential electricity "
                    "assistant. Return exactly one JSON object with one `intent` string; "
                    "do not include analysis, markdown, or extra fields. "
                    "Choose exactly one of these values: "
                    + ", ".join(sorted(cls._CLASSIFIABLE_INTENTS))
                    + ". Use conversation history only to resolve references and follow-ups; "
                    "classify the latest request itself. current_billing_summary means the "
                    "ongoing billing cycle; historical_telemetry_query means recorded past "
                    "usage or bills; forward_bill_prediction means a future forecast; "
                    "consumption_period_comparison means comparing periods; tariff_resolution "
                    "means resolving the customer's tariff; regulatory_standards_rag means "
                    "official standards or safety requirements; electricity_knowledge_rag "
                    "means general electricity knowledge; house_energy_planning means "
                    "planning a home installation; appliance_lifecycle_analysis means "
                    "appliance selection or upgrades; cost_management means reducing "
                    "household energy costs; complaint_center_guidance means reporting or "
                    "getting help with a utility/electrical complaint; general_energy_query "
                    "means other electricity-related requests; for a requested future "
                    "calendar-month usage or bill estimate, use forward_bill_prediction "
                    "only when the requested period is in the future; a period that has "
                    "already ended is historical telemetry even if the user says "
                    "predict. Preserve the requested month and year; do not silently "
                    "correct them. cost_management means creating a personalized, "
                    "quantified savings plan based on household usage or budget. "
                    "general_energy_query includes broad advice or explanations that "
                    "can be answered without new customer-specific data or calculations. "
                    "For follow-up questions asking for general tips or explanation of "
                    "a prior answer, classify the latest request as general_energy_query "
                    "and use the conversation context; require a new tool only when the "
                    "user asks for new customer-specific data or a calculation. "
                    "general_chat means greetings "
                    "or small talk; irrelevant means unrelated to electricity or GridVision."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Recent conversation: {json.dumps(recent_context, ensure_ascii=True)}\n"
                    f"Latest request: {prompt.strip()}"
                ),
            },
        ]
        try:
            if not llm_provider.is_available():
                return None
            classification_messages = messages
            for attempt in range(2):
                response = llm_provider.generate_chat_completion(
                    messages=classification_messages,
                    temperature=0.0,
                    max_tokens=256,
                )
                try:
                    intent = cls._parse_intent_response(response)
                    if intent not in cls._CLASSIFIABLE_INTENTS:
                        raise ValueError(
                            f"LLM classifier returned an unsupported intent: {intent!r}"
                        )
                    logger.info("LLM classified residential request as '%s'", intent)
                    return intent
                except ValueError:
                    if attempt:
                        raise
                    classification_messages = [
                        {
                            "role": "system",
                            "content": (
                                messages[0]["content"]
                                + " Your previous output was invalid. Return exactly "
                                '{"intent":"one_allowed_intent"} and nothing else.'
                            ),
                        },
                        messages[1],
                    ]
                    logger.warning(
                        "Residential LLM returned an invalid intent format; retrying classification once."
                    )
        except Exception as exc:
            logger.warning(
                "LLM intent classification failed; no keyword routing was attempted: %s",
                exc,
            )
            return None

    @classmethod
    def _parse_intent_response(cls, response: str) -> str:
        """Parse a supported intent from JSON or a bare LLM intent label."""
        text = (response or "").strip()
        candidates = [text]
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            candidates.append(fenced.group(1).strip())
        json_match = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
        if json_match:
            candidates.append(json_match.group(0))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("intent"), str):
                return parsed["intent"]

        if text in cls._CLASSIFIABLE_INTENTS:
            return text
        normalized = re.sub(r"[\s-]+", "_", text.strip().lower()).strip("`\"' .:")
        if normalized in cls._CLASSIFIABLE_INTENTS:
            return normalized

        labels = [
            intent
            for intent in cls._CLASSIFIABLE_INTENTS
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(intent)}(?![A-Za-z0-9_])", text)
        ]
        if len(labels) == 1:
            return labels[0]
        raise ValueError("LLM classifier did not return one supported intent.")

    @classmethod
    def _plan_from_classified_intent(
        cls,
        intent: str,
        prompt: str,
        resolved_state: ResolvedDialogueState,
    ) -> TurnRoutingPlan:
        """Set execution policy from intent; the tool-calling LLM chooses the actual tools."""
        common = {
            "is_continuation": resolved_state.is_continuation,
            "follow_up_type": (
                "topic_change" if resolved_state.is_topic_change else "new_request"
            ),
            "effective_prompt": resolved_state.effective_prompt or prompt,
            "is_topic_change": resolved_state.is_topic_change,
        }

        if resolved_state.follow_up_type in {"answer_to_pending", "partial_answer"}:
            return TurnRoutingPlan(
                primary_intent="conversation_continuation",
                resolved_workflow=resolved_state.resolved_mode,
                resolved_tool_scope="context_only",
                recommended_tools=[],
                requires_tool_execution=False,
                explanation=(
                    "The LLM-classified turn answers a pending dialogue question; "
                    "continue without running a calculation."
                ),
                **common,
            )

        if intent == "current_billing_summary":
            return TurnRoutingPlan(
                primary_intent=intent,
                resolved_workflow="general_chat",
                resolved_tool_scope="context_only",
                recommended_tools=[],
                requires_tool_execution=False,
                explanation="The LLM classified this as a current billing summary.",
                **common,
            )

        requires_tool_execution = intent in cls._TOOL_REQUIRED_INTENTS
        scope = "all" if requires_tool_execution else "context_only"
        workflow = cls._INTENT_WORKFLOWS.get(intent, resolved_state.resolved_mode)
        if intent in {"general_chat", "irrelevant"}:
            workflow = "general_chat" if intent == "general_chat" else "irrelevant"

        return TurnRoutingPlan(
            primary_intent=intent,
            resolved_workflow=workflow,
            resolved_tool_scope=scope,
            recommended_tools=[],
            requires_tool_execution=requires_tool_execution,
            explanation=(
                f"The LLM classified the request as '{intent}'. The tool-calling LLM "
                "selects the appropriate tool from the complete authorized toolset."
            ),
            **common,
        )

    @classmethod
    def create_routing_plan(
        cls,
        prompt: str,
        resolved_state: ResolvedDialogueState,
        active_state: Optional[ActiveConversationState] = None,
        classified_intent: Optional[str] = None,
    ) -> TurnRoutingPlan:
        """Create a route only from an allow-listed LLM intent; otherwise fail closed."""
        clean_prompt = prompt.strip()
        if classified_intent in cls._CLASSIFIABLE_INTENTS:
            return cls._plan_from_classified_intent(
                classified_intent,
                clean_prompt,
                resolved_state,
            )

        return TurnRoutingPlan(
            primary_intent="classification_unavailable",
            resolved_workflow=resolved_state.resolved_mode,
            resolved_tool_scope="context_only",
            recommended_tools=[],
            requires_tool_execution=False,
            effective_prompt=resolved_state.effective_prompt or clean_prompt,
            explanation="The LLM did not return a valid allow-listed intent; no keyword route was applied.",
        )

    @classmethod
    def route(
        cls,
        current_message: str,
        active_state: Optional[ActiveConversationState] = None,
        last_assistant_message: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        llm_provider: Any = None,
    ) -> TurnRoutingPlan:
        """Classify and route one turn using the same LLM path as the orchestrator."""
        synth_history = list(history or [])
        if last_assistant_message and not any(
            message.get("content") == last_assistant_message
            for message in synth_history
        ):
            synth_history.append(
                {"role": "assistant", "content": last_assistant_message}
            )

        resolved = resolve_dialogue_context(
            current_message,
            history=synth_history,
            active_state=active_state,
        )
        intent = cls.classify_intent(
            current_message,
            llm_provider=llm_provider,
            history=synth_history,
        )
        return cls.create_routing_plan(
            current_message,
            resolved,
            active_state=active_state,
            classified_intent=intent,
        )
