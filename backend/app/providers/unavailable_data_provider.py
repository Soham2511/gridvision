"""Fail-closed provider used when no approved domain data source is configured."""

from __future__ import annotations

from typing import Any, Callable

from app.api.error_handlers import AppError


class UnavailableDataProvider:
    """Duck-typed BaseDataProvider replacement that never fabricates data."""

    def __init__(self, reason: str = "No approved data provider is configured.") -> None:
        self.reason = reason

    def availability(self) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "provider": "unavailable",
            "reason": self.reason,
            "live_telemetry": "not_configured",
        }

    def __getattr__(self, method_name: str) -> Callable[..., Any]:
        if method_name.startswith("_"):
            raise AttributeError(method_name)

        def unavailable(*args: Any, **kwargs: Any) -> Any:
            raise AppError(
                self.reason,
                code="DATA_SOURCE_UNAVAILABLE",
                status_code=503,
                details={
                    "availability": "unavailable",
                    "source": "domain_data",
                    "live_telemetry": "not_configured",
                    "operation": method_name,
                },
            )

        return unavailable
