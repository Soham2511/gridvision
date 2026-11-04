"""SQLAlchemy 2.0 Declarative Models for Document Knowledge & RAG Chunking.

Stores structure-aware document chunks, metadata, and embeddings for regulatory and technical documents.
Subclasses DeclarativeBase Base to share database metadata and foreign keys with SourceDocumentModel.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.infrastructure.database.models.reference import Base


class DocumentChunkModel(Base):
    """Stores structure-aware text, clause, table, and footnote chunks extracted from documents."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    publisher: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # BIS, CEA, BEE, DISCOM, etc.
    chunk_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # section, clause, table, footnote
    section_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    clause_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    heading: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_est: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship to parent source document
    source = relationship("SourceDocumentModel", backref="chunks")

    __table_args__ = (
        Index("ix_chunks_pub_doc", "publisher", "document_identifier"),
        Index("ix_chunks_type_sec", "chunk_type", "section_id"),
    )


class RAGQueryAuditModel(Base):
    """Audit log for queries handled by the Agentic RAG system for observability and evaluation."""

    __tablename__ = "rag_query_audits"

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_prompt: Mapped[Text] = mapped_column(Text, nullable=False)
    query_tag: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    structured_refs_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    citations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
