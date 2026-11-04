"""Domain-grounded AI assistant service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class AssistantService:
    """Answers telemetry, tariff, peak shaving, and model evaluation inquiries."""

    def __init__(self, data_provider: BaseDataProvider) -> None:
        self.data_provider = data_provider

    def answer_query(
        self,
        prompt: str,
        persona: str = "household",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        # Keep this endpoint deterministic and contract-compatible. Until an
        # approved source is available, it must not assert telemetry, tariffs,
        # anomaly causes, or model behavior that the request did not establish.
        answer = (
            "I can’t provide a telemetry-based answer because no approved data "
            "source is currently available. Historical data, model predictions, "
            "and live meter readings are not interchangeable."
        )
        return {
            "answer": answer,
            "persona": persona,
            "entityId": entity_id,
            "status": "success",
            "availability": "unavailable",
        }
