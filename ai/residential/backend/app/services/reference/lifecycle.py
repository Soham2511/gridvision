"""Human Review Workflow Engine and Candidate Lifecycle Service.

Enforces:
- Strict state machine transitions:
  draft -> pending_review -> approved / rejected
  approved -> superseded (upon approval of newer version)
  approved -> expired
- Immutability of approved references with monotonic version incrementing.
- Traceable audit logging capturing reviewer identity, timestamps, and state diffs.
- Conflict detection flagging discrepancies between different sources for explicit human review.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models.reference import (
    ApprovedReferenceModel,
    CandidateReferenceModel,
    ReferenceAuditLogModel,
)
from app.services.reference.schemas import (
    CandidateReferenceCreate,
    CandidateReferenceResponse,
    CandidateReferenceSchema,
    EnergyUnitEnum,
    ReviewActionRequest,
)


class ReviewStatusEnum(str, Enum):
    """Permitted candidate reference lifecycle review statuses."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


VALID_TRANSITIONS: dict[str, set[str]] = {
    ReviewStatusEnum.DRAFT.value: {ReviewStatusEnum.PENDING_REVIEW.value},
    ReviewStatusEnum.PENDING_REVIEW.value: {
        ReviewStatusEnum.APPROVED.value,
        ReviewStatusEnum.REJECTED.value,
    },
    ReviewStatusEnum.APPROVED.value: {
        ReviewStatusEnum.SUPERSEDED.value,
        ReviewStatusEnum.EXPIRED.value,
    },
    ReviewStatusEnum.REJECTED.value: set(),
    ReviewStatusEnum.SUPERSEDED.value: set(),
    ReviewStatusEnum.EXPIRED.value: set(),
}


class WorkflowError(ValueError):
    """Base exception for lifecycle and review workflow errors."""
    pass


class InvalidStatusTransitionError(WorkflowError):
    """Raised when an invalid state machine transition is attempted."""
    pass


class ReviewAuthorizationError(WorkflowError):
    """Raised when reviewer identity is missing or invalid."""
    pass


class ConflictDetectedError(WorkflowError):
    """Raised or flagged when conflicting candidate references from different sources are detected."""
    pass


class ReviewWorkflowService:
    """Service managing the review lifecycle and immutable versioned persistence."""

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Database session not initialized on ReviewWorkflowService")
        return self._session

    def validate_transition(self, current_status: str, target_status: str) -> None:
        """Verify whether transition from current_status to target_status is permitted."""
        allowed = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Invalid lifecycle transition from '{current_status}' to '{target_status}'. "
                f"Allowed target states: {sorted(list(allowed)) or 'None (terminal state)'}"
            )

    def detect_conflicts(
        self,
        candidate_data: CandidateReferenceCreate | dict[str, Any],
        session: Optional[Session] = None,
    ) -> list[dict[str, Any]]:
        """Detect existing approved or pending references that conflict with this candidate.
        
        A conflict occurs when references share parameter_key and jurisdiction with overlapping
        validity dates, but come from different sources with differing normalized values.
        """
        sess = session or self.session
        param_key = (
            candidate_data.parameter_key
            if isinstance(candidate_data, CandidateReferenceCreate)
            else candidate_data["parameter_key"]
        )
        jurisdiction = (
            candidate_data.jurisdiction
            if isinstance(candidate_data, CandidateReferenceCreate)
            else candidate_data["jurisdiction"]
        )
        source_id = (
            candidate_data.source_id
            if isinstance(candidate_data, CandidateReferenceCreate)
            else candidate_data["source_id"]
        )
        norm_val = (
            candidate_data.normalized_value
            if isinstance(candidate_data, CandidateReferenceCreate)
            else candidate_data["normalized_value"]
        )
        eff_from = (
            candidate_data.effective_from
            if isinstance(candidate_data, CandidateReferenceCreate)
            else candidate_data["effective_from"]
        )
        eff_to = (
            candidate_data.effective_to
            if isinstance(candidate_data, CandidateReferenceCreate)
            else candidate_data.get("effective_to")
        )

        # Query existing approved references with matching parameter and jurisdiction
        stmt = (
            select(ApprovedReferenceModel)
            .where(
                ApprovedReferenceModel.parameter_key == param_key,
                ApprovedReferenceModel.jurisdiction == jurisdiction,
                ApprovedReferenceModel.is_latest == True,
            )
        )
        existing_approved = sess.execute(stmt).scalars().all()

        conflicts: list[dict[str, Any]] = []
        for app_ref in existing_approved:
            if app_ref.source_id != source_id:
                # Check date overlap
                overlap = True
                if eff_to and app_ref.effective_from > eff_to:
                    overlap = False
                if app_ref.effective_to and eff_from > app_ref.effective_to:
                    overlap = False

                if overlap and app_ref.normalized_value != norm_val:
                    conflicts.append({
                        "type": "source_value_conflict",
                        "existing_entity_type": "approved_reference",
                        "existing_id": app_ref.id,
                        "existing_source_id": app_ref.source_id,
                        "existing_value": app_ref.normalized_value,
                        "candidate_value": norm_val,
                    })

        return conflicts

    def submit_candidate(
        self,
        candidate_id: int,
        actor_id: str,
        session: Optional[Session] = None,
    ) -> CandidateReferenceModel:
        """Transition candidate from draft to pending_review."""
        sess = session or self.session
        candidate = sess.get(CandidateReferenceModel, candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate reference {candidate_id} not found")

        # Idempotent check
        if candidate.review_status == ReviewStatusEnum.PENDING_REVIEW.value:
            return candidate

        self.validate_transition(candidate.review_status, ReviewStatusEnum.PENDING_REVIEW.value)

        old_state = {"review_status": candidate.review_status}
        candidate.review_status = ReviewStatusEnum.PENDING_REVIEW.value
        new_state = {"review_status": candidate.review_status}

        audit = ReferenceAuditLogModel(
            entity_type="candidate_reference",
            entity_id=str(candidate.id),
            action="submit",
            old_state=old_state,
            new_state=new_state,
            performed_by=actor_id,
            performed_at=datetime.now(timezone.utc),
        )
        sess.add(audit)
        sess.flush()
        return candidate

    def approve_candidate(
        self,
        candidate_id: int,
        reviewer_id: str,
        session: Optional[Session] = None,
        reason: Optional[str] = None,
    ) -> ApprovedReferenceModel:
        """Approve candidate reference, incrementing version and persisting immutable record."""
        sess = session or self.session

        if not reviewer_id or not reviewer_id.strip():
            raise ReviewAuthorizationError("Reviewer identity cannot be empty or whitespace")

        candidate = sess.get(CandidateReferenceModel, candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate reference {candidate_id} not found")

        self.validate_transition(candidate.review_status, ReviewStatusEnum.APPROVED.value)

        # Check for latest active version to determine next version
        stmt = (
            select(ApprovedReferenceModel)
            .where(
                ApprovedReferenceModel.parameter_key == candidate.parameter_key,
                ApprovedReferenceModel.jurisdiction == candidate.jurisdiction,
                ApprovedReferenceModel.is_latest == True,
            )
            .order_by(ApprovedReferenceModel.version.desc())
        )
        prior_approved = sess.execute(stmt).scalars().first()

        new_version = (prior_approved.version + 1) if prior_approved else 1
        now_utc = datetime.now(timezone.utc)

        # Create new ApprovedReferenceModel
        new_approved = ApprovedReferenceModel(
            candidate_id=candidate.id,
            parameter_key=candidate.parameter_key,
            normalized_value=candidate.normalized_value,
            unit=candidate.unit,
            jurisdiction=candidate.jurisdiction,
            region=candidate.region,
            applicability_conditions=candidate.applicability_conditions,
            effective_from=candidate.effective_from,
            effective_to=candidate.effective_to,
            version=new_version,
            is_latest=True,
            superseded_by_id=None,
            source_id=candidate.source_id,
            provenance=candidate.provenance,
            approved_by=reviewer_id.strip(),
            approved_at=now_utc,
        )
        sess.add(new_approved)
        sess.flush()

        # If a prior version existed, mark it superseded
        if prior_approved is not None:
            prior_approved.is_latest = False
            prior_approved.superseded_by_id = new_approved.id

            # Also update candidate of prior approved if present
            if prior_approved.candidate_id:
                prior_cand = sess.get(CandidateReferenceModel, prior_approved.candidate_id)
                if prior_cand and prior_cand.review_status == ReviewStatusEnum.APPROVED.value:
                    prior_cand.review_status = ReviewStatusEnum.SUPERSEDED.value

            # Audit log for superseding
            supersede_audit = ReferenceAuditLogModel(
                entity_type="approved_reference",
                entity_id=str(prior_approved.id),
                action="supersede",
                old_state={"is_latest": True, "superseded_by_id": None},
                new_state={"is_latest": False, "superseded_by_id": new_approved.id},
                performed_by=reviewer_id.strip(),
                performed_at=now_utc,
            )
            sess.add(supersede_audit)

        # Update candidate status
        old_candidate_status = candidate.review_status
        candidate.review_status = ReviewStatusEnum.APPROVED.value

        # Audit log for candidate approval
        candidate_audit = ReferenceAuditLogModel(
            entity_type="candidate_reference",
            entity_id=str(candidate.id),
            action="approve",
            old_state={"review_status": old_candidate_status},
            new_state={"review_status": ReviewStatusEnum.APPROVED.value, "version": new_version},
            performed_by=reviewer_id.strip(),
            performed_at=now_utc,
        )
        sess.add(candidate_audit)

        # Audit log for approved reference creation
        approval_audit = ReferenceAuditLogModel(
            entity_type="approved_reference",
            entity_id=str(new_approved.id),
            action="approve",
            old_state=None,
            new_state={
                "parameter_key": new_approved.parameter_key,
                "version": new_version,
                "is_latest": True,
                "normalized_value": new_approved.normalized_value,
                "reviewer": reviewer_id.strip(),
            },
            performed_by=reviewer_id.strip(),
            performed_at=now_utc,
        )
        sess.add(approval_audit)
        sess.flush()

        return new_approved

    def reject_candidate(
        self,
        candidate_id: int,
        reviewer_id: str,
        reason: str,
        session: Optional[Session] = None,
    ) -> CandidateReferenceModel:
        """Reject candidate reference with mandatory reviewer rationale."""
        sess = session or self.session

        if not reviewer_id or not reviewer_id.strip():
            raise ReviewAuthorizationError("Reviewer identity cannot be empty or whitespace")
        if not reason or not reason.strip():
            raise ValueError("Rejection requires a non-empty explanatory rationale/comment")

        candidate = sess.get(CandidateReferenceModel, candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate reference {candidate_id} not found")

        self.validate_transition(candidate.review_status, ReviewStatusEnum.REJECTED.value)

        old_status = candidate.review_status
        candidate.review_status = ReviewStatusEnum.REJECTED.value

        # Append rejection reason to provenance
        prov = dict(candidate.provenance or {})
        prov["rejection_reason"] = reason.strip()
        candidate.provenance = prov

        audit = ReferenceAuditLogModel(
            entity_type="candidate_reference",
            entity_id=str(candidate.id),
            action="reject",
            old_state={"review_status": old_status},
            new_state={"review_status": ReviewStatusEnum.REJECTED.value, "reason": reason.strip()},
            performed_by=reviewer_id.strip(),
            performed_at=datetime.now(timezone.utc),
        )
        sess.add(audit)
        sess.flush()
        return candidate

    def expire_approved_reference(
        self,
        approved_id: int,
        actor_id: str,
        session: Optional[Session] = None,
    ) -> ApprovedReferenceModel:
        """Mark an approved reference expired when current date exceeds validity end."""
        sess = session or self.session
        approved = sess.get(ApprovedReferenceModel, approved_id)
        if approved is None:
            raise ValueError(f"Approved reference {approved_id} not found")

        old_latest = approved.is_latest
        approved.is_latest = False

        audit = ReferenceAuditLogModel(
            entity_type="approved_reference",
            entity_id=str(approved.id),
            action="expire",
            old_state={"is_latest": old_latest},
            new_state={"is_latest": False, "expired": True},
            performed_by=actor_id,
            performed_at=datetime.now(timezone.utc),
        )
        sess.add(audit)
        sess.flush()
        return approved


# Contract aliases
CandidateLifecycleService = ReviewWorkflowService
