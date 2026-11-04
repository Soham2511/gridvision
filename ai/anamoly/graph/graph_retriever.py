"""Retrieve graph-related documents by extracted technical entities."""

from __future__ import annotations

import re
from typing import Any

from ai.anamoly.graph.graph_builder import ENTITY_TERMS
from ai.anamoly.vector_store.retriever import KnowledgeRetriever


class GraphRetriever:
    """Use vector hits as anchors, then expand through shared graph entities."""

    def __init__(self, vector_retriever: KnowledgeRetriever | None = None) -> None:
        self.vector_retriever = vector_retriever or KnowledgeRetriever()

    @staticmethod
    def _entities(text: str) -> set[str]:
        normalized = text.lower()
        return {
            f"{kind}:{term}"
            for kind, terms in ENTITY_TERMS.items()
            for term in terms
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized)
        }

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        anchors = self.vector_retriever.search(query, limit=limit)
        related_entities: set[str] = set()
        for hit in anchors:
            title = hit["metadata"].get("title", "")
            overlap = self._entities(f"{title} {hit['text']}") & self._entities(query)
            if overlap:
                hit["graph_entities"] = sorted(overlap)
            related_entities.update(self._entities(f"{title} {hit['text']}"))

        related: list[dict[str, Any]] = []
        seen = {hit["id"] for hit in anchors}
        for entity in sorted(related_entities):
            term = entity.split(":", 1)[1]
            for hit in self.vector_retriever.search(term, limit=limit):
                if hit["id"] in seen:
                    continue
                title = hit["metadata"].get("title", "")
                overlap = self._entities(f"{title} {hit['text']}") & related_entities
                if overlap:
                    hit["graph_entities"] = sorted(overlap)
                    related.append(hit)
                    seen.add(hit["id"])
                    if len(related) >= limit:
                        break
            if len(related) >= limit:
                break
        return anchors + related

    def search_with_run(
        self,
        query: str,
        events: list[dict[str, Any]],
        anomaly_windows: list[dict[str, Any]],
        limit: int = 5,
    ) -> dict[str, Any]:
        """Join authorized run records to reference documents through shared entities."""
        documents = self.search(query, limit=limit)
        query_entities = self._entities(query)
        nodes: dict[str, dict[str, Any]] = {}
        edges: set[tuple[str, str, str]] = set()
        windows_by_event: dict[str, list[dict[str, Any]]] = {}
        for window in anomaly_windows:
            event_id = str(window.get("event_id", ""))
            if event_id:
                windows_by_event.setdefault(event_id, []).append(window)

        for event in events:
            event_id = str(event.get("event_id", ""))
            if not event_id:
                continue
            event_node = f"event:{event_id}"
            event_text = " ".join(
                str(event.get(key, ""))
                for key in ("dominant_anomaly_type", "anomaly_types", "event_scope")
            )
            event_entities = self._entities(event_text) & query_entities
            if query_entities and not event_entities:
                continue
            nodes[event_node] = {
                "id": event_node,
                "type": "event",
                "event_id": event_id,
                "event_scope": event.get("event_scope"),
                "event_start": event.get("event_start"),
                "event_end": event.get("event_end"),
            }
            for entity in event_entities:
                entity_node = f"entity:{entity}"
                nodes[entity_node] = {"id": entity_node, "type": "entity", "name": entity}
                edges.add((event_node, "shares_entity", entity_node))

            for customer_id in event.get("customer_ids", []):
                customer_node = f"customer:{customer_id}"
                nodes[customer_node] = {
                    "id": customer_node,
                    "type": "customer",
                    "customer_id": customer_id,
                }
                edges.add((event_node, "affects", customer_node))

            for window in windows_by_event.get(event_id, []):
                area_id = window.get("area_id") or window.get("event_spatial_cluster_id")
                if area_id is not None:
                    area_node = f"area:{area_id}"
                    nodes[area_node] = {"id": area_node, "type": "area", "area_id": area_id}
                    edges.add((event_node, "located_in", area_node))

        for document in documents:
            metadata = document.get("metadata", {})
            doc_id = str(document.get("id", ""))
            if not doc_id:
                continue
            document_node = f"document:{doc_id}"
            nodes[document_node] = {
                "id": document_node,
                "type": "document",
                "title": metadata.get("title"),
                "source_url": metadata.get("source_url"),
            }
            document_entities = self._entities(
                f"{metadata.get('title', '')} {document.get('text', '')}"
            )
            for entity in document_entities & query_entities:
                entity_node = f"entity:{entity}"
                nodes.setdefault(
                    entity_node, {"id": entity_node, "type": "entity", "name": entity}
                )
                edges.add((document_node, "mentions", entity_node))

        return {
            "documents": documents,
            "nodes": list(nodes.values()),
            "edges": [
                {"source": source, "relation": relation, "target": target}
                for source, relation, target in sorted(edges)
            ],
        }
