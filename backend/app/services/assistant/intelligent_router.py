"""Intelligent Intent Classification and Tool Routing Service for Residential Assistant.

Enforces:
1. Current user message is the primary driver of routing.
2. Context resolves references and follow-ups without overriding the current intent.
3. Distinguishes direct conversation, telemetry queries, predictions, planning, appliances, and standards.
4. Preserves tool availability so queries requiring actual data invoke the correct existing tools.
"""

from __future__ import annotations

import calendar
import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Set

from app.services.assistant.dialogue_state import ResolvedDialogueState
from app.services.assistant.memory_contracts import (
    ActiveConversationState,
    TurnRoutingPlan,
)

logger = logging.getLogger("gridvision.services.assistant.router")


class IntelligentRouter:
    """Classifies user intent, identifies follow-up relationships, and constructs a typed routing plan."""

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

    _MONTH_NUMBERS = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    _ELECTRICITY_KNOWLEDGE_TERMS = (
        "electricity", "electrical", "power", "energy", "voltage", "current",
        "amp", "watt", "circuit", "wire", "wiring", "socket", "outlet",
        "switch", "grid", "supply", "transformer", "generator", "solar",
        "inverter", "appliance", "rccb", "elcb", "mcb", "earthing",
        "grounding", "neutral", "phase", "safety", "shock", "fuse",
        "overload", "surge", "lighting", "conductor", "insulation",
    )

    @classmethod
    def _extract_month_range(cls, prompt: str) -> Optional[Dict[str, str]]:
        """Return inclusive date arguments for an explicitly named year and month."""
        month_number: Optional[int] = None
        year: Optional[int] = None

        numeric_match = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", prompt)
        if numeric_match:
            year = int(numeric_match.group(1))
            month_number = int(numeric_match.group(2))
        else:
            for name, number in cls._MONTH_NUMBERS.items():
                match = re.search(rf"\b{name}\b", prompt, re.IGNORECASE)
                if match:
                    month_number = number
                    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", prompt)
                    if year_match:
                        year = int(year_match.group(1))
                    break

        if month_number is None or year is None:
            return None

        last_day = calendar.monthrange(year, month_number)[1]
        return {
            "start_date": f"{year:04d}-{month_number:02d}-01",
            "end_date": f"{year:04d}-{month_number:02d}-{last_day:02d}",
            "granularity": "daily",
        }

    @staticmethod
    def _relative_month_range(month_offset: int, end_on_today: bool = False) -> Dict[str, str]:
        """Build a date range for a relative calendar month using the local current date."""
        today = date.today()
        month_index = today.year * 12 + today.month - 1 + month_offset
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        last_day = calendar.monthrange(year, month)[1]
        end_day = today.day if end_on_today else last_day
        return {
            "start_date": f"{year:04d}-{month:02d}-01",
            "end_date": f"{year:04d}-{month:02d}-{end_day:02d}",
            "granularity": "daily",
        }

    @classmethod
    def classify_intent(
        cls,
        prompt: str,
        llm_provider: Any,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Ask the configured LLM to classify a turn into a supported domain intent."""
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
                    "Classify the latest user request for GridVision's residential "
                    "electricity assistant. Return only a JSON object with one "
                    '"intent" string, no explanation. Choose exactly one: '
                    + ", ".join(sorted(cls._CLASSIFIABLE_INTENTS))
                    + ". Use current_billing_summary for the ongoing cycle; "
                    "historical_telemetry_query for recorded past usage or bills; "
                    "forward_bill_prediction for a requested forecast, even when the "
                    "word 'usage' appears; consumption_period_comparison for comparing "
                    "periods; tariff_resolution for the user's applicable tariff; "
                    "regulatory_standards_rag for safety, rules, or official standards; "
                    "electricity_knowledge_rag for general electricity questions; "
                    "house_energy_planning for planning a home installation; "
                    "appliance_lifecycle_analysis for appliance selection or upgrades; "
                    "cost_management for reducing household energy costs; "
                    "complaint_center_guidance for requests to report, file, or get help "
                    "with a residential utility or electrical complaint; "
                    "general_energy_query for other electricity-related requests; "
                    "general_chat for greetings or small talk; irrelevant only when "
                    "unrelated to electricity or GridVision."
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
            response = llm_provider.generate_chat_completion(
                messages=messages,
                temperature=0.0,
                max_tokens=60,
            )
            match = re.search(r"\{[^{}]*\}", response, flags=re.DOTALL)
            if not match:
                raise ValueError("LLM classifier did not return a JSON intent object.")
            intent = json.loads(match.group(0)).get("intent")
            if not isinstance(intent, str) or intent not in cls._CLASSIFIABLE_INTENTS:
                raise ValueError(f"LLM classifier returned an unsupported intent: {intent!r}")
            logger.info("LLM classified residential request as '%s'", intent)
            return intent
        except Exception as exc:
            logger.warning(
                "LLM intent classification failed; using deterministic routing fallback: %s",
                exc,
            )
            return None

    @classmethod
    def _plan_from_classified_intent(
        cls,
        intent: str,
        prompt: str,
        resolved_state: ResolvedDialogueState,
    ) -> TurnRoutingPlan:
        """Translate an LLM intent into an allow-listed tool plan and validated arguments."""
        month_range = cls._extract_month_range(prompt.lower())
        common = {
            "is_continuation": resolved_state.is_continuation,
            "follow_up_type": (
                "topic_change" if resolved_state.is_topic_change else "new_request"
            ),
            "effective_prompt": resolved_state.effective_prompt,
        }

        if intent == "current_billing_summary":
            return TurnRoutingPlan(
                primary_intent=intent,
                resolved_workflow="general_chat",
                resolved_tool_scope="context_only",
                recommended_tools=[],
                requires_tool_execution=False,
                explanation="LLM classified the request as a current billing summary.",
                **common,
            )
        if intent == "historical_telemetry_query":
            args = month_range or (
                cls._relative_month_range(-1)
                if re.search(r"\b(?:last|previous) month\b", prompt, re.I)
                else {}
            )
            return TurnRoutingPlan(
                primary_intent=intent,
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["query_consumption_history"],
                routed_tool_arguments=args,
                requires_tool_execution=True,
                explanation="LLM classified the request as a historical telemetry lookup.",
                **common,
            )
        if intent == "forward_bill_prediction":
            target_month = (
                month_range["start_date"][:7]
                if month_range
                else (
                    cls._relative_month_range(1)["start_date"][:7]
                    if re.search(r"\bnext month\b", prompt, re.I)
                    else None
                )
            )
            return TurnRoutingPlan(
                primary_intent=intent,
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["predict_usage_and_bill"],
                routed_tool_arguments=(
                    {"target_month": target_month} if target_month else {}
                ),
                requires_tool_execution=True,
                explanation="LLM classified the request as a forward usage prediction.",
                **common,
            )
        if intent == "consumption_period_comparison":
            previous_period = cls._relative_month_range(-1)
            current_period = cls._relative_month_range(0, end_on_today=True)
            return TurnRoutingPlan(
                primary_intent=intent,
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["compare_consumption_periods"],
                routed_tool_arguments={
                    "start_date_a": current_period["start_date"],
                    "end_date_a": current_period["end_date"],
                    "start_date_b": previous_period["start_date"],
                    "end_date_b": previous_period["end_date"],
                    "metric": "consumption",
                },
                requires_tool_execution=True,
                explanation="LLM classified the request as a period comparison.",
                **common,
            )
        intent_tools = {
            "complaint_center_guidance": (
                "complaint_guidance",
                ["get_residential_complaint_categories"],
            ),
            "tariff_resolution": (
                "telemetry_and_billing",
                ["resolve_reference_parameter", "get_customer_premises_profile"],
            ),
            "regulatory_standards_rag": (
                "regulatory_and_standards",
                ["search_regulatory_documents", "get_document_clause"],
            ),
            "electricity_knowledge_rag": (
                "regulatory_and_standards",
                ["search_regulatory_documents"],
            ),
            "house_energy_planning": (
                "planning_and_upgrades",
                ["plan_house_energy", "plan_house_area_m2", "search_regulatory_documents"],
            ),
            "appliance_lifecycle_analysis": (
                "planning_and_upgrades",
                [
                    "analyze_appliance_scenario",
                    "lookup_appliance_benchmark",
                    "get_customer_appliance_inventory",
                ],
            ),
            "cost_management": (
                "planning_and_upgrades",
                ["generate_energy_cost_recommendations"],
            ),
            "general_energy_query": (
                "balanced_core",
                [
                    "query_consumption_history",
                    "predict_usage_and_bill",
                    "generate_energy_cost_recommendations",
                ],
            ),
        }
        if intent in intent_tools:
            scope, tools = intent_tools[intent]
            return TurnRoutingPlan(
                primary_intent=intent,
                resolved_workflow=(
                    "house_planning" if intent == "house_energy_planning"
                    else "appliance_lifecycle" if intent == "appliance_lifecycle_analysis"
                    else resolved_state.resolved_mode
                ),
                resolved_tool_scope=scope,
                recommended_tools=tools,
                requires_tool_execution=intent != "general_energy_query",
                explanation=f"LLM classified the request as '{intent}'.",
                **common,
            )
        return TurnRoutingPlan(
            primary_intent=intent,
            resolved_workflow=resolved_state.resolved_mode,
            resolved_tool_scope="context_only",
            recommended_tools=[],
            requires_tool_execution=False,
            explanation=f"LLM classified the request as '{intent}'.",
            **common,
        )

    @staticmethod
    def create_routing_plan(
        prompt: str,
        resolved_state: ResolvedDialogueState,
        active_state: Optional[ActiveConversationState] = None,
        classified_intent: Optional[str] = None,
    ) -> TurnRoutingPlan:
        """Construct a deterministic routing decision driven by the current query and active context."""
        p_raw = prompt.strip()
        p_low = p_raw.lower()

        if classified_intent in IntelligentRouter._CLASSIFIABLE_INTENTS:
            return IntelligentRouter._plan_from_classified_intent(
                classified_intent,
                p_raw,
                resolved_state,
            )

        is_forward_prediction = any(
            word in p_low
            for word in ("predict", "forecast", "future", "upcoming", "next month", "projected")
        )
        month_range = IntelligentRouter._extract_month_range(p_low)
        asks_for_billing_or_usage = any(
            word in p_low
            for word in (
                "bill", "invoice", "consumption", "usage", "energy use",
                "power usage", "electricity use", "kwh",
            )
        )
        has_previous_month = bool(re.search(r"\b(?:last|previous)\s+month\b", p_low))
        has_current_month = bool(re.search(r"\b(?:this|current)\s+month\b", p_low))
        asks_to_compare_periods = bool(
            re.search(r"\b(?:compare|comparison|versus|vs\.?)\b", p_low)
        )
        if (
            has_previous_month
            and has_current_month
            and asks_to_compare_periods
            and asks_for_billing_or_usage
            and not is_forward_prediction
        ):
            previous_period = IntelligentRouter._relative_month_range(-1)
            current_period = IntelligentRouter._relative_month_range(0, end_on_today=True)
            return TurnRoutingPlan(
                primary_intent="consumption_period_comparison",
                is_continuation=False,
                follow_up_type="topic_change" if resolved_state.is_topic_change else "new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["compare_consumption_periods"],
                routed_tool_arguments={
                    "start_date_a": current_period["start_date"],
                    "end_date_a": current_period["end_date"],
                    "start_date_b": previous_period["start_date"],
                    "end_date_b": previous_period["end_date"],
                    "metric": "consumption",
                },
                requires_tool_execution=True,
                effective_prompt=p_raw,
                explanation="The customer requested a comparison of the current and previous calendar months.",
            )

        if (
            has_previous_month
            and asks_for_billing_or_usage
            and not is_forward_prediction
        ):
            return TurnRoutingPlan(
                primary_intent="historical_monthly_billing",
                is_continuation=False,
                follow_up_type="topic_change" if resolved_state.is_topic_change else "new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["query_consumption_history"],
                routed_tool_arguments=IntelligentRouter._relative_month_range(-1),
                requires_tool_execution=True,
                effective_prompt=p_raw,
                explanation="A previous-month usage or billing request requires actual historical meter records.",
            )

        if month_range and asks_for_billing_or_usage and not is_forward_prediction:
            return TurnRoutingPlan(
                primary_intent="historical_monthly_billing",
                is_continuation=False,
                follow_up_type="new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["query_consumption_history"],
                routed_tool_arguments=month_range,
                requires_tool_execution=True,
                effective_prompt=p_raw,
                explanation="An explicitly dated billing request requires actual historical meter records.",
            )

        is_historical_bill_query = (
            bool(re.search(r"\b(?:bill|billing|invoice)\b", p_low))
            and any(
                phrase in p_low
                for phrase in ("last month", "previous month", "historical", "recorded", "actual")
            )
        )
        if is_historical_bill_query:
            return TurnRoutingPlan(
                primary_intent="historical_billing_query",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["query_consumption_history"],
                routed_tool_arguments=(
                    IntelligentRouter._relative_month_range(-1)
                    if has_previous_month
                    else {}
                ),
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Historical billing questions must use recorded meter data, not a prediction.",
            )

        has_bill_term = bool(re.search(r"\b(?:bill|billing|invoice)\b", p_low))
        asks_for_current_bill = (
            bool(re.search(r"\b(?:current|curr|today|now)\b", p_low))
            or bool(re.search(r"\b(?:my|our)\s+(?:current|curr\s+)?bill\b", p_low))
            or bool(re.search(r"\bbill\s+(?:so far|amount|status)\b", p_low))
            or bool(re.search(r"\bmonth[- ]end\b", p_low))
            or p_low.strip() in {"bill", "billing", "invoice"}
        )
        is_current_bill_query = (
            has_bill_term
            and asks_for_current_bill
            and not is_forward_prediction
        )
        if is_current_bill_query:
            return TurnRoutingPlan(
                primary_intent="current_billing_summary",
                is_continuation=False,
                follow_up_type="new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="context_only",
                recommended_tools=[],
                requires_tool_execution=False,
                effective_prompt=p_raw,
                explanation="Use the verified current billing-cycle context; do not make a full-month prediction.",
            )

        # 1. Check for Pending Question Resolution
        if resolved_state.follow_up_type in ("answer_to_pending", "partial_answer"):
            workflow = resolved_state.resolved_mode
            tool_scope = "planning_and_upgrades" if workflow in ("house_planning", "appliance_lifecycle") else "telemetry_and_billing"
            rec_tools_by_workflow = {
                "house_planning": ["plan_house_energy"],
                "appliance_lifecycle": ["analyze_appliance_scenario"],
                "cost_management": ["generate_energy_cost_recommendations"],
            }
            rec_tools = rec_tools_by_workflow.get(workflow, [])

            return TurnRoutingPlan(
                primary_intent=f"answer_{resolved_state.answered_field or 'pending_question'}",
                is_continuation=True,
                follow_up_type=resolved_state.follow_up_type,
                resolved_workflow=workflow,
                resolved_tool_scope=tool_scope,
                recommended_tools=rec_tools,
                requires_tool_execution=True,
                answered_field=resolved_state.answered_field,
                answered_value=resolved_state.answered_value,
                effective_prompt=resolved_state.effective_prompt,
                explanation=f"Answered pending question field '{resolved_state.answered_field}'. Continuing active workflow '{workflow}'.",
            )

        # 2. Check for Explicit User Correction
        if resolved_state.follow_up_type == "correction":
            return TurnRoutingPlan(
                primary_intent="slot_correction",
                is_continuation=True,
                follow_up_type="correction",
                resolved_workflow=resolved_state.resolved_mode,
                resolved_tool_scope="planning_and_upgrades",
                recommended_tools=["analyze_appliance_scenario", "plan_house_energy"],
                requires_tool_execution=True,
                answered_field=resolved_state.answered_field,
                answered_value=resolved_state.answered_value,
                effective_prompt=resolved_state.effective_prompt,
                explanation=f"Corrected slot '{resolved_state.answered_field}' to {resolved_state.answered_value}.",
            )

        # 3. Check for Reference to Prior Calculation / Result
        if resolved_state.follow_up_type == "reference_to_result":
            return TurnRoutingPlan(
                primary_intent="result_optimization_or_explanation",
                is_continuation=True,
                follow_up_type="reference_to_result",
                resolved_workflow=resolved_state.resolved_mode,
                resolved_tool_scope=resolved_state.tool_scope,
                recommended_tools=["plan_house_energy", "analyze_appliance_scenario", "generate_energy_cost_recommendations"],
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Customer referenced a prior calculated metric or plan. Re-evaluating with optimizations.",
            )

        # 4. Check for Explicit Tariff / Rate Query
        # Example: "Which tariff applies to me?", "what is my tariff rate", "resolve tariff"
        if any(w in p_low for w in ["which tariff", "what tariff", "my tariff", "tariff rate", "tariff slab", "tariff applies to me"]):
            return TurnRoutingPlan(
                primary_intent="tariff_resolution",
                is_continuation=False,
                follow_up_type="new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["resolve_reference_parameter", "get_customer_premises_profile"],
                requires_tool_execution=True,
                effective_prompt=p_raw,
                explanation="Customer requested applicable electricity tariff or slab rate. Routing to reference and profile tools.",
            )

        # 5. Check for Historical Telemetry Analytics vs Forward Prediction
        # Historical: "what was my actual consumption?", "explain my last month's usage", "why did my bill increase"
        # Forward Prediction: "predict my next month bill", "forecast usage"
        is_negated_predict = any(w in p_low for w in ["dont predict", "don't predict", "not predict", "do not predict"])
        is_forward_prediction = is_forward_prediction and not is_negated_predict
        is_historical_telemetry = (
            any(w in p_low for w in [
                "explain my last month", "what was my usage", "what was my actual consumption",
                "actual consumption", "actually consume",
                "last month's usage", "last month consumption", "why is my electricity bill higher",
                "why did my bill increase", "what caused my electricity bill", "usage on", "consumption on",
                "find from the database", "database", "recorded", "telemetry", "yesterday", "all-time"
            ])
            or bool(
                re.search(
                    r"\bhow much (?:electricity|power|energy)\b.{0,30}\b(?:did|do|does|have)\s+(?:i|we|my household|our household)\b",
                    p_low,
                )
            )
            or is_negated_predict
        ) and not is_forward_prediction

        if is_historical_telemetry:
            return TurnRoutingPlan(
                primary_intent="historical_telemetry_query",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="topic_change" if resolved_state.is_topic_change else "new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["query_consumption_history", "compare_consumption_periods", "get_consumption_breakdown"],
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Customer requested historical smart meter telemetry or consumption breakdown. Invoking query tools.",
            )

        if is_forward_prediction:
            return TurnRoutingPlan(
                primary_intent="forward_bill_prediction",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="telemetry_and_billing",
                recommended_tools=["predict_usage_and_bill"],
                routed_tool_arguments=(
                    {"target_month": month_range["start_date"][:7]}
                    if month_range
                    else {}
                ),
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Customer requested future ML bill or consumption forecast. Invoking predictive tools.",
            )

        asks_for_personal_meter_data = bool(
            re.search(r"\b(?:my|our|household)\b", p_low)
            and re.search(
                r"\b(?:bill|billing|invoice|consumption|usage|kwh|reading|(?:energy|power|electricity) use)\b",
                p_low,
            )
        )
        if asks_for_personal_meter_data:
            return TurnRoutingPlan(
                primary_intent="current_household_usage_summary",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="topic_change" if resolved_state.is_topic_change else "new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="context_only",
                recommended_tools=[],
                requires_tool_execution=False,
                effective_prompt=resolved_state.effective_prompt,
                explanation=(
                    "No historical period was specified, so use the verified latest "
                    "household usage context instead of asking the model to invent dates."
                ),
            )

        # 6. Check for Appliance Lifecycle / Selection Query
        # Examples: "Help choose an AC", "Now help me choose an AC", "Compare my actual appliances", "replace ac", "bldc"
        if any(w in p_low for w in [
            "help choose an ac", "choose an ac", "choose ac", "help me choose an ac",
            "replace ac", "upgrade fan", "bldc", "iseer", "5-star ac", "3-star vs 5-star",
            "compare my actual appliances", "compare appliances", "appliance lifecycle", "payback"
        ]):
            return TurnRoutingPlan(
                primary_intent="appliance_lifecycle_analysis",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="new_request",
                resolved_workflow="appliance_lifecycle",
                resolved_tool_scope="planning_and_upgrades",
                recommended_tools=["analyze_appliance_scenario", "lookup_appliance_benchmark", "get_customer_appliance_inventory"],
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Customer requested appliance selection, upgrade comparison, or lifecycle payback.",
            )

        # 7. Check for New House Planning Query
        if any(w in p_low for w in [
            "plan house", "new house", "new home", "new villa", "electrical layout",
            "electrical load", "connected load", "wiring sub-circuit", "is 732",
        ]):
            return TurnRoutingPlan(
                primary_intent="house_energy_planning",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="new_request",
                resolved_workflow="house_planning",
                resolved_tool_scope="planning_and_upgrades",
                recommended_tools=["plan_house_energy", "plan_house_area_m2", "search_regulatory_documents"],
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Customer requested house electrical planning or connected load calculation under IS 732.",
            )

        # 8. Check for Electrical Safety & Regulatory Standards Query
        if any(w in p_low for w in [
            "safety", "guideline", "guidelines", "precaution", "hazard", "shock",
            "earthing", "grounding", "rccb", "elcb", "mcb", "electrical safety"
        ]):
            return TurnRoutingPlan(
                primary_intent="regulatory_standards_rag",
                is_continuation=False,
                follow_up_type="new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="regulatory_and_standards",
                recommended_tools=["search_regulatory_documents", "get_document_clause"],
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation="Customer requested electrical safety standards or official IS 732 guidelines.",
            )

        has_electricity_knowledge_topic = any(
            re.search(rf"\b{re.escape(term)}\b", p_low)
            for term in IntelligentRouter._ELECTRICITY_KNOWLEDGE_TERMS
        )
        is_specialized_workflow = resolved_state.resolved_mode in {
            "house_planning",
            "appliance_lifecycle",
            "cost_management",
        }
        if has_electricity_knowledge_topic and not is_specialized_workflow:
            return TurnRoutingPlan(
                primary_intent="electricity_knowledge_rag",
                is_continuation=resolved_state.is_continuation,
                follow_up_type="continuation" if resolved_state.is_continuation else "new_request",
                resolved_workflow="general_chat",
                resolved_tool_scope="regulatory_and_standards",
                recommended_tools=["search_regulatory_documents"],
                requires_tool_execution=True,
                effective_prompt=resolved_state.effective_prompt,
                explanation=(
                    "A general electricity knowledge request requires retrieval from "
                    "the verified document knowledge base."
                ),
            )

        # 9. Fallback: General conversational or core analytics query
        return TurnRoutingPlan(
            primary_intent="general_energy_query",
            is_continuation=resolved_state.is_continuation,
            follow_up_type="continuation" if resolved_state.is_continuation else "new_request",
            resolved_workflow=resolved_state.resolved_mode,
            resolved_tool_scope=resolved_state.tool_scope or "balanced_core",
            recommended_tools=["query_consumption_history", "predict_usage_and_bill", "generate_energy_cost_recommendations"],
            requires_tool_execution=False,
            effective_prompt=resolved_state.effective_prompt,
            explanation="General domain query processed with balanced tool availability.",
        )

    @classmethod
    def route(
        cls,
        current_message: str,
        active_state: Optional[ActiveConversationState] = None,
        last_assistant_message: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> TurnRoutingPlan:
        """Convenience method to classify intent and route a single user turn."""
        from app.services.assistant.dialogue_state import resolve_dialogue_context

        synth_history = list(history or [])
        if last_assistant_message and not any(m.get("content") == last_assistant_message for m in synth_history):
            synth_history.append({"role": "assistant", "content": last_assistant_message})

        resolved = resolve_dialogue_context(current_message, history=synth_history, active_state=active_state)
        return cls.create_routing_plan(current_message, resolved, active_state)
