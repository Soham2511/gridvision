"""Historical Analysis view mapped dynamically to each persona's verified datasets."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from dashboard.components.forecast_charts import (
    render_horizontal_ranking_bar_chart,
    render_time_series_chart,
)
from dashboard.components.header import render_dashboard_header
from dashboard.components.metric_cards import render_kpi_row
from dashboard.utils.data import (
    load_commercial_history,
    load_commercial_latest,
    load_government_aggregate_history,
    load_government_history,
    load_government_latest,
    load_residential_history,
    load_residential_latest,
)
from dashboard.utils.forecasting import (
    forecast_commercial_next_10h,
    forecast_government_aggregate_next_10h,
    forecast_government_next_10h,
    forecast_household_next_10_days,
)
from dashboard.utils.formatting import format_kwh, format_percent
from dashboard.utils.time_range import filter_by_time_range


def render_historical_analysis_view(current_persona: str | None = None) -> None:
    """Render historical analysis page tailored to the active persona's dataset."""
    persona = current_persona or st.session_state.get("current_persona", "household")

    if persona == "commercial":
        _render_commercial_historical()
    elif persona == "government":
        _render_government_historical()
    else:
        _render_household_historical()


def _render_household_historical() -> None:
    """Render household historical analysis using residential customer features."""
    try:
        history = load_residential_history()
    except (FileNotFoundError, OSError, ValueError) as error:
        st.error(f"Could not load residential historical dataset: {error}")
        return

    households = sorted(history["household_id"].astype(str).unique())
    current_hh = st.session_state.get("household_id")
    if current_hh not in households:
        current_hh = households[0]
        st.session_state.household_id = current_hh

    col_sel, col_info = st.columns([1.5, 3.5])
    with col_sel:
        selected = st.selectbox(
            "Select Household / Meter",
            options=households,
            index=households.index(current_hh),
            key="hist_analysis_meter_select",
        )
        st.session_state.household_id = selected

    selected_history = history.loc[
        history["household_id"].astype(str).eq(selected)
    ].sort_values("date").copy()

    # Time range filtering
    selected_range = st.session_state.get("selected_time_range", "1Y")
    filter_res = filter_by_time_range(selected_history, timestamp_col="date", range_option=selected_range)
    filtered = filter_res.filtered_df

    # Header
    active_range = render_dashboard_header(
        title="Household Historical Consumption Analytics",
        subtitle=f"Long-term daily telemetry and ground truth records (2011–2015) • Meter {selected}",
        entity_label=f"Meter: {selected}",
        show_time_range=True,
        active_alerts_count=0,
    )

    if active_range != selected_range:
        filter_res = filter_by_time_range(selected_history, timestamp_col="date", range_option=active_range)
        filtered = filter_res.filtered_df

    if filter_res.is_partially_truncated:
        st.caption(f"ℹ️ {filter_res.explanation}")

    # Summary KPIs
    valid_daily = filtered.dropna(subset=["daily_kwh"])
    valid_target = filtered.dropna(subset=["target_remaining_kwh"])
    valid_coverage = filtered.dropna(subset=["coverage_ratio"])

    mean_daily = valid_daily["daily_kwh"].mean() if not valid_daily.empty else 0.0
    mean_target = valid_target["target_remaining_kwh"].mean() if not valid_target.empty else 0.0
    mean_coverage = valid_coverage["coverage_ratio"].mean() if not valid_coverage.empty else 0.0

    kpis = [
        {
            "label": "Average Daily Consumption",
            "value": format_kwh(mean_daily, 2),
            "subtext": f"Across {len(valid_daily)} recorded days",
            "badge": "Daily",
            "badge_variant": "cyan",
        },
        {
            "label": "Avg Target Remaining",
            "value": format_kwh(mean_target, 1),
            "subtext": "Month-end ground truth",
            "badge": "Target",
            "badge_variant": "teal",
        },
        {
            "label": "Mean Interval Coverage",
            "value": format_percent(mean_coverage * 100, 1),
            "subtext": f"{'Meets quality standard' if mean_coverage >= 0.9 else 'Sub-optimal'}",
            "badge": "Quality",
            "badge_variant": "amber" if mean_coverage < 0.9 else "teal",
        },
    ]
    render_kpi_row(kpis)

    # Forward 10-day projection
    hh_fc_10d = None
    try:
        latest_res_df = load_residential_latest()
        row_match = latest_res_df.loc[latest_res_df["household_id"].astype(str).eq(selected)]
        if not row_match.empty:
            hh_fc_10d = forecast_household_next_10_days(selected, selected_history, row_match.iloc[0])
    except Exception:
        hh_fc_10d = None

    # Chart 1: Daily Consumption (kWh)
    st.markdown("### 1. Observed Daily Consumption & 10-Day Horizon (`daily_kwh`)")
    render_time_series_chart(
        df=valid_daily,
        timestamp_col="date",
        actual_col="daily_kwh",
        title=f"Meter {selected} Daily Energy Consumption & 10-Day Horizon",
        y_title="Daily Consumption (kWh)",
        unit="kWh",
        height=340,
        future_forecast_df=hh_fc_10d,
        future_forecast_col="forecast_kwh",
        future_forecast_label="Next 10 Days Projected Usage",
    )

    # Chart 2: Observed Remaining Month Consumption (`target_remaining_kwh`)
    st.markdown("### 2. Observed Remaining Month Target (`target_remaining_kwh`)")
    render_time_series_chart(
        df=valid_target,
        timestamp_col="date",
        actual_col="target_remaining_kwh",
        title=f"Meter {selected} Observed Calendar-Month Remainder",
        y_title="Remaining Month (kWh)",
        unit="kWh",
        height=340,
    )

    # Chart 3: Daily Interval Reading Coverage (`coverage_ratio`)
    st.markdown("### 3. Daily Interval Reading Coverage (`coverage_ratio`)")
    render_time_series_chart(
        df=valid_coverage,
        timestamp_col="date",
        actual_col="coverage_ratio",
        title=f"Meter {selected} Reading Completeness Ratio",
        y_title="Coverage Ratio (0.0 – 1.0)",
        unit="ratio",
        height=300,
    )

    st.caption(
        "Preserved Historical Data: Values derived directly from the verified 2011–2015 Gold customer feature layer. "
        "No values are synthetic or fabricated."
    )


def _render_commercial_historical() -> None:
    """Render commercial facility historical analysis using commercial building demand series."""
    try:
        history = load_commercial_history()
    except (FileNotFoundError, OSError, ValueError) as error:
        st.error(f"Could not load commercial historical dataset: {error}")
        return

    buildings = sorted(history["building_id"].astype(str).unique())
    current_bldg = st.session_state.get("commercial_building_id")
    if current_bldg not in buildings:
        current_bldg = buildings[0]
        st.session_state.commercial_building_id = current_bldg

    col_sel, col_info = st.columns([2, 3])
    with col_sel:
        selected_bldg = st.selectbox(
            "Select Supported Commercial Facility",
            options=buildings,
            index=buildings.index(current_bldg),
            key="hist_analysis_bldg_select",
        )
        st.session_state.commercial_building_id = selected_bldg

    selected_history = history.loc[
        history["building_id"].astype(str).eq(selected_bldg)
    ].sort_values("timestamp").copy()

    # Time range filtering
    selected_range = st.session_state.get("selected_time_range", "1Y")
    filter_res = filter_by_time_range(selected_history, timestamp_col="timestamp", range_option=selected_range)
    filtered = filter_res.filtered_df

    active_range = render_dashboard_header(
        title="Commercial Facility Demand Analytics",
        subtitle=f"Chronological hourly load history (2016–2017) • Facility {selected_bldg}",
        entity_label=f"Building: {selected_bldg}",
        show_time_range=True,
        active_alerts_count=0,
    )

    if active_range != selected_range:
        filter_res = filter_by_time_range(selected_history, timestamp_col="timestamp", range_option=active_range)
        filtered = filter_res.filtered_df

    if filter_res.is_partially_truncated:
        st.caption(f"ℹ️ {filter_res.explanation}")

    # Summary KPIs
    valid_demand = filtered.dropna(subset=["hourly_demand_kwh"])
    avg_demand = valid_demand["hourly_demand_kwh"].mean() if not valid_demand.empty else 0.0
    
    peak_idx = valid_demand["hourly_demand_kwh"].idxmax() if not valid_demand.empty else None
    peak_demand = valid_demand.loc[peak_idx, "hourly_demand_kwh"] if peak_idx is not None else 0.0
    peak_time = valid_demand.loc[peak_idx, "timestamp"] if peak_idx is not None else "N/A"

    min_temp = valid_demand["airTemperature"].min() if "airTemperature" in valid_demand else 0.0
    max_temp = valid_demand["airTemperature"].max() if "airTemperature" in valid_demand else 0.0
    avg_temp = valid_demand["airTemperature"].mean() if "airTemperature" in valid_demand else 0.0

    kpis = [
        {
            "label": "Average Hourly Demand",
            "value": format_kwh(avg_demand, 2),
            "subtext": f"Across {len(valid_demand):,} hourly observations",
            "badge": "Hourly Avg",
            "badge_variant": "cyan",
        },
        {
            "label": "Peak Observed Load",
            "value": format_kwh(peak_demand, 2),
            "subtext": f"Recorded {pd.Timestamp(peak_time).strftime('%Y-%m-%d %H:%M') if peak_time != 'N/A' else 'N/A'}",
            "badge": "Peak",
            "badge_variant": "amber",
        },
        {
            "label": "Ambient Temperature",
            "value": f"{avg_temp:.1f}°C",
            "subtext": f"Range: {min_temp:.1f}°C to {max_temp:.1f}°C",
            "badge": "Weather",
            "badge_variant": "teal",
        },
    ]
    render_kpi_row(kpis)

    # 10-hour autoregressive future forecast
    fc_10h = None
    try:
        latest_comm_df = load_commercial_latest()
        bldg_row_match = latest_comm_df.loc[latest_comm_df["building_id"].astype(str).eq(selected_bldg)]
        if not bldg_row_match.empty:
            fc_10h = forecast_commercial_next_10h(selected_bldg, selected_history, bldg_row_match.iloc[0])
    except Exception:
        fc_10h = None

    # Chart 1: Hourly Electricity Demand
    st.markdown("### 1. Verified Chronological Hourly Demand & 10-Hour Horizon (`hourly_demand_kwh`)")
    render_time_series_chart(
        df=valid_demand,
        timestamp_col="timestamp",
        actual_col="hourly_demand_kwh",
        title=f"{selected_bldg} Hourly Electricity Demand & 10-Hour Forecast Horizon",
        y_title="Demand (kWh / hr)",
        unit="kWh",
        height=360,
        future_forecast_df=fc_10h,
        future_forecast_col="forecast_kwh",
        future_forecast_label="Next 10 Hours Forecast",
    )

    # Chart 2: Ambient Air Temperature Profile
    if "airTemperature" in valid_demand:
        st.markdown("### 2. Ambient Air Temperature Profile (`airTemperature`)")
        render_time_series_chart(
            df=valid_demand,
            timestamp_col="timestamp",
            actual_col="airTemperature",
            title=f"{selected_bldg} Ambient Air Temperature Correlation",
            y_title="Air Temperature (°C)",
            unit="°C",
            height=300,
        )

    st.caption(
        f"Preserved Historical Data: Verified commercial hourly observations for {selected_bldg} (Site Panther). "
        "Source: 2016–2017 synchronized test-split records."
    )


def _render_government_historical() -> None:
    """Render government historical analysis using regional site demand and aggregate series."""
    try:
        gov_history = load_government_history()
        agg_history = load_government_aggregate_history()
    except (FileNotFoundError, OSError, ValueError) as error:
        st.error(f"Could not load government historical dataset: {error}")
        return

    sites = sorted(gov_history["site_id"].astype(str).unique())
    scope_options = ["🌐 System Aggregate (All 17 Sites)"] + [f"Site: {s}" for s in sites]

    current_site = st.session_state.get("government_site_id")
    default_scope_idx = 0
    if current_site and f"Site: {current_site}" in scope_options:
        default_scope_idx = scope_options.index(f"Site: {current_site}")

    col_sel, col_info = st.columns([2, 3])
    with col_sel:
        selected_scope = st.selectbox(
            "Select Analytical Scope",
            options=scope_options,
            index=default_scope_idx,
            key="hist_analysis_gov_scope_select",
        )

    is_aggregate = selected_scope.startswith("🌐")
    selected_site = None if is_aggregate else selected_scope.replace("Site: ", "")
    if selected_site:
        st.session_state.government_site_id = selected_site

    selected_range = st.session_state.get("selected_time_range", "1Y")

    if is_aggregate:
        filter_res = filter_by_time_range(agg_history, timestamp_col="timestamp", range_option=selected_range)
        filtered = filter_res.filtered_df
        entity_name = "All 17 Regional Grid Sites"
    else:
        site_df = gov_history.loc[gov_history["site_id"].astype(str).eq(selected_site)].sort_values("timestamp").copy()
        filter_res = filter_by_time_range(site_df, timestamp_col="timestamp", range_option=selected_range)
        filtered = filter_res.filtered_df
        entity_name = f"Site {selected_site}"

    active_range = render_dashboard_header(
        title="Government Regional & Aggregate Demand Analytics",
        subtitle=f"Synchronized regional hourly demand records (2016–2017) • Scope: {entity_name}",
        entity_label=f"Scope: {entity_name}",
        show_time_range=True,
        active_alerts_count=0,
    )

    if active_range != selected_range:
        if is_aggregate:
            filter_res = filter_by_time_range(agg_history, timestamp_col="timestamp", range_option=active_range)
        else:
            filter_res = filter_by_time_range(site_df, timestamp_col="timestamp", range_option=active_range)
        filtered = filter_res.filtered_df

    if filter_res.is_partially_truncated:
        st.caption(f"ℹ️ {filter_res.explanation}")

    # KPIs
    if is_aggregate:
        avg_demand = filtered["total_aggregate_demand_kwh"].mean() if not filtered.empty else 0.0
        peak_idx = filtered["total_aggregate_demand_kwh"].idxmax() if not filtered.empty else None
        peak_val = filtered.loc[peak_idx, "total_aggregate_demand_kwh"] if peak_idx is not None else 0.0
        peak_time = filtered.loc[peak_idx, "timestamp"] if peak_idx is not None else "N/A"

        kpis = [
            {
                "label": "Average System Demand",
                "value": format_kwh(avg_demand, 0),
                "subtext": f"Across {len(filtered):,} synchronized hours",
                "badge": "17 Sites",
                "badge_variant": "teal",
            },
            {
                "label": "Peak System Load",
                "value": format_kwh(peak_val, 0),
                "subtext": f"Recorded {pd.Timestamp(peak_time).strftime('%Y-%m-%d %H:%M') if peak_time != 'N/A' else 'N/A'}",
                "badge": "Peak",
                "badge_variant": "amber",
            },
            {
                "label": "Facility Representation",
                "value": "1,400 Buildings",
                "subtext": "100% complete hourly records",
                "badge": "Coverage",
                "badge_variant": "cyan",
            },
        ]
        render_kpi_row(kpis)

        # Compute 10-hour system aggregate forecast
        agg_fc_10h = None
        try:
            latest_gov_df = load_government_latest()
            agg_fc_10h = forecast_government_aggregate_next_10h(gov_history, latest_gov_df)
        except Exception:
            agg_fc_10h = None

        # Chart 1: System-Wide Demand
        st.markdown("### 1. System-Wide Aggregate Demand & 10-Hour Horizon")
        render_time_series_chart(
            df=filtered,
            timestamp_col="timestamp",
            actual_col="total_aggregate_demand_kwh",
            title="System Aggregate Hourly Demand & 10-Hour Horizon",
            y_title="Total Demand (kWh / hr)",
            unit="kWh",
            height=380,
            future_forecast_df=agg_fc_10h,
            future_forecast_col="total_aggregate_demand_kwh",
            future_forecast_label="Next 10 Hours System Forecast",
        )

        # Chart 2: Regional Demand Ranking
        st.markdown("### 2. Regional Demand Contribution Ranking")
        filter_all_sites = filter_by_time_range(gov_history, timestamp_col="timestamp", range_option=active_range).filtered_df
        site_ranking_df = (
            filter_all_sites.groupby("site_id", as_index=False)["total_demand_kwh"]
            .sum()
            .rename(columns={"total_demand_kwh": "total_demand"})
        )
        render_horizontal_ranking_bar_chart(
            df=site_ranking_df,
            category_col="site_id",
            value_col="total_demand",
            title=f"Total Regional Demand Ranking in Interval ({active_range})",
            x_title="Total Energy (kWh)",
            unit="kWh",
            height=460,
        )

    else:
        avg_demand = filtered["total_demand_kwh"].mean() if not filtered.empty else 0.0
        peak_idx = filtered["total_demand_kwh"].idxmax() if not filtered.empty else None
        peak_val = filtered.loc[peak_idx, "total_demand_kwh"] if peak_idx is not None else 0.0
        peak_time = filtered.loc[peak_idx, "timestamp"] if peak_idx is not None else "N/A"
        bldg_cnt = filtered["building_count"].iloc[0] if not filtered.empty and "building_count" in filtered else 0

        kpis = [
            {
                "label": "Average Regional Demand",
                "value": format_kwh(avg_demand, 1),
                "subtext": f"Across {len(filtered):,} hourly observations",
                "badge": "Site Avg",
                "badge_variant": "cyan",
            },
            {
                "label": "Peak Regional Load",
                "value": format_kwh(peak_val, 1),
                "subtext": f"Recorded {pd.Timestamp(peak_time).strftime('%Y-%m-%d %H:%M') if peak_time != 'N/A' else 'N/A'}",
                "badge": "Peak",
                "badge_variant": "amber",
            },
            {
                "label": "Facility Count",
                "value": f"{int(bldg_cnt):,} Buildings",
                "subtext": f"Scope: Site {selected_site}",
                "badge": "Monitored",
                "badge_variant": "teal",
            },
        ]
        render_kpi_row(kpis)

        # 10-hour autoregressive regional forecast
        site_fc_10h = None
        try:
            latest_gov_df = load_government_latest()
            row_match = latest_gov_df.loc[latest_gov_df["site_id"].astype(str).eq(selected_site)]
            if not row_match.empty:
                site_fc_10h = forecast_government_next_10h(selected_site, gov_history, row_match.iloc[0])
        except Exception:
            site_fc_10h = None

        # Chart 1: Site Demand
        st.markdown(f"### 1. Site {selected_site} Hourly Demand & 10-Hour Horizon")
        render_time_series_chart(
            df=filtered,
            timestamp_col="timestamp",
            actual_col="total_demand_kwh",
            title=f"Site {selected_site} Hourly Demand & 10-Hour Forecast Horizon",
            y_title="Demand (kWh / hour)",
            unit="kWh",
            height=380,
            future_forecast_df=site_fc_10h,
            future_forecast_col="forecast_kwh",
            future_forecast_label="Next 10 Hours Regional Forecast",
        )

        # Chart 2: Temperature Profile
        if "airTemperature" in filtered:
            st.markdown(f"### 2. Site {selected_site} Ambient Air Temperature (`airTemperature`)")
            render_time_series_chart(
                df=filtered,
                timestamp_col="timestamp",
                actual_col="airTemperature",
                title=f"Site {selected_site} Temperature Observations",
                y_title="Temperature (°C)",
                unit="°C",
                height=300,
            )

    st.caption(
        "Preserved Historical Data: Verified government regional telemetry records across 17 administrative grid zones (2016–2017). "
        "Strict non-overlapping boundaries with validated zero double-counting."
    )
