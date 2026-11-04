"""Repository implementation for persisting and querying Complaint aggregates."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.complaints.entities import (
    Complaint,
    ComplaintStatus,
    CustomerSegment,
    SeverityLevel,
    SeverityResult,
    StatusTransition,
    ValidationOutcome,
    ValidationResult,
)
from app.infrastructure.database.connection import get_engine, get_session
from app.infrastructure.database.models.complaint import ComplaintModel
from app.infrastructure.database.models.reference import Base

logger = logging.getLogger("gridvision.infrastructure.repositories.complaints")


class ComplaintRepository:
    """SQLAlchemy-backed repository for the Complaint domain model."""

    def __init__(self, engine=None) -> None:
        self.engine = engine or get_engine()
        self.ensure_tables()

    def ensure_tables(self) -> None:
        """Ensure the complaint database tables are created."""
        Base.metadata.create_all(bind=self.engine)

    def _to_entity(self, row: ComplaintModel) -> Complaint:
        """Convert ORM row to domain entity."""
        validation_res = None
        if row.validation_payload:
            try:
                validation_res = ValidationResult.model_validate(row.validation_payload)
            except Exception as e:
                logger.warning("Failed to deserialize validation payload: %s", e)

        severity_res = None
        if row.scoring_payload:
            try:
                severity_res = SeverityResult.model_validate(row.scoring_payload)
            except Exception as e:
                logger.warning("Failed to deserialize scoring payload: %s", e)

        history = []
        if row.status_history:
            for item in row.status_history:
                try:
                    history.append(StatusTransition.model_validate(item))
                except Exception:
                    pass

        return Complaint(
            id=row.id,
            customer_id=row.customer_id,
            meter_id=row.meter_id,
            customer_segment=CustomerSegment(row.customer_segment),
            category_id=row.category_id,
            category_label=row.category_label,
            title=row.title,
            description=row.description,
            category_data=row.category_data or {},
            status=ComplaintStatus(row.status),
            validation_result=validation_res,
            severity_result=severity_res,
            status_history=history,
            customer_care_escalation=row.customer_care_escalation,
            registration_metadata=row.registration_payload,
            created_at=row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat(),
            updated_at=row.updated_at.isoformat() if row.updated_at else datetime.now(timezone.utc).isoformat(),
        )

    def save(self, complaint: Complaint) -> Complaint:
        """Save a new complaint or update an existing complaint record."""
        with get_session() as session:
            existing = session.get(ComplaintModel, complaint.id)

            val_dict = complaint.validation_result.model_dump() if complaint.validation_result else None
            score_dict = complaint.severity_result.model_dump() if complaint.severity_result else None
            history_list = [h.model_dump() for h in complaint.status_history]

            if existing:
                existing.status = complaint.status.value
                existing.validation_outcome = complaint.validation_result.outcome.value if complaint.validation_result else None
                existing.severity_score = complaint.severity_result.severity_score if complaint.severity_result else None
                existing.severity_level = complaint.severity_result.severity_level.value if complaint.severity_result else None
                existing.category_data = complaint.category_data
                existing.validation_payload = val_dict
                existing.scoring_payload = score_dict
                existing.registration_payload = complaint.registration_metadata
                existing.status_history = history_list
                existing.customer_care_escalation = complaint.customer_care_escalation
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_row = ComplaintModel(
                    id=complaint.id,
                    customer_id=complaint.customer_id,
                    meter_id=complaint.meter_id,
                    customer_segment=complaint.customer_segment.value,
                    category_id=complaint.category_id,
                    category_label=complaint.category_label,
                    title=complaint.title,
                    description=complaint.description,
                    status=complaint.status.value,
                    validation_outcome=complaint.validation_result.outcome.value if complaint.validation_result else None,
                    severity_score=complaint.severity_result.severity_score if complaint.severity_result else None,
                    severity_level=complaint.severity_result.severity_level.value if complaint.severity_result else None,
                    category_data=complaint.category_data,
                    validation_payload=val_dict,
                    scoring_payload=score_dict,
                    registration_payload=complaint.registration_metadata,
                    status_history=history_list,
                    customer_care_escalation=complaint.customer_care_escalation,
                    created_at=datetime.fromisoformat(complaint.created_at) if complaint.created_at else datetime.now(timezone.utc),
                    updated_at=datetime.fromisoformat(complaint.updated_at) if complaint.updated_at else datetime.now(timezone.utc),
                )
                session.add(new_row)

        return complaint

    def get_by_id(self, complaint_id: str) -> Optional[Complaint]:
        """Retrieve a complaint by ID."""
        with get_session() as session:
            row = session.get(ComplaintModel, complaint_id)
            if not row:
                return None
            return self._to_entity(row)

    def list_by_customer(
        self,
        customer_id: str,
        status_filter: Optional[str] = None,
    ) -> List[Complaint]:
        """List all complaints belonging to a customer, optionally filtered by status."""
        with get_session() as session:
            stmt = select(ComplaintModel).where(ComplaintModel.customer_id == customer_id)

            if status_filter:
                sf = status_filter.strip().upper()
                if sf == "REGISTERED":
                    stmt = stmt.where(ComplaintModel.status == ComplaintStatus.REGISTERED.value)
                elif sf == "INVALID":
                    stmt = stmt.where(ComplaintModel.status == ComplaintStatus.INVALID.value)

            stmt = stmt.order_by(ComplaintModel.created_at.desc())
            rows = session.scalars(stmt).all()
            return [self._to_entity(r) for r in rows]

