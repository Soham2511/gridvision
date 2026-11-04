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
        """Report process readiness separately from optional source availability."""
        model_status = self.model_provider.get_model_status()
        data_status = (
            self.data_provider.availability()
            if hasattr(self.data_provider, "availability")
            else {"status": "configured"}
        )
        model_ready = model_status.get("status") == "ready"
        data_ready = data_status.get("status") in {"ready", "configured"}

        return {
            # The Flask process can serve health and structured unavailable
            # responses even when optional data/model sources are absent.
            "status": "ready",
            "optional_dependencies_ready": data_ready and model_ready,
            "data_availability": (
                "ready" if data_ready and model_ready else "degraded"
            ),
            "timestamp": datetime.now().isoformat() + "Z",
            "providers": {
                "data_provider": type(self.data_provider).__name__,
                "data_status": data_status,
                "model_provider": model_status.get("provider"),
                "model_status": model_status.get("status", "unknown"),
                "is_demo_mode": model_status.get("is_demo", False),
            },
            "models_ready": model_status.get("models_loaded", []),
        }

    def get_platform_health(self) -> dict[str, Any]:
        """Return platform telemetry and registry health summary."""
        if hasattr(self.data_provider, "availability"):
            return {
                "availability": self.data_provider.availability(),
                "models": self.model_provider.get_model_status(),
                "status": "degraded",
            }
        return self.data_provider.get_platform_health_summary()
