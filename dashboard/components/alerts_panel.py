"""Deterministic alerts evaluation and slide-over panel component."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st
from dashboard.utils.formatting import format_percent
from dashboard.utils.theme import (
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_ENERGY_AMBER,
    COLOR_MIDNIGHT_NAVY,
    COLOR_PURE_WHITE,
    COLOR_SMART_TEAL,
    COLOR_TEXT_MUTED,
)


@dataclass(frozen=True)
class AlertItem:
    """A deterministic, verifiable alert grounded in system data."""
    id: str
    severity: str  # "critical", "warning", "info"
    title: str
    message: str
    timestamp: str | None = None
    entity_id: str | None = None


def compute_system_alerts(
    api_readiness: dict[str, Any] | None = None,
    recent_prediction_result: dict[str, Any] | None = None,
    coverage_ratio: float | None = None,
    forecast_error_abs: float | None = None,
    error_threshold: float = 150.0,
) -> list[AlertItem]:
    """
    Generate deterministic alerts derived only from real data and model execution results.
    
    Never fabricates alerts or claims live network monitoring when inactive.
    """
    alerts: list[AlertItem] = []

    # 1. API & Model Readiness
    if api_readiness:
        status = api_readiness.get("status")
        if status != "ready":
            alerts.append(
                AlertItem(
                    id="api_unready",
                    severity="critical",
                    title="API Artifact Readiness Incomplete",
                    message=f"Backend reported status '{status}'. Expected models may not all be loaded.",
                    timestamp=None,
                )
            )
        loaded = set(api_readiness.get("models_loaded", []))
        expected = set(api_readiness.get("models_expected", []))
        missing = expected - loaded
        if missing:
            alerts.append(
                AlertItem(
                    id="models_missing",
                    severity="critical",
                    title="Model Artifact Not Verified",
                    message=f"Missing models: {', '.join(sorted(missing))}. Predictions unavailable for these domains.",
                    timestamp=None,
                )
            )

    # 2. Prediction Status & Negative Energy Checks
    if recent_prediction_result:
        pred_status = recent_prediction_result.get("prediction_status")
        if pred_status == "invalid_negative_energy":
            alerts.append(
                AlertItem(
                    id="negative_energy",
                    severity="critical",
                    title="Invalid Negative Energy Prediction",
                    message=(
                        f"Model returned a negative output ({recent_prediction_result.get('prediction'):.2f} kWh). "
                        "Excluded from billing and monthly forecast calculations."
                    ),
                    timestamp=str(recent_prediction_result.get("forecast_timestamp")),
                    entity_id=str(recent_prediction_result.get("entity_id")),
                )
            )

    # 3. Low Interval Reading Coverage (for Residential)
    if coverage_ratio is not None and coverage_ratio < 0.90:
        alerts.append(
            AlertItem(
                id="low_coverage",
                severity="warning",
                title="Low Daily Interval Coverage",
                message=(
                    f"Interval reading coverage today is {format_percent(coverage_ratio * 100)}, below the "
                    "0.90 minimum threshold required for certified billing accuracy."
                ),
                timestamp=None,
            )
        )

    # 4. Large Forecast Error / Deviation Check
    if forecast_error_abs is not None and forecast_error_abs > error_threshold:
        alerts.append(
            AlertItem(
                id="high_error",
                severity="warning",
                title="High Retrospective Forecast Deviation",
                message=(
                    f"Observed demand deviates by {forecast_error_abs:,.1f} kWh from the model prediction. "
                    "Review historical weather conditions or baseline parameters."
                ),
                timestamp=None,
            )
        )

    return alerts


def render_alerts_panel(alerts: list[AlertItem]) -> None:
    """Render the alerts drawer if toggled open."""
    if not st.session_state.get("alerts_open", False):
        return

    with st.sidebar:
        header_html = (
            f'<div style="background: {COLOR_PURE_WHITE}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.05);">'
            f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">'
            f'<span style="font-weight: 700; font-size: 1.05rem; color: {COLOR_MIDNIGHT_NAVY};">Active System Alerts</span>'
            f'<span class="gv-badge gv-badge-amber">{len(alerts)} alerts</span>'
            f'</div>'
        )
        st.markdown(header_html, unsafe_allow_html=True)

        if not alerts:
            st.info("No active system warnings or data-quality anomalies detected.")
        else:
            for item in alerts:
                sev_color = COLOR_DANGER if item.severity == "critical" else (
                    COLOR_ENERGY_AMBER if item.severity == "warning" else COLOR_SMART_TEAL
                )
                time_html = f'<div style="font-size: 0.72rem; color: {COLOR_TEXT_MUTED}; margin-top: 0.25rem;">Ref: {item.timestamp}</div>' if item.timestamp else ""
                entity_html = f'<div style="font-size: 0.72rem; color: {COLOR_TEXT_MUTED};">Entity: {item.entity_id}</div>' if item.entity_id else ""
                
                alert_html = (
                    f'<div class="gv-alert-item gv-alert-{item.severity}" style="border: 1px solid {COLOR_BORDER}; border-left: 4px solid {sev_color}; margin-bottom: 0.6rem; padding: 0.65rem 0.8rem; background: {COLOR_PURE_WHITE}; border-radius: 6px; box-shadow: 0 1px 4px rgba(11, 31, 51, 0.04);">'
                    f'<div style="display: flex; justify-content: space-between; font-weight: 600; font-size: 0.85rem; color: {COLOR_MIDNIGHT_NAVY};">'
                    f'<span>{item.title}</span>'
                    f'<span style="font-size: 0.7rem; text-transform: uppercase; color: {sev_color}; font-weight: 700;">{item.severity}</span>'
                    f'</div>'
                    f'<div style="font-size: 0.78rem; color: {COLOR_TEXT_MUTED}; margin-top: 0.25rem; line-height: 1.35;">'
                    f'{item.message}'
                    f'</div>'
                    f'{entity_html}'
                    f'{time_html}'
                    f'</div>'
                )
                st.markdown(alert_html, unsafe_allow_html=True)

        if st.button("Close Alerts Panel", key="close_alerts_btn"):
            st.session_state.alerts_open = False
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
