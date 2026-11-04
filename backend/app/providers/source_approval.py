"""Runtime source approval gates for data not authenticated by the repository."""

from __future__ import annotations

from flask import current_app

from app.api.error_handlers import AppError


def source_is_approved(source_id: str) -> bool:
    """Tests may use isolated fixtures; runtime requires explicit source approval."""
    if current_app.testing:
        return True
    configured = current_app.config.get("APPROVED_DATA_SOURCES", ())
    return source_id in configured


def require_approved_source(source_id: str, label: str | None = None) -> None:
    if source_is_approved(source_id):
        return
    raise AppError(
        f"{label or source_id} is unavailable because its data provenance has not been approved.",
        code="DATA_SOURCE_UNAVAILABLE",
        status_code=503,
        details={
            "availability": "provenance_unverified",
            "source": source_id,
            "live_telemetry": "not_configured",
        },
    )
