"""Cached access to compact dashboard-specific Parquet inputs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from dashboard.clients.api_client import APIClient
from dashboard.utils.config import API_BASE_URL, PROJECT_ROOT


@st.cache_resource
def get_api_client() -> APIClient:
    """Create one reusable API client for the Streamlit process."""
    return APIClient(API_BASE_URL)


@st.cache_data
def load_model_metadata(name: str) -> dict[str, object]:
    """Read a local model contract for building requests, not model execution."""
    if name not in {"residential", "commercial", "government"}:
        raise ValueError(f"Unsupported model name: {name}")
    path = PROJECT_ROOT / "artifacts" / "models" / name / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data
def _read_parquet(path: str) -> pd.DataFrame:
    parquet_path = Path(path)
    if not parquet_path.is_file():
        raise FileNotFoundError(
            f"Dashboard data file is missing: {parquet_path}. "
            "Run the data-preparation commands in the README."
        )
    return pd.read_parquet(parquet_path)


def load_residential_latest() -> pd.DataFrame:
    """Load one latest eligible Gold input per household."""
    return _read_parquet(
        str(PROJECT_ROOT / "data" / "gold" / "customer_latest_features.parquet")
    )


@st.cache_data
def load_residential_history() -> pd.DataFrame:
    """Read only compact columns needed for household usage history."""
    path = PROJECT_ROOT / "data" / "gold" / "customer_daily_features.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"Dashboard data file is missing: {path}. Run data preparation first."
        )
    return pd.read_parquet(
        path,
        columns=[
            "household_id",
            "date",
            "daily_kwh",
            "coverage_ratio",
            "target_remaining_kwh",
        ],
    )


def load_commercial_latest() -> pd.DataFrame:
    """Load latest test-split rows for categories supported by the model."""
    return _read_parquet(
        str(
            PROJECT_ROOT
            / "data"
            / "gold"
            / "dashboard"
            / "commercial_latest_test.parquet"
        )
    )


def load_government_latest() -> pd.DataFrame:
    """Load one latest test-split row per Government site."""
    return _read_parquet(
        str(
            PROJECT_ROOT
            / "data"
            / "gold"
            / "dashboard"
            / "government_latest_test.parquet"
        )
    )
