"""Streamlit session-state initialization and management helpers."""

from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    """Ensure all required session state keys exist with valid defaults."""
    if "current_persona" not in st.session_state:
        st.session_state.current_persona = None  # None or "landing" means persona picker
    if "selected_view" not in st.session_state:
        st.session_state.selected_view = "home"
    if "selected_time_range" not in st.session_state:
        st.session_state.selected_time_range = "1M"
    if "alerts_open" not in st.session_state:
        st.session_state.alerts_open = False
    if "household_id" not in st.session_state:
        st.session_state.household_id = None
    if "commercial_building_id" not in st.session_state:
        st.session_state.commercial_building_id = None
    if "commercial_region_id" not in st.session_state:
        st.session_state.commercial_region_id = "Panther"
    if "government_site_id" not in st.session_state:
        st.session_state.government_site_id = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []


def set_persona(persona: str | None) -> None:
    """Switch active persona and reset relevant state."""
    st.session_state.current_persona = persona
    st.session_state.selected_view = "home"
    st.session_state.alerts_open = False
    st.session_state.pop("sidebar_nav_radio", None)


def toggle_alerts() -> None:
    """Toggle alerts drawer visibility."""
    st.session_state.alerts_open = not st.session_state.get("alerts_open", False)
