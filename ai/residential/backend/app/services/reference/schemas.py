"""Deterministic Pydantic v2 schemas and validation rules for Candidate Reference Data.

Enforces:
- Explicit unit requirement (never assumed, validated against domain-allowed units).
- Explicit temporal boundaries (effective_from required, effective_to >= effective_from).
- Physical plausibility checks (negative efficiencies/ISEER rejected).
- Authoritative reviewer request validation.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EnergyUnitEnum(str, Enum):
    """Allowed engineering and economic units for energy reference data."""
    WH_PER_WH = "Wh/Wh"
    KWH = "kWh"
    KW = "kW"
    W = "W"
    KWH_PER_YEAR = "kWh/year"
    KWH_PER_DAY = "kWh/day"
    INR_PER_KWH = "INR/kWh"
    KG_CO2_PER_KWH = "kg CO2/kWh"
    W_PER_M2 = "W/m²"
    W_PER_M2_ALT = "W/m2"
    INR = "INR"
    PERCENTAGE = "%"
    RATIO = "ratio"
    DIMENSIONLESS = "dimensionless"
    TON = "ton"
    TONS = "tons"
    TR = "TR"
    V = "V"
    HZ = "Hz"
    A = "A"
    KVA = "kVA"
    PF = "PF"
    HOURS_PER_YEAR = "hours/year"


ALLOWED_UNITS = {u.value for u in EnergyUnitEnum}


class CandidateReferenceCreate(BaseModel):
    """Schema for creating and deterministically validating candidate references."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    parameter_key: str = Field(..., min_length=1, description="Registered parameter key")
    raw_value: str = Field(..., min_length=1, description="Verbatim raw string from source")
    normalized_value: Any = Field(..., description="Parsed typed numerical or structured value")
    unit: str = Field(..., description="Validated physical unit")
    jurisdiction: str = Field(..., min_length=1, description="ISO-3166-1 or subdivision code, e.g. IN, KA")
    region: Optional[str] = Field(None, description="DISCOM or regional identifier, e.g. BESCOM")
    applicability_conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Constraints defining applicability (capacity, star rating, tech)",
    )
    effective_from: date = Field(..., description="Start of validity interval")
    effective_to: Optional[date] = Field(None, description="End of validity interval, None if indefinite")
    source_id: str = Field(..., min_length=1, description="Foreign key to source document")
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Citation details: document, page, clause, table, excerpt",
    )
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Extraction confidence score [0.0, 1.0]")
    review_status: str = Field("draft", description="Lifecycle review status")

    @field_validator("unit", mode="before")
    @classmethod
    def validate_unit(cls, v: Any) -> str:
        if v is None:
            raise ValueError("Unit is required and cannot be assumed or null")
        if isinstance(v, EnergyUnitEnum):
            return v.value
        if not isinstance(v, str):
            raise TypeError("Unit must be a string")
        unit_str = v.strip()
        if not unit_str:
            raise ValueError("Unit cannot be empty or whitespace only")
        if unit_str not in ALLOWED_UNITS:
            raise ValueError(f"Unverified or disallowed unit '{unit_str}'. Allowed: {sorted(ALLOWED_UNITS)}")
        return unit_str

    @field_validator("effective_from", mode="before")
    @classmethod
    def validate_effective_from(cls, v: Any) -> date:
        if v is None:
            raise ValueError("effective_from date is required and cannot be assumed")
        return v

    @model_validator(mode="after")
    def validate_temporal_and_domain_rules(self) -> CandidateReferenceCreate:
        # Check temporal order
        if self.effective_to is not None:
            if self.effective_to < self.effective_from:
                raise ValueError(
                    f"effective_to ({self.effective_to}) cannot be earlier than effective_from ({self.effective_from})"
                )

        # Domain physics rule: efficiency, rating, ISEER, power, consumption cannot be negative
        if isinstance(self.normalized_value, (int, float)):
            key_lower = self.parameter_key.lower()
            restricted_terms = ("iseer", "efficiency", "star", "rating", "power", "consumption", "emission", "draw")
            if any(term in key_lower for term in restricted_terms) and self.normalized_value < 0:
                raise ValueError(
                    f"Physically implausible negative value {self.normalized_value} for parameter '{self.parameter_key}'"
                )

        return self


# Contract alias
CandidateReferenceSchema = CandidateReferenceCreate


class CandidateReferenceResponse(BaseModel):
    """Schema for candidate reference responses including system tracking attributes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    parameter_key: str
    raw_value: str
    normalized_value: Any
    unit: str
    jurisdiction: str
    region: Optional[str] = None
    applicability_conditions: dict[str, Any]
    effective_from: date
    effective_to: Optional[date] = None
    source_id: str
    provenance: dict[str, Any]
    confidence: float
    review_status: str
    created_at: datetime
    updated_at: datetime


class ReviewActionRequest(BaseModel):
    """Schema for submitting human review decisions."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"]
    reviewer_id: str = Field(..., min_length=1)
    reason: Optional[str] = None

    @field_validator("reviewer_id")
    @classmethod
    def validate_reviewer_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("reviewer_id cannot be empty or whitespace")
        return s

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> ReviewActionRequest:
        if self.status == "rejected":
            if not self.reason or not self.reason.strip():
                raise ValueError("Rejection requires an explanatory rationale/reason comment")
        return self
