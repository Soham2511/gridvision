"""Conversation Context Manager and Model-Aware Context Budgeting Service.

Assembles the 7 layers of context:
1. Authenticated Customer Scope
2. Persistent Customer Memories (Layer 3)
3. Rolling Conversation Summary (Layer 1)
4. Recent Message Window (Layer 1)
5. Active Conversational State (Layer 2)
6. Tool Execution Reference Continuity
7. Current User Request

Enforces strict context window budgeting to prevent token overflow and rate limit exhaustion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.infrastructure.repositories.conversation_memory_repository import (
    ConversationMemoryRepository,
)
from app.services.assistant.dialogue_state import (
    compact_history_for_llm,
    resolve_dialogue_context,
    ResolvedDialogueState,
)
from app.services.assistant.memory_contracts import (
    ActiveConversationState,
    CustomerMemoryItem,
    PendingQuestion,
    ToolExecutionReference,
)
from app.services.assistant.memory_service import CustomerMemoryService

logger = logging.getLogger("gridvision.services.assistant.context_manager")


@dataclass
class AssembledTurnContext:
    """Consolidated context payload for a single turn."""
    user_id: str
    meter_id: str
    customer_name: str
    tariff_rate: float
    conversation_id: str
    relevant_memories: List[CustomerMemoryItem]
    active_state: ActiveConversationState
    conversation_summary: Optional[str]
    recent_messages: List[Dict[str, str]]
    last_tool_execution: Optional[ToolExecutionReference]
    resolved_state: ResolvedDialogueState
    grounding_system_block: str

    @property
    def rolling_summary(self) -> Optional[Any]:
        if self.conversation_summary:
            from app.services.assistant.memory_contracts import ConversationSummary
            return ConversationSummary(
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                summary_text=self.conversation_summary,
            )
        return None


class ConversationContextManager:
    """Coordinates memory retrieval, active state tracking, rolling summarization, and context budgeting."""

    def __init__(
        self,
        repository: Optional[ConversationMemoryRepository] = None,
        memory_service: Optional[CustomerMemoryService] = None,
        max_recent_turns: int = 6,
        max_memory_tokens: int = 150,
        max_summary_tokens: int = 150,
        max_recent_history_tokens: int = 400,
        max_context_chars: int = 4000,
    ) -> None:
        self.repository = repository or ConversationMemoryRepository()
        self.memory_service = memory_service or CustomerMemoryService(repository=self.repository)
        self.max_recent_turns = max_recent_turns
        self.max_memory_tokens = max_memory_tokens
        self.max_summary_tokens = max_summary_tokens
        self.max_recent_history_tokens = max_recent_history_tokens
        self.max_context_chars = max_context_chars

    def assemble_turn_context(
        self,
        user_id: str,
        conversation_id: str,
        entity_id: str,
        current_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        customer_name: str = "Residential Customer",
        tariff_rate: float = 10.0,
    ) -> AssembledTurnContext:
        """Convenience method matching standard caller naming."""
        return self.assemble_context(
            user_id=user_id,
            meter_id=entity_id,
            customer_name=customer_name,
            tariff_rate=tariff_rate,
            prompt=current_message,
            history=history,
            conversation_id=conversation_id,
        )

    def format_system_context(self, assembled: AssembledTurnContext) -> str:
        """Return formatted system context string."""
        return assembled.grounding_system_block

    def assemble_context(
        self,
        user_id: str,
        meter_id: str,
        customer_name: str,
        tariff_rate: float,
        prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
        conversation_id: Optional[str] = None,
        persona: str = "residential",
        explicit_mode: Optional[str] = None,
    ) -> AssembledTurnContext:
        """Assemble all 7 layers of context with strict customer isolation and token budgeting."""
        clean_user = str(user_id).strip()
        clean_meter = str(meter_id).strip()

        # 1. Resolve or create persistent conversation session
        session = self.repository.get_or_create_session(
            conversation_id=conversation_id,
            user_id=clean_user,
            meter_id=clean_meter,
            persona=persona,
        )
        resolved_conv_id = session.id

        # 2. Rehydrate active conversational state from session
        active_state = self._rehydrate_active_state(session)

        # 3. Resolve dialogue context (pending questions, follow-ups, topic changes)
        resolved_state = resolve_dialogue_context(
            prompt=prompt,
            history=history,
            explicit_mode=explicit_mode,
            active_state=active_state,
        )

        # 4. Update active state based on resolution
        self._apply_resolution_to_active_state(active_state, resolved_state, prompt)

        # 5. Extract and persist any new candidate customer facts from prompt
        self.memory_service.extract_and_persist_candidate_memories(
            user_id=clean_user,
            user_prompt=prompt,
            conversation_id=resolved_conv_id,
            persona=persona,
        )

        # 6. Retrieve relevant persistent customer memories (filtered for this query)
        relevant_memories = self.memory_service.select_relevant_memories(
            user_id=clean_user,
            query=resolved_state.effective_prompt,
            persona=persona,
            active_workflow=resolved_state.resolved_mode,
            max_memories=5,
        )

        # 7. Retrieve last tool execution record for continuity / explanations
        last_tool_exec = self.repository.get_last_tool_execution(
            conversation_id=resolved_conv_id,
            user_id=clean_user,
        )

        # 8. Manage message history and rolling conversation summarization
        if history is not None and len(history) > 0:
            full_history = history
        else:
            db_messages = self.repository.get_session_messages(resolved_conv_id, clean_user)
            full_history = [{"role": m["role"], "content": m["content"]} for m in db_messages]

        summary_text = session.summary_text
        if len(full_history) > self.max_recent_turns:
            older_turns = full_history[:-self.max_recent_turns]
            recent_turns = full_history[-self.max_recent_turns:]
            # Generate or update rolling summary from older turns
            summary_text = self._update_rolling_summary(summary_text, older_turns)
            session.summary_text = summary_text
        else:
            recent_turns = full_history

        compacted_recent = compact_history_for_llm(
            recent_turns,
            max_turns=self.max_recent_turns,
            max_assistant_chars=350,
            max_user_chars=400,
        )

        # 9. Format structured grounding block
        grounding_block = self._format_grounding_block(
            customer_name=customer_name,
            meter_id=clean_meter,
            tariff_rate=tariff_rate,
            relevant_memories=relevant_memories,
            summary_text=summary_text,
            active_state=active_state,
            last_tool_exec=last_tool_exec,
        )

        # 10. Persist updated session state
        self.repository.update_session_state(
            conversation_id=resolved_conv_id,
            user_id=clean_user,
            active_state=active_state,
            summary_text=summary_text,
        )

        return AssembledTurnContext(
            user_id=clean_user,
            meter_id=clean_meter,
            customer_name=customer_name,
            tariff_rate=tariff_rate,
            conversation_id=resolved_conv_id,
            relevant_memories=relevant_memories,
            active_state=active_state,
            conversation_summary=summary_text,
            recent_messages=compacted_recent,
            last_tool_execution=last_tool_exec,
            resolved_state=resolved_state,
            grounding_system_block=grounding_block,
        )

    def _rehydrate_active_state(self, session: Any) -> ActiveConversationState:
        """Construct ActiveConversationState from database JSON."""
        state_json = session.pending_state_json
        if state_json and isinstance(state_json, dict):
            try:
                return ActiveConversationState.model_validate(state_json)
            except Exception as e:
                logger.warning("Could not rehydrate active state from JSON: %s", e)

        collected = session.collected_fields_json if isinstance(session.collected_fields_json, dict) else {}
        return ActiveConversationState(
            active_workflow=session.active_workflow,
            awaiting_user_response=False,
            pending_question=None,
            collected_fields=collected,
        )

    def _apply_resolution_to_active_state(
        self,
        active_state: ActiveConversationState,
        resolved_state: ResolvedDialogueState,
        raw_prompt: str,
    ) -> None:
        """Update active state based on follow-up and topic change resolution."""
        # 1. Handle Topic Change: suspend active workflow cleanly without losing state
        if resolved_state.is_topic_change:
            if active_state.active_workflow and active_state.active_workflow not in ("general_chat", "irrelevant"):
                active_state.suspended_workflow = active_state.active_workflow
                active_state.suspended_collected_fields = dict(active_state.collected_fields)
                active_state.suspended_pending_question = active_state.pending_question

            active_state.active_workflow = resolved_state.resolved_mode
            active_state.awaiting_user_response = False
            active_state.pending_question = None
            active_state.last_topic = "telemetry_and_billing"
            return

        # 2. Handle Answer to Pending Question
        if resolved_state.follow_up_type in ("answer_to_pending", "partial_answer") and resolved_state.answered_field:
            field_name = resolved_state.answered_field
            val = resolved_state.answered_value
            active_state.collected_fields[field_name] = val

            if resolved_state.follow_up_type == "answer_to_pending":
                active_state.awaiting_user_response = False
                active_state.pending_question = None
            elif resolved_state.follow_up_type == "partial_answer":
                # Keep outstanding question active for remaining slots
                active_state.awaiting_user_response = True

        # 3. Handle Explicit User Correction
        elif resolved_state.follow_up_type == "correction" and resolved_state.answered_field:
            field_name = resolved_state.answered_field
            active_state.collected_fields[field_name] = resolved_state.answered_value

        # 4. Standard workflow tracking
        if resolved_state.resolved_mode in ("house_planning", "appliance_lifecycle", "cost_management"):
            active_state.active_workflow = resolved_state.resolved_mode
        active_state.last_topic = resolved_state.resolved_mode

    def _update_rolling_summary(
        self,
        existing_summary: Optional[str],
        older_turns: List[Dict[str, Any]],
    ) -> str:
        """Generate or incrementally update rolling summary from older turns outside sliding window."""
        items: List[str] = []
        if existing_summary and len(existing_summary.strip()) > 10:
            items.append(existing_summary.strip())

        goals: List[str] = []
        facts: List[str] = []
        decisions: List[str] = []

        for turn in older_turns:
            content = str(turn.get("content", "")).strip()
            role = turn.get("role", "")
            c_low = content.lower()

            if role == "user":
                if any(w in c_low for w in ["plan", "build", "new house", "replace", "upgrade", "solar", "bill", "cost", "save", "reduce"]):
                    goals.append(content[:120])
                if any(w in c_low for w in ["bedroom", "bengaluru", "bangalore", "independent house", "2 acs", "3 acs", "kwh", "kw", "subsidy"]):
                    facts.append(content[:100])
            elif role == "assistant":
                if any(w in c_low for w in ["connected load", "peak demand", "payback", "recommended", "solar", "bill", "kwh", "subsidy"]):
                    # Capture key numerical verdict lines
                    lines = [ln.strip() for ln in content.split("\n") if any(k in ln.lower() for k in ["connected load", "peak demand", "savings", "tier", "solar", "subsidy", "bill"])]
                    if lines:
                        decisions.append("; ".join(lines[:2])[:150])
                    else:
                        decisions.append(content[:100])

        new_notes: List[str] = []
        if goals:
            new_notes.append(f"Inquiries & Goals: {'; '.join(goals[:3])}")
        if facts:
            new_notes.append(f"Confirmed details: {'; '.join(facts[:3])}")
        if decisions:
            new_notes.append(f"Prior milestones: {'; '.join(decisions[:2])}")

        # Fallback if specific keywords were not hit but older turns exist
        if not new_notes and older_turns:
            user_snippets = [t.get("content", "")[:60] for t in older_turns if t.get("role") == "user"]
            if user_snippets:
                new_notes.append(f"Prior topics: {'; '.join(user_snippets[:3])}")

        combined = "\n".join(filter(None, [existing_summary] + new_notes))
        # Hard budget cap: ~150 tokens (< 600 characters)
        if len(combined) > 600:
            combined = combined[:590] + "..."
        return combined

    def _format_grounding_block(
        self,
        customer_name: str,
        meter_id: str,
        tariff_rate: float,
        relevant_memories: List[CustomerMemoryItem],
        summary_text: Optional[str],
        active_state: ActiveConversationState,
        last_tool_exec: Optional[ToolExecutionReference],
    ) -> str:
        """Format high-density, budgeted prompt grounding block (< 250 tokens)."""
        lines: List[str] = [
            f"=== VERIFIED CUSTOMER PROFILE ===",
            f"CUSTOMER: {customer_name} | METER: {meter_id} | TARIFF: ₹{tariff_rate:.2f}/kWh",
        ]

        # 1. Relevant Persistent Memories
        if relevant_memories:
            mem_items = [f"{m.key}: {m.value}" for m in relevant_memories]
            lines.append(f"PERSISTENT CUSTOMER PREFERENCES: {', '.join(mem_items)}")

        # 2. Active Conversational State & Collected Fields
        if active_state.active_workflow and active_state.active_workflow != "general_chat":
            lines.append(f"ACTIVE WORKFLOW: {active_state.active_workflow}")
        if active_state.collected_fields:
            fields_str = ", ".join(f"{k}={v}" for k, v in active_state.collected_fields.items())
            lines.append(f"COLLECTED WORKFLOW FIELDS: {fields_str}")
        if active_state.awaiting_user_response and active_state.pending_question:
            lines.append(f"AWAITING FIELD: {active_state.pending_question.field} ('{active_state.pending_question.question}')")

        # 3. Rolling Conversation Summary
        if summary_text and len(summary_text.strip()) > 5:
            clean_sum = summary_text.replace("\n", " ").strip()
            lines.append(f"PRIOR CONVERSATION SUMMARY: {clean_sum[:300]}")

        # 4. Previous Tool Result Continuity
        if last_tool_exec and last_tool_exec.result_summary:
            summary_parts = [f"{k}: {v}" for k, v in list(last_tool_exec.result_summary.items())[:4]]
            lines.append(f"PREVIOUS TOOL EXECUTION ({last_tool_exec.tool_name}): {', '.join(summary_parts)}")

        return "\n".join(lines)
