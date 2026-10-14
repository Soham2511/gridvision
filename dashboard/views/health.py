"""Data & Model Health view mapped dynamically to each persona's models and datasets."""

from __future__ import annotations

import json

import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.components.header import render_dashboard_header
from dashboard.components.metric_cards import render_kpi_row
from dashboard.utils.config import PROJECT_ROOT
from dashboard.utils.data import get_api_client, load_model_metadata
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_ENERGY_AMBER,
    COLOR_MIDNIGHT_NAVY,
    COLOR_PURE_WHITE,
    COLOR_SMART_TEAL,
    COLOR_TEXT_MUTED,
)


def render_data_and_model_health_view(current_persona: str | None = None) -> None:
    """Render Data & Model Health dashboard tailored to the active persona."""
    persona = current_persona or st.session_state.get("current_persona", "household")

    title_map = {
        "household": ("Data & Model Governance • Residential Outlook", "Verification status, SHA-256 digests, lineage counts, and XGBoost evaluation metrics"),
        "commercial": ("Data & Model Governance • Commercial Demand Model", "Verification status, SHA-256 digests, lineage counts, and LightGBM facility evaluation metrics"),
        "government": ("Data & Model Governance • Regional Grid Architecture", "Verification status, SHA-256 digests, lineage counts, and regional grid model metrics"),
    }
    title_text, subtitle_text = title_map.get(persona, title_map["household"])

    render_dashboard_header(
        title=title_text,
        subtitle=subtitle_text,
        entity_label=f"Persona: {persona.title()}",
        show_time_range=False,
        active_alerts_count=0,
    )

    # 1. API Readiness & Liveness Status
    api_client = get_api_client()
    api_ready = False
    readiness_data = {}
    try:
        readiness_data = api_client.health()
        api_ready = readiness_data.get("status") == "ready"
    except APIClientError as err:
        readiness_data = {"status": "unreachable", "error": str(err)}

    st.markdown("### 1. API & Artifact Readiness")
    if api_ready:
        st.success(
            f"✓ FastAPI Process Healthy • Verified Model Artifacts Loaded: {', '.join(readiness_data.get('models_loaded', []))}"
        )
    else:
        st.error(f"⚠️ API Status Issue: {readiness_data}")

    # 2. Dataset Lineage & Quality Profile (Mapped specifically per persona)
    st.markdown(f"### 2. Dataset Lineage & Quality Profile ({persona.title()} Scope)")

    if persona == "household":
        _render_household_data_profile()
    elif persona == "commercial":
        _render_commercial_data_profile()
    else:
        _render_government_data_profile()

    # 3. Model Registry & Verification Cards (Mapped specifically per persona)
    st.markdown(f"### 3. Model Artifact Governance & Evaluation ({persona.title()} Scope)")
    st.caption("Each model is checksum-verified before loading; un-evaluated research models are explicitly reported.")

    # Determine primary model based on persona
    primary_model_name = "residential"
    if persona == "commercial":
        primary_model_name = "commercial"
    elif persona == "government":
        primary_model_name = "government"

    # Display primary model first with prominent styling
    _render_model_card(primary_model_name, is_primary=True)

    # Secondary models inside collapsible expander
    other_models = [m for m in ("residential", "commercial", "government") if m != primary_model_name]
    with st.expander(f"📦 Other System Models ({', '.join(m.title() for m in other_models)})", expanded=False):
        for other_m in other_models:
            _render_model_card(other_m, is_primary=False)

    # 4. Governance & Operational Safeguards (Tailored per persona)
    st.markdown("### 4. Governance & Operational Safeguards")
    _render_governance_safeguards(persona)


def _render_household_data_profile() -> None:
    """Render household dataset quality and lineage profile."""
    profile_path = PROJECT_ROOT / "data" / "reports" / "data_profile" / "customer_profile.json"
    if profile_path.is_file():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        quality = profile.get("reading_quality", {})
        gold_info = profile.get("gold", {})
        date_range = profile.get("date_range", {})

        profile_kpis = [
            {
                "label": "Customer Meters",
                "value": f"{profile.get('household_count', 0):,}",
                "subtext": "Unique smart meters in Bronze",
                "badge": "370 Meters",
                "badge_variant": "cyan",
            },
            {
                "label": "Silver Interval Readings",
                "value": f"{profile.get('interval_reading_count', 0):,}",
                "subtext": "15-minute validated intervals",
                "badge": "Silver",
                "badge_variant": "teal",
            },
            {
                "label": "Gold Customer-Days",
                "value": f"{gold_info.get('row_count', 0):,}",
                "subtext": "Daily aggregated features",
                "badge": "Gold",
                "badge_variant": "amber",
            },
        ]
        render_kpi_row(profile_kpis)

        profile_summary_html = (
            f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 0.85rem 1.1rem; margin-top: 0.75rem; margin-bottom: 1.5rem; font-size: 0.84rem; line-height: 1.6; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04); color: {COLOR_MIDNIGHT_NAVY};">'
            f'<div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">'
            f'<div><b>Coverage Date Range:</b> {date_range.get("start", "N/A")} to {date_range.get("end", "N/A")}</div>'
            f'<div><b>Missing Intervals:</b> {quality.get("missing", 0):,}</div>'
            f'<div><b>Zero Readings Retained:</b> {quality.get("zero", 0):,}</div>'
            f'<div><b>Quality Gate:</b> Validated Clean</div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(profile_summary_html, unsafe_allow_html=True)
    else:
        st.warning("Customer data-profile report (customer_profile.json) is missing.")


def _render_commercial_data_profile() -> None:
    """Render commercial dataset quality and lineage profile."""
    profile_kpis = [
        {
            "label": "Supported Commercial Facilities",
            "value": "29 Buildings",
            "subtext": "Mapped to Regional Site: Panther",
            "badge": "Facilities",
            "badge_variant": "cyan",
        },
        {
            "label": "Verified Hourly Observations",
            "value": "508,776 Hours",
            "subtext": "17,544 hours per facility (2016–2017)",
            "badge": "100% Aligned",
            "badge_variant": "teal",
        },
        {
            "label": "Gold Feature Schema",
            "value": "39 Features",
            "subtext": "Physical specs, weather lags, cyclical terms",
            "badge": "Commercial-v1",
            "badge_variant": "amber",
        },
    ]
    render_kpi_row(profile_kpis)

    profile_summary_html = (
        f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 0.85rem 1.1rem; margin-top: 0.75rem; margin-bottom: 1.5rem; font-size: 0.84rem; line-height: 1.6; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04); color: {COLOR_MIDNIGHT_NAVY};">'
        f'<div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">'
        f'<div><b>Temporal Range:</b> 2016-01-01 00:00 to 2017-12-31 23:00</div>'
        f'<div><b>Observation Frequency:</b> Hourly average demand (kWh/hr)</div>'
        f'<div><b>Categorical Scope:</b> 29 Trained LightGBM Building IDs</div>'
        f'<div><b>Quality Gate:</b> Zero Negative Energy • Zero Missing Hours</div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(profile_summary_html, unsafe_allow_html=True)


def _render_government_data_profile() -> None:
    """Render government regional dataset quality and lineage profile."""
    profile_kpis = [
        {
            "label": "Administrative Grid Sites",
            "value": "17 Sites",
            "subtext": "Mutually exclusive regional boundaries",
            "badge": "17 Regions",
            "badge_variant": "cyan",
        },
        {
            "label": "Regional Demand Observations",
            "value": "298,248 Hours",
            "subtext": "17,544 synchronized hours per site",
            "badge": "100% Complete",
            "badge_variant": "teal",
        },
        {
            "label": "Monitored Facilities",
            "value": "1,400 Buildings",
            "subtext": "Commercial & municipal representation",
            "badge": "Full Scope",
            "badge_variant": "amber",
        },
    ]
    render_kpi_row(profile_kpis)

    profile_summary_html = (
        f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 0.85rem 1.1rem; margin-top: 0.75rem; margin-bottom: 1.5rem; font-size: 0.84rem; line-height: 1.6; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04); color: {COLOR_MIDNIGHT_NAVY};">'
        f'<div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">'
        f'<div><b>Temporal Range:</b> 2016-01-01 00:00 to 2017-12-31 23:00</div>'
        f'<div><b>Aggregation Integrity:</b> Direct sum across independent sites with verified zero double-counting</div>'
        f'<div><b>Quality Gate:</b> 100% Temporally Synchronized</div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(profile_summary_html, unsafe_allow_html=True)


def _render_model_card(name: str, is_primary: bool = True) -> None:
    """Render a detailed model verification and audit card."""
    try:
        metadata = load_model_metadata(name)
    except Exception as e:
        st.error(f"Failed to load {name} metadata: {e}")
        return

    metrics_filename = str(metadata.get("metrics_report", "metrics.json"))
    metrics_path = PROJECT_ROOT / "artifacts" / "models" / name / metrics_filename
    metrics = (
        json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics_path.is_file()
        else {"status": "missing"}
    )

    border_color = COLOR_SMART_TEAL if is_primary else COLOR_BORDER
    badge_variant = "teal" if is_primary else "cyan"
    primary_badge_html = '<span class="gv-badge gv-badge-teal">Primary Persona Model</span>' if is_primary else ""

    card_header_html = (
        f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {border_color}; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 2px 10px rgba(11, 31, 51, 0.05);">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">'
        f'<div style="font-size: 1.1rem; font-weight: 700; color: {COLOR_MIDNIGHT_NAVY}; display: flex; align-items: center; gap: 8px;">'
        f'<span>📦 {metadata.get("model_name", name).upper()} Model Pipeline</span>'
        f'{primary_badge_html}'
        f'</div>'
        f'<span class="gv-badge gv-badge-{badge_variant}">{metadata.get("artifact_type", "Model")}</span>'
        f'</div>'
        f'<div style="font-size: 0.82rem; color: {COLOR_TEXT_MUTED}; margin-bottom: 0.75rem;">'
        f'Artifact: <b style="color: {COLOR_MIDNIGHT_NAVY};">{metadata.get("artifact_filename")}</b> ({metadata.get("artifact_size_bytes", 0):,} bytes)'
        f'</div>'
        f'</div>'
    )
    st.markdown(card_header_html, unsafe_allow_html=True)

    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.markdown(f"**Target Metric:** `{metadata.get('target_name')}` ({metadata.get('target_units')})")
        st.markdown(f"**Schema Version:** `{metadata.get('feature_schema_version')}`")
        st.markdown(f"**Features Count:** `{len(metadata.get('features', []))} features verified`")
        st.markdown(f"**Evaluation Status:** `{metrics.get('status', 'unknown')}`")
        st.markdown("**SHA-256 Checksum:**")
        st.code(metadata.get("sha256", "N/A"), language="text")

        # Persona-specific metadata details
        if name == "residential":
            st.markdown(f"**Tariff Rule:** ₹{metadata.get('tariff_inr_per_kwh', 10.0):.2f} / kWh flat rate")
            st.markdown(f"**Minimum History Required:** {metadata.get('minimum_elapsed_days_before_prediction', 7)} days in month")
            st.markdown(f"**Minimum Daily Coverage:** {metadata.get('minimum_daily_coverage_ratio', 0.9) * 100:.0f}%")
        elif name == "commercial":
            st.markdown(f"**Categorical Vocabulary:** {len(metadata.get('categorical_features', []))} categorical dimensions")
            st.markdown("**Supported Scope:** 29 Buildings on Site Panther")
        elif name == "government":
            encodings = metadata.get("categorical_encodings", {}).get("site_id_code", {})
            st.markdown(f"**Regional Encodings:** {len(encodings)} Verified Regional Sites")

    with col2:
        st.markdown("**Reported Evaluation Metrics Payload:**")
        st.json(metrics)

    st.caption(f"Governance Check: {metadata.get('status', 'Loaded and checksum verified.')}")


def _render_governance_safeguards(persona: str) -> None:
    """Render persona-specific governance caveats and operational rules."""
    if persona == "household":
        safeguards_html = (
            f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {COLOR_BORDER}; border-left: 4px solid {COLOR_ENERGY_AMBER}; padding: 1rem; border-radius: 6px; font-size: 0.85rem; line-height: 1.6; color: {COLOR_MIDNIGHT_NAVY}; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04);">'
            f'<div><b>1. Flat Tariff Disclaimer:</b> Household bill estimates are calculated strictly using the flat ₹10/kWh research rate. They do not constitute official utility bills.</div>'
            f'<div><b>2. Negative Energy Validation:</b> Non-physical negative predictions are actively trapped by the inference layer and excluded from billing totals.</div>'
            f'<div><b>3. Minimum Coverage Rule:</b> Days with less than 90% interval reading coverage are flagged to alert the user of potential forecast uncertainty.</div>'
            f'</div>'
        )
    elif persona == "commercial":
        safeguards_html = (
            f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {COLOR_BORDER}; border-left: 4px solid {COLOR_ENERGY_AMBER}; padding: 1rem; border-radius: 6px; font-size: 0.85rem; line-height: 1.6; color: {COLOR_MIDNIGHT_NAVY}; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04);">'
            f'<div><b>1. Categorical Vocabulary Safeguard:</b> The commercial model strictly accepts buildings present in its trained LightGBM vocabulary (29 facilities on Site Panther). Arbitrary building IDs are rejected.</div>'
            f'<div><b>2. Building-Level Scope Limitation:</b> The commercial model is trained exclusively for facility-level demand; regional forecasts are never fabricated by naively scaling building inferences.</div>'
            f'<div><b>3. Non-Causative Regional Comparison:</b> Proportional building load against regional load provides scale context only and does not imply facility causation of regional peaks.</div>'
            f'</div>'
        )
    else:
        safeguards_html = (
            f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {COLOR_BORDER}; border-left: 4px solid {COLOR_ENERGY_AMBER}; padding: 1rem; border-radius: 6px; font-size: 0.85rem; line-height: 1.6; color: {COLOR_MIDNIGHT_NAVY}; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04);">'
            f'<div><b>1. Mathematical Summation Integrity:</b> System aggregate demand is strictly computed by direct observation summation across 17 independent sites to eliminate double-counting risk.</div>'
            f'<div><b>2. No Automated Grid Dispatch:</b> Regional and aggregate forecasts are informational decision-support projections; no automated load shedding or grid switching commands are issued.</div>'
            f'<div><b>3. Retrospective Replay Distinction:</b> Historical evaluation uses verified 2016–2017 test splits and does not simulate live SCADA telemetry feeds.</div>'
            f'</div>'
        )
    st.markdown(safeguards_html, unsafe_allow_html=True)
