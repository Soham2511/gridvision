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
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Process conversational query scoped to authorized household entity and user identity."""
        if persona in ("government", "commercial"):
            p = prompt.lower()
            if any(w in p for w in ["peak", "reserve", "stress", "curtail"]):
                peak_data = self.data_provider.get_peak_demand_analysis()
                answer = (
                    f"**System Peak Demand & Reserve Status:**\n\n"
                    f"- **Expected Peak**: **{peak_data.get('expectedPeakMw', 3400)} MW** at `{peak_data.get('expectedPeakTime', '19:00')}`\n"
                    f"- **Current Active Load**: **{peak_data.get('currentLoadMw', 3120)} MW**\n"
                    f"- **Grid Capacity Ceiling**: **{peak_data.get('peakCapacityLimitMw', 3800)} MW**\n"
                    f"- **Reserve Margin**: **{peak_data.get('reserveMarginPct', 18.0)}%** ({peak_data.get('riskLevel', 'low').upper()} risk)\n\n"
                    "**Recommended Action**: " + peak_data.get("mitigationStrategy", "Maintain reserve threshold.")
                )
                return {
                    "answer": answer,
                    "persona": persona,
                    "entityId": entity_id or "North Region",
                    "status": "success",
                }

        return self.residential_orchestrator.answer_query(
            prompt=prompt,
            entity_id=entity_id,
            history=history,
            user_id=user_id,
            conversation_id=conversation_id,
        )
