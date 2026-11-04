"""Small deterministic groundedness and citation checks for assistant outputs."""

from __future__ import annotations

from typing import Any


def evaluate_grounding(
    answer: str, references: list[dict[str, Any]]
) -> dict[str, Any]:
    citations = [item.get("citation", {}) for item in references]
    cited_titles = {
        str(item.get("title", "")).casefold()
        for item in citations
        if item.get("title")
    }
    answer_lower = answer.casefold()
    matched = [title for title in cited_titles if title and title in answer_lower]
    return {
        "citation_count": len(citations),
        "cited_titles": matched,
        "citation_coverage": len(matched) / len(cited_titles) if cited_titles else 0.0,
        "has_references": bool(citations),
    }

