"""Repository pattern for Reference Data and Candidate Lifecycle persistence.

Provides unified transactional operations for:
- Candidate registration and deterministic schema validation.
- Status queries and lifecycle stage listing.
- Review workflow executions (submit, approve, reject).
- Active approved reference querying matching jurisdiction and temporal intervals.
- Full audit log retrieval.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.connection import get_session, get_session_factory
from app.infrastructure.database.models.reference import (
    ApprovedReferenceModel,
    CandidateReferenceModel,
    ReferenceAuditLogModel,
)
from app.services.reference.lifecycle import ReviewWorkflowService
from app.services.reference.schemas import CandidateReferenceCreate, CandidateReferenceSchema


class ReferenceRepository:
    """Repository managing candidate and approved reference data persistence."""

    def __init__(
        self,
        session: Optional[Session] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory or get_session_factory()
        self._workflow = ReviewWorkflowService(session=session)

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Database session not bound to ReferenceRepository")
        return self._session

    def add_candidate(
        self,
        candidate_data: CandidateReferenceCreate | dict[str, Any],
        initial_status: str = "draft",
        actor_id: str = "system",
    ) -> CandidateReferenceModel:
        """Deterministically validate and persist a new candidate reference record."""
        if isinstance(candidate_data, dict):
            validated = CandidateReferenceCreate.model_validate(candidate_data)
        else:
            validated = candidate_data

        candidate = CandidateReferenceModel(
            parameter_key=validated.parameter_key,
            raw_value=validated.raw_value,
            normalized_value=validated.normalized_value,
            unit=validated.unit,
            jurisdiction=validated.jurisdiction,
            region=validated.region,
            applicability_conditions=validated.applicability_conditions,
            effective_from=validated.effective_from,
            effective_to=validated.effective_to,
            source_id=validated.source_id,
            provenance=validated.provenance,
            confidence=validated.confidence,
            review_status=initial_status,
        )
        self.session.add(candidate)
        self.session.flush()

        audit = ReferenceAuditLogModel(
            entity_type="candidate_reference",
            entity_id=str(candidate.id),
            action="create",
            old_state=None,
            new_state={
                "parameter_key": candidate.parameter_key,
                "review_status": candidate.review_status,
                "normalized_value": candidate.normalized_value,
            },
            performed_by=actor_id,
            performed_at=datetime.now(timezone.utc),
        )
        self.session.add(audit)
        self.session.flush()

        return candidate

    def get_candidate(self, candidate_id: int) -> Optional[CandidateReferenceModel]:
        """Fetch candidate reference by primary key."""
        return self.session.get(CandidateReferenceModel, candidate_id)

    def list_candidates_by_status(self, status: str) -> List[CandidateReferenceModel]:
        """List all candidates matching the given review status."""
        stmt = (
            select(CandidateReferenceModel)
            .where(CandidateReferenceModel.review_status == status)
            .order_by(CandidateReferenceModel.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def submit_candidate(self, candidate_id: int, actor_id: str) -> CandidateReferenceModel:
        """Submit candidate for review (draft -> pending_review)."""
        return self._workflow.submit_candidate(candidate_id, actor_id, session=self.session)

    def approve_candidate(
        self,
        candidate_id: int,
        reviewer_id: str,
        reason: Optional[str] = None,
    ) -> ApprovedReferenceModel:
        """Authorize candidate and produce immutable approved version."""
        return self._workflow.approve_candidate(
            candidate_id=candidate_id,
            reviewer_id=reviewer_id,
            session=self.session,
            reason=reason,
        )

    def reject_candidate(
        self,
        candidate_id: int,
        reviewer_id: str,
        reason: str,
    ) -> CandidateReferenceModel:
        """Reject candidate with mandatory explanation."""
        return self._workflow.reject_candidate(
            candidate_id=candidate_id,
            reviewer_id=reviewer_id,
            reason=reason,
            session=self.session,
        )

    def get_active_references(
        self,
        parameter_key: str,
        jurisdiction: str,
        effective_date: date,
    ) -> List[ApprovedReferenceModel]:
        """Query active approved references matching parameter, jurisdiction, and validity date."""
        stmt = (
            select(ApprovedReferenceModel)
            .where(
                ApprovedReferenceModel.parameter_key == parameter_key,
                ApprovedReferenceModel.jurisdiction == jurisdiction,
                ApprovedReferenceModel.is_latest == True,
                ApprovedReferenceModel.effective_from <= effective_date,
                or_(
                    ApprovedReferenceModel.effective_to.is_(None),
                    ApprovedReferenceModel.effective_to >= effective_date,
                ),
            )
            .order_by(ApprovedReferenceModel.version.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_reference_by_id(self, approved_id: int) -> Optional[ApprovedReferenceModel]:
        """Fetch approved reference by primary key."""
        return self.session.get(ApprovedReferenceModel, approved_id)

    def get_reference_history(
        self,
        parameter_key: str,
        jurisdiction: str,
    ) -> List[ApprovedReferenceModel]:
        """Retrieve complete version history for a parameter in a jurisdiction."""
        stmt = (
            select(ApprovedReferenceModel)
            .where(
                ApprovedReferenceModel.parameter_key == parameter_key,
                ApprovedReferenceModel.jurisdiction == jurisdiction,
            )
            .order_by(ApprovedReferenceModel.version.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_audit_logs(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> List[ReferenceAuditLogModel]:
        """Retrieve audit log entries filtered by entity type and ID."""
        stmt = select(ReferenceAuditLogModel)
        conditions = []
        if entity_type:
            conditions.append(ReferenceAuditLogModel.entity_type == entity_type)
        if entity_id:
            conditions.append(ReferenceAuditLogModel.entity_id == entity_id)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(ReferenceAuditLogModel.performed_at.asc())
        return list(self.session.execute(stmt).scalars().all())
