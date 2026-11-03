"""Domain-grounded AI assistant service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.mock_adapter import MockLLMAdapter
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator


class AssistantService:
    """Answers telemetry, tariff, peak shaving, and model evaluation inquiries."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        llm_provider: BaseLLMProvider | None = None,
        tariff_rate: float = 10.0,
        authorized_meters: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
        agent_factory: Any = None,
        prediction_service: Any = None,
    ) -> None:
        self.data_provider = data_provider
        self.llm_provider = llm_provider or MockLLMAdapter()
        self.prediction_service = prediction_service
        self.residential_orchestrator = ResidentialAssistantOrchestrator(
            data_provider=data_provider,
            llm_provider=self.llm_provider,
            tariff_rate=tariff_rate,
            authorized_meters=authorized_meters,
            temperature=temperature,
            max_tokens=max_tokens,
            agent_factory=agent_factory,
            prediction_service=prediction_service,
        )

    def answer_query(
        self,
        prompt: str,
        persona: str = "household",
        entity_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Process conversational query scoped to authorized household entity."""
        return self.residential_orchestrator.answer_query(
            prompt=prompt,
            entity_id=entity_id,
            history=history,
        )
