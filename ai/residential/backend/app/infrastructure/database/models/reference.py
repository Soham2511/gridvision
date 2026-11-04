"""SQLAlchemy 2.0 Declarative Models for the Reference Data and Document Knowledge Infrastructure.

Defines schemas for:
- SourceDocumentModel (Source registry)
- DocumentArtifactModel (Separation of original vs extracted documents)
- ReferenceParameterModel (Registered technical parameters)
- CandidateReferenceModel (Extracted candidate references undergoing review)
- ApprovedReferenceModel (Immutable, versioned approved reference persistence)
- ReferenceAuditLogModel (Auditable transition history)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, synonym
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base declarative class for all reference infrastructure models."""
    pass


class SourceDocumentModel(Base):
    """Controlled source registry for official regulations, standards, and gazettes."""

    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    issuing_organization: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    official_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    document_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    edition_revision: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    retrieval_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    content_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    licensing: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Synonyms for seamless contract compatibility
    checksum_sha256 = synonym("content_checksum_sha256")
    edition = synonym("edition_revision")

    # Relationship to artifacts
    artifacts = relationship(
        "DocumentArtifactModel",
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "checksum_sha256" in kwargs and "content_checksum_sha256" not in kwargs:
            kwargs["content_checksum_sha256"] = kwargs.pop("checksum_sha256")
        if "edition" in kwargs and "edition_revision" not in kwargs:
            kwargs["edition_revision"] = kwargs.pop("edition")
        if "id" not in kwargs:
            kwargs["id"] = kwargs.get("document_identifier", str(uuid.uuid4()))
        super().__init__(**kwargs)


class DocumentArtifactModel(Base):
    """Physical artifact registry separating original documents from extracted representations."""

    __tablename__ = "document_artifacts"

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "original" or "extracted_structure"
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship to parent source document
    source = relationship("SourceDocumentModel", back_populates="artifacts")


class ReferenceParameterModel(Base):
    """Taxonomy of registered engineering and regulatory parameter definitions."""

    __tablename__ = "reference_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    parameter_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    standard_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __init__(self, **kwargs: Any) -> None:
        ident = kwargs.get("identifier")
        key = kwargs.get("parameter_key")
        if ident and not key:
            kwargs["parameter_key"] = ident
        elif key and not ident:
            kwargs["identifier"] = key
        super().__init__(**kwargs)


class CandidateReferenceModel(Base):
    """Extracted candidate reference value awaiting deterministic validation and human review."""

    __tablename__ = "candidate_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parameter_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    applicability_conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("source_documents.id"),
        nullable=False,
        index=True,
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    review_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    source = relationship("SourceDocumentModel")


class ApprovedReferenceModel(Base):
    """Immutable, versioned reference entity authoritative for domain engine calculations."""

    __tablename__ = "approved_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("candidate_references.id", ondelete="SET NULL"),
        nullable=True,
    )
    parameter_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    normalized_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    applicability_conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=True)
    superseded_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("approved_references.id"),
        nullable=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("source_documents.id"),
        nullable=False,
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    source = relationship("SourceDocumentModel")
    superseded_by = relationship("ApprovedReferenceModel", remote_side=[id])

    __table_args__ = (
        Index("ix_approved_lookup", "parameter_key", "jurisdiction", "is_latest"),
    )


class ReferenceAuditLogModel(Base):
    """Immutable audit trail capturing all lifecycle events, status changes, and diffs."""

    __tablename__ = "reference_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    old_state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    performed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    actor_id = synonym("performed_by")
    timestamp = synonym("performed_at")

    def __init__(self, **kwargs: Any) -> None:
        if "actor_id" in kwargs and "performed_by" not in kwargs:
            kwargs["performed_by"] = kwargs.pop("actor_id")
        if "timestamp" in kwargs and "performed_at" not in kwargs:
            kwargs["performed_at"] = kwargs.pop("timestamp")
        super().__init__(**kwargs)


# Interoperability aliases
SourceModel = SourceDocumentModel
SourceDocumentRecord = SourceDocumentModel
DocumentArtifactRecord = DocumentArtifactModel
ApprovedReferenceRecord = ApprovedReferenceModel
