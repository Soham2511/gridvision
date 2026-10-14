"""Main dashboard header component with title, entity badge, time range, and alerts trigger."""

from __future__ import annotations

import streamlit as st
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_MIDNIGHT_NAVY,
    COLOR_TEXT_MUTED,
)
from dashboard.utils.time_range import TIME_RANGE_OPTIONS


def render_dashboard_header(
    title: str,
    subtitle: str,
    entity_label: str | None = None,
    show_time_range: bool = True,
    active_alerts_count: int = 0,
) -> str:
    """
    Render consistent header with page context, time range selector, and alerts button.
    
    Returns the currently selected time range option.
    """
    left_col, right_col = st.columns([3, 2])

    with left_col:
        badge_html = ""
        if entity_label:
            badge_html = f'<span class="gv-badge gv-badge-cyan" style="margin-left: 0.75rem;">{entity_label}</span>'
        
        hdr_html = (
            f'<div style="margin-bottom: 0.25rem;">'
            f'<span style="font-size: 1.4rem; font-weight: 700; letter-spacing: -0.01em; color: {COLOR_MIDNIGHT_NAVY};">{title}</span>'
            f'{badge_html}'
            f'</div>'
            f'<div style="font-size: 0.85rem; color: {COLOR_TEXT_MUTED}; margin-bottom: 0.5rem;">'
            f'{subtitle}'
            f'</div>'
        )
        st.markdown(hdr_html, unsafe_allow_html=True)

    selected_range = st.session_state.get("selected_time_range", "1M")

    with right_col:
        controls_col1, controls_col2 = st.columns([3, 1])
        
        with controls_col1:
            if show_time_range:
                selected_range = st.select_slider(
                    "Time Horizon",
                    options=TIME_RANGE_OPTIONS,
                    value=st.session_state.get("selected_time_range", "1M"),
                    key="header_time_range_slider",
                    label_visibility="collapsed",
                )
                st.session_state.selected_time_range = selected_range

        with controls_col2:
            alert_label = f"🔔 ({active_alerts_count})" if active_alerts_count > 0 else "🔔"
            if st.button(alert_label, key="toggle_alerts_button", help="Toggle Alerts & Diagnostics"):
                st.session_state.alerts_open = not st.session_state.get("alerts_open", False)
                st.rerun()

    st.markdown(f'<div style="border-bottom: 1px solid {COLOR_BORDER}; margin-bottom: 1.25rem;"></div>', unsafe_allow_html=True)
    return selected_range
