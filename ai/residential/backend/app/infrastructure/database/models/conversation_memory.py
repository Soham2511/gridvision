"""Database models for customer persistent memory, conversation sessions, messages, and tool executions.

Provides strict customer-level data isolation using authenticated user IDs.
"""

from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from . import Base


class CustomerMemoryModel(Base):
    """Persistent customer-specific facts, preferences, and verified premises information.
    
    Isolated strictly by `user_id`. Never shared across different users.
    """

    __tablename__ = "customer_memories"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)
    persona = Column(String(50), nullable=False, default="residential")
    category = Column(String(50), nullable=False, default="preference")  # preference, property, appliance, constraint, priority
    key = Column(String(100), nullable=False, index=True)
    value_text = Column(Text, nullable=True)
    value_json = Column(JSON, nullable=True)
    source_conversation_id = Column(String(64), nullable=True)
    source_message = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    version = Column(Integer, nullable=False, default=1)
    is_verified = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "category", "key", name="uq_user_memory_category_key"),
        Index("ix_customer_memories_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<CustomerMemoryModel id={self.id} user={self.user_id} key={self.key} active={self.is_active}>"


class ConversationSessionModel(Base):
    """Persistent conversation session capturing dialogue state, active workflow, and rolling summary."""

    __tablename__ = "conversation_sessions"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)
    meter_id = Column(String(100), nullable=False, index=True)
    persona = Column(String(50), nullable=False, default="residential")
    title = Column(String(255), nullable=False, default="New Chat")
    summary_text = Column(Text, nullable=True)
    summary_version = Column(Integer, nullable=False, default=0)
    active_workflow = Column(String(100), nullable=True)
    pending_state_json = Column(JSON, nullable=True)
    collected_fields_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_archived = Column(Boolean, nullable=False, default=False, index=True)
    is_title_custom = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    messages = relationship(
        "ConversationMessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationMessageModel.created_at",
    )

    tool_executions = relationship(
        "ToolExecutionModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ToolExecutionModel.created_at",
    )

    __table_args__ = (
        Index("ix_conversation_sessions_user_meter", "user_id", "meter_id"),
    )

    def __repr__(self) -> str:
        return f"<ConversationSessionModel id={self.id} user={self.user_id} meter={self.meter_id}>"


class ConversationMessageModel(Base):
    """Individual user or assistant message stored persistently within a conversation."""

    __tablename__ = "conversation_messages"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(64), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    mode = Column(String(50), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    session = relationship("ConversationSessionModel", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ConversationMessageModel id={self.id} conv={self.conversation_id} role={self.role}>"


class ToolExecutionModel(Base):
    """Structured tool invocation records and calculated metrics for follow-up continuity and explainability."""

    __tablename__ = "tool_executions"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(64), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    meter_id = Column(String(100), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    parameters_json = Column(JSON, nullable=True)
    result_summary_json = Column(JSON, nullable=True)
    data_period = Column(String(100), nullable=True)
    status = Column(String(30), nullable=False, default="success")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    session = relationship("ConversationSessionModel", back_populates="tool_executions")

    def __repr__(self) -> str:
        return f"<ToolExecutionModel id={self.id} tool={self.tool_name} status={self.status}>"
