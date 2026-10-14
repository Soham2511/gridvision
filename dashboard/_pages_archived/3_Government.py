"""Government Overall and Regional Demand Dashboard Page."""

from __future__ import annotations

import streamlit as st
from dashboard.components.sidebar import render_sidebar
from dashboard.utils.session_state import init_session_state
from dashboard.utils.theme import apply_custom_theme
from dashboard.views.government import render_government_view

st.set_page_config(
    page_title="GridVision — Government Demand",
    page_icon="🌐",
    layout="wide",
)

init_session_state()
apply_custom_theme()
st.session_state.current_persona = "government"

active_entity = st.session_state.get("government_site_id")
render_sidebar(
    current_persona="government",
    active_entity=active_entity,
    current_view="government_overall",
)

render_government_view()
