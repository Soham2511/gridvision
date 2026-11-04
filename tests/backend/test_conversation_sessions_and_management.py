"""Comprehensive Verification Suite for Persistent Conversation Sessions and Chat Management (Section 10).

Covers:
1. Multiple conversations per customer with unique conversation IDs.
2. Automatic title generation from user content (3-7 words, e.g. 'Understanding My Electricity Bill').
3. Manual title editing and custom title protection (is_title_custom=True prevents auto-overwrite).
4. Resuming existing conversations with message history, rolling summary, and active state.
5. New Chat lifecycle: fresh conversation-specific context and empty pending state.
6. Conversation switching without context or pending question cross-contamination.
7. Customer-level persistent memory sharing across independent sessions.
8. Soft deletion (is_active=False) and archiving (is_archived=True).
9. Customer isolation and access controls (preventing cross-customer access/modification).
10. End-to-end REST API verification for conversation management endpoints.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from app import create_app
from app.config import TestingConfig
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models.conversation_memory import (
    ConversationMessageModel,
    ConversationSessionModel,
    CustomerMemoryModel,
)
from app.infrastructure.repositories.conversation_memory_repository import (
    ConversationMemoryRepository,
)
from app.services.assistant.context_manager import ConversationContextManager
from app.services.assistant.memory_contracts import (
    ActiveConversationState,
    CustomerMemoryItem,
    MemoryCategory,
    PendingQuestion,
)
from app.services.assistant.memory_service import CustomerMemoryService
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator


class TestConversationSessionRepository(unittest.TestCase):
    """Repository-level tests for conversation sessions, titles, archives, and deletions."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.repo = ConversationMemoryRepository()
        self.user_a = f"cust-a-{uuid.uuid4().hex[:8]}"
        self.user_b = f"cust-b-{uuid.uuid4().hex[:8]}"
        self.meter_a = "METER-1000"
        self.meter_b = "METER-1001"

    def tearDown(self):
        with get_session() as session:
            subquery = session.query(ConversationSessionModel.id).filter(
                ConversationSessionModel.user_id.in_([self.user_a, self.user_b])
            )
            session.query(ConversationMessageModel).filter(
                ConversationMessageModel.conversation_id.in_(subquery)
            ).delete(synchronize_session=False)
            session.query(ConversationSessionModel).filter(
                ConversationSessionModel.user_id.in_([self.user_a, self.user_b])
            ).delete(synchronize_session=False)
            session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id.in_([self.user_a, self.user_b])
            ).delete(synchronize_session=False)
            session.commit()

    def test_create_multiple_independent_sessions_for_same_customer(self):
        """A customer can maintain multiple distinct conversation sessions with unique IDs."""
        s1 = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="New Chat")
        s2 = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="New Chat")

        self.assertIsNotNone(s1.id)
        self.assertIsNotNone(s2.id)
        self.assertNotEqual(s1.id, s2.id)
        self.assertEqual(s1.user_id, self.user_a)
        self.assertEqual(s2.user_id, self.user_a)
        self.assertEqual(s1.title, "New Chat")
        self.assertFalse(s1.is_title_custom)
        self.assertFalse(s1.is_archived)
        self.assertTrue(s1.is_active)

    def test_list_sessions_ordering_and_pagination(self):
        """Conversations are returned ordered by most recent activity (updated_at DESC) with pagination."""
        s1 = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="First Chat")
        s2 = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="Second Chat")
        s3 = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="Third Chat")

        # Simulate update to s1 so it becomes the most recently active
        self.repo.append_message(s1.id, "user", "Hello again in first chat", user_id=self.user_a)

        sessions = self.repo.list_sessions(user_id=self.user_a, limit=10, offset=0)
        self.assertEqual(len(sessions), 3)
        self.assertEqual(sessions[0].id, s1.id)  # Most recently updated

        # Test pagination: limit=2
        page1 = self.repo.list_sessions(user_id=self.user_a, limit=2, offset=0)
        self.assertEqual(len(page1), 2)
        self.assertEqual(page1[0].id, s1.id)

        page2 = self.repo.list_sessions(user_id=self.user_a, limit=2, offset=2)
        self.assertEqual(len(page2), 1)

    def test_automatic_title_generation_topics(self):
        """Automatic title generation derives concise 3-7 word titles based on conversational context."""
        test_cases = [
            (
                "Why is my electricity bill so high this month?",
                "Your bill increased due to additional peak-hour air conditioning usage.",
                "Electricity Bill",
            ),
            (
                "I want to plan the electrical load for my new 4BHK house in Whitefield",
                "Certainly, let's configure your new home appliances and connected load.",
                "Home Energy Planning",
            ),
            (
                "Should I upgrade my 3-star split AC to a 5-star inverter AC?",
                "Replacing your current 1.5-ton AC with a 5-star model will save approximately 320 kWh annually.",
                "AC Replacement Comparison",
            ),
            (
                "What is my monthly energy consumption trend for this quarter?",
                "Here is your monthly telemetry consumption breakdown across the last three months.",
                "Energy Consumption",
            ),
            (
                "How do I apply for rooftop solar installation subsidy under PM Surya Ghar?",
                "You can receive up to Rs 78,000 central financial assistance for a 3kW solar installation.",
                "Solar Installation",
            ),
        ]

        for user_msg, asst_msg, expected_topic_keyword in test_cases:
            session = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="New Chat")
            generated_title = self.repo.auto_generate_session_title(
                conversation_id=session.id,
                user_id=self.user_a,
                first_user_message=user_msg,
                first_assistant_message=asst_msg,
            )

            self.assertIsNotNone(generated_title)
            self.assertIn(expected_topic_keyword.lower(), generated_title.lower())

            # Title length should be concise (2 to 8 words)
            words = generated_title.split()
            self.assertTrue(2 <= len(words) <= 8, f"Title '{generated_title}' word count {len(words)} not within expected range")

            # Check database persistence
            refreshed = self.repo.get_session(session.id, self.user_a)
            self.assertEqual(refreshed.title, generated_title)
            self.assertFalse(refreshed.is_title_custom)

    def test_manual_title_update_and_custom_flag_protection(self):
        """Manual title update sets is_title_custom=True and prevents automated overwrites."""
        session = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="New Chat")

        # Customer renames manually
        success = self.repo.update_session_title(
            conversation_id=session.id,
            user_id=self.user_a,
            title="My Custom Villa Project",
            is_custom=True,
        )
        self.assertTrue(success)

        refreshed = self.repo.get_session(session.id, self.user_a)
        self.assertEqual(refreshed.title, "My Custom Villa Project")
        self.assertTrue(refreshed.is_title_custom)

        # Subsequent automated topic classification attempt must NOT overwrite custom title
        second_title = self.repo.auto_generate_session_title(
            conversation_id=session.id,
            user_id=self.user_a,
            first_user_message="Why is my electricity bill so high?",
            first_assistant_message="Your AC consumption drove up the bill.",
        )
        self.assertEqual(second_title, "My Custom Villa Project")
        refreshed_after = self.repo.get_session(session.id, self.user_a)
        self.assertEqual(refreshed_after.title, "My Custom Villa Project")

    def test_title_generation_fallback(self):
        """Fallback to non-empty title when input lacks recognizable domain intent."""
        session = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="New Chat")
        title = self.repo.auto_generate_session_title(
            conversation_id=session.id,
            user_id=self.user_a,
            first_user_message="ok",
            first_assistant_message="How can I assist you?",
        )
        self.assertIsNotNone(title)
        self.assertNotEqual(title, "")

    def test_archive_and_unarchive_session(self):
        """Conversations can be archived and unarchived, filtering them from standard sidebar views."""
        session = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="Old Discussion")

        # Initially unarchived
        active_list = self.repo.list_sessions(user_id=self.user_a, include_archived=False)
        self.assertTrue(any(s.id == session.id for s in active_list))

        # Archive session
        self.repo.archive_session(conversation_id=session.id, user_id=self.user_a, is_archived=True)
        active_list_after = self.repo.list_sessions(user_id=self.user_a, include_archived=False)
        self.assertFalse(any(s.id == session.id for s in active_list_after))

        all_list = self.repo.list_sessions(user_id=self.user_a, include_archived=True)
        self.assertTrue(any(s.id == session.id for s in all_list))

        # Unarchive
        self.repo.archive_session(conversation_id=session.id, user_id=self.user_a, is_archived=False)
        restored_list = self.repo.list_sessions(user_id=self.user_a, include_archived=False)
        self.assertTrue(any(s.id == session.id for s in restored_list))

    def test_soft_delete_session_preserves_persistent_memory(self):
        """Deleting a session marks it inactive (soft delete) without deleting Layer 3 customer memory."""
        # Create persistent memory for Customer A
        self.repo.create_or_update_memory(
            user_id=self.user_a,
            category=MemoryCategory.PREFERENCE,
            key="ac_preferred_temp",
            value={"temperature": 24},
            confidence=1.0,
            source_turn="I keep AC at 24C",
        )

        session = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="Temporary Chat")
        self.repo.append_message(session.id, "user", "Hello", user_id=self.user_a)

        # Soft delete the session
        success = self.repo.delete_session(conversation_id=session.id, user_id=self.user_a)
        self.assertTrue(success)

        # Verify session is not returned in listing
        sessions = self.repo.list_sessions(user_id=self.user_a)
        self.assertFalse(any(s.id == session.id for s in sessions))

        # Direct fetch confirms is_active is False
        deleted_session = self.repo.get_session(session.id, user_id=self.user_a)
        self.assertFalse(deleted_session.is_active)

        # Layer 3 Customer persistent memory MUST remain completely intact
        customer_memories = self.repo.get_customer_memories(user_id=self.user_a)
        self.assertEqual(len(customer_memories), 1)
        self.assertEqual(customer_memories[0].key, "ac_preferred_temp")

    def test_customer_isolation_at_repository_level(self):
        """Customer B cannot view, rename, archive, or delete Customer A's session."""
        session_a = self.repo.create_session(user_id=self.user_a, meter_id=self.meter_a, title="Customer A Private Chat")

        # Customer B attempts to fetch Customer A's session
        fetched = self.repo.get_session(conversation_id=session_a.id, user_id=self.user_b)
        self.assertIsNone(fetched)

        # Customer B attempts to rename Customer A's session -> PermissionError
        with self.assertRaises(PermissionError):
            self.repo.update_session_title(
                conversation_id=session_a.id,
                user_id=self.user_b,
                title="Hacked Title",
            )

        # Customer B attempts to archive Customer A's session
        archived = self.repo.archive_session(
            conversation_id=session_a.id,
            user_id=self.user_b,
            is_archived=True,
        )
        self.assertFalse(archived)

        # Customer B attempts to delete Customer A's session
        deleted = self.repo.delete_session(
            conversation_id=session_a.id,
            user_id=self.user_b,
        )
        self.assertFalse(deleted)


class TestConversationLifecycleAndContextSwitching(unittest.TestCase):
    """Lifecycle and isolation tests for switching chats, active states, and persistent memory."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.repo = ConversationMemoryRepository()
        self.memory_service = CustomerMemoryService(repository=self.repo)
        self.context_mgr = ConversationContextManager(
            memory_service=self.memory_service,
            repository=self.repo,
        )
        self.user_id = f"cust-lifecycle-{uuid.uuid4().hex[:8]}"
        self.meter_id = "METER-1000"

    def tearDown(self):
        with get_session() as session:
            subquery = session.query(ConversationSessionModel.id).filter(
                ConversationSessionModel.user_id == self.user_id
            )
            session.query(ConversationMessageModel).filter(
                ConversationMessageModel.conversation_id.in_(subquery)
            ).delete(synchronize_session=False)
            session.query(ConversationSessionModel).filter(
                ConversationSessionModel.user_id == self.user_id
            ).delete(synchronize_session=False)
            session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id == self.user_id
            ).delete(synchronize_session=False)
            session.commit()

    def test_new_chat_clean_pending_state_and_isolated_context(self):
        """Starting a New Chat provides an empty pending state without carrying previous chat questions."""
        # Session 1: customer is midway through house planning
        s1 = self.repo.create_session(user_id=self.user_id, meter_id=self.meter_id, title="Villa Planning")
        self.repo.append_message(s1.id, "user", "I want to plan my villa load in Bengaluru.", user_id=self.user_id)
        self.repo.append_message(s1.id, "assistant", "How many bedrooms will your new home have?", user_id=self.user_id)

        # Save active workflow state in Session 1
        s1_state = ActiveConversationState(
            active_workflow="house_energy_planning",
            pending_question=PendingQuestion(
                field="bedrooms_count",
                question="How many bedrooms will your new home have?",
                expected_response_type="integer",
            ),
            collected_fields={"city": "Bengaluru"},
        )
        self.repo.save_active_state(s1.id, s1_state, user_id=self.user_id)

        # Verify Session 1 has active pending question
        s1_loaded = self.repo.get_active_state(s1.id, user_id=self.user_id)
        self.assertIsNotNone(s1_loaded)
        self.assertIsNotNone(s1_loaded.pending_question)
        self.assertEqual(s1_loaded.pending_question.field, "bedrooms_count")

        # Now customer starts Session 2 (New Chat)
        s2 = self.repo.create_session(user_id=self.user_id, meter_id=self.meter_id, title="New Chat")

        # Session 2 must NOT inherit Session 1's active workflow state or pending question
        s2_loaded = self.repo.get_active_state(s2.id, user_id=self.user_id)
        self.assertIsNone(s2_loaded)

        assembled_s2 = self.context_mgr.assemble_turn_context(
            user_id=self.user_id,
            conversation_id=s2.id,
            entity_id=self.meter_id,
            current_message="Hello, can you check my tariff?",
        )
        self.assertIsNone(assembled_s2.active_state.pending_question)
        self.assertEqual(len(assembled_s2.recent_messages), 0)

    def test_conversation_switching_without_state_mixing(self):
        """Switching between conversations loads the exact message history and state of the target session."""
        s1 = self.repo.create_session(user_id=self.user_id, meter_id=self.meter_id, title="Session 1")
        s2 = self.repo.create_session(user_id=self.user_id, meter_id=self.meter_id, title="Session 2")

        # Populate distinct messages
        self.repo.append_message(s1.id, "user", "What is my solar generation?", user_id=self.user_id)
        self.repo.append_message(s1.id, "assistant", "Your solar generation was 18 kWh today.", user_id=self.user_id)

        self.repo.append_message(s2.id, "user", "Tell me about my tariff slab.", user_id=self.user_id)
        self.repo.append_message(s2.id, "assistant", "Your domestic tariff is Rs 10.00/kWh.", user_id=self.user_id)

        # Context for Session 1
        c1 = self.context_mgr.assemble_turn_context(
            user_id=self.user_id,
            conversation_id=s1.id,
            entity_id=self.meter_id,
            current_message="Is that good?",
        )
        self.assertEqual(len(c1.recent_messages), 2)
        self.assertEqual(c1.recent_messages[0]["content"], "What is my solar generation?")

        # Context for Session 2
        c2 = self.context_mgr.assemble_turn_context(
            user_id=self.user_id,
            conversation_id=s2.id,
            entity_id=self.meter_id,
            current_message="When does peak start?",
        )
        self.assertEqual(len(c2.recent_messages), 2)
        self.assertEqual(c2.recent_messages[0]["content"], "Tell me about my tariff slab.")

    def test_persistent_memory_shared_across_distinct_sessions(self):
        """Layer 3 persistent customer memory is shared across all independent conversation sessions."""
        # Store persistent memory
        self.repo.create_or_update_memory(
            user_id=self.user_id,
            category=MemoryCategory.APPLIANCE,
            key="owned_ac_count",
            value=3,
            confidence=1.0,
            source_turn="I have 3 air conditioners in my home",
        )

        s1 = self.repo.create_session(user_id=self.user_id, meter_id=self.meter_id, title="Session 1")
        s2 = self.repo.create_session(user_id=self.user_id, meter_id=self.meter_id, title="Session 2")

        # Check context assembly in Session 1
        c1 = self.context_mgr.assemble_turn_context(
            user_id=self.user_id,
            conversation_id=s1.id,
            entity_id=self.meter_id,
            current_message="Recommend an AC upgrade for my cooling",
        )
        self.assertTrue(any(m.key == "owned_ac_count" for m in c1.relevant_memories))

        # Check context assembly in Session 2
        c2 = self.context_mgr.assemble_turn_context(
            user_id=self.user_id,
            conversation_id=s2.id,
            entity_id=self.meter_id,
            current_message="What appliances should I replace to save cost?",
        )
        self.assertTrue(any(m.key == "owned_ac_count" for m in c2.relevant_memories))

        # Verify Layer 3 memories exist independently of session counts
        all_memories = self.repo.get_customer_memories(self.user_id)
        self.assertEqual(len(all_memories), 1)
        self.assertEqual(all_memories[0].key, "owned_ac_count")


class TestConversationAPIEndpoints(unittest.TestCase):
    """End-to-end REST API tests for conversation sessions, titles, archives, and security."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.client = self.app.test_client()
        self.repo = ConversationMemoryRepository()
        self.user_a_header = {"X-Dev-User-Id": "usr-resident-1000"}
        self.user_b_header = {"X-Dev-User-Id": "usr-resident-1001"}

    def tearDown(self):
        with get_session() as session:
            subquery = session.query(ConversationSessionModel.id).filter(
                ConversationSessionModel.user_id.in_(["usr-resident-1000", "usr-resident-1001"])
            )
            session.query(ConversationMessageModel).filter(
                ConversationMessageModel.conversation_id.in_(subquery)
            ).delete(synchronize_session=False)
            session.query(ConversationSessionModel).filter(
                ConversationSessionModel.user_id.in_(["usr-resident-1000", "usr-resident-1001"])
            ).delete(synchronize_session=False)
            session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id.in_(["usr-resident-1000", "usr-resident-1001"])
            ).delete(synchronize_session=False)
            session.commit()

    def test_list_and_create_conversations_api(self):
        """POST and GET /api/v1/assistant/conversations create and list customer sessions."""
        # 1. Create a new conversation
        create_res = self.client.post(
            "/api/v1/assistant/conversations",
            json={"title": "Custom Project Plan"},
            headers=self.user_a_header,
        )
        self.assertEqual(create_res.status_code, 201)
        created_data = create_res.get_json()["data"]
        conv_id = created_data["id"]
        self.assertEqual(created_data["title"], "Custom Project Plan")
        self.assertEqual(created_data["userId"], "usr-resident-1000")

        # 2. List conversations
        list_res = self.client.get(
            "/api/v1/assistant/conversations",
            headers=self.user_a_header,
        )
        self.assertEqual(list_res.status_code, 200)
        items = list_res.get_json()["data"]
        self.assertTrue(any(c["id"] == conv_id for c in items))

    def test_get_conversation_messages_api(self):
        """GET /api/v1/assistant/conversations/<id> retrieves session details and message transcript."""
        # Create session
        create_res = self.client.post(
            "/api/v1/assistant/conversations",
            json={"title": "Solar Inquiry"},
            headers=self.user_a_header,
        )
        conv_id = create_res.get_json()["data"]["id"]

        # Append messages directly
        self.repo.append_message(conv_id, "user", "What is my solar generation?", user_id="usr-resident-1000")
        self.repo.append_message(conv_id, "assistant", "Your solar generation was 18 kWh today.", user_id="usr-resident-1000")

        # Retrieve conversation details
        get_res = self.client.get(
            f"/api/v1/assistant/conversations/{conv_id}",
            headers=self.user_a_header,
        )
        self.assertEqual(get_res.status_code, 200)
        data = get_res.get_json()["data"]
        self.assertEqual(data["session"]["id"], conv_id)
        self.assertEqual(len(data["messages"]), 2)

    def test_patch_conversation_title_and_archive_api(self):
        """PATCH /api/v1/assistant/conversations/<id> renames and archives sessions."""
        create_res = self.client.post(
            "/api/v1/assistant/conversations",
            json={"title": "New Chat"},
            headers=self.user_a_header,
        )
        conv_id = create_res.get_json()["data"]["id"]

        # Rename
        patch_res = self.client.patch(
            f"/api/v1/assistant/conversations/{conv_id}",
            json={"title": "Renamed Billing Analysis"},
            headers=self.user_a_header,
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["data"]["title"], "Renamed Billing Analysis")
        self.assertTrue(patch_res.get_json()["data"]["isTitleCustom"])

        # Archive
        archive_res = self.client.patch(
            f"/api/v1/assistant/conversations/{conv_id}",
            json={"is_archived": True},
            headers=self.user_a_header,
        )
        self.assertEqual(archive_res.status_code, 200)
        self.assertTrue(archive_res.get_json()["data"]["isArchived"])

    def test_delete_conversation_api(self):
        """DELETE /api/v1/assistant/conversations/<id> soft-deletes a customer session."""
        create_res = self.client.post(
            "/api/v1/assistant/conversations",
            json={"title": "To Be Deleted"},
            headers=self.user_a_header,
        )
        conv_id = create_res.get_json()["data"]["id"]

        # Delete
        del_res = self.client.delete(
            f"/api/v1/assistant/conversations/{conv_id}",
            headers=self.user_a_header,
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

        # Subsequent fetch returns 404
        get_res = self.client.get(
            f"/api/v1/assistant/conversations/{conv_id}",
            headers=self.user_a_header,
        )
        self.assertEqual(get_res.status_code, 404)

    def test_cross_customer_access_denied_api(self):
        """Customer B cannot view, rename, archive, or delete Customer A's conversation."""
        create_res = self.client.post(
            "/api/v1/assistant/conversations",
            json={"title": "Customer A Confidential"},
            headers=self.user_a_header,
        )
        conv_id = create_res.get_json()["data"]["id"]

        # Customer B attempts GET -> 404
        get_b = self.client.get(
            f"/api/v1/assistant/conversations/{conv_id}",
            headers=self.user_b_header,
        )
        self.assertEqual(get_b.status_code, 404)

        # Customer B attempts PATCH -> 403 or 404
        patch_b = self.client.patch(
            f"/api/v1/assistant/conversations/{conv_id}",
            json={"title": "Hacked Title"},
            headers=self.user_b_header,
        )
        self.assertIn(patch_b.status_code, [403, 404])

        # Customer B attempts DELETE -> 404
        del_b = self.client.delete(
            f"/api/v1/assistant/conversations/{conv_id}",
            headers=self.user_b_header,
        )
        self.assertEqual(del_b.status_code, 404)

    def test_chat_auto_generates_title_and_returns_in_response(self):
        """First turn of a chat session automatically derives and returns conversationTitle."""
        conv_id = f"auto-title-{uuid.uuid4().hex[:8]}"

        chat_res = self.client.post(
            "/api/v1/assistant/chat",
            json={
                "entity_id": "METER-1000",
                "persona": "household",
                "conversation_id": conv_id,
                "prompt": "Can you explain why my electricity bill increased?",
            },
            headers=self.user_a_header,
        )
        self.assertEqual(chat_res.status_code, 200)
        data = chat_res.get_json()["data"]
        self.assertIn("conversationTitle", data)
        self.assertIsNotNone(data["conversationTitle"])
        self.assertIn("bill", data["conversationTitle"].lower())


if __name__ == "__main__":
    unittest.main()
