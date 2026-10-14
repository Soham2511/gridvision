"""Shared dashboard navigation and sidebar shell."""

from __future__ import annotations

import streamlit as st
from dashboard.utils.config import PROJECT_ROOT
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_TEXT_MUTED,
)


def render_sidebar(
    current_persona: str,
    active_entity: str | None = None,
    current_view: str = "home",
) -> str:
    """
    Render standard GridVision sidebar with brand identity, persona navigation, and footer.
    
    Returns the selected view ID.
    """
    with st.sidebar:
        # Brand Header with Logo
        logo_path = PROJECT_ROOT / "logo.png"
        if logo_path.is_file():
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown(
                '<div style="font-size: 1.5rem; font-weight: 700; color: #0B1F33; letter-spacing: -0.02em;">Grid<span style="color: #00B8A9;">Vision</span></div>',
                unsafe_allow_html=True,
            )

        tagline_html = (
            f'<div style="font-size: 0.75rem; color: {COLOR_TEXT_MUTED}; margin-top: -0.25rem; margin-bottom: 1.25rem; border-bottom: 1px solid {COLOR_BORDER}; padding-bottom: 0.75rem;">'
            f'Energy Intelligence Platform'
            f'</div>'
        )
        st.markdown(tagline_html, unsafe_allow_html=True)

        persona_clean = current_persona.title()

        # Navigation Tabs list for the active persona
        NAV_TABS = [
            ("home", "Home", "🏠"),
            ("historical", "Historical Analysis", "📈"),
            ("health", "Data & model health", "🛡️"),
            ("assistant", "AI assistant", "🤖"),
            ("profile", "Profile", "👤"),
        ]

        active_key = current_view
        if active_key in {"household_detail", "commercial_building", "commercial_regional", "government_overall", "government_regional"}:
            active_key = "home"

        selected_view_key = active_key
        for key, title, icon in NAV_TABS:
            is_active = (active_key == key)
            btn_type = "primary" if is_active else "secondary"
            if st.button(
                f"{icon}  {title}",
                key=f"sidebar_tab_{key}",
                use_container_width=True,
                type=btn_type,
            ):
                selected_view_key = key
                st.session_state.selected_view = key
                st.rerun()

        # Bottom section: Persona indicator, Entity badge, Actions
        bottom_html = (
            f'<div style="margin-top: 2rem; padding-top: 1.25rem; border-top: 1px solid {COLOR_BORDER};">'
            f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">'
            f'<span style="font-size: 0.75rem; color: {COLOR_TEXT_MUTED};">Active Persona:</span>'
            f'<span class="gv-badge gv-badge-teal">{persona_clean}</span>'
            f'</div>'
        )
        st.markdown(bottom_html, unsafe_allow_html=True)

        if active_entity:
            entity_html = (
                f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">'
                f'<span style="font-size: 0.75rem; color: {COLOR_TEXT_MUTED};">Scope:</span>'
                f'<span style="font-size: 0.78rem; font-weight: 600; color: #0B1F33;">{active_entity}</span>'
                f'</div>'
            )
            st.markdown(entity_html, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("Log out", key="sidebar_logout", use_container_width=True):
            st.session_state.current_persona = None
            st.session_state.selected_view = "home"
            st.session_state.pop("sidebar_nav_radio", None)
            st.info("Demo session cleared. Returning to landing page.")
            st.rerun()

        st.caption(
            "GridVision v0.1.0 • Historical Replay Demo\n"
            "FastAPI @ 127.0.0.1:8000"
        )

    return selected_view_key
