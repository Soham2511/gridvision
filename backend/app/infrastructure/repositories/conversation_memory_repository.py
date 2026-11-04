"""Repository for persistent customer memories, conversation sessions, and tool execution logs.

Enforces strict customer isolation: Customer A can never access or modify Customer B's records.
Returns decoupled data containers to avoid SQLAlchemy DetachedInstanceError across session boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.infrastructure.database.connection import get_engine, get_session
from app.infrastructure.database.models import Base
from app.infrastructure.database.models.conversation_memory import (
    ConversationMessageModel,
    ConversationSessionModel,
    CustomerMemoryModel,
    ToolExecutionModel,
)
from app.services.assistant.memory_contracts import (
    ActiveConversationState,
    CustomerMemoryItem,
    ToolExecutionReference,
)

logger = logging.getLogger("gridvision.repositories.conversation_memory")


@dataclass
class ConversationSessionData:
    """Decoupled representation of a conversation session across database transactions."""
    id: str
    user_id: str
    meter_id: str
    persona: str = "residential"
    title: str = "New Chat"
    summary_text: Optional[str] = None
    summary_version: int = 0
    active_workflow: Optional[str] = None
    pending_state_json: Optional[Dict[str, Any]] = None
    collected_fields_json: Optional[Dict[str, Any]] = None
    is_active: bool = True
    is_archived: bool = False
    is_title_custom: bool = False
    message_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.id,
            "user_id": self.user_id,
            "userId": self.user_id,
            "meter_id": self.meter_id,
            "meterId": self.meter_id,
            "persona": self.persona,
            "title": self.title or "New Chat",
            "summary_text": self.summary_text,
            "summaryText": self.summary_text,
            "summary_version": self.summary_version,
            "summaryVersion": self.summary_version,
            "active_workflow": self.active_workflow,
            "activeWorkflow": self.active_workflow,
            "pending_state": self.pending_state_json,
            "collected_fields": self.collected_fields_json or {},
            "is_active": self.is_active,
            "isActive": self.is_active,
            "is_archived": self.is_archived,
            "isArchived": self.is_archived,
            "is_title_custom": self.is_title_custom,
            "isTitleCustom": self.is_title_custom,
            "message_count": self.message_count,
            "messageCount": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConversationMemoryRepository:
    """Provides customer-isolated data access for memories, sessions, and tool executions."""

    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory
        # Ensure database tables exist
        try:
            eng = get_engine()
            Base.metadata.create_all(bind=eng)
            with eng.begin() as conn:
                try:
                    conn.exec_driver_sql("ALTER TABLE customer_memories ADD COLUMN version INTEGER DEFAULT 1")
                except Exception:
                    pass
                try:
                    conn.exec_driver_sql("ALTER TABLE conversation_sessions ADD COLUMN is_archived BOOLEAN DEFAULT 0")
                except Exception:
                    pass
                try:
                    conn.exec_driver_sql("ALTER TABLE conversation_sessions ADD COLUMN is_title_custom BOOLEAN DEFAULT 0")
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Database metadata creation notice: %s", exc)

    def _get_session(self):
        return get_session(self.session_factory)

    # -------------------------------------------------------------------------
    # Layer 3: Persistent Customer Memory
    # -------------------------------------------------------------------------

    def get_memories(
        self,
        user_id: str,
        persona: str = "residential",
        active_only: bool = True,
    ) -> List[CustomerMemoryItem]:
        """Retrieve all memories for the authenticated user, strictly scoped to user_id."""
        clean_user = str(user_id).strip()
        with self._get_session() as session:
            query = session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id == clean_user,
                CustomerMemoryModel.persona == persona,
            )
            if active_only:
                query = query.filter(CustomerMemoryModel.is_active.is_(True))

            rows = query.order_by(CustomerMemoryModel.created_at.desc()).all()
            results: List[CustomerMemoryItem] = []
            for r in rows:
                val = r.value_json if r.value_json is not None else r.value_text
                results.append(
                    CustomerMemoryItem(
                        id=r.id,
                        user_id=r.user_id,
                        persona=r.persona,
                        category=r.category,
                        key=r.key,
                        value=val,
                        source_conversation_id=r.source_conversation_id,
                        source_message=r.source_message,
                        confidence=r.confidence,
                        version=getattr(r, "version", 1) or 1,
                        is_verified=r.is_verified,
                        is_active=r.is_active,
                        created_at=r.created_at,
                        updated_at=r.updated_at,
                    )
                )
            return results

    def get_active_memories(
        self,
        user_id: str,
        category: Optional[Any] = None,
        persona: str = "residential",
    ) -> List[CustomerMemoryItem]:
        """Convenience method returning all active memories, optionally filtered by category."""
        all_mems = self.get_memories(user_id=user_id, persona=persona, active_only=True)
        if category:
            cat_str = category.value if hasattr(category, "value") else str(category)
            return [m for m in all_mems if m.category.lower() == cat_str.lower()]
        return all_mems

    def create_or_update_memory(
        self,
        user_id: str,
        category: Any,
        key: str,
        value: Any,
        confidence: float = 1.0,
        source_turn: Optional[str] = None,
        persona: str = "residential",
    ) -> CustomerMemoryItem:
        """Convenience method to create or update a memory item directly."""
        cat_str = category.value if hasattr(category, "value") else str(category)
        item = CustomerMemoryItem(
            user_id=user_id,
            persona=persona,
            category=cat_str,
            key=key,
            value=value,
            confidence=confidence,
            source_message=source_turn,
        )
        return self.save_or_update_memory(user_id, item)

    def get_memory_by_key(
        self,
        user_id: str,
        key: str,
        category: Optional[str] = None,
    ) -> Optional[CustomerMemoryItem]:
        """Find a specific active memory for a user by key and category."""
        clean_user = str(user_id).strip()
        clean_key = str(key).strip().lower()
        with self._get_session() as session:
            query = session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id == clean_user,
                CustomerMemoryModel.key == clean_key,
                CustomerMemoryModel.is_active.is_(True),
            )
            if category:
                query = query.filter(CustomerMemoryModel.category == category)
            row = query.first()
            if not row:
                return None
            val = row.value_json if row.value_json is not None else row.value_text
            return CustomerMemoryItem(
                id=row.id,
                user_id=row.user_id,
                persona=row.persona,
                category=row.category,
                key=row.key,
                value=val,
                source_conversation_id=row.source_conversation_id,
                source_message=row.source_message,
                confidence=row.confidence,
                version=getattr(row, "version", 1) or 1,
                is_verified=row.is_verified,
                is_active=row.is_active,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def save_or_update_memory(
        self,
        user_id: str,
        item: CustomerMemoryItem,
    ) -> CustomerMemoryItem:
        """Create or update a customer memory record enforcing user ownership."""
        clean_user = str(user_id).strip()
        clean_key = str(item.key).strip().lower()
        clean_category = str(item.category).strip().lower()

        val_text = item.value if isinstance(item.value, str) else json.dumps(item.value, default=str)
        val_json = item.value if isinstance(item.value, (dict, list, bool, int, float)) else None

        with self._get_session() as session:
            existing = session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id == clean_user,
                CustomerMemoryModel.category == clean_category,
                CustomerMemoryModel.key == clean_key,
            ).first()

            now = datetime.utcnow()
            if existing:
                existing.value_text = val_text
                existing.value_json = val_json
                existing.confidence = item.confidence
                existing.version = (getattr(existing, "version", 1) or 1) + 1
                existing.is_verified = item.is_verified
                existing.is_active = True
                existing.source_conversation_id = item.source_conversation_id or existing.source_conversation_id
                existing.source_message = item.source_message or existing.source_message
                existing.updated_at = now
                session.flush()
                item.id = existing.id
                item.version = existing.version
                item.created_at = existing.created_at
                item.updated_at = existing.updated_at
            else:
                new_id = item.id or str(uuid.uuid4())
                new_row = CustomerMemoryModel(
                    id=new_id,
                    user_id=clean_user,
                    persona=item.persona,
                    category=clean_category,
                    key=clean_key,
                    value_text=val_text,
                    value_json=val_json,
                    source_conversation_id=item.source_conversation_id,
                    source_message=item.source_message,
                    confidence=item.confidence,
                    version=1,
                    is_verified=item.is_verified,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_row)
                session.flush()
                item.id = new_row.id
                item.version = new_row.version
                item.created_at = new_row.created_at
                item.updated_at = new_row.updated_at

            return item

    def delete_memory(self, user_id: str, key_or_id: str) -> bool:
        """Soft-delete memory for the user (sets is_active=False). Never modifies other customers' data."""
        clean_user = str(user_id).strip()
        target = str(key_or_id).strip()
        with self._get_session() as session:
            row = session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id == clean_user,
                (CustomerMemoryModel.id == target) | (CustomerMemoryModel.key == target.lower()),
            ).first()
            if not row:
                return False
            row.is_active = False
            row.updated_at = datetime.utcnow()
            return True

    # -------------------------------------------------------------------------
    # Layer 1 & 2: Conversation Sessions and Messages
    # -------------------------------------------------------------------------

    def get_or_create_session(
        self,
        conversation_id: Optional[str],
        user_id: str,
        meter_id: str,
        persona: str = "residential",
    ) -> ConversationSessionData:
        """Retrieve existing session ensuring user ownership, or create a new session scoped to user and meter."""
        clean_user = str(user_id).strip()
        clean_meter = str(meter_id).strip()

        with self._get_session() as session:
            if conversation_id:
                clean_conv_id = str(conversation_id).strip()
                existing_any = session.query(ConversationSessionModel).filter(
                    ConversationSessionModel.id == clean_conv_id,
                ).first()
                if existing_any:
                    if existing_any.user_id != clean_user:
                        raise PermissionError(
                            f"Access denied: conversation session '{clean_conv_id}' belongs to another user"
                        )
                    return ConversationSessionData(
                        id=existing_any.id,
                        user_id=existing_any.user_id,
                        meter_id=existing_any.meter_id,
                        persona=existing_any.persona,
                        title=existing_any.title or "New Chat",
                        summary_text=existing_any.summary_text,
                        summary_version=existing_any.summary_version or 0,
                        active_workflow=existing_any.active_workflow,
                        pending_state_json=existing_any.pending_state_json,
                        collected_fields_json=existing_any.collected_fields_json or {},
                        is_active=existing_any.is_active,
                        is_archived=bool(getattr(existing_any, "is_archived", False)),
                        is_title_custom=bool(getattr(existing_any, "is_title_custom", False)),
                        created_at=existing_any.created_at,
                        updated_at=existing_any.updated_at,
                    )

            # Create new session
            new_id = str(conversation_id).strip() if conversation_id else f"conv_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow()
            new_session = ConversationSessionModel(
                id=new_id,
                user_id=clean_user,
                meter_id=clean_meter,
                persona=persona,
                title="New Chat",
                summary_text=None,
                summary_version=0,
                active_workflow=None,
                pending_state_json=None,
                collected_fields_json={},
                is_active=True,
                is_archived=False,
                is_title_custom=False,
                created_at=now,
                updated_at=now,
            )
            session.add(new_session)
            session.flush()
            return ConversationSessionData(
                id=new_session.id,
                user_id=new_session.user_id,
                meter_id=new_session.meter_id,
                persona=new_session.persona,
                title=new_session.title,
                summary_text=new_session.summary_text,
                summary_version=new_session.summary_version,
                active_workflow=new_session.active_workflow,
                pending_state_json=new_session.pending_state_json,
                collected_fields_json=new_session.collected_fields_json,
                is_active=new_session.is_active,
                is_archived=bool(new_session.is_archived),
                is_title_custom=bool(new_session.is_title_custom),
                created_at=new_session.created_at,
                updated_at=new_session.updated_at,
            )

    def get_session(self, conversation_id: str, user_id: str) -> Optional[ConversationSessionData]:
        """Fetch a session strictly validating user ownership."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            row = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not row:
                return None
            msg_count = session.query(ConversationMessageModel).filter(
                ConversationMessageModel.conversation_id == row.id
            ).count()
            return ConversationSessionData(
                id=row.id,
                user_id=row.user_id,
                meter_id=row.meter_id,
                persona=row.persona,
                title=row.title or "New Chat",
                summary_text=row.summary_text,
                summary_version=row.summary_version or 0,
                active_workflow=row.active_workflow,
                pending_state_json=row.pending_state_json,
                collected_fields_json=row.collected_fields_json or {},
                is_active=row.is_active,
                is_archived=bool(getattr(row, "is_archived", False)),
                is_title_custom=bool(getattr(row, "is_title_custom", False)),
                message_count=msg_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_sessions(
        self,
        user_id: str,
        persona: str = "residential",
        include_archived: bool = False,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConversationSessionData]:
        """List conversation sessions for authenticated user ordered by most recently active first."""
        clean_user = str(user_id).strip()
        with self._get_session() as session:
            query = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.user_id == clean_user,
                ConversationSessionModel.persona == persona,
            )
            if active_only:
                query = query.filter(ConversationSessionModel.is_active.is_(True))
            if not include_archived:
                query = query.filter(
                    (ConversationSessionModel.is_archived.is_(False))
                    | (ConversationSessionModel.is_archived.is_(None))
                )

            # Order by most recently active conversation first
            query = query.order_by(ConversationSessionModel.updated_at.desc())
            rows = query.offset(offset).limit(limit).all()

            results: List[ConversationSessionData] = []
            for r in rows:
                msg_count = session.query(ConversationMessageModel).filter(
                    ConversationMessageModel.conversation_id == r.id
                ).count()
                results.append(
                    ConversationSessionData(
                        id=r.id,
                        user_id=r.user_id,
                        meter_id=r.meter_id,
                        persona=r.persona,
                        title=r.title or "New Chat",
                        summary_text=r.summary_text,
                        summary_version=r.summary_version or 0,
                        active_workflow=r.active_workflow,
                        pending_state_json=r.pending_state_json,
                        collected_fields_json=r.collected_fields_json or {},
                        is_active=r.is_active,
                        is_archived=bool(getattr(r, "is_archived", False)),
                        is_title_custom=bool(getattr(r, "is_title_custom", False)),
                        message_count=msg_count,
                        created_at=r.created_at,
                        updated_at=r.updated_at,
                    )
                )
            return results

    def create_session(
        self,
        user_id: str,
        meter_id: str,
        title: str = "New Chat",
        persona: str = "residential",
    ) -> ConversationSessionData:
        """Create an explicitly fresh, independently managed conversation session."""
        clean_user = str(user_id).strip()
        clean_meter = str(meter_id).strip()
        new_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        with self._get_session() as session:
            new_row = ConversationSessionModel(
                id=new_id,
                user_id=clean_user,
                meter_id=clean_meter,
                persona=persona,
                title=title or "New Chat",
                summary_text=None,
                summary_version=0,
                active_workflow=None,
                pending_state_json=None,
                collected_fields_json={},
                is_active=True,
                is_archived=False,
                is_title_custom=False,
                created_at=now,
                updated_at=now,
            )
            session.add(new_row)
            session.flush()
            return ConversationSessionData(
                id=new_row.id,
                user_id=new_row.user_id,
                meter_id=new_row.meter_id,
                persona=new_row.persona,
                title=new_row.title,
                summary_text=new_row.summary_text,
                summary_version=new_row.summary_version,
                active_workflow=new_row.active_workflow,
                pending_state_json=new_row.pending_state_json,
                collected_fields_json=new_row.collected_fields_json or {},
                is_active=new_row.is_active,
                is_archived=new_row.is_archived,
                is_title_custom=new_row.is_title_custom,
                message_count=0,
                created_at=new_row.created_at,
                updated_at=new_row.updated_at,
            )

    def update_session_title(
        self,
        conversation_id: str,
        user_id: str,
        title: str,
        is_custom: bool = True,
    ) -> bool:
        """Rename a conversation validating user ownership."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        clean_title = str(title).strip()
        if not clean_title or len(clean_title) > 100:
            raise ValueError("Conversation title must be between 1 and 100 characters")

        with self._get_session() as session:
            existing = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
            ).first()
            if not existing:
                return False
            if existing.user_id != clean_user:
                raise PermissionError(f"Access denied: Session '{clean_conv}' does not belong to user '{clean_user}'")
            existing.title = clean_title
            existing.is_title_custom = is_custom
            existing.updated_at = datetime.utcnow()
            return True

    def archive_session(
        self,
        conversation_id: str,
        user_id: str,
        is_archived: bool = True,
    ) -> bool:
        """Archive or unarchive a conversation validating user ownership."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            row = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not row:
                return False
            row.is_archived = is_archived
            row.updated_at = datetime.utcnow()
            return True

    def delete_session(
        self,
        conversation_id: str,
        user_id: str,
    ) -> bool:
        """Soft-delete a conversation ensuring user ownership. Clears pending state without touching persistent memory."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            row = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not row:
                return False
            row.is_active = False
            row.active_workflow = None
            row.pending_state_json = None
            row.updated_at = datetime.utcnow()
            return True

    def auto_generate_session_title(
        self,
        conversation_id: str,
        user_id: str,
        first_user_message: str,
        first_assistant_message: Optional[str] = None,
    ) -> Optional[str]:
        """Automatically generate a concise, relevant 3-7 word title from the initial conversation turn.
        
        Does not overwrite if customer manually edited the title (is_title_custom is True)
        or if title is already meaningful (not 'New Chat', 'Residential Assistant Conversation', or empty).
        """
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            sess = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not sess:
                return None

            # Guard against overwriting customer-customized or already-named sessions
            is_custom = bool(getattr(sess, "is_title_custom", False))
            current_title = (sess.title or "").strip()
            if is_custom:
                return current_title
            if current_title and current_title not in ("New Chat", "Residential Assistant Conversation", "Untitled Conversation", ""):
                return current_title

            # Generate title from conversation content
            generated_title = self._derive_topic_title(first_user_message, first_assistant_message)
            if generated_title and len(generated_title) >= 3:
                sess.title = generated_title
                sess.is_title_custom = False
                sess.updated_at = datetime.utcnow()
                session.flush()
                return generated_title
            return current_title or "New Chat"

    @staticmethod
    def _derive_topic_title(user_prompt: str, assistant_reply: Optional[str] = None) -> str:
        """Derive a concise, human-readable 3-7 word title based on actual conversation topic."""
        p = user_prompt.strip()
        p_low = p.lower()

        # 1. Topic: House energy planning / new home
        if any(w in p_low for w in ["new house", "new home", "plan house", "house plan", "connected load", "electrical layout", "wiring", "electrical load", "plan my villa", "load planning", "4bhk", "3bhk", "2bhk"]):
            return "New Home Energy Planning"

        # 2. Topic: AC selection, replacement or upgrade
        if any(w in p_low for w in ["replace ac", "choose an ac", "which ac", "inverter ac", "5-star ac", "split ac", "air conditioner"]):
            return "AC Replacement Comparison"

        # 3. Topic: Electricity bill inquiry / spike / charges
        if any(w in p_low for w in ["bill increased", "bill increase", "why was my bill", "why is my bill", "explain my bill", "electricity bill", "high bill", "bill spike"]):
            return "Understanding My Electricity Bill"

        # 4. Topic: Consumption / telemetry / daily average
        if any(w in p_low for w in ["consumption", "actual consumption", "how much electricity", "daily usage", "daily average", "last month's usage", "kwh", "yesterday"]):
            return "Monthly Energy Consumption"

        # 5. Topic: Solar PV installation, sizing or subsidies
        if any(w in p_low for w in ["solar", "rooftop", "pv", "surya ghar", "solar panel", "solar cost"]):
            return "Solar Installation Questions"

        # 6. Topic: Power cut, outage, safety or supply issues
        if any(w in p_low for w in ["power cut", "outage", "sparking", "voltage", "blackout", "tripping", "supply issue"]):
            return "Electricity Supply Issue"

        # 7. Topic: Appliance comparison or energy efficiency
        if any(w in p_low for w in ["bldc", "ceiling fan", "refrigerator", "geyser", "appliance", "payback", "iseer"]):
            return "Appliance Efficiency & Payback"

        # 8. Topic: Electricity tariff rates
        if any(w in p_low for w in ["tariff", "peak tariff", "tariff rate", "slab", "per kwh"]):
            return "Electricity Tariff Inquiries"

        # 9. Topic: Electrical safety guidelines
        if any(w in p_low for w in ["safety", "shock", "earthing", "grounding", "rccb", "elcb"]):
            return "Electrical Safety Guidelines"

        # Fallback heuristic: clean greetings and extract 3-6 key words
        clean = re.sub(
            r"^(hello|hi|hey|please|can you|could you|i want to|i need to|tell me|explain to me|help me with|what is|how do i)\s+",
            "",
            p,
            flags=re.IGNORECASE,
        ).strip()
        clean = re.sub(r"[?!.,:;]+$", "", clean).strip()

        words = clean.split()
        if 2 <= len(words) <= 7:
            return " ".join(words).title()
        elif len(words) > 7:
            return " ".join(words[:6]).title()
        elif len(words) == 1 and len(words[0]) > 2:
            return f"{words[0].title()} Energy Inquiries"

        return "New Chat"

    def update_session_state(
        self,
        conversation_id: str,
        user_id: str,
        active_state: ActiveConversationState,
        summary_text: Optional[str] = None,
        title: Optional[str] = None,
    ) -> bool:
        """Persist active conversational state and rolling summary for a user's session."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            sess = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not sess:
                return False

            sess.active_workflow = active_state.active_workflow
            sess.pending_state_json = active_state.model_dump(mode="json")
            sess.collected_fields_json = active_state.collected_fields
            if summary_text:
                sess.summary_text = summary_text
                sess.summary_version = (sess.summary_version or 0) + 1
            if title:
                sess.title = title
            sess.updated_at = datetime.utcnow()
            return True

    def save_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        mode: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Save a message record verifying session ownership."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            sess = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not sess:
                # Fallback create session to guarantee referential integrity
                sess = ConversationSessionModel(
                    id=clean_conv,
                    user_id=clean_user,
                    meter_id="METER-1000",
                    persona="residential",
                    is_active=True,
                )
                session.add(sess)
                session.flush()

            msg_id = f"msg_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow()
            msg = ConversationMessageModel(
                id=msg_id,
                conversation_id=sess.id,
                role=role,
                content=content,
                mode=mode,
                metadata_json=metadata or {},
                created_at=now,
            )
            session.add(msg)
            sess.updated_at = now
            session.flush()
            return {
                "id": msg_id,
                "conversation_id": sess.id,
                "role": role,
                "content": content,
                "mode": mode,
                "created_at": now.isoformat(),
            }

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str = "default_user",
        mode: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convenience alias for saving messages in a conversation."""
        return self.save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            mode=mode,
            metadata=metadata,
        )

    def get_session_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve message history for an authorized conversation."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            sess = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not sess:
                return []

            rows = (
                session.query(ConversationMessageModel)
                .filter(ConversationMessageModel.conversation_id == clean_conv)
                .order_by(ConversationMessageModel.created_at.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "mode": r.mode,
                    "metadata": r.metadata_json,
                    "timestamp": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    # -------------------------------------------------------------------------
    # Tool Execution Reference Continuity
    # -------------------------------------------------------------------------

    def save_tool_execution(
        self,
        tool_exec: ToolExecutionReference,
    ) -> ToolExecutionReference:
        """Store structured execution record of a domain tool for follow-up reference."""
        clean_user = str(tool_exec.user_id).strip()
        clean_conv = str(tool_exec.conversation_id).strip()
        with self._get_session() as session:
            # Verify session exists
            sess = session.query(ConversationSessionModel).filter(
                ConversationSessionModel.id == clean_conv,
                ConversationSessionModel.user_id == clean_user,
            ).first()
            if not sess:
                sess = ConversationSessionModel(
                    id=clean_conv,
                    user_id=clean_user,
                    meter_id=tool_exec.meter_id,
                    persona="residential",
                    is_active=True,
                )
                session.add(sess)
                session.flush()

            row = ToolExecutionModel(
                id=tool_exec.execution_id or str(uuid.uuid4()),
                conversation_id=sess.id,
                user_id=clean_user,
                meter_id=tool_exec.meter_id,
                tool_name=tool_exec.tool_name,
                parameters_json=tool_exec.parameters,
                result_summary_json=tool_exec.result_summary,
                data_period=tool_exec.data_period,
                status=tool_exec.status,
                created_at=tool_exec.created_at or datetime.utcnow(),
            )
            session.add(row)
            return tool_exec

    def get_last_tool_execution(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Optional[ToolExecutionReference]:
        """Retrieve most recent tool execution record for this conversation."""
        clean_user = str(user_id).strip()
        clean_conv = str(conversation_id).strip()
        with self._get_session() as session:
            row = (
                session.query(ToolExecutionModel)
                .filter(
                    ToolExecutionModel.conversation_id == clean_conv,
                    ToolExecutionModel.user_id == clean_user,
                )
                .order_by(ToolExecutionModel.created_at.desc())
                .first()
            )
            if not row:
                return None
            return ToolExecutionReference(
                execution_id=row.id,
                conversation_id=row.conversation_id,
                user_id=row.user_id,
                meter_id=row.meter_id,
                tool_name=row.tool_name,
                parameters=row.parameters_json or {},
                result_summary=row.result_summary_json or {},
                data_period=row.data_period,
                status=row.status,
                created_at=row.created_at,
            )

    def get_tool_execution(
        self,
        execution_id: str,
        user_id: str,
    ) -> Optional[ToolExecutionReference]:
        """Retrieve a specific tool execution record strictly verifying user ownership."""
        clean_user = str(user_id).strip()
        clean_id = str(execution_id).strip()
        with self._get_session() as session:
            row = (
                session.query(ToolExecutionModel)
                .filter(
                    ToolExecutionModel.id == clean_id,
                    ToolExecutionModel.user_id == clean_user,
                )
                .first()
            )
            if not row:
                return None
            return ToolExecutionReference(
                execution_id=row.id,
                conversation_id=row.conversation_id,
                user_id=row.user_id,
                meter_id=row.meter_id,
                tool_name=row.tool_name,
                parameters=row.parameters_json or {},
                result_summary=row.result_summary_json or {},
                data_period=row.data_period,
                status=row.status,
                created_at=row.created_at,
            )

    get_customer_memories = get_active_memories

    def get_active_state(self, conversation_id: str, user_id: str) -> Optional[ActiveConversationState]:
        """Convenience method to retrieve typed active conversation state."""
        sess = self.get_session(conversation_id=conversation_id, user_id=user_id)
        if not sess or not sess.pending_state_json:
            return None
        try:
            return ActiveConversationState.model_validate(sess.pending_state_json)
        except Exception:
            return None

    def save_active_state(self, conversation_id: str, active_state: ActiveConversationState, user_id: str) -> bool:
        """Convenience method to persist typed active conversation state."""
        return self.update_session_state(
            conversation_id=conversation_id,
            user_id=user_id,
            active_state=active_state,
        )
