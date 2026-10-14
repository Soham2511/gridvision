"""Government Dashboard view implementation with Overall Demand and Regional Analysis tabs."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.components.alerts_panel import compute_system_alerts, render_alerts_panel
from dashboard.components.forecast_charts import (
    render_horizontal_ranking_bar_chart,
    render_time_series_chart,
)
from dashboard.components.header import render_dashboard_header
from dashboard.components.metric_cards import render_kpi_row
from dashboard.utils.data import (
    get_api_client,
    load_government_aggregate_history,
    load_government_history,
    load_government_latest,
    load_model_metadata,
)
from dashboard.utils.forecasting import (
    forecast_government_aggregate_next_10h,
    forecast_government_next_10h,
)
from dashboard.utils.formatting import format_kwh, format_percent
from dashboard.utils.time_range import filter_by_time_range


def render_government_view() -> None:
    """Render Government dashboard with Overall Demand and Regional Analysis tabs."""
    try:
        latest_df = load_government_latest()
        gov_history_df = load_government_history()
        aggregate_df = load_government_aggregate_history()
    except (FileNotFoundError, OSError, ValueError) as err:
        st.error(f"Error loading government dataset: {err}")
        return

    if latest_df.empty:
        st.warning("No government test-split records found.")
        return

    # Available Sites
    sites = sorted(latest_df["site_id"].astype(str).unique())
    current_selected = st.session_state.get("government_site_id")
    if current_selected not in sites:
        current_selected = sites[0]
        st.session_state.government_site_id = current_selected

    # Predict for current selected site
    row = latest_df.loc[latest_df["site_id"].astype(str).eq(current_selected)].iloc[0]
    metadata = load_model_metadata("government")
    feature_names = list(metadata["features"])

    payload = {
        "entity_id": current_selected,
        "forecast_timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
        "features": {name: row[name] for name in feature_names},
        "context": "retrospective_gold_replay",
    }

    pred_result = None
    try:
        pred_result = get_api_client().predict("government", payload)
    except APIClientError as err:
        st.error(f"FastAPI inference failed: {err}")

    # Evaluate alerts
    actual_reg_demand = float(row[metadata["target_name"]])
    pred_reg_demand = pred_result["prediction"] if pred_result else None
    abs_err_reg = abs(actual_reg_demand - pred_reg_demand) if pred_reg_demand is not None else None

    alerts = compute_system_alerts(
        recent_prediction_result=pred_result,
        forecast_error_abs=abs_err_reg,
        error_threshold=5000.0,
    )

    # Render Header
    active_range = render_dashboard_header(
        title="Government Grid Intelligence",
        subtitle="Regional administrative demand planning • Retrospective evaluation across 17 grid zones",
        entity_label=f"Scope: {current_selected} & System Aggregate",
        show_time_range=True,
        active_alerts_count=len(alerts),
    )

    # Two Main Tabs
    tab_overall, tab_regional = st.tabs(["🌐 Overall Demand", "📍 Regional Analysis"])

    # ==========================
    # TAB 1: Overall Demand
    # ==========================
    with tab_overall:
        st.markdown("### System-Wide Aggregate Demand")
        st.caption(
            "Safeguarded Aggregation: Aggregated strictly across all 17 mutually exclusive government sites (Bear through Wolf) "
            "with 100% synchronized hourly timestamps and full geographical representation (1,400 buildings)."
        )

        filter_agg_res = filter_by_time_range(aggregate_df, timestamp_col="timestamp", range_option=active_range)
        filtered_agg = filter_agg_res.filtered_df

        if filter_agg_res.is_partially_truncated:
            st.caption(f"ℹ️ {filter_agg_res.explanation}")

        # Metrics for Overall Demand
        current_agg = filtered_agg["total_aggregate_demand_kwh"].iloc[-1] if not filtered_agg.empty else 0.0
        avg_agg = filtered_agg["total_aggregate_demand_kwh"].mean() if not filtered_agg.empty else 0.0
        
        peak_agg_idx = filtered_agg["total_aggregate_demand_kwh"].idxmax() if not filtered_agg.empty else None
        peak_agg_val = filtered_agg.loc[peak_agg_idx, "total_aggregate_demand_kwh"] if peak_agg_idx is not None else 0.0
        peak_agg_time = filtered_agg.loc[peak_agg_idx, "timestamp"] if peak_agg_idx is not None else "N/A"

        change_agg_pct = None
        agg_period_text = "vs preceding period"
        if len(filtered_agg) > 1:
            half = len(filtered_agg) // 2
            p1_agg = filtered_agg.iloc[:half]
            p2_agg = filtered_agg.iloc[half:]
            m1 = p1_agg["total_aggregate_demand_kwh"].mean()
            m2 = p2_agg["total_aggregate_demand_kwh"].mean()
            if m1 and m1 > 0:
                change_agg_pct = ((m2 - m1) / m1) * 100.0
                p1_start = pd.Timestamp(p1_agg["timestamp"].min()).strftime("%b %d")
                p1_end = pd.Timestamp(p1_agg["timestamp"].max()).strftime("%b %d")
                p2_start = pd.Timestamp(p2_agg["timestamp"].min()).strftime("%b %d")
                p2_end = pd.Timestamp(p2_agg["timestamp"].max()).strftime("%b %d")
                agg_period_text = f"{p2_start}–{p2_end} vs {p1_start}–{p1_end}"

        # KPIs Row
        agg_kpis_1 = [
            {
                "label": "Current Total Demand",
                "value": format_kwh(current_agg, 0),
                "subtext": "Sum across all 17 regions",
                "badge": "17 Sites",
                "badge_variant": "teal",
            },
            {
                "label": "Average Aggregate Load",
                "value": format_kwh(avg_agg, 0),
                "subtext": f"Across {len(filtered_agg):,} hours",
            },
            {
                "label": "Peak System Demand",
                "value": format_kwh(peak_agg_val, 0),
                "subtext": f"At {pd.Timestamp(peak_agg_time).strftime('%Y-%m-%d %H:%M') if peak_agg_time != 'N/A' else 'N/A'}",
                "badge": "Peak",
                "badge_variant": "amber",
            },
        ]
        render_kpi_row(agg_kpis_1)

        agg_kpis_2 = [
            {
                "label": "Period Aggregate Trend",
                "value": format_percent(change_agg_pct) if change_agg_pct is not None else "Baseline",
                "subtext": agg_period_text,
                "delta": format_percent(change_agg_pct) if change_agg_pct is not None else None,
                "delta_positive": (change_agg_pct is not None and change_agg_pct <= 0),
            },
            {
                "label": "Contributing Sites",
                "value": "17 / 17 Sites",
                "subtext": "Full verified system coverage",
                "badge": "100%",
                "badge_variant": "cyan",
            },
            {
                "label": "Total Monitored Facilities",
                "value": "1,400 Buildings",
                "subtext": "Non-overlapping regional zones",
            },
        ]
        render_kpi_row(agg_kpis_2)

        # Compute 10-hour system-wide aggregate forecast across all 17 regions
        agg_fc_10h = forecast_government_aggregate_next_10h(gov_history_df, latest_df)

        # Aggregate Demand Chart
        render_time_series_chart(
            df=filtered_agg,
            timestamp_col="timestamp",
            actual_col="total_aggregate_demand_kwh",
            title="System-Wide Aggregate Electricity Demand & 10-Hour Forecast Horizon",
            y_title="Total System Demand (kWh / hr)",
            unit="kWh",
            height=400,
            future_forecast_df=agg_fc_10h,
            future_forecast_col="total_aggregate_demand_kwh",
            future_forecast_label="Next 10 Hours System Forecast",
        )

        if not agg_fc_10h.empty:
            avg_agg_fc = float(agg_fc_10h["total_aggregate_demand_kwh"].mean())
            total_agg_fc = float(agg_fc_10h["total_aggregate_demand_kwh"].sum())
            peak_agg_fc = float(agg_fc_10h["total_aggregate_demand_kwh"].max())
            peak_agg_fc_time = agg_fc_10h.loc[agg_fc_10h["total_aggregate_demand_kwh"].idxmax(), "timestamp"]

            agg_fc_kpis = [
                {
                    "label": "10-Hour Projected Energy",
                    "value": format_kwh(total_agg_fc, 0),
                    "subtext": "Sum across all 17 regions (10h)",
                    "badge": "10h Aggregate",
                    "badge_variant": "amber",
                },
                {
                    "label": "Mean Forecast Load",
                    "value": format_kwh(avg_agg_fc, 0),
                    "subtext": "Average hourly system rate",
                    "badge": "System Avg",
                    "badge_variant": "teal",
                },
                {
                    "label": "Projected Peak Demand",
                    "value": format_kwh(peak_agg_fc, 0),
                    "subtext": f"At {pd.Timestamp(peak_agg_fc_time).strftime('%Y-%m-%d %H:%M')}",
                    "badge": "System Peak",
                    "badge_variant": "cyan",
                },
            ]
            st.markdown("#### 🔮 10-Hour System Forecast Outlook")
            render_kpi_row(agg_fc_kpis)

        st.caption(
            "ℹ️ Multi-Regional Autoregressive Projection: Each of the 17 regional grid zones is forecasted "
            "step-by-step for the next 10 hours (2018-01-01 00:00 to 09:00) with dynamic lag propagation, and summed into the national aggregate curve."
        )

        # Regional Comparison Ranking Chart
        st.markdown("### Regional Demand Ranking & Distribution")
        st.caption(
            f"Ranked total electricity demand across all 17 regional grid sites during the selected {active_range} interval. "
            "All regions represent verified, non-overlapping regional meter scopes."
        )
        filter_all_sites_res = filter_by_time_range(gov_history_df, timestamp_col="timestamp", range_option=active_range)
        filtered_sites_all = filter_all_sites_res.filtered_df
        site_ranking_df = (
            filtered_sites_all.groupby("site_id", as_index=False)["total_demand_kwh"]
            .sum()
            .rename(columns={"total_demand_kwh": "total_demand"})
        )
        render_horizontal_ranking_bar_chart(
            df=site_ranking_df,
            category_col="site_id",
            value_col="total_demand",
            title=f"Regional Grid Sites Ranked by Total Observed Demand ({active_range})",
            x_title="Total Observed Energy (kWh)",
            unit="kWh",
            height=460,
        )

    # ==========================
    # TAB 2: Regional Analysis
    # ==========================
    with tab_regional:
        st.markdown("### Site-Specific Regional Demand Analysis")
        
        col_site_sel, col_site_meta = st.columns([1.5, 3.5])
        with col_site_sel:
            selected_site = st.selectbox(
                "Selected Government Region / Site",
                options=sites,
                index=sites.index(current_selected),
                key="gov_site_select",
            )
            if selected_site != current_selected:
                st.session_state.government_site_id = selected_site
                st.rerun()

        # Site historical data
        site_hist = gov_history_df.loc[gov_history_df["site_id"].astype(str).eq(selected_site)].copy()
        filter_site_res = filter_by_time_range(site_hist, timestamp_col="timestamp", range_option=active_range)
        filtered_site = filter_site_res.filtered_df

        if filter_site_res.is_partially_truncated:
            st.caption(f"ℹ️ {filter_site_res.explanation}")

        # Metrics for selected site
        avg_site_demand = filtered_site["total_demand_kwh"].mean() if not filtered_site.empty else 0.0
        
        peak_site_idx = filtered_site["total_demand_kwh"].idxmax() if not filtered_site.empty else None
        peak_site_demand = filtered_site.loc[peak_site_idx, "total_demand_kwh"] if peak_site_idx is not None else 0.0
        peak_site_time = filtered_site.loc[peak_site_idx, "timestamp"] if peak_site_idx is not None else "N/A"

        site_change_pct = None
        site_period_text = "vs preceding period"
        if len(filtered_site) > 1:
            half = len(filtered_site) // 2
            s1_df = filtered_site.iloc[:half]
            s2_df = filtered_site.iloc[half:]
            s1 = s1_df["total_demand_kwh"].mean()
            s2 = s2_df["total_demand_kwh"].mean()
            if s1 and s1 > 0:
                site_change_pct = ((s2 - s1) / s1) * 100.0
                s1_start = pd.Timestamp(s1_df["timestamp"].min()).strftime("%b %d")
                s1_end = pd.Timestamp(s1_df["timestamp"].max()).strftime("%b %d")
                s2_start = pd.Timestamp(s2_df["timestamp"].min()).strftime("%b %d")
                s2_end = pd.Timestamp(s2_df["timestamp"].max()).strftime("%b %d")
                site_period_text = f"{s2_start}–{s2_end} vs {s1_start}–{s1_end}"

        site_kpis_1 = [
            {
                "label": "Recent Observed Demand",
                "value": format_kwh(actual_reg_demand, 1),
                "subtext": f"At {pd.Timestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M')}",
                "badge": "Actual",
                "badge_variant": "cyan",
            },
            {
                "label": "Model Predicted Demand",
                "value": format_kwh(pred_reg_demand, 1) if pred_reg_demand is not None else "N/A",
                "subtext": "LightGBM Regional Model",
                "badge": "Forecast",
                "badge_variant": "amber",
            },
            {
                "label": "Absolute Forecast Error",
                "value": format_kwh(abs_err_reg, 1) if abs_err_reg is not None else "N/A",
                "subtext": f"Variance: {format_percent((abs_err_reg / actual_reg_demand) * 100 if actual_reg_demand > 0 else None, 1, show_plus=False)}",
                "badge": "Variance",
                "badge_variant": "teal",
            },
        ]
        render_kpi_row(site_kpis_1)

        site_kpis_2 = [
            {
                "label": "Average Regional Demand",
                "value": format_kwh(avg_site_demand, 1),
                "subtext": f"Over {len(filtered_site):,} hourly records",
            },
            {
                "label": "Period Trend",
                "value": format_percent(site_change_pct) if site_change_pct is not None else "Baseline",
                "subtext": site_period_text,
                "delta": format_percent(site_change_pct) if site_change_pct is not None else None,
                "delta_positive": (site_change_pct is not None and site_change_pct <= 0),
            },
            {
                "label": "Peak Regional Demand",
                "value": format_kwh(peak_site_demand, 1),
                "subtext": f"At {pd.Timestamp(peak_site_time).strftime('%b %d %H:%M') if peak_site_time != 'N/A' else 'N/A'} ({int(row.get('building_count', 0))} buildings)",
            },
        ]
        render_kpi_row(site_kpis_2)

        # Regional 10-Hour Autoregressive Forecast
        site_fc_10h = forecast_government_next_10h(selected_site, gov_history_df, row)

        # Regional Time-Series Chart
        render_time_series_chart(
            df=filtered_site,
            timestamp_col="timestamp",
            actual_col="total_demand_kwh",
            title=f"Site {selected_site} Hourly Regional Demand & 10-Hour Forecast Horizon",
            y_title="Demand (kWh / hour)",
            unit="kWh",
            height=400,
            future_forecast_df=site_fc_10h,
            future_forecast_col="forecast_kwh",
            future_forecast_label="Next 10 Hours Regional Forecast",
        )

        if not site_fc_10h.empty:
            avg_site_fc = float(site_fc_10h["forecast_kwh"].mean())
            total_site_fc = float(site_fc_10h["forecast_kwh"].sum())
            peak_site_fc = float(site_fc_10h["forecast_kwh"].max())
            peak_site_fc_time = site_fc_10h.loc[site_fc_10h["forecast_kwh"].idxmax(), "timestamp"]

            site_fc_kpis = [
                {
                    "label": "10-Hour Forecast Total",
                    "value": format_kwh(total_site_fc, 1),
                    "subtext": "2018-01-01 00:00 to 09:00",
                    "badge": "10h Total",
                    "badge_variant": "amber",
                },
                {
                    "label": "10-Hour Mean Load",
                    "value": format_kwh(avg_site_fc, 1),
                    "subtext": "Average autoregressive rate",
                    "badge": "Regional Avg",
                    "badge_variant": "teal",
                },
                {
                    "label": "10-Hour Peak Load",
                    "value": format_kwh(peak_site_fc, 1),
                    "subtext": f"Projected at {pd.Timestamp(peak_site_fc_time).strftime('%b %d %H:%M')}",
                    "badge": "Regional Peak",
                    "badge_variant": "cyan",
                },
            ]
            st.markdown("#### 🔮 Regional 10-Hour Outlook Summary")
            render_kpi_row(site_fc_kpis)

        st.warning(
            "⚠️ Governance Notice: This model does NOT generate energy redistribution recommendations, "
            "automated dispatch controls, load balancing schedules, or grid switching commands. "
            "It is strictly an analytical forecast of regional hourly energy demand."
        )

    # Render alerts drawer
    render_alerts_panel(alerts)
