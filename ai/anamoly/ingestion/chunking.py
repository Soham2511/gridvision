"""Page-aware overlapping text chunking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.anamoly.ingestion.document_loader import SourceDocument
from ai.anamoly.ingestion.text_cleaner import clean_text


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


def chunk_document(
    document: SourceDocument,
    *,
    source_root: str,
    chunk_size: int = 1200,
    overlap: int = 180,
) -> list[DocumentChunk]:
    """Split pages into bounded chunks while retaining citation metadata."""
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap smaller than it.")
    chunks: list[DocumentChunk] = []
    stride = chunk_size - overlap
    for page in document.pages:
        text = clean_text(page.text)
        if not text:
            continue
        page_index = 0
        for start in range(0, len(text), stride):
            excerpt = text[start : start + chunk_size].strip()
            if not excerpt:
                continue
            chunk_index = len(chunks)
            chunk_id = f"{document.document_id}-{chunk_index:06d}"
            metadata = {
                key: value
                for key, value in document.metadata.items()
                if isinstance(value, (str, int, float, bool))
            }
            metadata.update(
                {
                    "page_number": page.page_number or 0,
                    "chunk_index": chunk_index,
                    "source_root": source_root,
                    "page_chunk_index": page_index,
                }
            )
            chunks.append(DocumentChunk(chunk_id, excerpt, metadata))
            page_index += 1
            if start + chunk_size >= len(text):
                break
    return chunks

