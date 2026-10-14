"""GridVision — Energy Intelligence Platform Streamlit Entry Point."""

from __future__ import annotations

import streamlit as st
from dashboard.components.assistant import render_ai_assistant_view
from dashboard.components.sidebar import render_sidebar
from dashboard.utils.session_state import init_session_state
from dashboard.utils.theme import apply_custom_theme
from dashboard.views.commercial import render_commercial_view
from dashboard.views.government import render_government_view
from dashboard.views.health import render_data_and_model_health_view
from dashboard.views.historical import render_historical_analysis_view
from dashboard.views.household import render_household_view
from dashboard.views.landing import render_landing_page
from dashboard.views.profile import render_profile_view

# Page Configuration
st.set_page_config(
    page_title="GridVision — Energy Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Session State & Inject Brand Theme
init_session_state()
apply_custom_theme()

current_persona = st.session_state.get("current_persona")

if current_persona is None or current_persona == "landing":
    render_landing_page()
else:
    # Determine active entity for sidebar display
    active_entity = None
    if current_persona == "household":
        active_entity = st.session_state.get("household_id")
    elif current_persona == "commercial":
        active_entity = st.session_state.get("commercial_building_id")
    elif current_persona == "government":
        active_entity = st.session_state.get("government_site_id")

    current_view = st.session_state.get("selected_view", "home")
    selected_view = render_sidebar(
        current_persona=current_persona,
        active_entity=active_entity,
        current_view=current_view,
    )
    st.session_state.selected_view = selected_view

    # Routing
    if selected_view in {"home", "household_detail"} and current_persona == "household":
        render_household_view()
    elif selected_view in {"home", "commercial_building", "commercial_regional"} and current_persona == "commercial":
        render_commercial_view()
    elif selected_view in {"home", "government_overall", "government_regional"} and current_persona == "government":
        render_government_view()
    elif selected_view == "historical":
        render_historical_analysis_view(current_persona=current_persona)
    elif selected_view == "health":
        render_data_and_model_health_view(current_persona=current_persona)
    elif selected_view == "profile":
        render_profile_view()
    elif selected_view == "assistant":
        context_data = {
            "entity_id": active_entity,
            "avg_demand": "142.5 kWh",
            "peak_val": "285.0 kWh",
            "peak_time": "2017-11-14 18:00",
            "change_val": "-4.2%",
        }
        render_ai_assistant_view(current_persona, context_data)
    else:
        # Fallback to persona default view
        if current_persona == "household":
            render_household_view()
        elif current_persona == "commercial":
            render_commercial_view()
        elif current_persona == "government":
            render_government_view()
