"""Comprehensive Verification Suite for Customer-Specific Memory, Context Management,
and Intelligent Tool Routing (Sections 16.1 - 16.5).

Covers:
1. Customer Memory Isolation (16.1, 16.5):
   - Strict tenant separation between Customer A and Customer B.
   - Authenticated backend ownership enforcement (cannot read/modify other customer's memory).
   - Memory updates and customer corrections ("I said two ACs, not three").
   - Soft deletion and deactivation ("Forget my previous preference").
2. Active Conversation State & Follow-up Resolution (16.2):
   - Pending question answer resolution ("Bengaluru" resolves to house planning without out-of-scope notice).
   - Multi-field partial answers (e.g. 2 bedrooms answered, AC rooms pending).
   - Topic interruption and resumption (billing inquiry during planning preserves active state).
3. Intelligent Tool Routing (16.3):
   - Scenario 1: House planning -> usage query routes to telemetry/analytics.
   - Scenario 2: Billing analysis -> choose AC routes to appliance lifecycle.
   - Scenario 3: Appliance comparison -> tariff inquiry routes to tariff/billing.
   - Scenario 4: Technical RAG -> actual consumption routes to meter telemetry.
4. Long-Conversation Summarization & Context Budgeting (16.4):
   - Rolling summarization across 10+ turns.
   - Strict token/character budget enforcement.
   - Structured multi-layer context assembly.
5. End-to-End API Integration & Ownership Protection (16.5):
   - Authenticated API turns with session persistence.
   - Cross-customer session access denial.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
import uuid

from app import create_app
from app.config import TestingConfig, BaseConfig
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models.conversation_memory import (
    CustomerMemoryModel,
    ConversationSessionModel,
    ConversationMessageModel,
)
from app.infrastructure.database.models.user import User
from app.infrastructure.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.services.assistant.memory_contracts import (
    ActiveConversationState,
    CustomerMemoryItem,
    MemoryCategory,
    PendingQuestion,
)
from app.services.assistant.memory_service import CustomerMemoryService
from app.services.assistant.dialogue_state import (
    resolve_dialogue_context,
    extract_pending_question_from_context,
)
from app.services.assistant.intelligent_router import IntelligentRouter
from app.services.assistant.context_manager import ConversationContextManager
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator
from app.providers.sample_data_provider import SampleDataProvider


class TestCustomerMemoryIsolationAndSecurity(unittest.TestCase):
    """Test suite for customer memory persistence, isolation, corrections, and soft deletions (16.1, 16.5)."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.repo = ConversationMemoryRepository()
        self.memory_service = CustomerMemoryService(repository=self.repo)
        self.user_a = f"user-a-{uuid.uuid4().hex[:8]}"
        self.user_b = f"user-b-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        with get_session() as session:
            session.query(CustomerMemoryModel).filter(
                CustomerMemoryModel.user_id.in_([self.user_a, self.user_b])
            ).delete(synchronize_session=False)
            session.query(ConversationSessionModel).filter(
                ConversationSessionModel.user_id.in_([self.user_a, self.user_b])
            ).delete(synchronize_session=False)
            session.commit()

    def test_strict_isolation_between_customers(self):
        """Customer A's memory must never be accessible to Customer B."""
        # Store preference for Customer A
        self.repo.create_or_update_memory(
            user_id=self.user_a,
            category=MemoryCategory.PREFERENCE,
            key="thermostat_setpoint",
            value={"temperature_c": 24.0, "unit": "celsius"},
            confidence=1.0,
            source_turn="I like my AC at 24 degrees",
        )

        # Store preference for Customer B
        self.repo.create_or_update_memory(
            user_id=self.user_b,
            category=MemoryCategory.PREFERENCE,
            key="thermostat_setpoint",
            value={"temperature_c": 21.0, "unit": "celsius"},
            confidence=1.0,
            source_turn="Keep my room chilled at 21 C",
        )

        # Query Customer A's memories
        memories_a = self.repo.get_active_memories(self.user_a)
        self.assertEqual(len(memories_a), 1)
        self.assertEqual(memories_a[0].user_id, self.user_a)
        self.assertEqual(memories_a[0].value.get("temperature_c"), 24.0)

        # Query Customer B's memories
        memories_b = self.repo.get_active_memories(self.user_b)
        self.assertEqual(len(memories_b), 1)
        self.assertEqual(memories_b[0].user_id, self.user_b)
        self.assertEqual(memories_b[0].value.get("temperature_c"), 21.0)

        # Ensure no cross-contamination
        self.assertNotIn(memories_b[0], memories_a)
        self.assertNotIn(memories_a[0], memories_b)

    def test_memory_correction_updates_version_and_value(self):
        """Customer correcting prior information ('I said two ACs, not three') updates the existing entry."""
        # Initial statement: Customer has 3 ACs
        mem1 = self.repo.create_or_update_memory(
            user_id=self.user_a,
            category=MemoryCategory.APPLIANCE,
            key="owned_ac_count",
            value=3,
            confidence=0.8,
            source_turn="I have 3 air conditioners in my home",
        )
        self.assertEqual(mem1.version, 1)
        self.assertEqual(mem1.value, 3)

        # Customer correction: "I said two ACs, not three"
        corr_mem = self.memory_service.process_user_turn_for_memories(
            user_id=self.user_a,
            user_message="I said two ACs, not three.",
        )
        self.assertTrue(len(corr_mem) >= 1)

        # Verify active memory in repository is updated
        active_mems = self.repo.get_active_memories(self.user_a, category=MemoryCategory.APPLIANCE)
        ac_mem = next((m for m in active_mems if m.key == "owned_ac_count"), None)
        self.assertIsNotNone(ac_mem)
        self.assertEqual(ac_mem.value, 2)
        self.assertGreater(ac_mem.version, 1)

    def test_soft_deletion_and_deactivation(self):
        """Customer requesting 'forget my preference' deactivates the memory and excludes it from future queries."""
        # Add memory
        self.repo.create_or_update_memory(
            user_id=self.user_a,
            category=MemoryCategory.PREFERENCE,
            key="solar_budget_inr",
            value={"budget": 150000},
            confidence=0.9,
            source_turn="My budget for solar is 1.5 lakhs",
        )

        active = self.repo.get_active_memories(self.user_a)
        self.assertEqual(len(active), 1)

        # Process user request to forget
        deleted_keys = self.memory_service.process_user_deletions(
            user_id=self.user_a,
            user_message="Please forget my solar budget preference",
        )
        self.assertIn("solar_budget_inr", deleted_keys)

        # Verify memory is no longer active
        active_after = self.repo.get_active_memories(self.user_a)
        self.assertEqual(len(active_after), 0)

        # Verify record still exists in DB with is_active = False (audit trail preserved)
        with get_session() as session:
            record = session.query(CustomerMemoryModel).filter_by(
                user_id=self.user_a,
                key="solar_budget_inr",
            ).first()
            self.assertIsNotNone(record)
            self.assertFalse(record.is_active)

    def test_cross_customer_session_access_denied(self):
        """Customer B cannot retrieve or alter Customer A's conversation session."""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

        # Customer A creates session
        created_session = self.repo.get_or_create_session(
            conversation_id=session_id,
            user_id=self.user_a,
            meter_id="METER-1000",
        )
        self.assertIsNotNone(created_session)
        self.assertEqual(created_session.user_id, self.user_a)

        # Customer B attempts to access Customer A's session -> must raise PermissionError
        with self.assertRaises(PermissionError):
            self.repo.get_or_create_session(
                conversation_id=session_id,
                user_id=self.user_b,  # Spoofed user ID
                meter_id="METER-1000",
            )


class TestFollowUpAndConversationState(unittest.TestCase):
    """Test suite for Layer 2: Active Conversation State and Follow-up Resolution (16.2)."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.provider = SampleDataProvider()
        self.orchestrator = ResidentialAssistantOrchestrator(
            data_provider=self.provider,
            tariff_rate=10.0,
            authorized_meters=["METER-1000", "2254213", "METER-2254213"],
        )

    def test_bengaluru_followup_resolves_without_out_of_scope_notice(self):
        """Customer responding 'Bengaluru' to 'Which city is your property located in?' must resolve cleanly."""
        history = [
            {
                "role": "user",
                "content": "I am planning the electrical load for my new home.",
            },
            {
                "role": "assistant",
                "content": "I would be happy to help you plan your new home's energy setup. Which city is your property located in?",
            },
        ]

        resolved = resolve_dialogue_context("Bengaluru", history=history)
        self.assertTrue(resolved.is_continuation)
        self.assertEqual(resolved.resolved_mode, "house_planning")
        self.assertEqual(resolved.answered_field, "location_city")
        self.assertEqual(resolved.answered_value, "Bengaluru")

        # Run through orchestrator end-to-end
        resp = self.orchestrator.answer_query(
            prompt="Bengaluru",
            entity_id="METER-1000",
            history=history,
            user_id="test-resident-user",
        )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("mode"), "house_planning")
        answer = resp.get("answer", "")
        # Must acknowledge Bengaluru and ask for next details (bedrooms / AC)
        self.assertIn("Bengaluru", answer)
        # Must NEVER trigger domain scope notice or reject
        self.assertNotIn("Domain Scope Notice", answer)
        self.assertNotIn("appears outside the domain", answer)

    def test_multi_field_partial_answer_preserves_remaining_questions(self):
        """When assistant asks for multiple fields and user provides only one, remaining fields stay pending."""
        history = [
            {
                "role": "assistant",
                "content": "How many bedrooms do you have, and in which rooms do you need air conditioning?",
            }
        ]

        # User only answers bedroom count: "3 bedrooms"
        resolved = resolve_dialogue_context("3 bedrooms", history=history)
        self.assertTrue(resolved.is_continuation)
        self.assertEqual(resolved.answered_field, "bedrooms_count")
        self.assertEqual(resolved.answered_value, 3)

        # Verify active conversation state model tracks missing fields
        pq = PendingQuestion(
            field="bedrooms_count",
            question="How many bedrooms do you have, and in which rooms do you need air conditioning?",
            expected_response_type="integer",
            missing_fields=["ac_rooms"],
            collected_fields={"bedrooms_count": 3},
        )
        self.assertEqual(pq.collected_fields["bedrooms_count"], 3)
        self.assertIn("ac_rooms", pq.missing_fields)

    def test_topic_interruption_routes_billing_and_rejects_unverified_mock_answer(self):
        """An analytics topic switch is recognized, but a non-tool mock cannot fabricate results."""
        history = [
            {
                "role": "user",
                "content": "Help me plan my new house load.",
            },
            {
                "role": "assistant",
                "content": "Which city is your property located in?",
            },
        ]

        interrupt_prompt = "Wait, first explain why my electricity bill increased last month."
        resolved = resolve_dialogue_context(interrupt_prompt, history=history)

        # Must recognize topic change and NOT treat the billing question as a city name
        self.assertTrue(resolved.is_topic_change)
        self.assertEqual(resolved.tool_scope, "telemetry_and_billing")

        # Run through orchestrator
        resp = self.orchestrator.answer_query(
            prompt=interrupt_prompt,
            entity_id="METER-1000",
            history=history,
            user_id="test-resident-user",
        )

        self.assertEqual(resp.get("status"), "error")
        self.assertIn("No unverified answer was generated", resp.get("answer", ""))


class TestIntelligentToolRouting(unittest.TestCase):
    """Test suite for Intent Classification and Intelligent Tool Routing (16.3)."""

    def setUp(self):
        self.router = IntelligentRouter()

    def test_scenario_1_house_planning_to_usage_query(self):
        """Scenario 1: House planning -> usage query routes to historical analytics / telemetry."""
        plan = self.router.route(
            current_message="How much electricity did I actually consume last month?",
            active_state=ActiveConversationState(active_workflow="house_planning"),
            last_assistant_message="Which city is your house located in?",
        )
        self.assertIn("historical", plan.primary_intent)
        self.assertEqual(plan.tool_scope, "telemetry_and_billing")
        self.assertIn("query_consumption_history", plan.candidate_tools)

    def test_scenario_2_billing_analysis_to_choose_ac(self):
        """Scenario 2: Billing analysis -> choose AC routes to appliance lifecycle."""
        plan = self.router.route(
            current_message="Which 5-star AC should I buy to cut my summer bills?",
            active_state=ActiveConversationState(active_workflow="historical_analytics"),
            last_assistant_message="Your cooling contributed to 45% of last month's bill.",
        )
        self.assertIn("appliance", plan.primary_intent)
        self.assertEqual(plan.tool_scope, "planning_and_upgrades")
        self.assertIn("analyze_appliance_scenario", plan.candidate_tools)

    def test_scenario_3_appliance_comparison_to_tariff_inquiry(self):
        """Scenario 3: Appliance comparison -> tariff inquiry routes to tariff/billing."""
        plan = self.router.route(
            current_message="What is my current peak tariff rate per kWh?",
            active_state=ActiveConversationState(active_workflow="appliance_lifecycle"),
            last_assistant_message="The inverter model saves Rs 4,200 annually.",
        )
        self.assertIn("tariff", plan.primary_intent)
        self.assertEqual(plan.tool_scope, "telemetry_and_billing")

    def test_scenario_4_technical_rag_to_actual_consumption(self):
        """Scenario 4: Technical RAG -> actual consumption routes to meter telemetry."""
        plan = self.router.route(
            current_message="What was my actual energy consumption yesterday?",
            active_state=ActiveConversationState(active_workflow="general_inquiry"),
            last_assistant_message="Power factor is the ratio of real power to apparent power.",
        )
        self.assertIn("historical", plan.primary_intent)
        self.assertEqual(plan.tool_scope, "telemetry_and_billing")
        self.assertIn("query_consumption_history", plan.candidate_tools)

    def test_current_bill_uses_verified_context_not_prediction(self):
        plan = self.router.route(current_message="tell me my curr bill")
        self.assertEqual(plan.primary_intent, "current_billing_summary")
        self.assertEqual(plan.tool_scope, "context_only")
        self.assertFalse(plan.requires_tool_execution)
        self.assertEqual(plan.candidate_tools, [])

    def test_dated_bill_executes_actual_month_telemetry(self):
        plan = self.router.route(current_message="tell bill for dec 2018")
        self.assertEqual(plan.primary_intent, "historical_monthly_billing")
        self.assertEqual(plan.candidate_tools, ["query_consumption_history"])
        self.assertTrue(plan.requires_tool_execution)
        self.assertEqual(
            plan.routed_tool_arguments,
            {
                "start_date": "2018-12-01",
                "end_date": "2018-12-31",
                "granularity": "daily",
            },
        )

    def test_last_month_consumption_routes_to_verified_historical_tool(self):
        plan = self.router.route(
            current_message="What was my electricity consumption last month?",
            active_state=ActiveConversationState(active_workflow="house_planning"),
        )
        self.assertEqual(plan.primary_intent, "historical_monthly_billing")
        self.assertEqual(plan.candidate_tools, ["query_consumption_history"])
        self.assertTrue(plan.requires_tool_execution)
        expected = self.router._relative_month_range(-1)
        self.assertEqual(plan.routed_tool_arguments, expected)

    def test_current_vs_last_month_comparison_overrides_previous_workflow(self):
        plan = self.router.route(
            current_message="Compare my electricity consumption this month with last month.",
            active_state=ActiveConversationState(active_workflow="house_planning"),
        )
        self.assertEqual(plan.primary_intent, "consumption_period_comparison")
        self.assertEqual(plan.candidate_tools, ["compare_consumption_periods"])
        self.assertEqual(plan.follow_up_type, "new_request")
        self.assertTrue(plan.requires_tool_execution)
        self.assertEqual(
            set(plan.routed_tool_arguments),
            {"start_date_a", "end_date_a", "start_date_b", "end_date_b", "metric"},
        )
        self.assertEqual(plan.routed_tool_arguments["metric"], "consumption")

    def test_general_electricity_knowledge_routes_to_document_rag(self):
        plan = self.router.route(
            current_message="What does a household circuit breaker do?"
        )
        self.assertEqual(plan.primary_intent, "electricity_knowledge_rag")
        self.assertEqual(plan.tool_scope, "regulatory_and_standards")
        self.assertEqual(plan.candidate_tools, ["search_regulatory_documents"])
        self.assertTrue(plan.requires_tool_execution)

    def test_appliance_usage_question_routes_to_rag_not_household_telemetry(self):
        plan = self.router.route(
            current_message="How much electricity does a refrigerator use?"
        )
        self.assertEqual(plan.primary_intent, "electricity_knowledge_rag")
        self.assertEqual(plan.candidate_tools, ["search_regulatory_documents"])

    def test_personal_electricity_usage_routes_to_meter_telemetry(self):
        plan = self.router.route(
            current_message="How much electricity did I use last week?"
        )
        self.assertEqual(plan.primary_intent, "historical_telemetry_query")
        self.assertEqual(plan.tool_scope, "telemetry_and_billing")
        self.assertIn("query_consumption_history", plan.candidate_tools)
        self.assertTrue(plan.requires_tool_execution)

    def test_general_conversation_does_not_force_tool_execution(self):
        """A generic greeting should not trigger an unrelated analytics tool call."""
        plan = self.router.route(current_message="Hello")
        self.assertFalse(plan.requires_tool_execution)


class TestContextManagerAndSummarization(unittest.TestCase):
    """Test suite for Long-Conversation Summarization and Context Budgeting (16.4)."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.repo = ConversationMemoryRepository()
        self.context_mgr = ConversationContextManager(
            repository=self.repo,
            max_recent_turns=4,
            max_context_chars=4000,
        )
        self.user_id = f"test-long-user-{uuid.uuid4().hex[:8]}"
        self.conv_id = f"conv-long-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        with get_session() as session:
            session.query(ConversationMessageModel).filter_by(
                conversation_id=self.conv_id
            ).delete(synchronize_session=False)
            session.query(ConversationSessionModel).filter_by(
                id=self.conv_id
            ).delete(synchronize_session=False)
            session.commit()

    def test_long_conversation_summarization_and_budget_enforcement(self):
        """Verify that a 12-turn conversation produces a rolling summary and enforces context budget."""
        # Seed 12 conversation messages
        topics = [
            ("What is my current monthly bill?", "Your current month-to-date bill is Rs 3,450 for 345 kWh."),
            ("Why did it go up from last month?", "The increase was driven by 3 extra hours of daytime AC usage."),
            ("Can I switch to solar?", "Based on your 12 kWh daily consumption, a 3 kW rooftop solar array would offset 80%."),
            ("How much does 3kW solar cost?", "A 3 kW rooftop system typically costs around Rs 1,80,000 before subsidies."),
            ("What subsidies are available in Bengaluru?", "Under PM Surya Ghar, you are eligible for up to Rs 78,000 central subsidy."),
            ("Okay, help me plan electrical load for new house.", "Certainly. Which city is your new property located in?"),
        ]

        for user_msg, asst_msg in topics:
            self.repo.append_message(self.conv_id, "user", user_msg, user_id=self.user_id)
            self.repo.append_message(self.conv_id, "assistant", asst_msg, user_id=self.user_id)

        # Assemble prompt context for user answering "Bengaluru"
        assembled = self.context_mgr.assemble_turn_context(
            user_id=self.user_id,
            conversation_id=self.conv_id,
            entity_id="METER-1000",
            current_message="Bengaluru",
        )

        # Verify recent turns count is capped at max_recent_turns
        self.assertLessEqual(len(assembled.recent_messages), 4)

        # Verify rolling summary was triggered for the earlier turns
        self.assertIsNotNone(assembled.rolling_summary)
        summary_text = assembled.rolling_summary.summary_text
        self.assertGreater(len(summary_text), 10)

        # Verify total assembled system context strictly obeys context budget
        system_prompt = self.context_mgr.format_system_context(assembled)
        self.assertLessEqual(len(system_prompt), 4500)

        # Verify structured layers are present in system prompt
        self.assertIn("VERIFIED CUSTOMER PROFILE", system_prompt)
        self.assertIn("METER-1000", system_prompt)


class TestAPIIntegrationWithCustomerMemory(unittest.TestCase):
    """End-to-end REST API integration tests for customer memory and follow-up (16.1, 16.2)."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.client = self.app.test_client()

    def test_api_followup_and_session_continuity(self):
        """API client maintains conversation_id across turns and resolves follow-ups."""
        conv_id = f"api-session-{uuid.uuid4().hex[:8]}"

        # Turn 1: User initiates planning
        t1_res = self.client.post(
            "/api/v1/assistant/chat",
            json={
                "entity_id": "METER-1000",
                "persona": "household",
                "conversation_id": conv_id,
                "prompt": "I want to plan my electrical load for my new villa.",
            },
        )
        self.assertEqual(t1_res.status_code, 200)
        t1_data = t1_res.get_json()["data"]
        self.assertEqual(t1_data["status"], "success")

        # Turn 2: Follow-up answer "Bengaluru"
        t2_res = self.client.post(
            "/api/v1/assistant/chat",
            json={
                "entity_id": "METER-1000",
                "persona": "household",
                "conversation_id": conv_id,
                "prompt": "Bengaluru",
                "history": [
                    {"role": "user", "content": "I want to plan my electrical load for my new villa."},
                    {"role": "assistant", "content": "Which city is your property located in?"},
                ],
            },
        )
        self.assertEqual(t2_res.status_code, 200)
        t2_data = t2_res.get_json()["data"]
        self.assertEqual(t2_data["status"], "success")
        self.assertEqual(t2_data["mode"], "house_planning")
        self.assertIn("Bengaluru", t2_data["answer"])
        self.assertNotIn("Domain Scope Notice", t2_data["answer"])


if __name__ == "__main__":
    unittest.main()
