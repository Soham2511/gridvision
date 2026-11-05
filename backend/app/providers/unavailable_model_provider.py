"""Model provider used when a model source is not explicitly enabled."""

from __future__ import annotations

from typing import Any

from app.api.error_handlers import ModelUnavailableError
from app.providers.model_provider import BaseModelProvider, PredictionOutput


class UnavailableModelProvider(BaseModelProvider):
    """Fail-closed model provider; never returns mock predictions."""

    def __init__(self, reason: str = "No approved forecast model provider is configured.") -> None:
        self.reason = reason

    def predict(
        self,
        model_name: str,
        entity_id: str,
        features: dict[str, Any],
        actual_kwh_so_far: float | None = None,
        context: str = "future_forecast",
    ) -> PredictionOutput:
        raise ModelUnavailableError(self.reason)

    def predict_horizon(
        self, sector: str, entity_id: str, horizon_count: int = 24
    ) -> list[dict[str, Any]]:
        raise ModelUnavailableError(self.reason)

    def get_model_status(self) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "provider": "unavailable",
            "is_demo": False,
            "models_loaded": [],
            "reason": self.reason,
        }

    def get_forecast_model_info(self, sector: str) -> dict[str, Any]:
        return {
            "model_name": sector,
            "model_version": "unavailable",
            "provider": "unavailable",
            "is_demo": False,
            "status": "unavailable",
            "reason": self.reason,
        }
