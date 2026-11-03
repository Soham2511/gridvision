"""Peak demand prediction and automated curtailment routes."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.utils.responses import success_response
from app.utils.validation import CurtailmentRequestModel

bp = Blueprint("peak", __name__)


@bp.route("/peak-demand", methods=["GET"])
def get_peak_demand():
    """System peak capacity analysis, reserve margins, and hourly timeline."""
    service = current_app.extensions["peak_service"]
    return success_response(service.get_peak_analysis())


@bp.route("/peak-demand/curtail", methods=["POST"])
def dispatch_curtailment():
    """Simulate automated demand response (ADR) curtailment dispatch."""
    data = request.get_json(force=True, silent=False) or {}
    validated = CurtailmentRequestModel.model_validate(data)

    service = current_app.extensions["peak_service"]
    result = service.simulate_curtailment(
        curtailment_mw=validated.curtailment_mw,
        duration_hours=validated.duration_hours,
    )
    return success_response(result)
