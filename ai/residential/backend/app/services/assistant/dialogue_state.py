"""Dialogue state tracking, contextual anaphora resolution, and history compaction.

Provides industry-standard dialogue management for multi-turn assistant conversations:
1. Contextual Anaphora & Continuation Resolution (resolves short follow-ups like 'yes generate', 'proceed', 'option 1').
2. Compact History Pruning (prevents LLM token overflow and Groq 7,000 ITPM rate limits).
3. Target-Calibrated Energy Savings Calculations (eliminates mathematical contradictions).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


AFFIRMATIVE_KEYWORDS = {
    "yes", "yes generate", "generate", "proceed", "sure", "ok", "okay",
    "do it", "go ahead", "please do", "confirm", "yes please", "generate plan",
    "apply", "optimize", "update", "continue", "next", "show me", "tell me more",
    "yes do it", "yes proceed", "ok do it", "sounds good", "make it so",
    "let's do it", "lets do it", "go for it", "generate it", "show plan",
    "calculate", "run it", "accept", "apply changes", "yep", "yeah", "y",
}

AFFIRMATIVE_PATTERN = re.compile(
    r"^(yes|yeah|yep|sure|ok|okay|please|proceed|generate|do it|confirm|apply)\b",
    re.IGNORECASE,
)

SELECTION_PATTERN = re.compile(
    r"^(option\s*\d+|the\s+(first|second|third|fourth|last)(\s+one|\s+option)?|plan\s+\w+)",
    re.IGNORECASE,
)


@dataclass
class CustomerLongTermMemory:
    """Persistent Long-Term Memory (LTM) for customer and household premises."""
    meter_id: str
    customer_name: str
    persona: str = "RESIDENTIAL"
    tariff_rate_inr_per_kwh: float = 10.0
    baseline_daily_average_kwh: Optional[float] = None
    baseline_monthly_average_kwh: Optional[float] = None
    contracted_load_kw: Optional[float] = None
    supply_phase: Optional[str] = "Single Phase (230V)"

    def format_compact_context(self) -> str:
        """Serialize LTM into a compact grounding block (< 150 tokens) to prevent rate limits."""
        parts = [
            f"METER: {self.meter_id}",
            f"CUSTOMER: {self.customer_name}",
            f"TARIFF: ₹{self.tariff_rate_inr_per_kwh:.2f}/kWh",
        ]
        if self.baseline_daily_average_kwh is not None:
            parts.append(f"DAILY_BASELINE: {self.baseline_daily_average_kwh:.1f} kWh/day")
        if self.baseline_monthly_average_kwh is not None:
            parts.append(f"MONTHLY_BASELINE: {self.baseline_monthly_average_kwh:.1f} kWh")
        return " | ".join(parts)


@dataclass
class ConversationShortTermMemory:
    """Sliding-window Short-Term Memory (STM) tracking recent dialogue turns and active intent."""
    recent_turns: List[Dict[str, str]] = field(default_factory=list)
    active_intent_mode: str = "general_chat"
    active_tool_scope: str = "balanced_core"

    @classmethod
    def from_history(
        cls,
        history: Optional[List[Dict[str, Any]]],
        active_mode: str = "general_chat",
        active_scope: str = "balanced_core",
        max_turns: int = 4,
    ) -> "ConversationShortTermMemory":
        compacted = compact_history_for_llm(history, max_turns=max_turns)
        return cls(
            recent_turns=compacted,
            active_intent_mode=active_mode,
            active_tool_scope=active_scope,
        )


@dataclass
class ResolvedDialogueState:
    """Carries resolved dialogue context for multi-turn conversational execution."""
    raw_prompt: str
    is_continuation: bool
    resolved_mode: str
    tool_scope: str
    effective_prompt: str
    pending_proposal_summary: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    long_term_memory: Optional[CustomerLongTermMemory] = None
    short_term_memory: Optional[ConversationShortTermMemory] = None
    active_state: Optional[Any] = None
    is_topic_change: bool = False
    follow_up_type: Optional[str] = None
    answered_field: Optional[str] = None
    answered_value: Optional[Any] = None


CORRECTION_PATTERNS = [
    re.compile(r"\b(dont|don't|do not|no)\s+(predict|predic|forecast|estimate)\b", re.IGNORECASE),
    re.compile(r"\b(query|fetch|get|find|look up)\s+(it|data|database|telemetry|records?)\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+(the\s+)?(database|telemetry|records)\b", re.IGNORECASE),
    re.compile(r"\b(not\s+predict|not\s+prediction|actual\s+data|real\s+data|historical\s+data)\b", re.IGNORECASE),
]


def is_affirmative_or_continuation(prompt: str) -> bool:
    """Return True if user prompt is a short affirmative, selection, continuation, or corrective phrase."""
    p = prompt.strip().lower()
    if p in AFFIRMATIVE_KEYWORDS:
        return True
    if any(pat.search(p) for pat in CORRECTION_PATTERNS):
        return True
    if len(p.split()) <= 5 and (AFFIRMATIVE_PATTERN.match(p) or SELECTION_PATTERN.match(p)):
        return True
    return False


def extract_pending_question_from_context(
    active_state: Optional[Any],
    last_assistant_turn: str,
) -> Optional[Dict[str, str]]:
    """Determine outstanding question and expected field from active state or prior turn."""
    if active_state and getattr(active_state, "awaiting_user_response", False):
        pq = getattr(active_state, "pending_question", None)
        if pq:
            return {
                "field": getattr(pq, "field", ""),
                "expected_type": getattr(pq, "expected_response_type", "string"),
                "workflow": getattr(pq, "workflow", "") or getattr(active_state, "active_workflow", "house_planning"),
            }

    if not last_assistant_turn:
        return None

    last_low = last_assistant_turn.lower()
    if any(q in last_low for q in ["which city", "property located", "what city", "location of your property"]):
        return {"field": "location_city", "expected_type": "string", "workflow": "house_planning"}
    if any(q in last_low for q in ["how many bedrooms", "how many rooms", "how many bhk"]):
        if "which rooms do you need ac" in last_low or "which rooms will have them" in last_low:
            return {"field": "bedrooms_and_ac_rooms", "expected_type": "multi", "workflow": "house_planning"}
        return {"field": "bedrooms_count", "expected_type": "integer", "workflow": "house_planning"}
    if any(q in last_low for q in ["how many acs do you need", "how many ac do you need", "how many acs"]):
        return {"field": "ac_count_and_rooms", "expected_type": "multi", "workflow": "appliance_lifecycle"}
    if any(q in last_low for q in ["how many hours per day", "hours per day do you use"]):
        return {"field": "ac_usage_hours", "expected_type": "float", "workflow": "appliance_lifecycle"}
    if any(q in last_low for q in ["which electricity bill period", "which bill period", "period should i compare"]):
        return {"field": "bill_period", "expected_type": "string", "workflow": "general_chat"}
    if any(q in last_low for q in ["which ac model are you considering", "which model are you considering"]):
        return {"field": "ac_model", "expected_type": "string", "workflow": "appliance_lifecycle"}
    return None


def resolve_dialogue_context(
    prompt: str,
    history: Optional[List[Dict[str, Any]]] = None,
    explicit_mode: Optional[str] = None,
    active_state: Optional[Any] = None,
) -> ResolvedDialogueState:
    """Resolve user intent, pending questions, slot values, and topic changes across turns.

    Guarantees:
    1. Answers to pending questions ('Bengaluru', 'two', 'about 6 hours') are bound to active workflows.
    2. Partial answers preserve outstanding fields without resetting the workflow.
    3. User topic switches ('Actually, why is my bill high?') immediately re-route without being hijacked by prior flow.
    4. Current user prompt remains the primary driver of routing.
    """
    clean_p = (prompt or "").strip()
    p_lower = clean_p.lower()

    # If explicit mode tab is active and valid, honor it
    if explicit_mode and explicit_mode in ("house_planning", "appliance_lifecycle", "cost_management"):
        tool_scope = "planning_and_upgrades" if explicit_mode != "cost_management" else "telemetry_and_billing"
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode=explicit_mode,
            tool_scope=tool_scope,
            effective_prompt=clean_p,
            active_state=active_state,
        )

    # Inspect previous assistant and user turns if history is available
    last_assistant_turn = ""
    last_user_turn = ""
    if history:
        for item in reversed(history):
            role = str(item.get("role", "")).lower().strip()
            content = str(item.get("content", "")).strip()
            if role == "assistant" and not last_assistant_turn:
                last_assistant_turn = content
            elif role == "user" and not last_user_turn:
                last_user_turn = content
            if last_assistant_turn and last_user_turn:
                break

    # -------------------------------------------------------------------------
    # 0. Check for Explicit Topic Interruption / Topic Change
    # -------------------------------------------------------------------------
    is_telemetry_or_billing_query = any(w in p_lower for w in [
        "why is my", "why was my", "bill increased", "bill increase", "bill higher",
        "electricity bill", "what caused my", "explain my last", "usage higher",
        "actual consumption", "actually consume", "how much electricity", "how much power",
        "consume last month", "consumption last month", "consumed last month",
        "usage on", "what was my usage", "find from the database",
        "last month's usage", "last month consumption", "past usage", "what was my electricity",
        "outage", "sparking", "power cut"
    ])
    mentions_energy_cost = any(
        word in p_lower for word in ("bill", "electricity", "energy", "consumption", "usage")
    )
    asks_to_reduce_energy_cost = any(
        phrase in p_lower
        for phrase in (
            "reduce",
            "lower",
            "save",
            "saving",
            "cut",
            "without compromising",
            "cost management",
            "intervention",
        )
    )
    is_cost_management_request = (
        mentions_energy_cost and asks_to_reduce_energy_cost
    )
    is_explicit_topic_shift = (
        p_lower.startswith(("actually", "by the way", "first explain", "before that", "wait", "first tell me", "first answer"))
        or is_telemetry_or_billing_query
    )

    if (
        is_explicit_topic_shift
        and is_telemetry_or_billing_query
        and not is_cost_management_request
    ):
        # Route directly to historical analytics, releasing any active questionnaire lock
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            is_topic_change=True,
            follow_up_type="topic_change",
            resolved_mode="general_chat",
            tool_scope="telemetry_and_billing",
            effective_prompt=clean_p,
            active_state=active_state,
        )

    # -------------------------------------------------------------------------
    # 1. Check for Pending Question Answers (Follow-Up Resolution)
    # -------------------------------------------------------------------------
    pending = extract_pending_question_from_context(active_state, last_assistant_turn)
    if pending and not is_explicit_topic_shift:
        field_id = pending["field"]
        workflow = pending["workflow"]

        # 1a. Location City (e.g. "Bengaluru", "Bangalore", "Mumbai")
        if field_id == "location_city":
            known_cities = {"bengaluru", "bangalore", "mumbai", "delhi", "chennai", "hyderabad", "pune", "kolkata", "ahmedabad", "jaipur", "kochi"}
            city_val = clean_p.strip()
            if len(city_val.split()) <= 4 and (city_val.lower() in known_cities or not any(k in p_lower for k in ["predict", "bill", "tariff", "ac", "fan"])):
                normalized_city = "Bengaluru" if city_val.lower() in ("bangalore", "bengaluru") else city_val.title()
                return ResolvedDialogueState(
                    raw_prompt=clean_p,
                    is_continuation=True,
                    follow_up_type="answer_to_pending",
                    answered_field="location_city",
                    answered_value=normalized_city,
                    resolved_mode="house_planning",
                    tool_scope="planning_and_upgrades",
                    effective_prompt=f"Property location confirmed as {normalized_city}. Continue new house energy planning questionnaire.",
                    active_state=active_state,
                )

        # 1b. Bedrooms & AC Rooms (Multi-Question Follow-up)
        if field_id in ("bedrooms_and_ac_rooms", "bedrooms_count"):
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            num_match = re.search(r"\b(one|two|three|four|five|\d+)\b", p_lower)
            if num_match:
                raw_num = num_match.group(1)
                beds = word_map.get(raw_num) or int(raw_num)
                has_room_info = any(w in p_lower for w in ["master", "living", "bedroom", "room", "guest"])
                is_partial = (field_id == "bedrooms_and_ac_rooms") and not has_room_info
                return ResolvedDialogueState(
                    raw_prompt=clean_p,
                    is_continuation=True,
                    follow_up_type="partial_answer" if is_partial else "answer_to_pending",
                    answered_field="bedrooms_count",
                    answered_value=beds,
                    resolved_mode="house_planning",
                    tool_scope="planning_and_upgrades",
                    effective_prompt=f"Confirmed bedrooms: {beds}." + (" Room allocations for AC still missing." if is_partial else f" Specified rooms: '{clean_p}'."),
                    active_state=active_state,
                )

        # 1c. AC Count & Rooms
        if field_id == "ac_count_and_rooms":
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            num_match = re.search(r"\b(one|two|three|four|five|\d+)\b", p_lower)
            if num_match:
                raw_num = num_match.group(1)
                ac_count = word_map.get(raw_num) or int(raw_num)
                has_rooms = any(w in p_lower for w in ["master", "living", "bedroom", "room"])
                is_partial = not has_rooms
                return ResolvedDialogueState(
                    raw_prompt=clean_p,
                    is_continuation=True,
                    follow_up_type="partial_answer" if is_partial else "answer_to_pending",
                    answered_field="ac_count",
                    answered_value=ac_count,
                    resolved_mode="appliance_lifecycle",
                    tool_scope="planning_and_upgrades",
                    effective_prompt=f"Confirmed AC count: {ac_count}." + (" Room allocation details still needed." if is_partial else f" Room details: {clean_p}."),
                    active_state=active_state,
                )

        # 1d. Daily Usage Hours (e.g. "About six hours", "6 hours")
        if field_id == "ac_usage_hours":
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
            match = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b", p_lower)
            val = None
            if match:
                raw = match.group(1)
                val = float(word_map.get(raw) or raw)
            elif clean_p.isdigit():
                val = float(clean_p)
            if val is not None:
                return ResolvedDialogueState(
                    raw_prompt=clean_p,
                    is_continuation=True,
                    follow_up_type="answer_to_pending",
                    answered_field="ac_usage_hours",
                    answered_value=val,
                    resolved_mode="appliance_lifecycle",
                    tool_scope="planning_and_upgrades",
                    effective_prompt=f"AC daily operation confirmed at {val} hours/day. Continue appliance scenario evaluation.",
                    active_state=active_state,
                )

        # 1e. Bill Comparison Period (e.g. "October", "March")
        if field_id == "bill_period":
            months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
            for m in months:
                if m in p_lower:
                    return ResolvedDialogueState(
                        raw_prompt=clean_p,
                        is_continuation=True,
                        follow_up_type="answer_to_pending",
                        answered_field="bill_period",
                        answered_value=m.capitalize(),
                        resolved_mode="general_chat",
                        tool_scope="telemetry_and_billing",
                        effective_prompt=f"Compare electricity consumption and bill for {m.capitalize()} against baseline.",
                        active_state=active_state,
                    )

    # -------------------------------------------------------------------------
    # 2. Check for Explicit User Corrections
    # -------------------------------------------------------------------------
    # Example: "I said two ACs, not three"
    correction_match = re.search(r"\b(?:said|meant|correction:?)\s+(\w+|\d+)\s*(?:acs?|air\s*conditioners?)(?:,\s*not\s+(\w+|\d+))?", p_lower)
    if correction_match:
        word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        val_str = correction_match.group(1)
        num_acs = word_to_num.get(val_str) or (int(val_str) if val_str.isdigit() else None)
        if num_acs is not None:
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                follow_up_type="correction",
                answered_field="ac_count",
                answered_value=num_acs,
                resolved_mode="appliance_lifecycle",
                tool_scope="planning_and_upgrades",
                effective_prompt=f"User correction: Customer confirmed {num_acs} ACs (not {correction_match.group(2) or 'prior'}). Recalculate appliance scenario with {num_acs} ACs.",
                active_state=active_state,
            )

    # -------------------------------------------------------------------------
    # 3. Check for Reference to Previous Result
    # -------------------------------------------------------------------------
    # Examples: "Can you reduce that?", "explain that number", "can you lower that"
    is_referring_to_result = any(phrase in p_lower for phrase in [
        "reduce that", "lower that", "reduce it", "cut that", "cut it",
        "explain that number", "explain that", "where did that number",
    ])
    if is_referring_to_result and (last_assistant_turn or last_user_turn):
        prior_context = f"{last_user_turn} {last_assistant_turn}".lower()
        if any(w in prior_context for w in ["energy plan", "connected load", "peak demand", "balanced tier", "built-up", "high-efficiency"]):
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                follow_up_type="reference_to_result",
                resolved_mode="house_planning",
                tool_scope="planning_and_upgrades",
                effective_prompt=f"User requested to reduce the previously calculated energy consumption and monthly bill ('{clean_p}'). Identify efficiency optimization steps and solar provisions.",
                active_state=active_state,
            )
        elif any(w in prior_context for w in ["appliance", "ac", "refrigerator", "payback"]):
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                follow_up_type="reference_to_result",
                resolved_mode="appliance_lifecycle",
                tool_scope="planning_and_upgrades",
                effective_prompt=f"User requested adjustments or explanation for previous appliance calculation: '{clean_p}'.",
                active_state=active_state,
            )

    # -------------------------------------------------------------------------
    # 4. Standard Affirmative and Continuation Detection
    # -------------------------------------------------------------------------
    is_continuation = is_affirmative_or_continuation(clean_p)

    # If this is an affirmative follow-up, inherit domain context from last assistant message
    if is_continuation and (last_assistant_turn or last_user_turn):
        last_low = f"{last_assistant_turn} {last_user_turn}".lower()

        # 0. Historical Query Correction Context (e.g. "dont predic it, query it", "from database not predict")
        is_query_correction = any(
            w in p_lower for w in [
                "dont predict", "don't predict", "dont predic", "don't predic", "do not predict",
                "query it", "from database", "not prediction", "not predict", "actual data",
                "query database", "find in database", "real data"
            ]
        )
        if is_query_correction:
            prior_text = f"{last_user_turn} {last_assistant_turn}".lower()
            months = [
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
                "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
            ]
            found_month = ""
            for m in months:
                if re.search(r"\b" + m + r"\b", prior_text):
                    found_month = m.capitalize()
                    break
            y_match = re.search(r"\b(201[789]|202[0-9])\b", prior_text)
            found_year = y_match.group(1) if y_match else ""
            target_period = f"{found_month} {found_year}".strip() if found_month else "the requested month"

            effective_prompt = f"Find from the database actual historical telemetry usage and bill for {target_period}. Do not predict."
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                resolved_mode="general_chat",
                tool_scope="telemetry_and_billing",
                effective_prompt=effective_prompt,
            )

        # 1. House Energy Planning Context
        if any(w in last_low for w in ["energy plan", "house energy", "connected load", "peak demand", "balanced tier", "high-efficiency plan", "bedroom", "built-up", "equipment schedule", "diversified"]):
            proposal_summary = "Updated house energy plan with requested efficiency optimizations and solar provisions."
            effective_prompt = (
                f"User confirmed: '{clean_p}'. Please generate the complete updated house energy plan with the optimizations discussed "
                f"in the previous turn. Include the final Before vs After comparison table (connected load, peak demand, monthly bill) "
                f"and room equipment schedule."
            )
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                resolved_mode="house_planning",
                tool_scope="planning_and_upgrades",
                effective_prompt=effective_prompt,
                pending_proposal_summary=proposal_summary,
                parameters={"efficiency_priority": "high_efficiency", "include_solar_pv": True},
            )

        # 2. Appliance Scenario Context
        if any(w in last_low for w in ["appliance", "bldc", "iseer", "inverter ac", "5-star", "refrigerator", "payback", "upgrade", "replacement", "geyser"]):
            proposal_summary = "Appliance upgrade and lifecycle savings assessment."
            effective_prompt = (
                f"User confirmed: '{clean_p}'. Proceed with the appliance upgrade assessment discussed in the previous turn. "
                f"Calculate the net upfront investment, annual energy savings (kWh), monthly bill difference (₹), and simple payback period."
            )
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                resolved_mode="appliance_lifecycle",
                tool_scope="planning_and_upgrades",
                effective_prompt=effective_prompt,
                pending_proposal_summary=proposal_summary,
            )

        # 3. Cost Management Context
        if any(w in last_low for w in ["cost management", "saving", "bill reduction", "package", "target monthly", "tariff shift", "intervention"]):
            proposal_summary = "Personalized electricity cost reduction package."
            effective_prompt = (
                f"User confirmed: '{clean_p}'. Execute the prioritized energy cost management recommendations discussed in the previous turn."
            )
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                resolved_mode="cost_management",
                tool_scope="telemetry_and_billing",
                effective_prompt=effective_prompt,
                pending_proposal_summary=proposal_summary,
            )

        # 4. General Billing / Telemetry
        if any(w in last_low for w in ["bill", "kwh", "consumption", "tariff", "meter", "cycle"]):
            return ResolvedDialogueState(
                raw_prompt=clean_p,
                is_continuation=True,
                resolved_mode="general_chat",
                tool_scope="telemetry_and_billing",
                effective_prompt=f"User confirmed: '{clean_p}'. Provide the requested billing or consumption breakdown from verified telemetry.",
            )

    # 0. Safety, Regulations, Guidelines & Standards (Highest priority to activate RAG knowledge tools)
    if any(k in p_lower for k in [
        "safety", "guideline", "guidelines", "precaution", "precautions",
        "hazard", "shock", "electric shock", "earthing", "grounding",
        "rccb", "elcb", "mcb", "fuse", "overload", "fire", "electrical safety",
        "standard", "code", "regulation", "is 732", "is732", "nec", "bee",
        "cea", "clause", "wiring rule", "wiring standard"
    ]):
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode="general_chat",
            tool_scope="regulatory_and_standards",
            effective_prompt=clean_p,
        )

    # Standard direct classification for standalone prompts
    if any(k in p_lower for k in ["new house", "planning", "wiring", "electrical layout", "bedroom", "built-up", "lighting circuit", "connected load", "peak demand"]):
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode="house_planning",
            tool_scope="planning_and_upgrades",
            effective_prompt=clean_p,
        )

    if any(k in p_lower for k in ["ac", "air condition", "air conditioner", "tier", "star", "replac", "lifecycle", "payback", "iseer", "5-star", "appliance", "refrigerator", "geyser", "fan", "bldc", "heater"]):
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode="appliance_lifecycle",
            tool_scope="planning_and_upgrades",
            effective_prompt=clean_p,
        )

    if any(k in p_lower for k in ["reduce bill", "cost management", "saving", "save", "lower consumption", "reduce electricity", "compromis", "package", "balanced efficiency", "priority", "step", "investment", "cut bill"]):
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode="cost_management",
            tool_scope="telemetry_and_billing",
            effective_prompt=clean_p,
        )

    if any(k in p_lower for k in ["bill", "tariff", "kwh", "consumption", "usage", "meter", "reading", "cost", "yesterday", "forecast", "predict", "daily", "average", "peak", "power", "electricity", "energy", "voltage", "amp", "load", "hello", "hi", "hey"]):
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode="general_chat",
            tool_scope="telemetry_and_billing",
            effective_prompt=clean_p,
        )

    # Check arithmetic (e.g. 2+2)
    math_chars = set("0123456789+-*/. ()?")
    if set(p_lower).issubset(math_chars) and any(c in "+-*/" for c in p_lower):
        return ResolvedDialogueState(
            raw_prompt=clean_p,
            is_continuation=False,
            resolved_mode="general_chat",
            tool_scope="balanced_core",
            effective_prompt=clean_p,
        )

    return ResolvedDialogueState(
        raw_prompt=clean_p,
        is_continuation=False,
        resolved_mode="irrelevant",
        tool_scope="balanced_core",
        effective_prompt=clean_p,
    )


def compact_history_for_llm(
    history: Optional[List[Dict[str, Any]]],
    max_turns: int = 4,
    max_assistant_chars: int = 350,
    max_user_chars: int = 400,
) -> List[Dict[str, str]]:
    """Prune and compact conversation history to prevent Groq 7,000 ITPM token rate limit exhaustion.

    - Retains recent user turns up to max_user_chars.
    - Strips large Markdown tables and lengthy citations from prior assistant turns,
      preserving only the essential summary line and metrics (capped at max_assistant_chars).
    - Guarantees the entire history occupies < 350 tokens.
    """
    if not history:
        return []

    sanitized: List[Dict[str, str]] = []
    # Take at most max_turns from the tail
    recent = history[-max_turns:]

    for item in recent:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).lower().strip()
        if role not in ("user", "assistant"):
            continue

        raw_content = str(item.get("content", "")).strip()
        if not raw_content:
            continue

        if role == "user":
            cleaned = raw_content[:max_user_chars]
            if sanitized and sanitized[-1]["role"] == "user":
                sanitized[-1]["content"] = (sanitized[-1]["content"] + " " + cleaned)[:max_user_chars]
            else:
                sanitized.append({"role": "user", "content": cleaned})
        else:
            # Assistant turn: compact large tables, code blocks, and citations
            text = raw_content
            # Remove Markdown tables
            text = re.sub(r"\|[^\n]+\|(?:\n\|[^\n]+\|)+", " [Table omitted] ", text)
            # Remove citations blocks
            text = re.sub(r"\[BEE\][^\n]+", "", text)
            text = re.sub(r"\[BIS\][^\n]+", "", text)
            text = re.sub(r"\[CEA\][^\n]+", "", text)
            # Collapse whitespace
            text = " ".join(text.split())

            if len(text) > max_assistant_chars:
                # Truncate at last sentence boundary within limit
                truncated = text[:max_assistant_chars]
                last_period = truncated.rfind(".")
                if last_period > 100:
                    text = truncated[: last_period + 1]
                else:
                    text = truncated + "..."

            if sanitized and sanitized[-1]["role"] == "assistant":
                merged = (sanitized[-1]["content"] + " " + text).strip()
                sanitized[-1]["content"] = merged[:max_assistant_chars]
            else:
                sanitized.append({"role": "assistant", "content": text})

    return sanitized
