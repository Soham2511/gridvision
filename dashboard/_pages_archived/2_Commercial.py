"""Commercial Building and Regional Energy Demand Dashboard Page."""

from __future__ import annotations

import streamlit as st
from dashboard.components.sidebar import render_sidebar
from dashboard.utils.session_state import init_session_state
from dashboard.utils.theme import apply_custom_theme
from dashboard.views.commercial import render_commercial_view

st.set_page_config(
    page_title="GridVision — Commercial Demand",
    page_icon="🏢",
    layout="wide",
)

init_session_state()
apply_custom_theme()
st.session_state.current_persona = "commercial"

active_entity = st.session_state.get("commercial_building_id")
render_sidebar(
    current_persona="commercial",
    active_entity=active_entity,
    current_view="commercial_building",
)

render_commercial_view()
