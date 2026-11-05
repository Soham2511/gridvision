"""Strict Pydantic schema for Rectification Agent anomaly reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SeverityInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    score: float = Field(ge=0.0, le=1.0, description="Normalized severity score")
    level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(description="Severity classification")
    mean_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_score: float | None = Field(default=None, ge=0.0, le=1.0)


class EventCoordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    latitude: float | None = None
    longitude: float | None = None


class EventDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scope: str = Field(description="SINGLE_CUSTOMER, LOCAL_AREA, or MULTI_AREA")
    start_time: str = Field(description="ISO 8601 start timestamp")
    end_time: str = Field(description="ISO 8601 end timestamp")
    duration_hours: float = Field(ge=0.0, description="Duration in hours")
    affected_customer_count: int = Field(ge=1, description="Number of affected customers")
    coordinates: EventCoordinates | None = None


class GuidanceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(description="Standard or regulatory reference document title")
    publisher: str | None = Field(default=None, description="Publishing organization")
    clause: str | None = Field(default=None, description="Specific clause, chapter, or page")


class RectificationReportPayload(BaseModel):
    """Structured, verified anomaly report produced by the Rectification Agent."""

    model_config = ConfigDict(extra="forbid", strict=True)

    event_id: str = Field(min_length=1, description="Unique anomaly event identifier")
    run_id: str = Field(min_length=1, description="Source anomaly analysis run ID")
    persona: Literal["household", "commercial", "government"] = Field(description="Target persona")
    customer_id: str | int | None = Field(default=None, description="Affected customer or meter ID")
    customer_name: str = Field(default="Customer", description="Resolved customer or entity name")
    customer_email: str | None = Field(default=None, description="Target recipient email for reporting")
    company_name: str = Field(default="GridVision Energy Intelligence", description="Utility or organization")
    
    anomaly_type: str = Field(description="Dominant anomaly classification")
    dominant_anomaly_type: str = Field(description="Dominant anomaly classification")
    anomaly_types: list[str] = Field(default_factory=list, description="All observed anomaly subtypes")
    
    severity: SeverityInfo
    event_details: EventDetails
    
    probable_causes: list[str] = Field(min_length=1, max_length=20, description="Physics-grounded probable causes")
    corrective_actions: list[str] = Field(min_length=1, max_length=20, description="Immediate verification and corrective steps")
    preventive_recommendations: list[str] = Field(min_length=1, max_length=20, description="Long-term preventive engineering recommendations")
    
    guidance_citations: list[GuidanceCitation] = Field(default_factory=list, description="Technical standard citations")
    limitations: list[str] = Field(default_factory=list, description="Data provenance and engineering limits")
    
    generated_at: str = Field(description="ISO 8601 generation timestamp")

    @field_validator("generated_at")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("generated_at must be an ISO 8601 timestamp") from exc
        return value

