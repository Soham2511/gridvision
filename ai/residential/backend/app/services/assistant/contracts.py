"""Shared Knowledge Contracts and Data Transfer Schemas for GridVision Assistant.

Enforces unambiguous data structures across the 7 knowledge sources,
LangGraph agentic state transitions, and the final response contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class KnowledgeSourceType(str, Enum):
    """Authoritative knowledge source classification."""

    DOCUMENT_RAG = "document_rag"
    STRUCTURED_REFERENCE = "structured_reference"
    CUSTOMER_CONTEXT = "customer_context"
    HOUSEHOLD_TELEMETRY = "household_telemetry"
    ML_PREDICTIONS = "ml_predictions"
    DOMAIN_ENGINE = "domain_engine"
    CONVERSATION_SESSION = "conversation_session"


class DocumentCitation(BaseModel):
    """Citation referencing an exact official document passage."""

    source_id: str = Field(..., description="Unique source identifier")
    document_identifier: str = Field(..., description="Official document code or gazette reference (e.g. 'IS 732 / NEC India')")
    publisher: str = Field(..., description="Issuing authority (BIS, CEA, BEE, DISCOM)")
    section: str = Field(..., description="Section title or clause name")
    clause_id: Optional[str] = Field(default=None, description="Clause number if applicable")
    page: int = Field(default=1, description="Page number in original document")
    text_snippet: str = Field(..., description="Verbatim text snippet grounding the answer")
    url: Optional[str] = Field(default=None, description="Official publication URL")


class StructuredReferenceProvenance(BaseModel):
    """Provenance for deterministic parameters resolved via ReferenceResolver."""

    parameter_key: str
    value: Any
    unit: str
    jurisdiction: str = "IN"
    source_document: str
    version: int = 1
    is_verified: bool = True


class CalculationProvenance(BaseModel):
    """Provenance for deterministic domain engine computations."""

    engine_name: str
    use_case: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    key_outputs: Dict[str, Any] = Field(default_factory=dict)
    formula_or_method: Optional[str] = None


class AssistantProvenance(BaseModel):
    """Combined provenance tracking all knowledge sources consulted during query execution."""

    knowledge_sources_used: List[str] = Field(default_factory=list)
    structured_references: List[StructuredReferenceProvenance] = Field(default_factory=list)
    calculations: List[CalculationProvenance] = Field(default_factory=list)


class AssistantResponseContract(BaseModel):
    """Authoritative final assistant response payload returned by API and displayed by Frontend."""

    answer: str = Field(..., description="Conversational, data-grounded response text formatted in GitHub markdown")
    content: Optional[str] = None
    mode: str = Field(default="general_chat", description="Active assistant mode: 'general_chat', 'house_planning', 'appliance_lifecycle', 'cost_management'")
    persona: str = Field(default="household", description="Authorized user persona")
    entityId: Optional[str] = Field(default=None, description="Authorized meter or premise identifier")
    customerName: Optional[str] = Field(default=None, description="Authorized resident name or ID")
    status: str = Field(default="success", description="'success', 'clarification_needed', 'unsupported', 'unauthorized', 'irrelevant'")
    relevance: str = Field(default="relevant", description="'relevant', 'irrelevant', 'partially_relevant'")
    isLlmGenerated: bool = Field(default=False, description="Whether LLM generated the conversational synthesis")
    citations: List[DocumentCitation] = Field(default_factory=list, description="Grounding citations for document claims")
    provenance: AssistantProvenance = Field(default_factory=AssistantProvenance, description="Audit trace of knowledge sources used")
    assumptions: List[str] = Field(default_factory=list, description="Explicit modeling assumptions made")
    limitations: List[str] = Field(default_factory=list, description="Engineering safety and regulatory caveats")
    missing_information: List[str] = Field(default_factory=list, description="Fields or parameters required but unavailable")
    structured_data: Optional[Dict[str, Any]] = Field(default=None, description="Optional structured payload for UI widgets")

    def model_post_init(self, __context: Any) -> None:
        if not self.content:
            self.content = self.answer
        elif not self.answer:
            self.answer = self.content

