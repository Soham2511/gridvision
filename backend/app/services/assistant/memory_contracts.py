"""Typed schemas and contracts for customer persistent memory, dialogue state, and tool routing."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MemoryCategory(str, Enum):
    """Classification of persistent customer memories."""
    PREFERENCE = "preference"
    PROPERTY = "property"
    APPLIANCE = "appliance"
    CONSTRAINT = "constraint"
    PRIORITY = "priority"


class CustomerMemoryItem(BaseModel):
    """Single persistent customer memory fact."""
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    user_id: str
    persona: str = "residential"
    category: str = MemoryCategory.PREFERENCE.value
    key: str
    value: Any
    source_conversation_id: Optional[str] = None
    source_message: Optional[str] = None
    confidence: float = 1.0
    version: int = 1
    is_verified: bool = True
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PendingQuestion(BaseModel):
    """Representation of an outstanding question asked to the customer."""
    model_config = ConfigDict(extra="ignore")

    field: str
    question: str
    expected_response_type: str = "string"  # string, integer, float, choice, boolean
    valid_options: Optional[List[str]] = None
    clarification_prompt: Optional[str] = None
    workflow: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list)
    collected_fields: Dict[str, Any] = Field(default_factory=dict)


class ActiveConversationState(BaseModel):
    """Structured active conversational state across turns within a conversation."""
    model_config = ConfigDict(extra="ignore")

    active_workflow: Optional[str] = None
    awaiting_user_response: bool = False
    pending_question: Optional[PendingQuestion] = None
    pending_questions_queue: List[PendingQuestion] = Field(default_factory=list)
    collected_fields: Dict[str, Any] = Field(default_factory=dict)
    required_missing_fields: List[str] = Field(default_factory=list)
    last_topic: Optional[str] = None
    last_intent: Optional[str] = None
    last_tool_execution: Optional[Dict[str, Any]] = None
    # Support for suspended workflows when user changes topic temporarily
    suspended_workflow: Optional[str] = None
    suspended_collected_fields: Optional[Dict[str, Any]] = None
    suspended_pending_question: Optional[PendingQuestion] = None


class ToolExecutionReference(BaseModel):
    """Structured tool execution record for follow-up explanations and recalculations."""
    model_config = ConfigDict(extra="ignore")

    execution_id: str
    conversation_id: str
    user_id: str
    meter_id: str
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result_summary: Dict[str, Any] = Field(default_factory=dict)
    data_period: Optional[str] = None
    status: str = "success"
    created_at: Optional[datetime] = None


class ConversationSummary(BaseModel):
    """Rolling summary of older dialogue turns in a conversation."""
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    user_id: str
    summary_text: str
    main_topic: Optional[str] = None
    user_goal: Optional[str] = None
    established_requirements: Dict[str, Any] = Field(default_factory=dict)
    confirmed_facts: List[str] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    decisions_and_conclusions: List[str] = Field(default_factory=list)
    key_calculation_results: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    updated_at: Optional[datetime] = None


class TurnRoutingPlan(BaseModel):
    """Deterministic routing decision for current customer turn."""
    model_config = ConfigDict(extra="ignore")

    primary_intent: str
    secondary_intent: Optional[str] = None
    is_continuation: bool = False
    follow_up_type: Optional[str] = None  # answer_to_pending, partial_answer, continuation, correction, reference_to_result, topic_change, new_request
    resolved_workflow: Optional[str] = None
    resolved_tool_scope: str = "all"
    recommended_tools: List[str] = Field(default_factory=list)
    routed_tool_arguments: Dict[str, Any] = Field(default_factory=dict)
    requires_tool_execution: bool = True
    answered_field: Optional[str] = None
    answered_value: Optional[Any] = None
    is_topic_change: bool = False
    effective_prompt: str
    explanation: Optional[str] = None

    @property
    def tool_scope(self) -> str:
        return self.resolved_tool_scope

    @property
    def candidate_tools(self) -> List[str]:
        return self.recommended_tools
