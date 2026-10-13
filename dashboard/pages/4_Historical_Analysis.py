"""Residential daily history from the generated Gold feature layer."""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from dashboard.utils.data import load_residential_history

st.title("Historical analysis")
st.caption(
    "Residential readings and month-end target values from the 2011-2015 Gold "
    "dataset. This history is not live data."
)

try:
    history = load_residential_history()
except (FileNotFoundError, OSError, ValueError) as error:
    st.error(str(error))
    st.stop()

households = sorted(history["household_id"].astype(str).unique())
selected = st.selectbox("Household / meter", households)
selected_history = history.loc[
    history["household_id"].astype(str).eq(selected)
].sort_values("date")
daily_history = selected_history.dropna(subset=["daily_kwh"])
target_history = selected_history.dropna(subset=["target_remaining_kwh"])
st.plotly_chart(
    px.line(
        daily_history,
        x="date",
        y="daily_kwh",
        title="Daily consumption (kWh)",
    ),
    use_container_width=True,
)
st.plotly_chart(
    px.line(
        target_history,
        x="date",
        y="target_remaining_kwh",
        title="Observed remaining month consumption (kWh)",
    ),
    use_container_width=True,
)
st.plotly_chart(
    px.line(
        selected_history.dropna(subset=["coverage_ratio"]),
        x="date",
        y="coverage_ratio",
        title="Daily interval coverage",
    ),
    use_container_width=True,
)
