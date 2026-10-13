"""Validated configuration shared by the Streamlit pages."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_BASE_URL = os.environ.get("GRIDVISION_API_URL", "http://127.0.0.1:8000").strip()
if not API_BASE_URL.startswith(("http://", "https://")):
    raise ValueError("GRIDVISION_API_URL must use http:// or https://.")
