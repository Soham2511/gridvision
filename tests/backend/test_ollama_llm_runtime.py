"""Comprehensive Verification Suite for Ollama Runtime LLM Provider (qwen3:8b).

Validates:
1. Provider Configuration:
   - OLLAMA_BASE_URL and OLLAMA_MODEL (qwen3:8b) configured through environment.
   - Groq credentials retained in configuration and .env without being active.
2. OllamaLLMAdapter:
   - BaseLLMProvider contract implementation.
   - Health check and availability probing (http://localhost:11434/api/tags).
   - Chat completion with Ollama /api/chat.
   - Actionable diagnostics when Ollama server or model is unavailable (no silent fallback).
3. ResidentialAgentFactory with Ollama:
   - Constructs ChatOllama with configured qwen3:8b model.
   - Respects custom chat models for deterministic unit testing.
4. ResidentialAssistantOrchestrator Integration:
   - Centralized provider integration without Groq runtime invocation.
   - Zero active Groq fallback calls.
"""

from __future__ import annotations

import os
import json
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from app import create_app
from app.config import BaseConfig, TestingConfig
from app.providers.llm.base import BaseLLMProvider, LLMInferenceError
from app.providers.llm.mock_adapter import MockLLMAdapter
from app.providers.llm.ollama_adapter import OllamaLLMAdapter
from app.providers.sample_data_provider import SampleDataProvider
from app.services.assistant.agent_factory import (
    MockChatModel,
    ResidentialAgentFactory,
)
from app.interfaces.assistant.tools.registry import create_residential_tools
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator


class TestOllamaConfigurationAndCredentials(unittest.TestCase):
    """Verify environment configuration for Ollama and preservation of Groq credentials."""

    def test_ollama_configuration_defaults(self):
        """OLLAMA_BASE_URL and OLLAMA_MODEL default to local service and qwen3:8b."""
        self.assertIn("11434", BaseConfig.OLLAMA_BASE_URL)
        self.assertEqual(BaseConfig.OLLAMA_MODEL, "qwen3:8b")

    def test_groq_credentials_retained(self):
        """Existing Groq configuration remains in BaseConfig for future switch-back."""
        self.assertTrue(hasattr(BaseConfig, "GROQ_API_KEY"))
        self.assertTrue(hasattr(BaseConfig, "GROQ_BASE_URL"))
        self.assertTrue(hasattr(BaseConfig, "GROQ_MODEL"))

    def test_env_file_retains_groq_and_defines_ollama(self):
        """backend/.env must have OLLAMA_MODEL=qwen3:8b and preserve GROQ_API_KEY."""
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("OLLAMA_MODEL=qwen3:8b", content)
            self.assertIn("OLLAMA_BASE_URL=", content)
            self.assertIn("GROQ_API_KEY=", content)


class TestOllamaLLMAdapter(unittest.TestCase):
    """Verify Ollama adapter health probing, error handling, and completion behavior."""

    def setUp(self):
        self.adapter = OllamaLLMAdapter(
            base_url="http://localhost:11434",
            model="qwen3:8b",
            timeout=5.0,
        )

    def test_effective_properties(self):
        """Adapter correctly derives effective base URL and model name."""
        self.assertEqual(self.adapter.effective_base_url, "http://localhost:11434")
        self.assertEqual(self.adapter.effective_model, "qwen3:8b")
        versioned_adapter = OllamaLLMAdapter(
            base_url="http://localhost:11434/v1",
            model="qwen3:8b",
        )
        self.assertEqual(versioned_adapter.effective_base_url, "http://localhost:11434")

    def test_unreachable_server_raises_clear_actionable_error(self):
        """When Ollama is unreachable, adapter raises LLMInferenceError with actionable instructions."""
        bad_adapter = OllamaLLMAdapter(
            base_url="http://localhost:59999",
            model="qwen3:8b",
            timeout=1.0,
        )
        self.assertFalse(bad_adapter.is_available())

        with self.assertRaises(LLMInferenceError) as ctx:
            bad_adapter.generate_chat_completion(
                messages=[{"role": "user", "content": "Hello"}]
            )

        err_msg = str(ctx.exception)
        self.assertIn("Ollama server is not reachable", err_msg)
        self.assertIn("qwen3:8b", err_msg)
        self.assertIn("ollama run", err_msg)

    def test_empty_model_response_raises_inference_error(self):
        """A successful HTTP response with empty model content must not look like success."""
        adapter = OllamaLLMAdapter(
            base_url="http://localhost:11434",
            model="qwen3:8b",
            max_retries=0,
        )
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"message":{"content":""}}'
        response.__enter__.return_value = response
        with patch.object(adapter, "is_available", return_value=True):
            with patch("urllib.request.urlopen", return_value=response):
                with self.assertRaises(LLMInferenceError) as ctx:
                    adapter.generate_chat_completion(
                        messages=[{"role": "user", "content": "Hello"}]
                    )

        self.assertIn("empty completion", str(ctx.exception))

    def test_completion_disables_qwen_thinking_mode(self):
        """Qwen3 must return its user-visible answer in message.content."""
        adapter = OllamaLLMAdapter(
            base_url="http://localhost:11434",
            model="qwen3:8b",
            max_retries=0,
        )
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"message":{"content":"OK"}}'
        response.__enter__.return_value = response
        with patch.object(adapter, "is_available", return_value=True):
            with patch("urllib.request.urlopen", return_value=response) as urlopen:
                answer = adapter.generate_chat_completion(
                    messages=[{"role": "user", "content": "Reply OK."}]
                )

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertFalse(payload["think"])
        self.assertEqual(answer, "OK")

    def test_is_available_when_ollama_server_up(self):
        """Adapter detects running local Ollama server on port 11434."""
        is_up = self.adapter.is_available(timeout=2.0, force_live=True)
        # Server is active on port 11434
        self.assertTrue(is_up)

    def test_list_installed_models_parses_tags(self):
        """list_installed_models returns a list from /api/tags without throwing."""
        models = self.adapter.list_installed_models(timeout=2.0)
        self.assertIsInstance(models, list)


class TestResidentialAgentFactoryWithOllama(unittest.TestCase):
    """Verify LangChain agent factory builds ChatOllama and supports test mocks."""

    def setUp(self):
        self.factory = ResidentialAgentFactory(
            base_url="http://localhost:11434",
            model_name="qwen3:8b",
        )

    def test_factory_ollama_properties(self):
        """Factory initializes with Ollama base URL and qwen3:8b model."""
        self.assertEqual(self.factory.ollama_base_url, "http://localhost:11434")
        self.assertEqual(self.factory.model_name, "qwen3:8b")
        versioned_factory = ResidentialAgentFactory(
            base_url="http://localhost:11434/v1",
            model_name="qwen3:8b",
        )
        self.assertEqual(versioned_factory.ollama_base_url, "http://localhost:11434")

    def test_factory_builds_chat_ollama_when_available(self):
        """When Ollama is running, factory returns a LangChain ChatOllama instance."""
        if self.factory.is_ollama_available():
            chat_model = self.factory.build_chat_model(force_live=True)
            from langchain_ollama import ChatOllama
            self.assertIsInstance(chat_model, ChatOllama)
            self.assertEqual(chat_model.model, "qwen3:8b")
            self.assertEqual(chat_model.base_url.rstrip("/"), "http://localhost:11434")
            self.assertFalse(chat_model.reasoning)

    def test_factory_disables_qwen_reasoning_using_langchain_ollama_option(self):
        """Qwen3 must receive the supported reasoning=False setting."""
        with (
            patch.object(self.factory, "is_ollama_available", return_value=True),
            patch("langchain_ollama.ChatOllama") as chat_ollama,
        ):
            self.factory.build_chat_model(force_live=True)

        self.assertIs(chat_ollama.call_args.kwargs["reasoning"], False)
        self.assertNotIn("think", chat_ollama.call_args.kwargs)

    def test_factory_honors_custom_chat_model(self):
        """Factory always prioritizes custom_chat_model (e.g. MockChatModel) for testing."""
        mock_model = MockChatModel(canned_response="Custom test completion")
        factory = ResidentialAgentFactory(custom_chat_model=mock_model)
        built = factory.build_chat_model()
        self.assertEqual(built, mock_model)

    def test_agent_cache_does_not_reuse_stale_grounding_or_routing(self):
        """A new turn gets an agent compiled with its current context and tool selection."""
        factory = ResidentialAgentFactory(custom_chat_model=MockChatModel())
        first = factory.create_agent_for_household(
            meter_id="METER-1000",
            system_prompt="Grounding for the first turn",
            tool_scope="telemetry_and_billing",
        )
        second = factory.create_agent_for_household(
            meter_id="METER-1000",
            system_prompt="Grounding for the second turn",
            tool_scope="telemetry_and_billing",
            recommended_tools=["query_consumption_history"],
            requires_tool_execution=True,
        )

        self.assertIsNot(first, second)
        self.assertEqual(len(factory._agent_cache), 2)

    def test_langchain_agent_routes_only_selected_tools_and_exact_arguments(self):
        """The existing agent receives the selected native tools and router-resolved args."""
        factory = ResidentialAgentFactory(custom_chat_model=MockChatModel())
        with patch(
            "app.services.assistant.agent_factory.create_agent",
            return_value=object(),
        ) as create_agent_mock:
            agent = factory.create_agent_for_household(
                meter_id="METER-1000",
                system_prompt="Grounded prompt",
                tool_scope="telemetry_and_billing",
                recommended_tools=["query_consumption_history"],
                routed_tool_arguments={
                    "start_date": "2018-12-01",
                    "end_date": "2018-12-31",
                    "granularity": "daily",
                },
                requires_tool_execution=True,
            )

        self.assertIs(agent, create_agent_mock.return_value)
        agent_tools = create_agent_mock.call_args.kwargs["tools"]
        self.assertEqual([tool.name for tool in agent_tools], ["query_consumption_history"])
        system_prompt = create_agent_mock.call_args.kwargs["system_prompt"]
        self.assertIn('"start_date": "2018-12-01"', system_prompt)
        self.assertIn("tool execution is required", system_prompt)

    def test_live_ollama_executes_existing_tool_and_synthesizes_final_answer(self):
        """Qwen3 uses native tool-call IDs, real meter data, and final synthesis."""
        if not self.factory.is_ollama_available():
            self.skipTest("Local Ollama is unavailable.")

        agent = self.factory.create_agent_for_household(
            meter_id="METER-1000",
            system_prompt=(
                "You are a household energy assistant. Use actual historical data for "
                "completed months and answer only from tool results."
            ),
            tool_scope="telemetry_and_billing",
            recommended_tools=["query_consumption_history"],
            routed_tool_arguments={
                "start_date": "2018-12-01",
                "end_date": "2018-12-31",
                "granularity": "daily",
            },
            requires_tool_execution=True,
            timeout=90.0,
            force_live=True,
        )
        result = agent.invoke({
            "messages": self.factory.sanitize_history_and_prompt(
                "What was my electricity consumption in December 2018?"
            )
        })
        messages = result["messages"]
        tool_call_messages = [
            message for message in messages
            if getattr(message, "tool_calls", None)
        ]
        tool_result_messages = [
            message for message in messages
            if getattr(message, "type", None) == "tool"
        ]
        self.assertTrue(tool_call_messages)
        self.assertTrue(tool_result_messages)
        call = tool_call_messages[0].tool_calls[0]
        self.assertEqual(call["name"], "query_consumption_history")
        self.assertEqual(call["args"]["start_date"], "2018-12-01")
        self.assertEqual(call["args"]["end_date"], "2018-12-31")
        self.assertEqual(tool_result_messages[0].tool_call_id, call["id"])
        self.assertIn("382.9", tool_result_messages[0].content)
        self.assertIn("382.9", messages[-1].content)
        self.assertEqual(tool_result_messages[0].name, "query_consumption_history")

    def test_live_orchestrator_answers_historical_bill_from_verified_tool_result(self):
        """The full request path returns a concise calculated bill after historical lookup."""
        if not self.factory.is_ollama_available():
            self.skipTest("Local Ollama is unavailable.")

        app = create_app(config_class=TestingConfig)
        with (
            app.app_context(),
            patch.object(BaseConfig, "TESTING", False),
            patch.dict(os.environ, {"FLASK_ENV": "production"}),
        ):
            orchestrator = ResidentialAssistantOrchestrator(
                data_provider=SampleDataProvider(),
                authorized_meters=["METER-1000"],
                agent_factory=self.factory,
            )
            result = orchestrator.answer_query(
                prompt="tell bill for dec 2018",
                entity_id="METER-1000",
                user_id="ollama-bill-test",
                conversation_id="ollama-bill-test",
            )

        self.assertEqual(result["status"], "success")
        self.assertIn("382.9", result["answer"])
        self.assertIn("3,829", result["answer"])
        self.assertIn("calculated", result["answer"].lower())
        self.assertLessEqual(len(result["answer"]), 500)

    def test_live_ollama_generates_direct_response_without_tool_call(self):
        """Simple conceptual questions receive a normal answer without invoking tools."""
        if not self.factory.is_ollama_available():
            self.skipTest("Local Ollama is unavailable.")

        model = self.factory.build_chat_model(force_live=True)
        response = model.invoke([
            HumanMessage(content="In one sentence, what is electricity consumption?")
        ])
        self.assertTrue(response.content.strip())
        self.assertFalse(response.tool_calls)

    def test_context_only_agent_does_not_expose_prediction_tool(self):
        """Current-bill questions should only see the verified billing context."""
        tools = create_residential_tools(
            authorized_meter_id="METER-1000",
            tool_scope="context_only",
        )
        self.assertEqual(tools, [])

    def test_factory_offline_error_gives_clear_instructions(self):
        """In non-test mode with bad URL, factory raises RuntimeError with explicit Ollama guidance."""
        offline_factory = ResidentialAgentFactory(
            base_url="http://localhost:59999",
            model_name="qwen3:8b",
        )
        with patch.object(BaseConfig, "TESTING", False):
            with patch.dict(os.environ, {"FLASK_ENV": "production"}):
                with self.assertRaises(RuntimeError) as ctx:
                    offline_factory.build_chat_model()
                self.assertIn("Ollama server is unavailable", str(ctx.exception))
                self.assertIn("Groq fallback is disabled", str(ctx.exception))


class TestOrchestratorCentralizedOllama(unittest.TestCase):
    """Verify orchestrator uses centralized Ollama LLM provider without Groq fallback."""

    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.mock_llm = MockLLMAdapter(canned_response="Verified Ollama completion")

    def test_orchestrator_initializes_with_ollama_adapter(self):
        """Orchestrator creates agent_factory when given OllamaLLMAdapter."""
        ollama_adapter = OllamaLLMAdapter(
            base_url="http://localhost:11434",
            model="qwen3:8b",
        )
        orchestrator = ResidentialAssistantOrchestrator(
            data_provider=SampleDataProvider(),
            llm_provider=ollama_adapter,
        )
        self.assertIsNotNone(orchestrator.agent_factory)
        self.assertEqual(orchestrator.agent_factory.model_name, "qwen3:8b")

    def test_required_tool_query_does_not_accept_a_mock_direct_answer(self):
        """A tool-required query fails clearly when the injected model skips its tool."""
        orchestrator = ResidentialAssistantOrchestrator(
            data_provider=SampleDataProvider(),
            llm_provider=self.mock_llm,
            agent_factory=ResidentialAgentFactory(custom_chat_model=MockChatModel()),
        )
        res = orchestrator.answer_query(
            prompt="What is my connected load?",
            entity_id="METER-1000",
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("couldn't complete the required verified data lookup", res["answer"])


if __name__ == "__main__":
    unittest.main()
