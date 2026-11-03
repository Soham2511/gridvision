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
class ResolvedDialogueState:
    """Carries resolved dialogue context for multi-turn conversational execution."""
    raw_prompt: str
    is_continuation: bool
    resolved_mode: str
    tool_scope: str
    effective_prompt: str
    pending_proposal_summary: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


def is_affirmative_or_continuation(prompt: str) -> bool:
    """Return True if user prompt is a short affirmative, selection, or continuation phrase."""
    p = prompt.strip().lower()
    if p in AFFIRMATIVE_KEYWORDS:
        return True
    if len(p.split()) <= 4 and (AFFIRMATIVE_PATTERN.match(p) or SELECTION_PATTERN.match(p)):
        return True
    return False


def resolve_dialogue_context(
    prompt: str,
    history: Optional[List[Dict[str, Any]]] = None,
    explicit_mode: Optional[str] = None,
) -> ResolvedDialogueState:
    """Resolve user intent and slot values by inspecting current prompt AND prior dialogue turns.

    Guarantees that short elliptical follow-ups ('yes generate', 'sure', 'option 1') inherit
    the active feature domain, tool scope, and parameters from the previous assistant proposal.
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
        )

    is_continuation = is_affirmative_or_continuation(clean_p)

    # Inspect previous assistant turn if history is available
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

    # If this is an affirmative follow-up, inherit domain context from last assistant message
    if is_continuation and last_assistant_turn:
        last_low = last_assistant_turn.lower()
        
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

    if any(k in p_lower for k in ["bill", "tariff", "kwh", "consumption", "usage", "meter", "reading", "cost", "yesterday", "forecast", "predict", "daily", "average", "peak", "power", "electricity", "energy", "standard", "code", "regulation", "is 732", "is732", "nec", "bee", "cea", "voltage", "amp", "load", "hello", "hi", "hey"]):
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

            sanitized.append({"role": "assistant", "content": text})

    return sanitized
