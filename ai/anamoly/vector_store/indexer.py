"""Incremental, metadata-preserving document indexing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai.anamoly.ingestion.chunking import DocumentChunk
from ai.anamoly.vector_store.database import get_collection
from ai.anamoly.vector_store.embeddings import embed_texts


class VectorIndexer:
    """Upsert chunks while skipping unchanged source documents."""

    def __init__(self, collection: Any | None = None) -> None:
        self.collection = collection or get_collection()

    def index_document(
        self, document_id: str, content_sha256: str, chunks: Sequence[DocumentChunk]
    ) -> dict[str, int | bool]:
        existing = self.collection.get(
            where={"document_id": document_id}, include=["metadatas"]
        )
        old_metadata = existing.get("metadatas") or []
        if old_metadata and all(
            item.get("content_sha256") == content_sha256 for item in old_metadata
        ):
            return {"indexed": 0, "skipped": len(old_metadata), "unchanged": True}

        if not chunks:
            if existing.get("ids"):
                self.collection.delete(ids=existing["ids"])
            return {"indexed": 0, "skipped": 0, "unchanged": False}

        embeddings = embed_texts([chunk.text for chunk in chunks])
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        self.collection.upsert(
            ids=chunk_ids,
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata for chunk in chunks],
            embeddings=embeddings,
        )
        stale_ids = [
            chunk_id for chunk_id in existing.get("ids", []) if chunk_id not in chunk_ids
        ]
        if stale_ids:
            self.collection.delete(ids=stale_ids)
        return {"indexed": len(chunks), "skipped": 0, "unchanged": False}

    def delete_document(self, document_id: str) -> int:
        """Remove one source document's chunks by its stable document ID."""
        existing = self.collection.get(
            where={"document_id": document_id}, include=["metadatas"]
        )
        ids = existing.get("ids") or []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)
