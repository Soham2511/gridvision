"""Presentation formatting helpers for values, units, currency, and timestamps."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def format_kwh(value: float | int | None, decimals: int = 1) -> str:
    """Format energy values in kWh with thousand separators."""
    if value is None:
        return "N/A"
    try:
        num = float(value)
        return f"{num:,.{decimals}f} kWh"
    except (ValueError, TypeError):
        return "N/A"


def format_inr(value: float | int | None, decimals: int = 0) -> str:
    """Format currency values in INR (₹) with thousand separators."""
    if value is None:
        return "N/A"
    try:
        num = float(value)
        if decimals == 0:
            return f"₹{num:,.0f}"
        return f"₹{num:,.{decimals}f}"
    except (ValueError, TypeError):
        return "N/A"


def format_percent(value: float | int | None, decimals: int = 1, show_plus: bool = True) -> str:
    """Format percentage with optional plus sign for positive values."""
    if value is None:
        return "N/A"
    try:
        num = float(value)
        plus = "+" if show_plus and num > 0 else ""
        return f"{plus}{num:.{decimals}f}%"
    except (ValueError, TypeError):
        return "N/A"


def format_timestamp(value: Any, format_str: str = "%Y-%m-%d %H:%M") -> str:
    """Format timestamp into human-readable string."""
    if value is None:
        return "N/A"
    if isinstance(value, datetime):
        return value.strftime(format_str)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime(format_str)
    except Exception:
        return str(value)
