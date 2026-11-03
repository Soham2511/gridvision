"""Health, readiness, and platform telemetry service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.providers.data_provider import BaseDataProvider
from app.providers.model_provider import BaseModelProvider


class HealthService:
    """Coordinates system health and operational readiness."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        model_provider: BaseModelProvider,
    ) -> None:
        self.data_provider = data_provider
        self.model_provider = model_provider

    def get_liveness(self) -> dict[str, Any]:
        """Report process liveness."""
        return {
            "status": "alive",
            "service": "GridVision REST API",
            "timestamp": datetime.now().isoformat() + "Z",
            "version": "1.0.0",
        }

    def get_readiness(self) -> dict[str, Any]:
        """Report dependency and provider readiness."""
        model_status = self.model_provider.get_model_status()
        is_ready = model_status.get("status") == "ready"

        return {
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now().isoformat() + "Z",
            "providers": {
                "data_provider": type(self.data_provider).__name__,
                "model_provider": model_status.get("provider"),
                "is_demo_mode": model_status.get("is_demo", False),
            },
            "models_ready": model_status.get("models_loaded", []),
        }

    def get_platform_health(self) -> dict[str, Any]:
        """Return platform telemetry and registry health summary."""
        return self.data_provider.get_platform_health_summary()
