"""Domain entities and value objects for the GridVision Complaint Management system.

Designed for customer segment agnosticism (supports RESIDENTIAL now, COMMERCIAL extensible).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CustomerSegment(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"


class ComplaintStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    VALIDATING = "VALIDATING"
    INVALID = "INVALID"
    SCORING = "SCORING"
    REGISTERED = "REGISTERED"
    PROCESSING_FAILED = "PROCESSING_FAILED"


class ValidationOutcome(str, Enum):
    INVALID = "INVALID"
    PLAUSIBLE = "PLAUSIBLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class SeverityLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class EvidenceItem(BaseModel):
    """Specific verifiable evidence collected during validation."""
    source_tool: str
    metric_name: str
    observed_value: Any
    expected_or_contradicting_value: Optional[Any] = None
    timestamp_range: Optional[str] = None
    finding: str
    supports_invalidation: bool = False


class ValidationResult(BaseModel):
    """Structured, auditable output from the Complaint Validator Agent."""
    outcome: ValidationOutcome
    reason: str
    explanation: str
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    data_coverage: str = "complete"  # complete, partial, unavailable
    timestamps_checked: List[str] = Field(default_factory=list)
    validated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScoringFactorBreakdown(BaseModel):
    """Individual factor assessments used in deterministic severity calculation."""
    safety_risk: float = Field(0.0, ge=0.0, le=100.0, description="Risk to person or property (0-100)")
    disruption_extent: float = Field(0.0, ge=0.0, le=100.0, description="Breadth of electrical failure (0-100)")
    duration_factor: float = Field(0.0, ge=0.0, le=100.0, description="Duration or ongoing nature of condition (0-100)")
    recurrence_factor: float = Field(0.0, ge=0.0, le=100.0, description="Frequency/recurrence history (0-100)")
    essential_services_impact: float = Field(0.0, ge=0.0, le=100.0, description="Impact on medical, food, heating (0-100)")
    safety_override_applied: bool = False
    override_reason: Optional[str] = None


class SeverityResult(BaseModel):
    """Structured, reproducible output from the Complaint Severity Scoring Agent."""
    severity_score: float = Field(..., ge=0.0, le=100.0)
    severity_level: SeverityLevel
    scoring_rationale: str
    factor_breakdown: ScoringFactorBreakdown
    benchmark_version: str = "v1.0-approved"
    scored_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StatusTransition(BaseModel):
    """Traceable state transition record."""
    from_status: Optional[str]
    to_status: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    note: Optional[str] = None


class Complaint(BaseModel):
    """Authoritative Complaint aggregate root."""
    id: str = Field(default_factory=lambda: f"CMP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}")
    customer_id: str
    meter_id: str
    customer_segment: CustomerSegment = CustomerSegment.RESIDENTIAL
    category_id: str
    category_label: str
    title: str
    description: str
    category_data: Dict[str, Any] = Field(default_factory=dict)
    status: ComplaintStatus = ComplaintStatus.SUBMITTED
    validation_result: Optional[ValidationResult] = None
    severity_result: Optional[SeverityResult] = None
    status_history: List[StatusTransition] = Field(default_factory=list)
    customer_care_escalation: Optional[Dict[str, Any]] = None
    registration_metadata: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def transition_to(self, new_status: ComplaintStatus, note: Optional[str] = None) -> None:
        """Record status transition with audit note."""
        old = self.status.value if self.status else None
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.status_history.append(
            StatusTransition(from_status=old, to_status=new_status.value, note=note)
        )

