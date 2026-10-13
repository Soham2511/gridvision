"""Government regional hourly-demand replay."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.utils.data import (
    get_api_client,
    load_government_latest,
    load_model_metadata,
)

st.title("Government regional demand")
st.info(
    "Retrospective test-split replay from the supplied Government Gold dataset. "
    "This model does not generate redistribution recommendations."
)

try:
    data = load_government_latest()
except (FileNotFoundError, OSError, ValueError) as error:
    st.error(str(error))
    st.stop()

if data.empty:
    st.error("No Government test rows are available.")
    st.stop()

site_ids = sorted(data["site_id"].astype(str).unique())
selected = st.selectbox("Region / site", site_ids)
row = data.loc[data["site_id"].astype(str).eq(selected)].iloc[0]
metadata = load_model_metadata("government")
feature_names = list(metadata["features"])
payload = {
    "entity_id": selected,
    "forecast_timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
    "features": {name: row[name] for name in feature_names},
    "context": "retrospective_gold_replay",
}

try:
    result = get_api_client().predict("government", payload)
except APIClientError as error:
    st.error(str(error))
    st.stop()

actual = float(row[metadata["target_name"]])
first, second, third = st.columns(3)
first.metric("Actual demand", f"{actual:,.2f} kWh")
second.metric("Model prediction", f"{result['prediction']:,.2f} kWh")
third.metric("Absolute replay error", f"{abs(actual - result['prediction']):,.2f} kWh")
st.caption(
    f"Site: {selected} | Timestamp: {result['forecast_timestamp']} | "
    f"Model: {result['model_version']} | "
    f"Data: {result['data_quality_status']}"
)
comparison = pd.DataFrame(
    {
        "Series": ["Actual test-split value", "Model prediction"],
        "Hourly demand (kWh)": [actual, result["prediction"]],
    }
)
st.plotly_chart(
    px.bar(comparison, x="Series", y="Hourly demand (kWh)"),
    use_container_width=True,
)
if result["prediction_status"] != "valid":
    st.error("The model returned a physically invalid negative energy output.")
for caveat in result["caveats"]:
    st.warning(caveat)
st.caption(
    f"Evaluation report status: {result['evaluation_status']}. "
    "A single historical replay is not a model evaluation report."
)
