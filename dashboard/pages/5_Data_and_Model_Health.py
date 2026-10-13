"""Dataset lineage, model artifacts, and API readiness."""

from __future__ import annotations

import json

import streamlit as st
from dashboard.clients.errors import APIClientError
from dashboard.utils.config import PROJECT_ROOT
from dashboard.utils.data import get_api_client, load_model_metadata

st.title("Data and model health")

try:
    readiness = get_api_client().health()
    if readiness.get("status") == "ready":
        st.success(f"API ready: {', '.join(readiness['models_loaded'])}")
    else:
        st.error(f"API not ready: {readiness}")
except APIClientError as error:
    st.error(str(error))

profile_path = (
    PROJECT_ROOT / "data" / "reports" / "data_profile" / "customer_profile.json"
)
if profile_path.is_file():
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    quality = profile["reading_quality"]
    first, second, third = st.columns(3)
    first.metric("Customer meters", f"{profile['household_count']:,}")
    second.metric("Silver interval rows", f"{profile['interval_reading_count']:,}")
    third.metric("Gold customer-days", f"{profile['gold']['row_count']:,}")
    st.caption(
        f"Source range: {profile['date_range']['start']} — "
        f"{profile['date_range']['end']} | "
        f"Missing readings: {quality['missing']:,} | "
        f"Zero readings retained: {quality['zero']:,}"
    )
else:
    st.warning("Customer data-profile report is missing; run data preparation.")

for name in ("residential", "commercial", "government"):
    metadata = load_model_metadata(name)
    metrics_path = (
        PROJECT_ROOT / "artifacts" / "models" / name / str(metadata["metrics_report"])
    )
    metrics = (
        json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics_path.is_file()
        else {"status": "missing"}
    )
    with st.expander(name.title(), expanded=False):
        st.write(f"**Model version:** {metadata['model_version']}")
        st.write(f"**Artifact SHA-256:** `{metadata['sha256']}`")
        st.write(f"**Evaluation status:** {metrics.get('status', 'unknown')}")
        st.write(f"**Target:** {metadata['target_name']} ({metadata['target_units']})")
        st.write(f"**Feature count:** {len(metadata['features'])}")
        st.json(metrics)
