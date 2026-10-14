"""Reusable minimalist metric cards matching GridVision visual design."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_kpi_card(
    label: str,
    value: str,
    subtext: str | None = None,
    delta: str | None = None,
    delta_positive: bool = True,
    badge: str | None = None,
    badge_variant: str = "cyan",
    help_text: str | None = None,
) -> None:
    """Render a single compact, polished KPI card using HTML/CSS."""
    delta_html = ""
    if delta:
        delta_class = "gv-delta-pos" if delta_positive else "gv-delta-neg"
        delta_html = f'<span class="{delta_class}">{delta}</span>'

    badge_html = ""
    if badge:
        badge_html = f'<span class="gv-badge gv-badge-{badge_variant}">{badge}</span>'

    subtext_html = ""
    if subtext or delta_html:
        subtext_html = (
            f'<div class="gv-kpi-subtext" style="display:flex; justify-content:space-between; align-items:center;">'
            f'<span>{subtext or ""}</span>'
            f'{delta_html}'
            f'</div>'
        )

    title_attr = f' title="{help_text}"' if help_text else ""
    card_html = (
        f'<div class="gv-kpi-card"{title_attr}>'
        f'<div class="gv-kpi-label"><span>{label}</span>{badge_html}</div>'
        f'<div class="gv-kpi-value">{value}</div>'
        f'{subtext_html}'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def render_kpi_row(cards_data: list[dict[str, Any]]) -> None:
    """Render a horizontal row of balanced KPI cards."""
    cols = st.columns(len(cards_data))
    for col, card in zip(cols, cards_data, strict=True):
        with col:
            render_kpi_card(
                label=card["label"],
                value=card["value"],
                subtext=card.get("subtext"),
                delta=card.get("delta"),
                delta_positive=card.get("delta_positive", True),
                badge=card.get("badge"),
                badge_variant=card.get("badge_variant", "cyan"),
                help_text=card.get("help_text"),
            )
