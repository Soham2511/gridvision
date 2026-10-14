"""Dedicated Profile and Environment Context view for GridVision (Light Mode)."""

from __future__ import annotations

import streamlit as st
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_ENERGY_AMBER,
    COLOR_MIDNIGHT_NAVY,
    COLOR_SMART_TEAL,
    COLOR_TEXT_MUTED,
)


def render_profile_view() -> None:
    """Render the dedicated prototype Profile and Preferences page."""
    current_persona = st.session_state.get("current_persona", "household")
    persona_title = current_persona.title() if current_persona else "Household"

    # Header
    st.markdown(
        f'<div style="margin-bottom: 1.5rem;">'
        f'<h2 style="font-size: 1.75rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY}; margin-bottom: 0.25rem;">'
        f'Profile & Environment Context'
        f'</h2>'
        f'<div style="font-size: 0.85rem; color: {COLOR_TEXT_MUTED};">'
        f'Active session parameters, data scope, and analytical preferences for {persona_title} persona.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([1.8, 2.2])

    # =========================================================================
    # SECTION A: Profile Overview
    # =========================================================================
    with col_left:
        initials_map = {
            "household": "HC",
            "commercial": "FA",
            "government": "GA",
        }
        role_label_map = {
            "household": "Residential Account Holder (Demo)",
            "commercial": "Commercial Facility Energy Manager (Demo)",
            "government": "Regional Grid Operations Analyst (Demo)",
        }
        entity_val = None
        if current_persona == "household":
            entity_val = st.session_state.get("household_id", "MAC000002")
        elif current_persona == "commercial":
            entity_val = st.session_state.get("commercial_building_id", "Panther_office_Lorraine")
        elif current_persona == "government":
            entity_val = st.session_state.get("government_site_id", "Panther")

        user_initials = initials_map.get(current_persona, "GV")
        role_label = role_label_map.get(current_persona, "Energy Analyst (Prototype)")

        overview_card_html = (
            f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 2px 10px rgba(11, 31, 51, 0.05);">'
            f'<div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">'
            f'<div style="width: 52px; height: 52px; border-radius: 50%; background: rgba(0, 184, 169, 0.12); border: 2px solid {COLOR_SMART_TEAL}; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.2rem; color: {COLOR_MIDNIGHT_NAVY};">'
            f'{user_initials}'
            f'</div>'
            f'<div>'
            f'<div style="font-size: 1.15rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY};">{persona_title} Analyst</div>'
            f'<div style="font-size: 0.8rem; color: {COLOR_TEXT_MUTED};">{role_label}</div>'
            f'</div>'
            f'</div>'
            f'<div style="border-top: 1px solid {COLOR_BORDER}; padding-top: 0.85rem; font-size: 0.82rem; line-height: 1.8;">'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Active Persona:</span> <span class="gv-badge gv-badge-teal" style="margin-left: 0.35rem;">{persona_title}</span></div>'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Assigned Entity ID:</span> <b style="color: {COLOR_MIDNIGHT_NAVY}; margin-left: 0.35rem;">{entity_val}</b></div>'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Authentication:</span> <span class="gv-badge gv-badge-amber" style="margin-left: 0.35rem;">Prototype Session</span></div>'
            f'</div>'
            f'<div style="margin-top: 0.75rem; font-size: 0.75rem; color: {COLOR_ENERGY_AMBER};">'
            f'ℹ️ Prototype notice: Identity verification is not configured. This profile reflects active demo session state.'
            f'</div>'
            f'</div>'
        )
        st.markdown(overview_card_html, unsafe_allow_html=True)

        # =========================================================================
        # SECTION B: Energy Account Context
        # =========================================================================
        context_rows_html = ""
        if current_persona == "household":
            context_rows_html = (
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Meter / Customer ID:</span> <b style="color: {COLOR_MIDNIGHT_NAVY};">{entity_val}</b></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Historical Telemetry Span:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">2011-12-01 to 2014-02-28</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Telemetry Aggregation:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">Daily half-hourly aggregated sum (kWh)</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Forecasting Horizon:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">Calendar month remaining cumulative kWh</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Baseline Tariff:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">₹10.00 / kWh (Flat Research Tariff)</span></div>'
            )
        elif current_persona == "commercial":
            context_rows_html = (
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Facility Identifier:</span> <b style="color: {COLOR_MIDNIGHT_NAVY};">{entity_val}</b></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Regional Site Mapping:</span> <span style="color: {COLOR_SMART_TEAL}; font-weight: 600;">Site: Panther</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Verified Period:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">2016-01-01 to 2017-12-31 (17,544 hours)</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Observation Frequency:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">Hourly average demand (kWh/hr / kW)</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Model Scope:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">LightGBM Building Model (29 Supported Facilities)</span></div>'
            )
        elif current_persona == "government":
            context_rows_html = (
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Analytical Scope:</span> <b style="color: {COLOR_MIDNIGHT_NAVY};">17 Mutually Exclusive Regional Grid Sites</b></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Active Region in Focus:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">{entity_val}</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Aggregate Representation:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">1,400 Commercial & Municipal Buildings</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Temporal Alignment:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">100% synchronized hourly test records</span></div>'
                f'<div><span style="color: {COLOR_TEXT_MUTED};">Aggregate Integrity:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">Direct summation with verified zero double-counting</span></div>'
            )

        account_card_html = (
            f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 2px 10px rgba(11, 31, 51, 0.05);">'
            f'<div style="font-size: 0.95rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY}; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">'
            f'⚡ Energy Account & Telemetry Context'
            f'</div>'
            f'<div style="font-size: 0.82rem; line-height: 1.9;">'
            f'{context_rows_html}'
            f'</div>'
            f'</div>'
        )
        st.markdown(account_card_html, unsafe_allow_html=True)

    # =========================================================================
    # SECTION C: Preferences & Display Settings
    # =========================================================================
    with col_right:
        pref_card_html = (
            f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 2px 10px rgba(11, 31, 51, 0.05);">'
            f'<div style="font-size: 0.95rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY}; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">'
            f'⚙️ Analytical & Display Preferences'
            f'</div>'
            f'<div style="font-size: 0.82rem; color: {COLOR_TEXT_MUTED}; margin-bottom: 1rem;">'
            f'Customize default visualization timeframes and notification states for this session.'
            f'</div>'
            f'</div>'
        )
        st.markdown(pref_card_html, unsafe_allow_html=True)

        current_default_range = st.session_state.get("selected_time_range", "1M")
        range_options = ["1D", "1W", "1M", "3M", "6M", "1Y"]
        pref_range_idx = range_options.index(current_default_range) if current_default_range in range_options else 2

        new_range = st.selectbox(
            "Default Chart Time Range",
            options=range_options,
            index=pref_range_idx,
            key="pref_time_range_select",
            help="Sets the initial zoom and filtering range across all telemetry charts.",
        )
        if new_range != current_default_range:
            st.session_state.selected_time_range = new_range
            st.success(f"Default time range set to {new_range}")

        # Display preference toggles
        alert_pref = st.checkbox(
            "Auto-open Alerts Drawer when anomalies or warnings occur",
            value=False,
            key="pref_alerts_auto_open",
            help="Automatically open the right-side alert drawer when a model error threshold is exceeded.",
        )
        st.caption(f"Alerts auto-open: {'Enabled' if alert_pref else 'Disabled (Default)'}")

        # =========================================================================
        # SECTION D: Data & Application Information
        # =========================================================================
        app_info_html = (
            f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1.25rem; margin-top: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 2px 10px rgba(11, 31, 51, 0.05);">'
            f'<div style="font-size: 0.95rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY}; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">'
            f'🛡️ Data & Platform Environment'
            f'</div>'
            f'<div style="font-size: 0.82rem; line-height: 1.8;">'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Application Version:</span> <b style="color: {COLOR_MIDNIGHT_NAVY};">GridVision v0.1.0</b></div>'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Inference Backend:</span> <span style="color: {COLOR_SMART_TEAL};">FastAPI @ 127.0.0.1:8000 (Active)</span></div>'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Model Pipeline:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">Production Gold Artifacts (SHA-256 Verified)</span></div>'
            f'<div><span style="color: {COLOR_TEXT_MUTED};">Temporal Scope:</span> <span style="color: {COLOR_MIDNIGHT_NAVY};">Synchronized Retrospective Replay (2011–2017)</span></div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(app_info_html, unsafe_allow_html=True)

        if st.button("Inspect Data & Model Health →", key="btn_goto_health", use_container_width=True):
            st.session_state.selected_view = "health"
            st.session_state.pop("sidebar_nav_radio", None)
            st.rerun()

        # =========================================================================
        # SECTION E: Account Actions
        # =========================================================================
        st.markdown(
            f'<div style="margin-top: 1.25rem; border-top: 1px solid {COLOR_BORDER}; padding-top: 1rem;">'
            f'<div style="font-size: 0.82rem; color: {COLOR_TEXT_MUTED}; margin-bottom: 0.5rem;">Session Actions:</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col_action_back, col_action_logout = st.columns(2)
        with col_action_back:
            if st.button("🏠 Return to Dashboard", key="btn_profile_return_home", use_container_width=True):
                st.session_state.selected_view = "home"
                st.session_state.pop("sidebar_nav_radio", None)
                st.rerun()

        with col_action_logout:
            if st.button("Log out Session", key="btn_profile_logout", use_container_width=True):
                st.session_state.current_persona = None
                st.session_state.selected_view = "home"
                st.session_state.pop("sidebar_nav_radio", None)
                st.info("Demo session cleared. Returning to landing page.")
                st.rerun()
