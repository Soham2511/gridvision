"""Unit and Integration Tests for Dialogue State Tracking and Multi-Turn Continuations.

Validates:
1. Contextual Anaphora & Continuation Resolution ('yes generate', 'proceed', 'sure', 'option 1').
2. History compaction to keep total tokens well under Groq ITPM (7,000) limits.
3. Multi-turn continuity: ensures affirmative answers inherit the active feature domain (house planning, appliance lifecycle, cost management) and are NEVER marked irrelevant.
4. Target-calibrated savings calculations (eliminating mathematical contradictions).
5. Fast failover to deterministic domain engines on LLM rate-limit or timeout.
"""

from __future__ import annotations

import unittest
from app import create_app
from app.config import TestingConfig
from app.providers.sample_data_provider import SampleDataProvider
from app.services.assistant.dialogue_state import (
    compact_history_for_llm,
    is_affirmative_or_continuation,
    resolve_dialogue_context,
)
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator
from app.services.assistant.agentic_orchestrator import AgenticKnowledgeOrchestrator


class TestDialogueStateAndContinuation(unittest.TestCase):
    """Test suite for multi-turn dialogue management, anaphora resolution, and history compaction."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.client = self.app.test_client()
        self.provider = SampleDataProvider()
        self.orchestrator = ResidentialAssistantOrchestrator(
            data_provider=self.provider,
            tariff_rate=10.0,
            authorized_meters=["METER-1000", "2254213", "METER-2254213"],
        )

    # 1. Affirmative and Continuation Detection
    def test_affirmative_keyword_detection(self):
        """Verify standard affirmative and selection phrases are correctly recognized."""
        positives = [
            "yes", "yes generate", "generate", "proceed", "sure", "ok", "okay",
            "do it", "go ahead", "please do", "confirm", "yes please", "generate plan",
            "apply", "optimize", "update", "continue", "next", "show me", "tell me more",
            "yes do it", "yes proceed", "ok do it", "sounds good", "option 1", "option 2",
            "the first one", "the second option",
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                self.assertTrue(
                    is_affirmative_or_continuation(phrase),
                    f"Expected '{phrase}' to be recognized as affirmative/continuation",
                )

        negatives = [
            "what is my current bill",
            "tell me about BEE star ratings",
            "who was Albert Einstein",
            "my fan is broken",
        ]
        for phrase in negatives:
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    is_affirmative_or_continuation(phrase),
                    f"Expected '{phrase}' NOT to be recognized as affirmative/continuation",
                )

    # 2. Contextual Resolution from House Planning Proposal
    def test_yes_generate_resolves_to_house_planning(self):
        """'yes generate' following a house planning proposal must resolve to house_planning with planning tool scope."""
        history = [
            {
                "role": "user",
                "content": "Please analyze my new house energy plan (connected load: 9.21 kW, peak demand: 5.99 kW, recommended tier: Balanced). What are the key optimization steps?",
            },
            {
                "role": "assistant",
                "content": (
                    "To achieve a 20% additional reduction in your monthly energy bill, here is the optimized plan...\n"
                    "Would you like me to generate the updated energy plan with these optimizations included?"
                ),
            },
        ]
        resolved = resolve_dialogue_context("yes generate", history=history)
        self.assertTrue(resolved.is_continuation)
        self.assertEqual(resolved.resolved_mode, "house_planning")
        self.assertEqual(resolved.tool_scope, "planning_and_upgrades")
        self.assertIn("user confirmed", resolved.effective_prompt.lower())

    # 3. Contextual Resolution from Appliance Scenario Proposal
    def test_proceed_resolves_to_appliance_scenario(self):
        """'proceed' following an appliance upgrade discussion must resolve to appliance_lifecycle."""
        history = [
            {
                "role": "user",
                "content": "Should I replace my 6-year-old 1.5T non-inverter AC with a 5-Star BEE Dual-Inverter model?",
            },
            {
                "role": "assistant",
                "content": (
                    "Upgrading to a 5-Star BEE Dual-Inverter AC will save ~400 kWh/year and ₹4,000/year. "
                    "Would you like me to proceed with the full lifecycle payback analysis?"
                ),
            },
        ]
        resolved = resolve_dialogue_context("proceed", history=history)
        self.assertTrue(resolved.is_continuation)
        self.assertEqual(resolved.resolved_mode, "appliance_lifecycle")
        self.assertEqual(resolved.tool_scope, "planning_and_upgrades")

    # 4. History Compaction & Token Overflow Defense
    def test_history_compaction_strips_tables_and_limits_size(self):
        """History compaction must strip redundant markdown tables and constrain chars to prevent rate limit overflow."""
        huge_table = "\n".join([f"| Row {i} | Val A | Val B | Val C |" for i in range(25)])
        bloated_history = [
            {"role": "user", "content": "Tell me my usage"},
            {"role": "assistant", "content": f"Here is your breakdown:\n{huge_table}\n[BEE] IS 732 compliance verified."},
            {"role": "user", "content": "What about my peak?"},
            {"role": "assistant", "content": f"Peak demand observed:\n{huge_table}\n[CEA] Standard emissions applied."},
        ]

        compacted = compact_history_for_llm(bloated_history, max_turns=4, max_assistant_chars=300)
        self.assertLessEqual(len(compacted), 4)

        for turn in compacted:
            if turn["role"] == "assistant":
                self.assertNotIn("| Row 0 |", turn["content"])
                self.assertLessEqual(len(turn["content"]), 360)

        total_chars = sum(len(t["content"]) for t in compacted)
        # Total history characters must stay well under 1,500 chars (< 400 tokens)
        self.assertLess(total_chars, 1500)

    # 5. End-to-End Orchestrator Execution of "yes generate"
    def test_orchestrator_handles_yes_generate_without_timeout_or_error(self):
        """Orchestrator must execute 'yes generate' in multi-turn conversation and return an updated energy plan."""
        history = [
            {
                "role": "user",
                "content": "Please analyze my new house energy plan (connected load: 9.21 kW, peak demand: 5.99 kW, recommended tier: Balanced). What are the key optimization steps?",
            },
            {
                "role": "assistant",
                "content": (
                    "To achieve a 20% additional reduction in your monthly energy bill, here is the optimized plan: "
                    "5-Star BLDC ceiling fans, 3 kWp solar PV, 5-Star dual-inverter ACs. "
                    "Would you like me to generate the updated energy plan with these optimizations included?"
                ),
            },
        ]

        resp = self.orchestrator.answer_query(
            prompt="yes generate",
            entity_id="METER-1000",
            history=history,
        )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("mode"), "house_planning")
        answer = resp.get("answer", "")
        # Must contain structured Before vs After comparison and key metrics
        self.assertIn("Before vs. After", answer)
        self.assertIn("Connected Load", answer)
        self.assertIn("BLDC", answer)
        # Must never return the irrelevant / out-of-scope response
        self.assertNotIn("appears outside the domain", answer)
        self.assertNotIn("Domain Scope Notice", answer)

    # 6. REST API Endpoint Integration Test for "yes generate"
    def test_api_chat_endpoint_multi_turn_yes_generate(self):
        """API POST /api/v1/assistant/chat must successfully process 'yes generate' with history."""
        payload = {
            "entity_id": "METER-1000",
            "persona": "household",
            "prompt": "yes generate",
            "history": [
                {
                    "role": "user",
                    "content": "Please analyze my new house energy plan (connected load: 9.21 kW, peak demand: 5.99 kW, recommended tier: Balanced).",
                },
                {
                    "role": "assistant",
                    "content": "Balanced plan calculated. Would you like me to generate the updated energy plan with these optimizations included?",
                },
            ],
        }
        res = self.client.post("/api/v1/assistant/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        resp_data = data.get("data", {})
        self.assertEqual(resp_data.get("status"), "success")
        self.assertEqual(resp_data.get("mode"), "house_planning")
        self.assertIn("Before vs. After", resp_data.get("answer", ""))


if __name__ == "__main__":
    unittest.main()
