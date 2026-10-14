"""Reusable Plotly visualizations adhering strictly to GridVision visual identity (Light Mode)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dashboard.utils.theme import (
    COLOR_ELECTRIC_CYAN,
    COLOR_ENERGY_AMBER,
    COLOR_GRID_BLUE,
    COLOR_MIDNIGHT_NAVY,
    COLOR_PURE_WHITE,
    COLOR_SMART_TEAL,
)


def _base_chart_layout(
    title: str,
    x_title: str = "Date / Time",
    y_title: str = "Demand (kWh)",
    height: int = 420,
) -> dict[str, Any]:
    """Create standardized clean light-mode Plotly layout."""
    return {
        "title": {
            "text": f"<b>{title}</b>",
            "font": {"size": 15, "color": COLOR_MIDNIGHT_NAVY, "family": "Plus Jakarta Sans, sans-serif"},
            "x": 0.01,
            "xanchor": "left",
        },
        "paper_bgcolor": "#FFFFFF",
        "plot_bgcolor": "rgba(11, 31, 51, 0.01)",
        "font": {"color": "rgba(11, 31, 51, 0.7)", "family": "Plus Jakarta Sans, sans-serif", "size": 12},
        "margin": {"l": 55, "r": 25, "t": 55, "b": 45},
        "height": height,
        "xaxis": {
            "title": {"text": x_title, "font": {"size": 12, "color": COLOR_MIDNIGHT_NAVY}},
            "gridcolor": "rgba(11, 31, 51, 0.08)",
            "zerolinecolor": "rgba(11, 31, 51, 0.12)",
            "showgrid": True,
            "tickfont": {"size": 11, "color": "rgba(11, 31, 51, 0.7)"},
        },
        "yaxis": {
            "title": {"text": y_title, "font": {"size": 12, "color": COLOR_MIDNIGHT_NAVY}},
            "gridcolor": "rgba(11, 31, 51, 0.08)",
            "zerolinecolor": "rgba(11, 31, 51, 0.12)",
            "showgrid": True,
            "tickfont": {"size": 11, "color": "rgba(11, 31, 51, 0.7)"},
        },
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1.0,
            "font": {"size": 11, "color": COLOR_MIDNIGHT_NAVY},
        },
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": COLOR_MIDNIGHT_NAVY,
            "bordercolor": COLOR_SMART_TEAL,
            "font": {"size": 12, "color": COLOR_PURE_WHITE},
        },
    }


def render_time_series_chart(
    df: pd.DataFrame,
    timestamp_col: str,
    actual_col: str,
    predicted_col: str | None = None,
    title: str = "Energy Demand Over Time",
    y_title: str = "Consumption (kWh)",
    unit: str = "kWh",
    height: int = 420,
    forecast_marker_timestamp: Any | None = None,
    forecast_marker_value: float | None = None,
    forecast_marker_label: str = "Model Forecast",
    future_forecast_df: pd.DataFrame | None = None,
    future_forecast_col: str = "forecast_kwh",
    future_forecast_label: str = "Next 10 Hours Forecast",
) -> None:
    """Render an interactive Plotly chronological demand chart (Light Mode) with forward horizon support."""
    if df.empty:
        st.info("No observations available for the selected interval.")
        return

    df_sorted = df.sort_values(timestamp_col).copy()
    fig = go.Figure()

    # Actual Observations Series (Grid Blue for crisp readability on white)
    fig.add_trace(
        go.Scatter(
            x=df_sorted[timestamp_col],
            y=df_sorted[actual_col],
            mode="lines",
            name="Actual Observation",
            line={"color": COLOR_GRID_BLUE, "width": 2},
            hovertemplate=f"Actual: <b>%{{y:,.2f}} {unit}</b><extra></extra>",
        )
    )

    # Optional continuous predicted series
    if predicted_col and predicted_col in df_sorted.columns:
        fig.add_trace(
            go.Scatter(
                x=df_sorted[timestamp_col],
                y=df_sorted[predicted_col],
                mode="lines",
                name="Historical Model Replay",
                line={"color": "rgba(8, 126, 189, 0.5)", "width": 1.5, "dash": "dot"},
                hovertemplate=f"Replay: <b>%{{y:,.2f}} {unit}</b><extra></extra>",
            )
        )

    # Future multi-step forecast series (e.g. Next 10 Hours)
    if future_forecast_df is not None and not future_forecast_df.empty:
        fc_sorted = future_forecast_df.sort_values(timestamp_col).copy()
        last_actual_ts = df_sorted[timestamp_col].iloc[-1]
        last_actual_val = df_sorted[actual_col].iloc[-1]

        # Connect future line smoothly from last observed timestamp
        fc_x = [last_actual_ts] + list(fc_sorted[timestamp_col])
        fc_y = [last_actual_val] + list(fc_sorted[future_forecast_col])

        fig.add_trace(
            go.Scatter(
                x=fc_x,
                y=fc_y,
                mode="lines+markers",
                name=f"🔮 {future_forecast_label}",
                line={"color": COLOR_ENERGY_AMBER, "width": 2.5, "dash": "dash"},
                marker={
                    "size": 6,
                    "color": COLOR_ENERGY_AMBER,
                    "line": {"color": COLOR_MIDNIGHT_NAVY, "width": 1},
                },
                hovertemplate=f"{future_forecast_label}: <b>%{{y:,.2f}} {unit}</b><extra></extra>",
            )
        )

        # Vertical demarcation line marking "Current Time" (boundary between history and future)
        fig.add_vline(
            x=last_actual_ts,
            line_width=1.5,
            line_dash="dot",
            line_color="rgba(11, 31, 51, 0.4)",
        )
        fig.add_annotation(
            x=last_actual_ts,
            y=1,
            yref="paper",
            text="Current Time (Forecast Horizon Start)",
            showarrow=False,
            xanchor="right",
            yanchor="top",
            font={"size": 10, "color": COLOR_MIDNIGHT_NAVY},
            bgcolor="rgba(255, 255, 255, 0.8)",
            bordercolor="rgba(11, 31, 51, 0.2)",
            borderwidth=1,
        )

    # Forecast Marker Point (for horizon / point forecast)
    if forecast_marker_timestamp is not None and forecast_marker_value is not None:
        fig.add_trace(
            go.Scatter(
                x=[forecast_marker_timestamp],
                y=[forecast_marker_value],
                mode="markers+text",
                name=forecast_marker_label,
                marker={
                    "color": COLOR_ENERGY_AMBER,
                    "size": 10,
                    "symbol": "diamond",
                    "line": {"color": COLOR_MIDNIGHT_NAVY, "width": 1},
                },
                text=[f" {forecast_marker_label}: {forecast_marker_value:,.2f} {unit}"],
                textposition="top right",
                textfont={"color": COLOR_MIDNIGHT_NAVY, "size": 11},
                hovertemplate=f"{forecast_marker_label}: <b>%{{y:,.2f}} {unit}</b><extra></extra>",
            )
        )

    layout = _base_chart_layout(title=title, y_title=y_title, height=height)
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_comparison_bar_chart(
    categories: list[str],
    values: list[float | None],
    title: str = "Comparison",
    y_title: str = "Consumption (kWh)",
    unit: str = "kWh",
    height: int = 340,
) -> None:
    """Render comparison bar chart with custom brand palette colors and data labels."""
    colors = [COLOR_GRID_BLUE, COLOR_ENERGY_AMBER, COLOR_SMART_TEAL, COLOR_ELECTRIC_CYAN]
    bar_colors = [colors[i % len(colors)] for i in range(len(categories))]

    clean_cats = []
    clean_vals = []
    for cat, val in zip(categories, values, strict=False):
        if val is not None:
            clean_cats.append(cat)
            clean_vals.append(val)

    fig = go.Figure(
        data=[
            go.Bar(
                x=clean_cats,
                y=clean_vals,
                marker={"color": bar_colors[:len(clean_cats)], "line": {"color": "rgba(11, 31, 51, 0.15)", "width": 1}},
                text=[f"{v:,.1f} {unit}" for v in clean_vals],
                textposition="auto",
                textfont={"color": COLOR_MIDNIGHT_NAVY, "size": 11},
                hovertemplate=f"<b>%{{x}}</b><br>Value: %{{y:,.2f}} {unit}<extra></extra>",
            )
        ]
    )

    layout = _base_chart_layout(title=title, x_title="", y_title=y_title, height=height)
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_horizontal_ranking_bar_chart(
    df: pd.DataFrame,
    category_col: str,
    value_col: str,
    title: str = "Regional Demand Comparison",
    x_title: str = "Total Observed Demand (kWh)",
    unit: str = "kWh",
    height: int = 440,
) -> None:
    """Render a ranked horizontal bar chart for regional demand comparison (Light Mode)."""
    if df.empty:
        st.info("No regional data available for ranking in this interval.")
        return

    df_sorted = df.sort_values(value_col, ascending=True).copy()

    fig = go.Figure(
        data=[
            go.Bar(
                y=df_sorted[category_col].astype(str),
                x=df_sorted[value_col],
                orientation="h",
                marker={
                    "color": COLOR_SMART_TEAL,
                    "line": {"color": COLOR_GRID_BLUE, "width": 1},
                },
                text=[f" {v:,.0f} {unit}" for v in df_sorted[value_col]],
                textposition="auto",
                textfont={"color": COLOR_MIDNIGHT_NAVY, "size": 11},
                hovertemplate=f"<b>%{{y}}</b><br>{x_title}: <b>%{{x:,.0f}} {unit}</b><extra></extra>",
            )
        ]
    )

    layout = _base_chart_layout(title=title, x_title=x_title, y_title="Region / Site", height=height)
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)
