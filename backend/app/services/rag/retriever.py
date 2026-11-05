"""Hybrid Document Retriever for Regulatory and Technical Knowledge.

Combines dense vector similarity with lexical BM25 ranking via Reciprocal Rank Fusion (RRF),
supports structured metadata filtering, and produces fully traceable citation objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database.models.rag import DocumentChunkModel
from app.services.rag.embeddings import (
    BaseEmbeddingProvider,
    LocalResilientEmbeddingProvider,
    cosine_similarity,
)
from app.services.rag.lexical_search import BM25Index

logger = logging.getLogger("gridvision.services.rag.retriever")


@dataclass
class RetrievedChunk:
    """Retrieved document chunk with relevance score and complete citation provenance."""

    chunk_id: str
    source_id: str
    document_identifier: str
    publisher: str
    chunk_type: str
    section_id: Optional[str]
    clause_id: Optional[str]
    heading: Optional[str]
    page_number: int
    content: str
    snippet: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_section_id: Optional[str] = None
    parent_heading: Optional[str] = None
    parent_context: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_citation(self) -> Dict[str, Any]:
        """Convert chunk into user-facing citation contract."""
        return {
            "source_id": self.source_id,
            "document_identifier": self.document_identifier,
            "publisher": self.publisher,
            "section": self.heading or (f"Clause {self.clause_id}" if self.clause_id else f"Section {self.section_id}"),
            "clause_id": self.clause_id,
            "page": self.page_number,
            "text_snippet": self.snippet,
            "chunk_id": self.chunk_id,
            "category": self.category or self.metadata.get("category"),
            "parent_heading": self.parent_heading or self.metadata.get("parent_heading") or self.metadata.get("section_heading"),
            "parent_context": self.parent_context or self.metadata.get("parent_context") or self.metadata.get("parent_path"),
            "tags": self.tags or self.metadata.get("tags", []),
            "url": self.metadata.get("url") or self.metadata.get("source_url"),
        }


class HybridDocumentRetriever:
    """Executes hybrid vector + lexical search across indexed official documents."""

    def __init__(
        self,
        session_factory: Any,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        dense_weight: float = 0.6,
        lexical_weight: float = 0.4,
        rrf_k: int = 60,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_provider = embedding_provider or LocalResilientEmbeddingProvider()
        self.dense_weight = dense_weight
        self.lexical_weight = lexical_weight
        self.rrf_k = rrf_k
        self._bm25_index: Optional[BM25Index] = None
        self._chunk_cache: Dict[str, DocumentChunkModel] = {}
        self._warmup_cache()

    def _warmup_cache(self) -> None:
        """Pre-warm memory BM25 index and chunk cache from database."""
        try:
            from app.infrastructure.database.connection import init_db
            with self.session_factory() as session:
                init_db(session.bind)
                chunks = session.scalars(select(DocumentChunkModel)).all()
                if not chunks:
                    from app.services.rag.indexing_service import DocumentIndexingService
                    indexer = DocumentIndexingService(session_factory=self.session_factory)
                    indexer.seed_authoritative_corpus()
                    chunks = session.scalars(select(DocumentChunkModel)).all()

                new_bm25 = BM25Index()
                new_cache: Dict[str, DocumentChunkModel] = {}
                for ch in chunks:
                    new_cache[ch.id] = ch
                    meta = ch.metadata_json or {}
                    tags_str = " ".join(meta.get("tags", []))
                    cat_str = meta.get("category", "")
                    parent_str = meta.get("parent_path", "")
                    searchable_text = f"{ch.document_identifier} {ch.publisher} {ch.heading or ''} {cat_str} {parent_str} {tags_str} {ch.content}"
                    new_bm25.add_document(ch.id, searchable_text)
                self._bm25_index = new_bm25
                self._chunk_cache = new_cache
                logger.info("HybridDocumentRetriever indexed %d document chunks in memory.", len(chunks))
        except Exception as e:
            logger.warning("Could not pre-warm RAG cache: %s", e)
            self._bm25_index = BM25Index()

    def sync_cache(self) -> None:
        """Force re-synchronization of retrieval cache from database."""
        self._warmup_cache()

    def search(
        self,
        query: str,
        top_k: Optional[int] = 5,
        publisher: Optional[str] = None,
        document_identifier: Optional[str] = None,
        chunk_type: Optional[str] = None,
        category: Optional[str] = None,
        min_score: float = 0.01,
    ) -> List[RetrievedChunk]:
        """Perform hybrid dense + lexical search with reciprocal rank fusion."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # If cache is empty, try to reload
        if not self._chunk_cache:
            self._warmup_cache()

        if not self._chunk_cache:
            return []

        # 1. Candidate pre-filtering by metadata
        eligible_chunk_ids = set()
        for c_id, ch in self._chunk_cache.items():
            if publisher and ch.publisher.upper() != publisher.upper():
                continue
            if document_identifier and document_identifier.lower() not in ch.document_identifier.lower():
                continue
            if chunk_type and ch.chunk_type.lower() != chunk_type.lower():
                continue
            if category:
                ch_cat = (ch.metadata_json.get("category") or "").lower()
                ch_tags = [t.lower() for t in ch.metadata_json.get("tags", [])]
                cat_lower = category.lower()
                if ch_cat != cat_lower and cat_lower not in ch_tags:
                    continue
            eligible_chunk_ids.add(c_id)

        if not eligible_chunk_ids:
            return []

        # 2. Dense Semantic Retrieval
        query_vec = self.embedding_provider.embed_text(clean_query)
        dense_scores: List[tuple[str, float]] = []
        for c_id in eligible_chunk_ids:
            ch = self._chunk_cache[c_id]
            if ch.embedding:
                sim = cosine_similarity(query_vec, ch.embedding)
                dense_scores.append((c_id, sim))
            else:
                dense_scores.append((c_id, 0.0))

        dense_ranked = sorted(dense_scores, key=lambda x: x[1], reverse=True)
        dense_rank_map = {doc_id: rank for rank, (doc_id, _) in enumerate(dense_ranked)}

        # 3. Lexical BM25 Retrieval
        bm25_raw = self._bm25_index.search(clean_query, top_k=len(self._chunk_cache)) if self._bm25_index else []
        lexical_ranked = [(doc_id, score) for doc_id, score in bm25_raw if doc_id in eligible_chunk_ids]
        lexical_rank_map = {doc_id: rank for rank, (doc_id, _) in enumerate(lexical_ranked)}

        # 4. Reciprocal Rank Fusion (RRF)
        all_candidate_ids = set(dense_rank_map.keys()) | set(lexical_rank_map.keys())
        rrf_scores: Dict[str, float] = {}

        for c_id in all_candidate_ids:
            dense_rank = dense_rank_map.get(c_id)
            lexical_rank = lexical_rank_map.get(c_id)

            score = 0.0
            if dense_rank is not None:
                score += self.dense_weight / (self.rrf_k + dense_rank + 1)
            if lexical_rank is not None:
                score += self.lexical_weight / (self.rrf_k + lexical_rank + 1)

            rrf_scores[c_id] = score

        ranked_candidates = sorted(
            rrf_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if top_k is None:
            source_counts: Dict[tuple[str, str], int] = {}
            top_candidates = []
            for candidate in ranked_candidates:
                chunk = self._chunk_cache[candidate[0]]
                source_key = (chunk.publisher, chunk.document_identifier)
                if source_counts.get(source_key, 0) >= 2:
                    continue
                source_counts[source_key] = source_counts.get(source_key, 0) + 1
                top_candidates.append(candidate)
        else:
            top_candidates = ranked_candidates[:top_k]

        results: List[RetrievedChunk] = []
        for c_id, score in top_candidates:
            if score < min_score:
                continue
            ch = self._chunk_cache[c_id]

            # Generate concise snippet (~250 chars) centered around match or beginning
            text = ch.content
            snippet = text[:280].strip() + ("..." if len(text) > 280 else "")

            meta = dict(ch.metadata_json or {})
            results.append(
                RetrievedChunk(
                    chunk_id=ch.id,
                    source_id=ch.source_id,
                    document_identifier=ch.document_identifier,
                    publisher=ch.publisher,
                    chunk_type=ch.chunk_type,
                    section_id=ch.section_id,
                    clause_id=ch.clause_id,
                    heading=ch.heading,
                    page_number=ch.page_number,
                    content=ch.content,
                    snippet=snippet,
                    score=round(score, 5),
                    metadata=meta,
                    parent_section_id=meta.get("parent_section_id"),
                    parent_heading=meta.get("parent_heading") or meta.get("section_heading"),
                    parent_context=meta.get("parent_context") or meta.get("parent_path"),
                    category=meta.get("category"),
                    tags=list(meta.get("tags", [])),
                )
            )

        return results
