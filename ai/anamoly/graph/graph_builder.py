"""Derive entity-to-document edges from indexed source metadata."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

ENTITY_TERMS = {
    "anomaly_type": ("spike", "drop", "zero_block", "flatline", "voltage sag"),
    "safety_topic": ("electrical safety", "fire", "arc flash", "lockout", "lithium-ion"),
    "grid_topic": ("outage", "distribution", "transmission", "transformer", "substation"),
}


def build_document_graph(documents: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build a compact graph whose edges link recognized terms to source documents."""
    graph: dict[str, set[str]] = defaultdict(set)
    for document in documents:
        doc_id = str(document.get("document_id", ""))
        text = f"{document.get('title', '')} {document.get('text', '')}".lower()
        if not doc_id:
            continue
        for kind, terms in ENTITY_TERMS.items():
            for term in terms:
                if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text):
                    graph[f"{kind}:{term}"].add(doc_id)
    return {node: sorted(doc_ids) for node, doc_ids in graph.items()}

