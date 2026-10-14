"""System, Dataset Lineage, and Model Verification Health Dashboard Page."""

from __future__ import annotations

import streamlit as st
from dashboard.components.sidebar import render_sidebar
from dashboard.utils.session_state import init_session_state
from dashboard.utils.theme import apply_custom_theme
from dashboard.views.health import render_data_and_model_health_view

st.set_page_config(
    page_title="GridVision — Data & Model Health",
    page_icon="🛡️",
    layout="wide",
)

init_session_state()
apply_custom_theme()

current_persona = st.session_state.get("current_persona") or "government"
active_entity = None

render_sidebar(
    current_persona=current_persona,
    active_entity=active_entity,
    current_view="health",
)

render_data_and_model_health_view(current_persona=current_persona)
