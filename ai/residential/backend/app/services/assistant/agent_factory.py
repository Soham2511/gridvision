"""LangChain agent factory for the GridVision residential assistant."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, List, Optional
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool

from app.config import BaseConfig
from app.interfaces.assistant.tools.registry import create_residential_tools
from app.providers.llm.ollama_adapter import normalize_ollama_base_url
from app.services.assistant.dialogue_state import compact_history_for_llm

logger = logging.getLogger("gridvision.services.assistant.agent_factory")


class MockChatModel(BaseChatModel):
    """Deterministic chat model for tests and explicitly offline environments."""

    canned_response: str = "This is a verified mock residential assistant completion."

    @property
    def _llm_type(self) -> str:
        return "mock_chat_model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.canned_response))]
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


class _RequireToolExecutionMiddleware(AgentMiddleware):
    """Force an initial native tool call when routing marks one as mandatory."""

    def __init__(self, routed_tool_call: dict[str, Any] | None = None) -> None:
        self.routed_tool_call = routed_tool_call

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        tool_already_ran = any(
            isinstance(message, ToolMessage) for message in request.messages
        )
        if self.routed_tool_call and not tool_already_ran:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": self.routed_tool_call["name"],
                    "args": self.routed_tool_call["args"],
                    "id": uuid4().hex,
                    "type": "tool_call",
                }],
            )
        if (
            tool_already_ran
            and self.routed_tool_call
            and self.routed_tool_call["name"] == "query_consumption_history"
        ):
            tool_result = next(
                message for message in reversed(request.messages)
                if isinstance(message, ToolMessage)
            )
            user_message = next(
                message for message in reversed(request.messages)
                if isinstance(message, HumanMessage)
            )
            system_prompt = (
                request.system_message.text if request.system_message else ""
            )
            tariff_match = re.search(
                r"tariff is ₹([\d.]+)/kWh", system_prompt, re.IGNORECASE
            )
            tariff_instruction = (
                f"The verified tariff is ₹{tariff_match.group(1)}/kWh."
                if tariff_match
                else "No verified tariff rate is available; do not calculate a bill amount."
            )
            request = request.override(
                system_message=SystemMessage(
                    content=(
                        "You are GridVision's household energy assistant. Use only the "
                        "verified tool result to answer the user's exact request. "
                        f"{tariff_instruction} For historical bills, calculate the "
                        "energy charge from recorded kWh and the verified tariff, and "
                        "label it as a calculated energy charge, not an official invoice. "
                        "Keep the answer to at most two short sentences. Include the "
                        "date range and data completeness when available. Do not list "
                        "daily readings, add unsolicited analysis, or guess missing values."
                    )
                ),
                messages=[
                    HumanMessage(
                        content=(
                            f"User request: {user_message.text}\n"
                            f"Verified tool result (JSON): {tool_result.content}"
                        )
                    )
                ],
                tools=[],
            )
        if request.tools and not tool_already_ran:
            request = request.override(tool_choice="any")
        return handler(request)


class ResidentialAgentFactory:
    """Create the existing LangChain tool-calling workflow with Ollama as its model."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        complex_timeout: float | None = None,
        max_retries: int | None = None,
        custom_chat_model: BaseChatModel | None = None,
        api_key: str | None = None,
    ) -> None:
        self.ollama_base_url = normalize_ollama_base_url(
            base_url
            or os.getenv("OLLAMA_BASE_URL")
            or getattr(BaseConfig, "OLLAMA_BASE_URL", "http://localhost:11434")
        )
        self.model_name = (
            model_name
            or os.getenv("OLLAMA_MODEL")
            or getattr(BaseConfig, "OLLAMA_MODEL", "qwen3:8b")
        ).strip()
        self.temperature = (
            temperature if temperature is not None else BaseConfig.ASSISTANT_TEMPERATURE
        )
        self.max_tokens = (
            max_tokens if max_tokens is not None else BaseConfig.ASSISTANT_MAX_TOKENS
        )
        self.timeout = (
            timeout if timeout is not None else BaseConfig.ASSISTANT_TIMEOUT_SECONDS
        )
        self.complex_timeout = (
            complex_timeout
            if complex_timeout is not None
            else getattr(BaseConfig, "ASSISTANT_COMPLEX_TIMEOUT_SECONDS", 75.0)
        )
        self.max_retries = (
            max_retries if max_retries is not None else BaseConfig.ASSISTANT_MAX_RETRIES
        )
        self.custom_chat_model = custom_chat_model
        # Retained only for configuration compatibility; runtime never calls Groq.
        self.api_key = (api_key or BaseConfig.GROQ_API_KEY or "").strip()
        self._agent_cache: dict[tuple[Any, ...], Any] = {}

    @staticmethod
    def _is_testing() -> bool:
        if (
            os.getenv("FLASK_ENV") == "production"
            and not getattr(BaseConfig, "TESTING", False)
        ):
            return False
        if (
            getattr(BaseConfig, "TESTING", False)
            or os.getenv("FLASK_ENV") == "testing"
            or bool(os.getenv("PYTEST_CURRENT_TEST"))
        ):
            return True
        try:
            from flask import current_app

            return bool(current_app and current_app.config.get("TESTING"))
        except RuntimeError:
            return False

    def is_ollama_available(self, timeout: float = 2.0) -> bool:
        """Return whether the configured Ollama server responds to its tags endpoint."""
        import urllib.request

        try:
            request = urllib.request.Request(
                f"{self.ollama_base_url}/api/tags",
                headers={"User-Agent": "GridVision-HealthCheck"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

    def is_available(self, force_live: bool = False) -> bool:
        """Return availability of the injected model or active Ollama runtime."""
        if self.custom_chat_model is not None:
            return True
        if self._is_testing() and not force_live:
            return False
        return self.is_ollama_available()

    def build_chat_model(
        self,
        timeout: float | None = None,
        model_override: str | None = None,
        force_live: bool = False,
    ) -> BaseChatModel:
        """Build ChatOllama for Qwen3, or the deterministic model in tests."""
        if self.custom_chat_model is not None:
            return self.custom_chat_model

        effective_model = (model_override or self.model_name).strip()
        if self._is_testing() and not force_live:
            return MockChatModel()
        if not self.is_ollama_available():
            raise RuntimeError(
                f"Ollama server is unavailable at '{self.ollama_base_url}' or model "
                f"'{effective_model}' is not reachable. Ensure Ollama is running and "
                f"the model is pulled. Groq fallback is disabled."
            )

        try:
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=effective_model,
                base_url=self.ollama_base_url,
                temperature=self.temperature,
                num_predict=self.max_tokens,
                timeout=timeout if timeout is not None else self.timeout,
                reasoning=False,
            )
        except Exception as exc:
            logger.exception("Failed to initialize ChatOllama model '%s'", effective_model)
            raise RuntimeError(
                f"Failed to initialize Ollama chat model '{effective_model}' "
                f"at '{self.ollama_base_url}': {exc}"
            ) from exc

    def create_agent_for_household(
        self,
        meter_id: str,
        system_prompt: str,
        prediction_service: Any = None,
        tariff_rate: float = 10.0,
        additional_tools: list[BaseTool] | None = None,
        include_knowledge_tools: bool = True,
        retriever: Any = None,
        resolver: Any = None,
        tool_scope: str = "all",
        recommended_tools: List[str] | None = None,
        routed_tool_arguments: dict[str, Any] | None = None,
        requires_tool_execution: bool = False,
        timeout: float | None = None,
        model_override: str | None = None,
        force_live: bool = False,
    ) -> Any:
        """Create a LangChain graph that owns native tool execution and result handoff."""
        tools = create_residential_tools(
            authorized_meter_id=meter_id,
            prediction_service=prediction_service,
            tariff_rate=tariff_rate,
            include_knowledge_tools=include_knowledge_tools,
            retriever=retriever,
            resolver=resolver,
            tool_scope=tool_scope,
        )
        if additional_tools:
            tools.extend(additional_tools)

        selected_names = list(dict.fromkeys(recommended_tools or []))
        if selected_names:
            tools = [tool for tool in tools if tool.name in selected_names]
        if requires_tool_execution and not tools:
            raise RuntimeError(
                f"Required assistant tools are unavailable for scope '{tool_scope}'."
            )

        routed_prompt = system_prompt
        if selected_names:
            routed_prompt += (
                "\n\nFor this request, the router selected these tools: "
                + ", ".join(selected_names)
                + ". Use the relevant selected tool before answering."
            )
        if requires_tool_execution:
            routed_prompt += (
                "\nA tool execution is required for this request. Do not answer from "
                "memory or guess if the tool cannot provide the requested data."
            )
        if routed_tool_arguments:
            routed_prompt += (
                "\nThe router resolved these exact arguments for the selected tool; "
                "use them unchanged:\n"
                + json.dumps(routed_tool_arguments, sort_keys=True)
            )

        prompt_digest = hashlib.sha256(routed_prompt.encode("utf-8")).hexdigest()
        cache_key = (
            meter_id,
            tool_scope,
            timeout,
            model_override,
            force_live,
            prompt_digest,
            tuple(tool.name for tool in tools),
        )
        if not additional_tools and cache_key in self._agent_cache:
            return self._agent_cache[cache_key]

        model = self.build_chat_model(
            timeout=timeout,
            model_override=model_override,
            force_live=force_live,
        )
        routed_tool_call = None
        if routed_tool_arguments:
            if not selected_names:
                raise RuntimeError(
                    "Routed tool arguments were provided without a selected tool."
                )
            routed_tool_call = {
                "name": selected_names[0],
                "args": routed_tool_arguments,
            }
        middleware = (
            [_RequireToolExecutionMiddleware(routed_tool_call)]
            if requires_tool_execution
            else []
        )
        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=routed_prompt,
            middleware=middleware,
        )
        if not additional_tools:
            self._agent_cache[cache_key] = agent
        return agent

    @staticmethod
    def sanitize_history_and_prompt(
        prompt: str,
        history: list[dict[str, Any]] | None = None,
        max_history_turns: int = 4,
    ) -> list[BaseMessage]:
        """Compact prior turns while preserving the complete current prompt."""
        messages: list[BaseMessage] = []
        if history:
            compacted = compact_history_for_llm(
                history,
                max_turns=max_history_turns,
                max_assistant_chars=250,
                max_user_chars=350,
            )
            for item in compacted:
                if item["role"] == "user":
                    messages.append(HumanMessage(content=item["content"]))
                elif item["role"] == "assistant":
                    messages.append(AIMessage(content=item["content"]))
        clean_prompt = (prompt or "").strip()
        if clean_prompt:
            messages.append(HumanMessage(content=clean_prompt))
        return messages
