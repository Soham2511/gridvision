"""Energy insights and recommendations route."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.utils.responses import success_response

bp = Blueprint("insights", __name__)


@bp.route("/energy-insights", methods=["GET"])
def get_energy_insights():
    """Retrieve algorithmic business recommendations for grid optimization."""
    category = request.args.get("category")
    sector = request.args.get("sector")

    service = current_app.extensions["insight_service"]
    insights = service.get_insights(category=category, sector=sector)
    return success_response(insights)
