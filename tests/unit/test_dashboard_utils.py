"""Unit tests for formatting, config, and data loaders."""

from __future__ import annotations

from dashboard.utils.formatting import (
    format_inr,
    format_kwh,
    format_percent,
)


def test_formatting_kwh() -> None:
    assert format_kwh(1234.567, 1) == "1,234.6 kWh"
    assert format_kwh(None) == "N/A"


def test_formatting_inr() -> None:
    assert format_inr(2500) == "₹2,500"
    assert format_inr(None) == "N/A"


def test_formatting_percent() -> None:
    assert format_percent(15.23, 1, show_plus=True) == "+15.2%"
    assert format_percent(-5.4, 1, show_plus=True) == "-5.4%"
    assert format_percent(None) == "N/A"


def test_brand_palette_enforcement() -> None:
    from dashboard.utils.theme import (
        COLOR_DANGER,
        COLOR_ELECTRIC_CYAN,
        COLOR_ENERGY_AMBER,
        COLOR_GRID_BLUE,
        COLOR_MIDNIGHT_NAVY,
        COLOR_PURE_WHITE,
        COLOR_SMART_TEAL,
    )

    approved = {
        COLOR_MIDNIGHT_NAVY: "#0B1F33",
        COLOR_SMART_TEAL: "#00B8A9",
        COLOR_ELECTRIC_CYAN: "#21C7D9",
        COLOR_GRID_BLUE: "#087EBD",
        COLOR_ENERGY_AMBER: "#FFC247",
        COLOR_PURE_WHITE: "#FFFFFF",
    }
    for col, expected in approved.items():
        assert col.upper() == expected

    # Strict status mapping: COLOR_DANGER must be Energy Amber (no unauthorized reds)
    assert COLOR_DANGER == "#FFC247"

