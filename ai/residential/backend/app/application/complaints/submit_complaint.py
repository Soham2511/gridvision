"""Submit and process a customer service complaint through validation and severity scoring."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.application.complaints.scoring_agent import ComplaintSeverityScoringAgent
from app.application.complaints.validator_agent import ComplaintValidatorAgent
from app.domain.complaints.categories import get_category_by_id
from app.domain.complaints.entities import (
    Complaint,
    ComplaintStatus,
    CustomerSegment,
    ValidationOutcome,
)
from app.infrastructure.repositories.complaint_repository import ComplaintRepository

logger = logging.getLogger("gridvision.application.complaints.submit")


class SubmitComplaintRequest(BaseModel):
    """Input payload for registering a complaint."""
    category_id: str = Field(..., description="Complaint category ID from the approved catalogue")
    title: str = Field(..., min_length=3, max_length=200, description="Customer-provided summary title")
    description: str = Field(..., min_length=10, max_length=4000, description="Detailed description of the issue")
    category_data: Dict[str, Any] = Field(default_factory=dict, description="Category-specific form values")
    customer_segment: str = Field(default="RESIDENTIAL", description="Customer segment (RESIDENTIAL or COMMERCIAL)")


class SubmitComplaintUseCase:
    """Orchestrates complaint registration, validation agent, and severity scoring agent."""

    def __init__(
        self,
        repository: Optional[ComplaintRepository] = None,
        validator_agent: Optional[ComplaintValidatorAgent] = None,
        scoring_agent: Optional[ComplaintSeverityScoringAgent] = None,
        customer_care_contact: Optional[str] = None,
    ) -> None:
        self.repository = repository or ComplaintRepository()
        self.validator_agent = validator_agent or ComplaintValidatorAgent()
        self.scoring_agent = scoring_agent or ComplaintSeverityScoringAgent()
        self.customer_care_contact = customer_care_contact

    def execute(
        self,
        customer_id: str,
        meter_id: str,
        request: SubmitComplaintRequest,
    ) -> Complaint:
        """Execute end-to-end complaint lifecycle."""
        # 1. Validate Category Definition
        category = get_category_by_id(request.category_id)
        if not category:
            raise ValueError(f"Invalid complaint category '{request.category_id}'. Must be one of the registered categories.")

        # 2. Validate Category Required Fields
        missing_fields = []
        for field_def in category.fields:
            if field_def.required and field_def.field_id not in request.category_data:
                # Check if default value exists
                if field_def.default_value is None:
                    missing_fields.append(field_def.label)

        if missing_fields:
            raise ValueError(f"Missing required fields for category '{category.label}': {', '.join(missing_fields)}")

        # 3. Create Aggregate Root in SUBMITTED State
        segment_enum = CustomerSegment.RESIDENTIAL
        try:
            segment_enum = CustomerSegment(request.customer_segment.upper())
        except ValueError:
            pass

        complaint = Complaint(
            customer_id=customer_id,
            meter_id=meter_id,
            customer_segment=segment_enum,
            category_id=category.category_id,
            category_label=category.label,
            title=request.title.strip(),
            description=request.description.strip(),
            category_data=request.category_data,
            status=ComplaintStatus.SUBMITTED,
        )
        complaint.transition_to(ComplaintStatus.SUBMITTED, note="Complaint submitted by customer.")
        self.repository.save(complaint)

        # 4. Stage 1: AI Validation Agent
        complaint.transition_to(ComplaintStatus.VALIDATING, note="Complaint Validator Agent evaluating telemetry and evidence.")
        self.repository.save(complaint)

        try:
            val_result = self.validator_agent.validate_complaint(
                meter_id=meter_id,
                category_id=category.category_id,
                category_data=request.category_data,
                title=request.title,
                description=request.description,
            )
            complaint.validation_result = val_result
        except Exception as e:
            logger.error("Validator Agent failed unexpectedly: %s", e, exc_info=True)
            complaint.transition_to(ComplaintStatus.PROCESSING_FAILED, note=f"Validation error: {e}")
            self.repository.save(complaint)
            return complaint

        # 5. Handle Invalidation
        if val_result.outcome == ValidationOutcome.INVALID:
            complaint.transition_to(
                ComplaintStatus.INVALID,
                note=f"Determined invalid by AI Validator: {val_result.reason}",
            )
            # Add customer-care escalation contact if available
            complaint.customer_care_escalation = {
                "escalation_available": True,
                "customer_care_contact": self.customer_care_contact,
                "advisory": (
                    f"If you believe this assessment is incorrect, you may contact customer care"
                    f"{' at ' + self.customer_care_contact if self.customer_care_contact else ''} "
                    "for manual inspection and dispute escalation."
                ),
            }
            self.repository.save(complaint)
            return complaint

        # 6. Stage 2: Severity Scoring Agent (for PLAUSIBLE or INCONCLUSIVE)
        complaint.transition_to(ComplaintStatus.SCORING, note="Complaint Severity Scoring Agent evaluating priority.")
        self.repository.save(complaint)

        try:
            severity_res = self.scoring_agent.score_complaint(
                category_id=category.category_id,
                category_data=request.category_data,
                title=request.title,
                description=request.description,
            )
            complaint.severity_result = severity_res
        except Exception as e:
            logger.error("Scoring Agent failed unexpectedly: %s", e, exc_info=True)
            complaint.transition_to(ComplaintStatus.PROCESSING_FAILED, note=f"Scoring error: {e}")
            self.repository.save(complaint)
            return complaint

        # 7. Final Registration Snapshot
        complaint.registration_metadata = {
            "registration_status": "REGISTERED",
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": "1.0",
            "workflow_version": "1.0",
            "gridvision_reference_id": complaint.id,
            "validation_outcome": val_result.outcome.value,
            "assigned_severity_level": severity_res.severity_level.value,
            "assigned_severity_score": severity_res.severity_score,
            "persistence_system": "GridVision Relational Store",
        }
        complaint.transition_to(
            ComplaintStatus.REGISTERED,
            note=f"Successfully registered with severity {severity_res.severity_level.value} ({severity_res.severity_score:.1f}).",
        )

        self.repository.save(complaint)
        return complaint

