from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.anamoly.ingestion.chunking import chunk_document
from ai.anamoly.ingestion.document_loader import discover_documents, load_document
from ai.anamoly.vector_store import indexer as indexer_module
from ai.anamoly.vector_store.indexer import VectorIndexer


class FakeCollection:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def get(self, where, include):
        document_id = where["document_id"]
        matches = {
            key: value
            for key, value in self.items.items()
            if value["metadata"]["document_id"] == document_id
        }
        return {
            "ids": list(matches),
            "metadatas": [item["metadata"] for item in matches.values()],
        }

    def upsert(self, ids, documents, metadatas, embeddings):
        for key, text, metadata, embedding in zip(ids, documents, metadatas, embeddings):
            self.items[key] = {
                "document": text,
                "metadata": metadata,
                "embedding": embedding,
            }

    def delete(self, ids):
        for key in ids:
            self.items.pop(key, None)


def test_loads_supported_files_and_preserves_manifest_metadata(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    page = source / "guide.txt"
    page.write_text("A technical guide. " * 120, encoding="utf-8")
    (source / "readme.csv").write_text("large,customer,data", encoding="utf-8")

    files = discover_documents(source)
    document = load_document(
        files[0],
        source,
        {"url": "https://example.gov/guide", "source_domain": "example.gov"},
    )
    chunks = chunk_document(document, source_root=str(source), chunk_size=300, overlap=20)

    assert files == [page]
    assert document.metadata["source_url"] == "https://example.gov/guide"
    assert document.metadata["publisher"] == "example.gov"
    assert chunks
    assert all(chunk.metadata["document_id"] == document.document_id for chunk in chunks)


def test_indexer_skips_unchanged_sources_and_replaces_changed_chunks(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "page.md"
    path.write_text("A" * 800, encoding="utf-8")
    document = load_document(path, source)
    chunks = chunk_document(document, source_root=str(source), chunk_size=200, overlap=10)
    collection = FakeCollection()
    monkeypatch.setattr(indexer_module, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])
    indexer = VectorIndexer(collection)

    first = indexer.index_document(document.document_id, document.content_sha256, chunks)
    repeated = indexer.index_document(document.document_id, document.content_sha256, chunks)
    path.write_text("B" * 80, encoding="utf-8")
    changed = load_document(path, source)
    changed_chunks = chunk_document(changed, source_root=str(source), chunk_size=200, overlap=10)
    replaced = indexer.index_document(
        changed.document_id, changed.content_sha256, changed_chunks
    )

    assert first["indexed"] > 0
    assert repeated["unchanged"] is True
    assert replaced["unchanged"] is False
    assert len(collection.items) == len(changed_chunks)
    assert indexer.delete_document(document.document_id) == len(changed_chunks)

