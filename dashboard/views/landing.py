"""Landing Page: Persona Selection entry point for GridVision."""

from __future__ import annotations

import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.utils.config import PROJECT_ROOT
from dashboard.utils.data import get_api_client
from dashboard.utils.session_state import set_persona
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_TEXT_MUTED,
)


def render_landing_page() -> None:
    """Render the primary public landing page with persona selection cards."""
    st.write("")

    # Centered Header with Brand Logo
    col_left, col_center, col_right = st.columns([1, 2.5, 1])
    with col_center:
        logo_path = PROJECT_ROOT / "logo.png"
        if logo_path.is_file():
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown(
                '<h1 style="text-align: center; font-size: 2.8rem; margin-bottom: 0; color: #0B1F33;">Grid<span style="color: #00B8A9;">Vision</span></h1>',
                unsafe_allow_html=True,
            )

        tagline_html = (
            f'<div style="text-align: center; margin-top: 0.5rem; margin-bottom: 1.75rem;">'
            f'<div style="font-size: 1.25rem; font-weight: 700; color: #087EBD; letter-spacing: -0.01em;">'
            f'See demand clearly. Plan energy intelligently.'
            f'</div>'
            f'<div style="font-size: 0.92rem; color: {COLOR_TEXT_MUTED}; margin-top: 0.5rem; line-height: 1.5;">'
            f'GridVision is an enterprise energy intelligence platform providing verified consumption analytics, '
            f'demand forecasting, and structural grid insights across household, commercial, and government sectors.'
            f'</div>'
            f'</div>'
        )
        st.markdown(tagline_html, unsafe_allow_html=True)

    # API Readiness Indicator
    try:
        readiness = get_api_client().health()
        if readiness.get("status") == "ready":
            loaded_str = ", ".join(readiness.get("models_loaded", []))
            ready_html = (
                f'<div style="text-align: center; margin-bottom: 2rem;">'
                f'<span class="gv-badge gv-badge-teal">● Backend Operational</span>'
                f'<span style="font-size: 0.78rem; color: {COLOR_TEXT_MUTED}; margin-left: 0.5rem;">'
                f'Loaded models: {loaded_str}'
                f'</span>'
                f'</div>'
            )
            st.markdown(ready_html, unsafe_allow_html=True)
        else:
            st.warning(f"⚠️ Prediction API report: {readiness.get('status')}")
    except APIClientError:
        offline_html = (
            f'<div style="text-align: center; margin-bottom: 2rem;">'
            f'<span class="gv-badge gv-badge-amber">Offline Standalone Mode</span>'
            f'<span style="font-size: 0.78rem; color: {COLOR_TEXT_MUTED}; margin-left: 0.5rem;">'
            f'FastAPI offline; local Parquet analytics available'
            f'</span>'
            f'</div>'
        )
        st.markdown(offline_html, unsafe_allow_html=True)

    # Persona Selection Cards
    section_title_html = (
        f'<div style="font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: {COLOR_TEXT_MUTED}; text-align: center; margin-bottom: 1rem;">'
        f'Select Persona to Access Workspace'
        f'</div>'
    )
    st.markdown(section_title_html, unsafe_allow_html=True)

    card_col1, card_col2, card_col3 = st.columns(3)

    with card_col1:
        hh_card = (
            f'<div class="gv-persona-card">'
            f'<div>'
            f'<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">'
            f'<span style="font-size: 1.8rem;">🏠</span>'
            f'<span class="gv-badge gv-badge-cyan">Residential</span>'
            f'</div>'
            f'<div style="font-size: 1.25rem; font-weight: 700; color: #0B1F33; margin-bottom: 0.5rem;">Household</div>'
            f'<div style="font-size: 0.88rem; color: {COLOR_TEXT_MUTED}; line-height: 1.45; min-height: 3.5rem;">'
            f'Understand your consumption patterns and forecast your monthly energy usage and estimated bills.'
            f'</div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(hh_card, unsafe_allow_html=True)
        if st.button("Explore Household →", key="btn_persona_household", use_container_width=True):
            set_persona("household")
            st.rerun()

    with card_col2:
        comm_card = (
            f'<div class="gv-persona-card">'
            f'<div>'
            f'<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">'
            f'<span style="font-size: 1.8rem;">🏢</span>'
            f'<span class="gv-badge gv-badge-amber">Commercial</span>'
            f'</div>'
            f'<div style="font-size: 1.25rem; font-weight: 700; color: #0B1F33; margin-bottom: 0.5rem;">Commercial</div>'
            f'<div style="font-size: 0.88rem; color: {COLOR_TEXT_MUTED}; line-height: 1.45; min-height: 3.5rem;">'
            f'Monitor building demand, peak loads, and understand regional energy patterns across facilities.'
            f'</div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(comm_card, unsafe_allow_html=True)
        if st.button("Explore Commercial →", key="btn_persona_commercial", use_container_width=True):
            set_persona("commercial")
            st.rerun()

    with card_col3:
        gov_card = (
            f'<div class="gv-persona-card">'
            f'<div>'
            f'<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">'
            f'<span style="font-size: 1.8rem;">🌐</span>'
            f'<span class="gv-badge gv-badge-teal">Government</span>'
            f'</div>'
            f'<div style="font-size: 1.25rem; font-weight: 700; color: #0B1F33; margin-bottom: 0.5rem;">Government</div>'
            f'<div style="font-size: 0.88rem; color: {COLOR_TEXT_MUTED}; line-height: 1.45; min-height: 3.5rem;">'
            f'Analyze aggregate grid demand and compare energy patterns across regional administrative sites.'
            f'</div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(gov_card, unsafe_allow_html=True)
        if st.button("Explore Government →", key="btn_persona_government", use_container_width=True):
            set_persona("government")
            st.rerun()

    # Footer note & disclaimers
    footer_html = (
        f'<div style="margin-top: 3.5rem; padding-top: 1.5rem; border-top: 1px solid {COLOR_BORDER}; text-align: center;">'
        f'<div style="font-size: 0.78rem; color: {COLOR_TEXT_MUTED};">'
        f'Persona selection is an interactive prototype navigation feature. No authentication password or session token required.'
        f'</div>'
        f'<div style="font-size: 0.72rem; color: rgba(143, 174, 197, 0.7); margin-top: 0.35rem;">'
        f'Historical replay environment • Residential records (2011–2015) • Commercial & Government records (2016–2017)'
        f'</div>'
        f'</div>'
    )
    st.markdown(footer_html, unsafe_allow_html=True)
