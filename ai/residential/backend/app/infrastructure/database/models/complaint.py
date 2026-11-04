"""SQLAlchemy 2.0 declarative database model for the Complaint Management system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import (
    DateTime,
    Float,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.database.models.reference import Base


class ComplaintModel(Base):
    """Persistent database representation of a customer service complaint."""

    __tablename__ = "complaints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    meter_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_segment: Mapped[str] = mapped_column(String(32), nullable=False, default="RESIDENTIAL", index=True)
    category_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category_label: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUBMITTED", index=True)

    validation_outcome: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    severity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    severity_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    category_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    validation_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    scoring_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    registration_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    customer_care_escalation: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

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

    __table_args__ = (
        Index("ix_complaints_customer_status", "customer_id", "status"),
        Index("ix_complaints_meter_created", "meter_id", "created_at"),
    )

