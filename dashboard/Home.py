"""GridVision Streamlit dashboard landing page."""

import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.utils.data import get_api_client

st.set_page_config(page_title="GridVision", page_icon="⚡", layout="wide")
st.title("GridVision")
st.subheader("Energy-demand model demonstrations")
st.write(
    "Explore Residential month-end consumption estimates and Commercial and "
    "Government hourly-demand model replays."
)

try:
    readiness = get_api_client().health()
    if readiness.get("status") == "ready":
        st.success(f"Prediction API ready: {', '.join(readiness['models_loaded'])}")
    else:
        st.warning(f"Prediction API is not ready: {readiness}")
except APIClientError as error:
    st.error(str(error))

st.warning(
    "The supplied model reports are not independently approved. Commercial and "
    "Government pages replay historical test-split rows; Residential uses the "
    "latest eligible row in a dataset ending in 2015. These are not live forecasts."
)

left, middle, right = st.columns(3)
left.metric("Residential", "Month-end estimate", help="Prototype flat ₹10/kWh tariff")
middle.metric("Commercial", "Hourly demand", help="Historical test-split replay")
right.metric(
    "Government", "Hourly regional demand", help="Historical test-split replay"
)
st.caption(
    "Start the FastAPI service and prepare the data snapshots before using the "
    "prediction pages. See README.md for commands."
)
