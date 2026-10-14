"""Household / Residential Dashboard view implementation."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.components.alerts_panel import compute_system_alerts, render_alerts_panel
from dashboard.components.forecast_charts import (
    render_comparison_bar_chart,
    render_time_series_chart,
)
from dashboard.components.header import render_dashboard_header
from dashboard.components.metric_cards import render_kpi_row
from dashboard.utils.data import (
    get_api_client,
    load_model_metadata,
    load_residential_history,
    load_residential_latest,
)
from dashboard.utils.forecasting import forecast_household_next_10_days
from dashboard.utils.formatting import (
    format_inr,
    format_kwh,
    format_percent,
)
from dashboard.utils.theme import (
    COLOR_BORDER,
)
from dashboard.utils.time_range import filter_by_time_range


def render_household_view() -> None:
    """Render complete Household dashboard with entity selection, KPIs, chart, and insights."""
    # 1. Load data
    try:
        latest_df = load_residential_latest()
        history_df = load_residential_history()
    except (FileNotFoundError, OSError, ValueError) as err:
        st.error(f"Error loading residential dataset: {err}")
        return

    if latest_df.empty:
        st.warning("No residential feature records found.")
        return

    # Entity selection
    households = sorted(latest_df["household_id"].astype(str).unique())
    current_selected = st.session_state.get("household_id")
    if current_selected not in households:
        current_selected = households[0]
        st.session_state.household_id = current_selected

    col_selector, col_spacer = st.columns([1.5, 3.5])
    with col_selector:
        selected_household = st.selectbox(
            "Selected Household / Meter ID",
            options=households,
            index=households.index(current_selected),
            key="household_meter_select",
        )
        st.session_state.household_id = selected_household

    # Row data & Model Prediction
    row = latest_df.loc[latest_df["household_id"].astype(str).eq(selected_household)].iloc[0]
    metadata = load_model_metadata("residential")
    feature_names = metadata["features"]
    
    payload = {
        "entity_id": selected_household,
        "forecast_timestamp": pd.Timestamp(row["date"]).isoformat(),
        "features": {name: row[name] for name in feature_names},
        "context": "retrospective_gold_replay",
        "actual_kwh_so_far": float(row["actual_cycle_kwh_so_far"]),
    }

    pred_result = None
    try:
        pred_result = get_api_client().predict("residential", payload)
    except APIClientError as err:
        st.warning(f"FastAPI inference unavailable: {err}")

    # Historical filtering for this household
    hh_history = history_df.loc[
        history_df["household_id"].astype(str).eq(selected_household)
    ].sort_values("date").copy()

    # Time-range filtering
    selected_range = st.session_state.get("selected_time_range", "1M")
    filter_res = filter_by_time_range(hh_history, timestamp_col="date", range_option=selected_range)
    filtered_history = filter_res.filtered_df

    # Evaluate alerts
    coverage_today = float(row.get("coverage_today", 1.0))
    alerts = compute_system_alerts(
        recent_prediction_result=pred_result,
        coverage_ratio=coverage_today,
    )

    # Render Header with time range & alerts toggle
    # Render Header with time range & alerts toggle
    active_range = render_dashboard_header(
        title="Your Energy Outlook",
        subtitle=f"Historical telemetry through {filter_res.available_end.strftime('%Y-%m-%d')} • Calendar month-end forecast",
        entity_label=f"Meter: {selected_household}",
        show_time_range=True,
        active_alerts_count=len(alerts),
    )

    # Re-apply filter if range changed in header
    if active_range != selected_range:
        filter_res = filter_by_time_range(hh_history, timestamp_col="date", range_option=active_range)
        filtered_history = filter_res.filtered_df

    if filter_res.is_partially_truncated:
        st.caption(f"ℹ️ {filter_res.explanation}")

    # Compute KPIs
    # 1. Current usage (latest daily reading)
    current_usage = float(row["daily_kwh"]) if "daily_kwh" in row else 0.0
    
    # 2. Monthly usage so far
    monthly_usage_so_far = float(row["actual_cycle_kwh_so_far"])
    
    # 3. Predicted month-end usage
    pred_remaining = pred_result["prediction"] if pred_result else None
    pred_month_end = pred_result.get("estimated_month_end_kwh") if pred_result else None
    
    # 4. Daily average over selected interval
    daily_avg = filtered_history["daily_kwh"].mean() if not filtered_history.empty else 0.0
    
    # 5. Change vs previous comparable period with explicit dates
    change_pct = None
    period_comparison_text = "vs preceding period"
    if len(filtered_history) > 1:
        half_len = len(filtered_history) // 2
        p1_df = filtered_history.iloc[:half_len]
        p2_df = filtered_history.iloc[half_len:]
        prev_half = p1_df["daily_kwh"].mean()
        curr_half = p2_df["daily_kwh"].mean()
        if prev_half and prev_half > 0:
            change_pct = ((curr_half - prev_half) / prev_half) * 100.0
            p1_start = pd.Timestamp(p1_df["date"].min()).strftime("%b %d")
            p1_end = pd.Timestamp(p1_df["date"].max()).strftime("%b %d")
            p2_start = pd.Timestamp(p2_df["date"].min()).strftime("%b %d")
            p2_end = pd.Timestamp(p2_df["date"].max()).strftime("%b %d")
            period_comparison_text = f"{p2_start}–{p2_end} vs {p1_start}–{p1_end}"

    # 6. Estimated Monthly Bill (₹10/kWh flat tariff)
    bill_estimate = pred_result.get("estimated_month_end_bill_inr") if pred_result else None

    # Render Primary KPI Cards
    kpi_primary = [
        {
            "label": "Current Daily Usage",
            "value": format_kwh(current_usage, 1),
            "subtext": f"Observed on {pd.Timestamp(row['date']).strftime('%b %d')}",
            "badge": "Daily",
            "badge_variant": "cyan",
        },
        {
            "label": "Month-to-Date Accumulated",
            "value": format_kwh(monthly_usage_so_far, 1),
            "subtext": f"Cycle day {int(row.get('elapsed_days', 0))} of month",
            "badge": "Actual",
            "badge_variant": "teal",
        },
        {
            "label": "Predicted Month-End Usage",
            "value": format_kwh(pred_month_end, 1) if pred_month_end else "Unavailable",
            "subtext": f"Model remaining: {format_kwh(pred_remaining, 1)}",
            "badge": "Forecast",
            "badge_variant": "amber",
        },
    ]
    render_kpi_row(kpi_primary)

    # Render Secondary KPI Cards
    kpi_secondary = [
        {
            "label": "Daily Average (Interval)",
            "value": format_kwh(daily_avg, 1),
            "subtext": f"Across {len(filtered_history)} days",
        },
        {
            "label": "Period Trend",
            "value": format_percent(change_pct) if change_pct is not None else "Baseline",
            "subtext": period_comparison_text,
            "delta": format_percent(change_pct) if change_pct is not None else None,
            "delta_positive": (change_pct is not None and change_pct <= 0),  # lower usage is positive for customer
        },
        {
            "label": "Estimated Monthly Bill",
            "value": format_inr(bill_estimate) if bill_estimate is not None else "Unavailable",
            "subtext": "Prototype flat tariff (₹10/kWh)",
            "badge": "₹10/kWh",
            "badge_variant": "teal",
            "help_text": "Illustrative estimate calculated at ₹10/kWh. Not an official utility invoice.",
        },
    ]
    render_kpi_row(kpi_secondary)

    # Demand Chart Section
    st.markdown("### Historical Daily Consumption & Month-End Projection")
    
    # Forward 10-day projected usage
    hh_fc_10d = forecast_household_next_10_days(selected_household, hh_history, row)

    # We plot the daily consumption history and forward horizon
    render_time_series_chart(
        df=filtered_history,
        timestamp_col="date",
        actual_col="daily_kwh",
        title=f"Meter {selected_household} Daily Electricity Consumption & 10-Day Projection",
        y_title="Daily Consumption (kWh)",
        unit="kWh",
        height=380,
        future_forecast_df=hh_fc_10d,
        future_forecast_col="forecast_kwh",
        future_forecast_label="Next 10 Days Projected Usage",
    )

    # Month-end Projection Comparison Breakdown
    obs_remaining = float(row.get("target_remaining_kwh", 0.0))
    breakdown_col1, breakdown_col2 = st.columns([1.6, 1])
    
    with breakdown_col1:
        st.markdown("#### Month-End Projection Components")
        st.caption(
            "The residential XGBoost model predicts the cumulative remainder of the calendar month (target_remaining_kwh). "
            "It does not predict individual daily readings."
        )
        if pred_result and pred_remaining is not None:
            render_comparison_bar_chart(
                categories=[
                    "Actual Month-to-Date",
                    "Model Remaining Forecast",
                    "Observed Remaining (Retrospective)",
                    "Projected Month-End Total",
                ],
                values=[
                    monthly_usage_so_far,
                    pred_remaining,
                    obs_remaining,
                    pred_month_end,
                ],
                title="Month-End Estimate vs Retrospective Ground Truth",
                y_title="Energy (kWh)",
                unit="kWh",
                height=320,
            )

    with breakdown_col2:
        st.markdown("#### Supporting Operational Insights")
        peak_idx = filtered_history["daily_kwh"].idxmax() if not filtered_history.empty else None
        peak_val = filtered_history.loc[peak_idx, "daily_kwh"] if peak_idx is not None else 0.0
        peak_date = filtered_history.loc[peak_idx, "date"] if peak_idx is not None else "N/A"
        
        coverage_status = "Reliable (Full coverage)" if coverage_today >= 0.9 else "Reduced confidence (<90% telemetry)"
        trend_explanation = (
            f"Consumption {'decreased' if change_pct and change_pct < 0 else 'increased'} by {abs(change_pct):.1f}% ({period_comparison_text})."
            if change_pct is not None
            else "Single period baseline."
        )
        
        insight_html = (
            f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 1rem; font-size: 0.82rem; line-height: 1.7; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04); color: #0B1F33;">'
            f'<div style="margin-bottom: 0.4rem;"><b>⚡ Peak Day:</b> {pd.Timestamp(peak_date).strftime("%Y-%m-%d") if peak_date != "N/A" else "N/A"} ({peak_val:,.1f} kWh) — highest consumption recorded during this timeframe.</div>'
            f'<div style="margin-bottom: 0.4rem;"><b>📊 Interval Trend:</b> {trend_explanation}</div>'
            f'<div style="margin-bottom: 0.4rem;"><b>🗓️ Daily Average:</b> {daily_avg:,.1f} kWh/day across {len(filtered_history)} observed days.</div>'
            f'<div style="margin-bottom: 0.4rem;"><b>📡 Data Coverage:</b> {coverage_today * 100:.1f}% — {coverage_status}.</div>'
            f'<div style="margin-bottom: 0.4rem;"><b>🔮 Month-End Projection:</b> {format_kwh(monthly_usage_so_far, 1)} MTD + {format_kwh(pred_remaining, 1) if pred_remaining else "N/A"} forecast remainder = {format_kwh(pred_month_end, 1) if pred_month_end else "N/A"}.</div>'
            f'<div style="margin-top: 0.5rem; color: #087EBD; font-size: 0.75rem; font-weight: 600;">'
            f'⚠️ Retrospective Replay: Data derived from 2011–2015 test records. Not a live telemetry feed.'
            f'</div>'
            f'</div>'
        )
        st.markdown(insight_html, unsafe_allow_html=True)

    # Render alerts panel if open
    render_alerts_panel(alerts)
