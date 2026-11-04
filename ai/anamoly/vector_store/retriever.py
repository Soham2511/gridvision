"""Citation-aware semantic retrieval from the shared Chroma collection."""

from __future__ import annotations

from typing import Any

from ai.anamoly.vector_store.database import get_collection
from ai.anamoly.vector_store.embeddings import embed_texts


class KnowledgeRetriever:
    def __init__(self, collection: Any | None = None) -> None:
        self.collection = collection or get_collection()

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("A non-empty knowledge query is required.")
        if limit < 1 or limit > 20:
            raise ValueError("Knowledge retrieval limit must be between 1 and 20.")
        if self.collection.count() == 0:
            return []
        query_embedding = embed_texts([query])[0]
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        ids = result.get("ids") or [[]]
        hits: list[dict[str, Any]] = []
        for index, text in enumerate(documents[0]):
            metadata = metadatas[0][index] or {}
            distance = distances[0][index]
            hits.append(
                {
                    "id": ids[0][index],
                    "text": text,
                    "metadata": metadata,
                    "distance": float(distance),
                    "citation": {
                        "title": metadata.get("title", "Untitled source"),
                        "sourceUrl": metadata.get("source_url") or None,
                        "page": metadata.get("page_number") or None,
                        "publisher": metadata.get("publisher") or None,
                    },
                }
            )
        return hits

