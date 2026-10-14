"""Residential / Household Demand and Month-End Prediction Dashboard Page."""

from __future__ import annotations

import streamlit as st
from dashboard.components.sidebar import render_sidebar
from dashboard.utils.session_state import init_session_state
from dashboard.utils.theme import apply_custom_theme
from dashboard.views.household import render_household_view

st.set_page_config(
    page_title="GridVision — Household Demand",
    page_icon="⚡",
    layout="wide",
)

init_session_state()
apply_custom_theme()
st.session_state.current_persona = "household"

active_entity = st.session_state.get("household_id")
render_sidebar(
    current_persona="household",
    active_entity=active_entity,
    current_view="household_detail",
)

render_household_view()
