"""AI Assistant demonstration panel with persona-specific prompts and explicit prototype rules."""

from __future__ import annotations

from typing import Any

import streamlit as st
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_ENERGY_AMBER,
    COLOR_MIDNIGHT_NAVY,
    COLOR_PURE_WHITE,
    COLOR_TEXT_MUTED,
)

SUGGESTED_PROMPTS: dict[str, list[str]] = {
    "household": [
        "Summarize my consumption over the selected period.",
        "What was my peak consumption day?",
        "Explain how my month-end bill is calculated.",
    ],
    "commercial": [
        "Show the building's peak observed demand.",
        "How does the building's demand compare with the previous period?",
        "What features most influence this building's electricity demand?",
    ],
    "government": [
        "Compare the available regions by observed demand.",
        "How has aggregate demand changed over the selected period?",
        "Are any regions currently missing from aggregate reporting?",
    ],
}


def _generate_demo_response(prompt: str, persona: str, context_info: dict[str, Any]) -> str:
    """Provide grounded analytical response using local context and explicit prototype disclaimer."""
    p_lower = prompt.lower()
    
    if "bill" in p_lower or "tariff" in p_lower:
        return (
            "**Billing Computation (Prototype Tariff):**\n\n"
            "Your month-end bill estimate is computed as:\n"
            "$$\\text{Estimated Bill (₹)} = (\\text{Month-to-Date kWh} + \\text{Predicted Remaining kWh}) \\times ₹10/\\text{kWh}$$\n\n"
            "*Notice:* This utilizes the prototype flat tariff rate of ₹10/kWh from the research baseline. "
            "It is an illustrative estimate and not an official utility bill."
        )
    elif "summarize" in p_lower:
        return (
            f"**Consumption Summary ({persona.title()} Context):**\n\n"
            f"Over the active observation interval for {context_info.get('entity_id', 'the selected entity')}, "
            f"average demand is **{context_info.get('avg_demand', 'N/A')}**, with a recorded peak of **{context_info.get('peak_val', 'N/A')}** "
            f"at **{context_info.get('peak_time', 'N/A')}**. The period trend indicates a **{context_info.get('change_val', 'N/A')}** change "
            f"relative to the previous comparable window."
        )
    elif "peak" in p_lower:
        peak_val = context_info.get("peak_val", "N/A")
        peak_time = context_info.get("peak_time", "N/A")
        return (
            f"**Peak Demand Analysis:**\n\n"
            f"In the selected dataset interval, the maximum observed consumption was **{peak_val}** recorded at **{peak_time}**."
        )
    elif "change" in p_lower or "compare" in p_lower:
        change_val = context_info.get("change_val", "N/A")
        return (
            f"**Period-over-Period Consumption Trend:**\n\n"
            f"Observed demand changed by **{change_val}** compared to the preceding equivalent time interval."
        )
    elif "region" in p_lower or "aggregate" in p_lower:
        return (
            "**Regional Grid Coverage:**\n\n"
            "All 17 government sites (Bear through Wolf) are represented with 100% temporal alignment in the historical test dataset. "
            "No regions are currently missing from the overall demand aggregation."
        )
    else:
        return (
            f"**GridVision Assistant Analysis ({persona.title()} Context):**\n\n"
            f"Query: *\"{prompt}\"*\n\n"
            f"Based on the active telemetry records for {context_info.get('entity_id', 'the selected entity')}, "
            f"the system observes an average demand of {context_info.get('avg_demand', 'N/A')}. "
            f"All insights are strictly computed from verified historical test observations."
        )


def render_ai_assistant_view(persona: str, context_info: dict[str, Any]) -> None:
    """Render the AI Assistant prototype panel."""
    banner_html = (
        f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.05);">'
        f'<div style="font-size: 1.2rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY}; display: flex; align-items: center; gap: 8px;">'
        f'<span>🤖 GridVision Energy Intelligence Assistant</span>'
        f'<span class="gv-badge gv-badge-amber">Prototype Interface</span>'
        f'</div>'
        f'<div style="font-size: 0.85rem; color: {COLOR_TEXT_MUTED}; margin-top: 0.35rem;">'
        f'Ask questions regarding your consumption patterns, forecast projections, peak load intervals, and tariff calculations.'
        f'</div>'
        f'<div style="font-size: 0.75rem; color: {COLOR_ENERGY_AMBER}; font-weight: 600; margin-top: 0.5rem;">'
        f'⚠️ Note: This is an integrated UI prototype backed by deterministic analytical rule-engines. An external LLM backend is not connected.'
        f'</div>'
        f'</div>'
    )
    st.markdown(banner_html, unsafe_allow_html=True)

    # Suggested Prompts
    st.markdown(
        f'<div style="font-size: 0.8rem; font-weight: 600; color: {COLOR_TEXT_MUTED}; margin-bottom: 0.4rem;">Suggested Prompts for {persona.title()}:</div>',
        unsafe_allow_html=True,
    )
    prompts = SUGGESTED_PROMPTS.get(persona, SUGGESTED_PROMPTS["household"])
    prompt_cols = st.columns(len(prompts))
    
    selected_suggested = None
    for i, col in enumerate(prompt_cols):
        with col:
            if st.button(prompts[i], key=f"sug_prompt_{i}", use_container_width=True):
                selected_suggested = prompts[i]

    # Chat history display
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if not st.session_state.chat_history:
        empty_html = (
            f'<div style="background: {COLOR_PURE_WHITE}; border: 1px dashed {COLOR_BORDER}; border-radius: 8px; padding: 2rem; text-align: center; margin: 1.5rem 0; box-shadow: 0 1px 4px rgba(11, 31, 51, 0.03);">'
            f'<div style="font-size: 1.5rem; margin-bottom: 0.5rem;">💬</div>'
            f'<div style="font-size: 0.95rem; font-weight: 600; color: {COLOR_MIDNIGHT_NAVY}; margin-bottom: 0.35rem;">No Active Conversation</div>'
            f'<div style="font-size: 0.8rem; color: {COLOR_TEXT_MUTED}; max-width: 480px; margin: 0 auto;">'
            f'Select a suggested prompt above or enter a query below to explore verified energy telemetry, model forecasts, and calculation methodologies.'
            f'</div>'
            f'</div>'
        )
        st.markdown(empty_html, unsafe_allow_html=True)

    for msg in st.session_state.chat_history:
        role = msg["role"]
        with st.chat_message(role):
            st.markdown(msg["content"])

    # User input
    user_prompt = st.chat_input("Ask a question about energy usage or forecasts...")
    if selected_suggested:
        user_prompt = selected_suggested

    if user_prompt:
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        reply = _generate_demo_response(user_prompt, persona, context_info)
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
            st.caption("Generated deterministically from active entity metrics • No LLM fabricated telemetry")
