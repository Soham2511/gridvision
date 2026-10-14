"""Commercial Dashboard view implementation with Building Demand and Regional Demand tabs."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.components.alerts_panel import compute_system_alerts, render_alerts_panel
from dashboard.components.forecast_charts import (
    render_time_series_chart,
)
from dashboard.components.header import render_dashboard_header
from dashboard.components.metric_cards import render_kpi_row
from dashboard.utils.data import (
    get_api_client,
    load_commercial_history,
    load_commercial_latest,
    load_government_history,
    load_government_latest,
    load_model_metadata,
)
from dashboard.utils.forecasting import (
    forecast_commercial_next_10h,
    forecast_government_next_10h,
)
from dashboard.utils.formatting import format_kwh, format_percent
from dashboard.utils.theme import COLOR_BORDER, COLOR_TEXT_MUTED
from dashboard.utils.time_range import filter_by_time_range


def render_commercial_view() -> None:
    """Render Commercial dashboard with Building Demand and Regional Demand tabs."""
    try:
        latest_df = load_commercial_latest()
        building_history_df = load_commercial_history()
    except (FileNotFoundError, OSError, ValueError) as err:
        st.error(f"Error loading commercial dataset: {err}")
        return

    if latest_df.empty:
        st.warning("No commercial test-split records found.")
        return

    # Buildings supported by LightGBM model artifact
    supported_buildings = sorted(latest_df["building_id"].astype(str).unique())
    current_selected = st.session_state.get("commercial_building_id")
    if current_selected not in supported_buildings:
        current_selected = supported_buildings[0]
        st.session_state.commercial_building_id = current_selected

    col_selector, col_spacer = st.columns([2, 3])
    with col_selector:
        selected_bldg = st.selectbox(
            "Selected Supported Commercial Facility",
            options=supported_buildings,
            index=supported_buildings.index(current_selected),
            key="commercial_bldg_select",
            help="Only buildings present in the trained LightGBM model's categorical palette are supported.",
        )
        st.session_state.commercial_building_id = selected_bldg

    # Row data & Model Prediction
    row = latest_df.loc[latest_df["building_id"].astype(str).eq(selected_bldg)].iloc[0]
    metadata = load_model_metadata("commercial")
    feature_names = list(metadata["features"])

    payload = {
        "entity_id": selected_bldg,
        "forecast_timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
        "features": {name: row[name] for name in feature_names},
        "context": "retrospective_gold_replay",
    }

    pred_result = None
    try:
        pred_result = get_api_client().predict("commercial", payload)
    except APIClientError as err:
        st.error(f"FastAPI inference failed: {err}")

    # Evaluate alerts
    alerts = []
    actual_demand_latest = float(row[metadata["target_name"]])
    pred_val_latest = pred_result["prediction"] if pred_result else None
    abs_err_latest = abs(actual_demand_latest - pred_val_latest) if pred_val_latest is not None else None

    alerts = compute_system_alerts(
        recent_prediction_result=pred_result,
        forecast_error_abs=abs_err_latest,
        error_threshold=200.0,
    )

    # Render Header with time-range selector
    active_range = render_dashboard_header(
        title="Commercial Facility Intelligence",
        subtitle=f"Building: {selected_bldg} • Site: {row.get('site_id', 'Panther')} • Space: {row.get('primaryspaceusage', 'Commercial')}",
        entity_label=f"ID: {selected_bldg}",
        show_time_range=True,
        active_alerts_count=len(alerts),
    )

    # Two Main Tabs
    tab_building, tab_regional = st.tabs(["🏢 Building Demand", "🌐 Regional Demand"])

    # ==========================
    # TAB 1: Building Demand
    # ==========================
    with tab_building:
        # Filter building history
        bldg_hist = building_history_df.loc[
            building_history_df["building_id"].astype(str).eq(selected_bldg)
        ].copy()
        
        filter_res = filter_by_time_range(bldg_hist, timestamp_col="timestamp", range_option=active_range)
        filtered_bldg = filter_res.filtered_df

        if filter_res.is_partially_truncated:
            st.caption(f"ℹ️ {filter_res.explanation}")

        # Metrics computation
        avg_demand = filtered_bldg["hourly_demand_kwh"].mean() if not filtered_bldg.empty else 0.0
        
        peak_idx = filtered_bldg["hourly_demand_kwh"].idxmax() if not filtered_bldg.empty else None
        peak_demand = filtered_bldg.loc[peak_idx, "hourly_demand_kwh"] if peak_idx is not None else 0.0
        peak_demand_time = filtered_bldg.loc[peak_idx, "timestamp"] if peak_idx is not None else "N/A"
        
        # Period-over-period change with explicit date ranges
        bldg_change_pct = None
        bldg_period_text = "vs preceding period"
        if len(filtered_bldg) > 1:
            half_len = len(filtered_bldg) // 2
            p1 = filtered_bldg.iloc[:half_len]
            p2 = filtered_bldg.iloc[half_len:]
            m1 = p1["hourly_demand_kwh"].mean()
            m2 = p2["hourly_demand_kwh"].mean()
            if m1 and m1 > 0:
                bldg_change_pct = ((m2 - m1) / m1) * 100.0
                p1_start = pd.Timestamp(p1["timestamp"].min()).strftime("%b %d")
                p1_end = pd.Timestamp(p1["timestamp"].max()).strftime("%b %d")
                p2_start = pd.Timestamp(p2["timestamp"].min()).strftime("%b %d")
                p2_end = pd.Timestamp(p2["timestamp"].max()).strftime("%b %d")
                bldg_period_text = f"{p2_start}–{p2_end} vs {p1_start}–{p1_end}"
        
        pct_err = None
        if pred_val_latest is not None and actual_demand_latest > 0:
            pct_err = (abs_err_latest / actual_demand_latest) * 100.0

        # Primary KPIs
        kpi_row_1 = [
            {
                "label": "Recent Observed Demand",
                "value": format_kwh(actual_demand_latest, 2),
                "subtext": f"At {pd.Timestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M')}",
                "badge": "Actual",
                "badge_variant": "cyan",
            },
            {
                "label": "Model Predicted Demand",
                "value": format_kwh(pred_val_latest, 2) if pred_val_latest is not None else "N/A",
                "subtext": f"LightGBM v{pred_result.get('model_version', '1.0') if pred_result else '1.0'}",
                "badge": "Forecast",
                "badge_variant": "amber",
            },
            {
                "label": "Absolute Forecast Error",
                "value": format_kwh(abs_err_latest, 2) if abs_err_latest is not None else "N/A",
                "subtext": f"Percentage: {format_percent(pct_err, 1, show_plus=False)}" if pct_err is not None else "N/A",
                "badge": "Variance",
                "badge_variant": "teal",
            },
        ]
        render_kpi_row(kpi_row_1)

        # Secondary KPIs
        kpi_row_2 = [
            {
                "label": "Average Hourly Demand",
                "value": format_kwh(avg_demand, 2),
                "subtext": f"Over {len(filtered_bldg):,} hourly intervals",
            },
            {
                "label": "Peak Observed Demand",
                "value": format_kwh(peak_demand, 2),
                "subtext": f"At {pd.Timestamp(peak_demand_time).strftime('%b %d %H:%M') if peak_demand_time != 'N/A' else 'N/A'}",
            },
            {
                "label": "Period Demand Trend",
                "value": format_percent(bldg_change_pct) if bldg_change_pct is not None else "Baseline",
                "subtext": bldg_period_text,
                "delta": format_percent(bldg_change_pct) if bldg_change_pct is not None else None,
                "delta_positive": (bldg_change_pct is not None and bldg_change_pct <= 0),
            },
        ]
        render_kpi_row(kpi_row_2)

        # Compute 10-hour autoregressive future forecast from current time (end of dataset)
        fc_10h = forecast_commercial_next_10h(selected_bldg, bldg_hist, row)

        # Interactive Demand Time-Series Chart
        st.markdown("### Chronological Hourly Demand & 10-Hour Forecast Horizon")
        st.caption(
            "Displaying verified hourly electricity demand through the dataset boundary (2017-12-31 23:00) "
            "and projecting the next 10 hours (2018-01-01 00:00 – 09:00). "
            "Prediction is computed step-by-step autoregressively with dynamic lag updates from preceding predictions."
        )

        render_time_series_chart(
            df=filtered_bldg,
            timestamp_col="timestamp",
            actual_col="hourly_demand_kwh",
            title=f"{selected_bldg} Hourly Electricity Demand & Future Horizon",
            y_title="Demand (kWh / hour)",
            unit="kWh",
            height=400,
            future_forecast_df=fc_10h,
            future_forecast_col="forecast_kwh",
            future_forecast_label="Next 10 Hours Forecast",
        )

        if not fc_10h.empty:
            avg_fc_10h = float(fc_10h["forecast_kwh"].mean())
            total_fc_10h = float(fc_10h["forecast_kwh"].sum())
            peak_fc_10h = float(fc_10h["forecast_kwh"].max())
            peak_fc_time = fc_10h.loc[fc_10h["forecast_kwh"].idxmax(), "timestamp"]

            fc_kpi_row = [
                {
                    "label": "10-Hour Projected Total",
                    "value": format_kwh(total_fc_10h, 1),
                    "subtext": "2018-01-01 00:00 to 09:00",
                    "badge": "10h Total",
                    "badge_variant": "amber",
                },
                {
                    "label": "10-Hour Mean Load",
                    "value": format_kwh(avg_fc_10h, 2),
                    "subtext": "Average autoregressive rate",
                    "badge": "Hourly Avg",
                    "badge_variant": "teal",
                },
                {
                    "label": "10-Hour Peak Load",
                    "value": format_kwh(peak_fc_10h, 2),
                    "subtext": f"Projected at {pd.Timestamp(peak_fc_time).strftime('%b %d %H:%M')}",
                    "badge": "Peak Hour",
                    "badge_variant": "cyan",
                },
            ]
            st.markdown("#### 🔮 10-Hour Forward Outlook Summary")
            render_kpi_row(fc_kpi_row)

        # Model Caveats
        if pred_result:
            for caveat in pred_result.get("caveats", []):
                st.caption(f"ℹ️ {caveat}")

    # ==========================
    # TAB 2: Regional Demand
    # ==========================
    with tab_regional:
        st.markdown("### Regional Energy Demand Context")
        st.caption(
            "The selected commercial building belongs to the regional site listed below. "
            "You can analyze the actual observed regional load profile over time."
        )

        building_site = str(row.get("site_id", "Panther"))
        
        # Load government/regional dataset for actual regional demand
        try:
            gov_history_df = load_government_history()
            all_sites = sorted(gov_history_df["site_id"].astype(str).unique())
        except Exception as e:
            st.error(f"Could not load regional dataset: {e}")
            all_sites = [building_site]

        col_reg_sel, col_reg_info = st.columns([1.5, 3.5])
        with col_reg_sel:
            selected_site = st.selectbox(
                "Regional Grid Site",
                options=all_sites,
                index=all_sites.index(building_site) if building_site in all_sites else 0,
                key="commercial_region_select",
            )
        with col_reg_info:
            if selected_site == building_site:
                st.markdown(
                    f'<div style="padding-top: 1.8rem; font-size: 0.85rem; color: #00B8A9;">✓ Site directly mapped to {selected_bldg}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="padding-top: 1.8rem; font-size: 0.85rem; color: {COLOR_TEXT_MUTED};">Comparing with alternate regional grid site</div>',
                    unsafe_allow_html=True,
                )

        site_data = gov_history_df.loc[gov_history_df["site_id"].astype(str).eq(selected_site)].copy()
        filter_reg_res = filter_by_time_range(site_data, timestamp_col="timestamp", range_option=active_range)
        filtered_reg = filter_reg_res.filtered_df

        # Regional KPIs
        current_reg_actual = filtered_reg["total_demand_kwh"].iloc[-1] if not filtered_reg.empty else 0.0
        avg_reg_demand = filtered_reg["total_demand_kwh"].mean() if not filtered_reg.empty else 0.0
        peak_reg_demand = filtered_reg["total_demand_kwh"].max() if not filtered_reg.empty else 0.0

        reg_kpis = [
            {
                "label": "Current Regional Demand",
                "value": format_kwh(current_reg_actual, 1),
                "subtext": f"Site: {selected_site}",
                "badge": "Observed",
                "badge_variant": "teal",
            },
            {
                "label": "Average Regional Demand",
                "value": format_kwh(avg_reg_demand, 1),
                "subtext": f"Over selected interval ({active_range})",
            },
            {
                "label": "Peak Regional Demand",
                "value": format_kwh(peak_reg_demand, 1),
                "subtext": "Historical peak in period",
            },
        ]
        render_kpi_row(reg_kpis)

        # Contextual Comparison: Building vs Regional Load
        if selected_site == building_site and avg_reg_demand > 0:
            bldg_share_pct = (avg_demand / avg_reg_demand) * 100.0
            comp_html = (
                f'<div style="background: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 1.1rem; margin-top: 1rem; margin-bottom: 1.25rem; font-size: 0.84rem; line-height: 1.6; box-shadow: 0 2px 8px rgba(11, 31, 51, 0.04); color: #0B1F33;">'
                f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">'
                f'<span style="font-weight: 700; color: #0B1F33; font-size: 0.95rem;">Facility Demand vs Regional Site Load ({selected_site})</span>'
                f'<span class="gv-badge gv-badge-teal">{bldg_share_pct:.2f}% of Site Average</span>'
                f'</div>'
                f'<div>Over the selected <b>{active_range}</b> interval, facility <b>{selected_bldg}</b> maintained an average load of <b>{avg_demand:,.1f} kWh/hr</b>, representing approximately <b>{bldg_share_pct:.2f}%</b> of Site {selected_site}\'s total aggregate observed load (<b>{avg_reg_demand:,.1f} kWh/hr</b>).</div>'
                f'<div style="margin-top: 0.45rem; font-size: 0.76rem; color: {COLOR_TEXT_MUTED};">'
                f'Audit Context: Both measurements represent verified hourly meter telemetry over the identical timeframe. This comparison reflects proportional scale and does not imply the individual facility caused regional load shifts.'
                f'</div>'
                f'</div>'
            )
            st.markdown(comp_html, unsafe_allow_html=True)

        # Regional 10-Hour Autoregressive Forecast
        site_fc_10h = pd.DataFrame()
        try:
            gov_latest_df = load_government_latest()
            site_row_match = gov_latest_df.loc[gov_latest_df["site_id"].astype(str).eq(selected_site)]
            if not site_row_match.empty:
                site_row = site_row_match.iloc[0]
                site_fc_10h = forecast_government_next_10h(selected_site, gov_history_df, site_row)
        except Exception:
            pass

        # Regional Chart
        render_time_series_chart(
            df=filtered_reg,
            timestamp_col="timestamp",
            actual_col="total_demand_kwh",
            title=f"Site {selected_site} Regional Demand & 10-Hour Forecast Horizon",
            y_title="Total Site Demand (kWh / hr)",
            unit="kWh",
            height=380,
            future_forecast_df=site_fc_10h,
            future_forecast_col="forecast_kwh",
            future_forecast_label="Next 10 Hours Regional Forecast",
        )

        st.info(
            f"ℹ️ Regional 10-Hour Horizon: Projected for Site {selected_site} across the next 10 hours (2018-01-01 00:00 – 09:00) "
            "using the Regional Grid LightGBM model with dynamic autoregressive lag updates."
        )

    # Render alerts drawer
    render_alerts_panel(alerts)
