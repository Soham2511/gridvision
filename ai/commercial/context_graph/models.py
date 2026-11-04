"""Typed, provenance-bearing entities and relationships for factory context."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ContextEntityType = Literal[
    "Factory",
    "Department",
    "ProductionLine",
    "Machine",
    "Operation",
    "EnergySource",
    "Constraint",
    "MaintenanceProcedure",
    "ProductionTarget",
    "Guideline",
    "SourceDocument",
    "Passage",
]

ContextRelationship = Literal[
    "HAS_DEPARTMENT",
    "CONTAINS",
    "PERFORMS",
    "DEPENDS_ON",
    "CONSUMES",
    "PRODUCES",
    "REQUIRES",
    "RESTRICTED_BY",
    "MAINTAINED_BY",
    "OPTIMIZABLE_BY",
    "FEEDS",
    "SUPPORTED_BY",
    "ABOUT_TOPIC",
    "HAS_PASSAGE",
    "HAS_CONSTRAINT",
]


class ContextEntity(BaseModel):
    """Entity extracted from a source passage with stable identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1, max_length=500)
    entity_type: ContextEntityType
    label: str = Field(min_length=1, max_length=500)
    properties: dict[str, Any] = Field(default_factory=dict)
    source_id: str = Field(min_length=1, max_length=500)
    page_number: int = Field(ge=1)
    section: str | None = Field(default=None, max_length=500)
    evidence_chunk_id: str = Field(min_length=1, max_length=128)
    extraction_confidence: float = Field(ge=0, le=1)


class ContextRelationshipEdge(BaseModel):
    """Relationship between graph entities, tied to the passage supporting it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_entity_id: str = Field(min_length=1, max_length=500)
    target_entity_id: str = Field(min_length=1, max_length=500)
    relationship: ContextRelationship
    source_id: str = Field(min_length=1, max_length=500)
    page_number: int = Field(ge=1)
    section: str | None = Field(default=None, max_length=500)
    evidence_chunk_id: str = Field(min_length=1, max_length=128)
    extraction_confidence: float = Field(ge=0, le=1)


class PassageGraph(BaseModel):
    """Entities and edges conservatively extracted from one passage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entities: tuple[ContextEntity, ...] = ()
    relationships: tuple[ContextRelationshipEdge, ...] = ()
