"""Historical demand analysis route."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.utils.responses import success_response

bp = Blueprint("historical", __name__)


@bp.route("/historical", methods=["GET"])
def get_historical_analysis():
    """Historical telemetry curves and dynamic KPI rollups."""
    persona = request.args.get("persona", "household")
    time_range = request.args.get("time_range", "30D")
    entity_id = request.args.get("entity_id")

    service = current_app.extensions["dashboard_service"]
    data = service.get_historical_insights(
        persona=persona,
        time_range=time_range,
        entity_id=entity_id,
    )
    return success_response(data)
