"""LangChain AI Agent Factory for GridVision Residential Assistant.

Constructs LangChain chat models, registers meter-isolated tools, enforces conversation safety,
and returns compiled agent graphs for standard tool-calling execution.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool

from app.config import BaseConfig
from app.interfaces.assistant.tools.registry import create_residential_tools

logger = logging.getLogger("gridvision.services.assistant.agent_factory")


class MockChatModel(BaseChatModel):
    """Deterministic, provider-free LangChain ChatModel for unit testing and offline development."""

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
        # Mock model acknowledges tool binding without changing execution
        return self


from app.services.assistant.dialogue_state import compact_history_for_llm


class ResidentialAgentFactory:
    """Factory responsible for creating configured LangChain models and tool-calling agents."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        complex_timeout: float | None = None,
        max_retries: int | None = None,
        custom_chat_model: BaseChatModel | None = None,
    ) -> None:
        self.api_key = (api_key or BaseConfig.GROQ_API_KEY or "").strip()
        self.base_url = (base_url or BaseConfig.GROQ_BASE_URL or "").strip()
        self.model_name = (model_name or BaseConfig.GROQ_MODEL or "openai/gpt-oss-20b").strip()
        self.temperature = temperature if temperature is not None else BaseConfig.ASSISTANT_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else BaseConfig.ASSISTANT_MAX_TOKENS
        self.timeout = timeout if timeout is not None else BaseConfig.ASSISTANT_TIMEOUT_SECONDS
        self.complex_timeout = (
            complex_timeout
            if complex_timeout is not None
            else getattr(BaseConfig, "ASSISTANT_COMPLEX_TIMEOUT_SECONDS", 35.0)
        )
        self.max_retries = max_retries if max_retries is not None else BaseConfig.ASSISTANT_MAX_RETRIES
        self.custom_chat_model = custom_chat_model
        self._agent_cache: dict[str, Any] = {}

    def is_groq_available(self) -> bool:
        """Return True if a valid Groq API key is present."""
        return bool(self.api_key and len(self.api_key) > 5)

    def build_chat_model(self, timeout: float | None = None) -> BaseChatModel:
        """Construct the underlying BaseChatModel (ChatGroq or MockChatModel) with optional adaptive timeout."""
        if self.custom_chat_model is not None:
            return self.custom_chat_model

        effective_timeout = timeout if timeout is not None else self.timeout

        if self.is_groq_available():
            try:
                from langchain_groq import ChatGroq

                clean_base_url = (self.base_url or "").strip().rstrip("/")
                if clean_base_url.endswith("/openai/v1"):
                    clean_base_url = clean_base_url[:-len("/openai/v1")].rstrip("/")
                if not clean_base_url:
                    clean_base_url = "https://api.groq.com"

                logger.info(
                    "Configuring ChatGroq with model '%s' (base_url=%s, timeout=%.1fs, retries=%d)",
                    self.model_name,
                    clean_base_url,
                    effective_timeout,
                    self.max_retries,
                )
                return ChatGroq(
                    model=self.model_name,
                    api_key=self.api_key,
                    base_url=clean_base_url,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=effective_timeout,
                    max_retries=self.max_retries,
                )
            except Exception as exc:
                logger.error("Failed to construct ChatGroq: %s; falling back to MockChatModel", exc)

        logger.info("Groq API key not configured or failed; using MockChatModel.")
        return MockChatModel()

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
        timeout: float | None = None,
    ) -> Any:
        """Construct or retrieve a compiled LangChain agent for the authorized household.

        Caches compiled graphs per (meter_id, tool_scope, timeout) to eliminate per-request graph compile latency.
        """
        cache_key = f"{meter_id}:{tool_scope}:{timeout}"
        if not additional_tools and cache_key in self._agent_cache:
            return self._agent_cache[cache_key]

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

        chat_model = self.build_chat_model(timeout=timeout)

        # Compile standard LangChain tool-calling agent loop
        agent = create_agent(
            model=chat_model,
            tools=tools,
            system_prompt=system_prompt,
        )
        if not additional_tools:
            self._agent_cache[cache_key] = agent
        return agent

    @staticmethod
    def sanitize_history_and_prompt(
        prompt: str,
        history: list[dict[str, Any]] | None = None,
        max_prompt_chars: int = 2000,
        max_history_turns: int = 4,
    ) -> list[BaseMessage]:
        """Sanitize and compact conversation history and prompt to prevent prompt injection and token overflow.

        - Uses compact_history_for_llm to prune bulky prior markdown tables and disclaimers.
        - Guarantees the prompt + history remains well within Groq ITPM (7,000) token ceilings.
        """
        clean_prompt = (prompt or "").strip()[:max_prompt_chars]
        messages: list[BaseMessage] = []

        if history:
            compacted = compact_history_for_llm(
                history,
                max_turns=max_history_turns,
                max_assistant_chars=350,
                max_user_chars=400,
            )
            for item in compacted:
                role = item["role"]
                content = item["content"]
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        if clean_prompt:
            messages.append(HumanMessage(content=clean_prompt))

        return messages
