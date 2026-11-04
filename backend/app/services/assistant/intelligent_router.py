"""Intelligent Intent Classification and Tool Routing Service for Residential Assistant.

Enforces:
1. Current user message is the primary driver of routing.
2. Context resolves references and follow-ups without overriding the current intent.
3. Distinguishes direct conversation, telemetry queries, predictions, planning, appliances, and standards.
4. Preserves tool availability so queries requiring actual data invoke the correct existing tools.
"""

from __future__ import annotations

import calendar
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

    @staticmethod
    def create_routing_plan(
        prompt: str,
        resolved_state: ResolvedDialogueState,
        active_state: Optional[ActiveConversationState] = None,
    ) -> TurnRoutingPlan:
        """Construct a deterministic routing decision driven by the current query and active context."""
        p_raw = prompt.strip()
        p_low = p_raw.lower()

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
        )

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
                recommended_tools=["predict_usage_and_bill", "forecast_consumption"],
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
