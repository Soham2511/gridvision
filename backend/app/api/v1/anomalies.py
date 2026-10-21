"""Anomaly detection and incident management routes."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.api.error_handlers import ResourceNotFoundError
from app.utils.responses import success_response
from app.utils.validation import AnomalyStatusUpdateModel

bp = Blueprint("anomalies", __name__)


@bp.route("/anomalies", methods=["GET"])
def get_anomalies():
    """Retrieve filtered anomaly detection events."""
    severity = request.args.get("severity")
    status = request.args.get("status")
    search = request.args.get("search")

    service = current_app.extensions["anomaly_service"]
    events = service.get_anomalies(
        severity=severity,
        status=status,
        search=search,
    )
    return success_response(events)


@bp.route("/anomalies/<event_id>", methods=["PATCH"])
def update_anomaly(event_id: str):
    """Update status of a specific anomaly incident."""
    data = request.get_json(force=True, silent=False) or {}
    validated = AnomalyStatusUpdateModel.model_validate(data)

    service = current_app.extensions["anomaly_service"]
    updated = service.update_status(event_id=event_id, status=validated.status)
    if not updated:
        raise ResourceNotFoundError(f"Anomaly event '{event_id}' not found.")
    return success_response(updated)
