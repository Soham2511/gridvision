"""Evidence-grounded, non-diagnostic anomaly recommendations."""

from __future__ import annotations

from typing import Any


RECOMMENDATION_SYSTEM_PROMPT = """You are GridVision's evidence-grounded anomaly advisor.
Distinguish observed measurements from probable causes; never label a probable cause
as a confirmed fault. Use only supplied GridVision results and cited reference excerpts.
State missing evidence and limitations. Address spike, drop, zero_block, and flatline
when they occur in the supplied results. Do not instruct residential users to perform
electrical work; advise contacting a qualified utility or licensed professional instead.
Return observed problem, probable cause (or unknown), recommended investigation,
possible corrective/mitigation measures, priority, responsible party, supporting
citations with page numbers, confidence, and limitations."""


def recommendation_context(
    results: dict[str, Any], references: list[dict[str, Any]]
) -> dict[str, Any]:
    """Prepare a bounded, citation-rich payload for the local language model."""
    events = results.get("items") or results.get("events") or []
    return {
        "events": events[:20],
        "references": [
            {
                "text": item.get("text", "")[:1800],
                "citation": item.get("citation", {}),
            }
            for item in references[:5]
        ],
    }

