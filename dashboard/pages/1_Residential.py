"""Residential historical month-end prediction replay."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.utils.data import (
    get_api_client,
    load_model_metadata,
    load_residential_latest,
)

st.title("Residential month-end estimate")
st.info(
    "Historical replay only: the available residential data ends in 2015. "
    "The displayed bill uses the prototype flat tariff of ₹10/kWh."
)

try:
    data = load_residential_latest()
except (FileNotFoundError, OSError, ValueError) as error:
    st.error(str(error))
    st.stop()

if data.empty:
    st.error("No prediction-eligible household rows were generated.")
    st.stop()

households = sorted(data["household_id"].astype(str).unique())
selected = st.selectbox("Household / meter", households)
row = data.loc[data["household_id"].astype(str).eq(selected)].iloc[0]
metadata = load_model_metadata("residential")
feature_names = metadata["features"]
payload = {
    "entity_id": selected,
    "forecast_timestamp": pd.Timestamp(row["date"]).isoformat(),
    "features": {name: row[name] for name in feature_names},
    "context": "retrospective_gold_replay",
    "actual_kwh_so_far": float(row["actual_cycle_kwh_so_far"]),
}

try:
    result = get_api_client().predict("residential", payload)
except APIClientError as error:
    st.error(str(error))
    st.stop()

first, second, third, fourth = st.columns(4)
first.metric("Actual month-to-date", f"{result['actual_kwh_so_far']:,.1f} kWh")
second.metric("Raw model remaining output", f"{result['prediction']:,.1f} kWh")
third.metric(
    "Observed month-end remainder",
    f"{float(row['target_remaining_kwh']):,.1f} kWh",
)
fourth.metric(
    "Estimated month-end bill",
    (
        f"₹{result['estimated_month_end_bill_inr']:,.0f}"
        if result["estimated_month_end_bill_inr"] is not None
        else "Unavailable"
    ),
)
month_end_usage = (
    f"{result['estimated_month_end_kwh']:,.1f} kWh"
    if result["estimated_month_end_kwh"] is not None
    else "unavailable (invalid model output)"
)
st.caption(
    f"Forecast origin: {result['forecast_timestamp']} | "
    f"Estimated month-end usage: {month_end_usage} | "
    f"Coverage: {result['data_quality_status']} | "
    f"Model: {result['model_version']}"
)

chart_data = pd.DataFrame(
    {
        "Period": [
            "Actual through forecast origin",
            "Raw model remaining output",
            "Observed remaining (retrospective)",
        ],
        "Consumption (kWh)": [
            result["actual_kwh_so_far"],
            result["prediction"],
            float(row["target_remaining_kwh"]),
        ],
    }
)
st.plotly_chart(
    px.bar(chart_data, x="Period", y="Consumption (kWh)", title="Month-end estimate"),
    use_container_width=True,
)
for caveat in result["caveats"]:
    st.warning(caveat)
if result["prediction_status"] != "valid":
    st.error(
        "This model output is physically invalid and must not be interpreted as a "
        "remaining-consumption forecast."
    )
st.caption(
    "Model evaluation: "
    f"{result['evaluation_status']}. The notebook's reported test metrics were "
    "worse than its recent-rate baseline; use the estimate as a prototype only."
)
