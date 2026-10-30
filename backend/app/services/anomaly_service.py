"""Anomaly detection and event state management service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class AnomalyService:
    """Manages telemetry anomalies, diagnostics, and triage workflows."""

    def __init__(self, data_provider: BaseDataProvider) -> None:
        self.data_provider = data_provider

    def get_anomalies(
        self,
        severity: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.data_provider.get_anomaly_events(
            severity=severity,
            status=status,
            search=search,
        )

    def update_status(self, event_id: str, status: str) -> dict[str, Any] | None:
        return self.data_provider.update_anomaly_status(
            event_id=event_id,
            status=status,
        )
