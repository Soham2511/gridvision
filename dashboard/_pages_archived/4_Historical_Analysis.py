"""Historical Consumption and Interval Coverage Analysis Page."""

from __future__ import annotations

import streamlit as st
from dashboard.components.sidebar import render_sidebar
from dashboard.utils.session_state import init_session_state
from dashboard.utils.theme import apply_custom_theme
from dashboard.views.historical import render_historical_analysis_view

st.set_page_config(
    page_title="GridVision — Historical Analysis",
    page_icon="📈",
    layout="wide",
)

init_session_state()
apply_custom_theme()

current_persona = st.session_state.get("current_persona") or "household"
active_entity = st.session_state.get("household_id")

render_sidebar(
    current_persona=current_persona,
    active_entity=active_entity,
    current_view="historical",
)

render_historical_analysis_view(current_persona=current_persona)
