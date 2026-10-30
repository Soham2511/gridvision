"""Customer segmentation and load profiling routes."""

from __future__ import annotations

from flask import Blueprint, current_app
from app.utils.responses import success_response

bp = Blueprint("customers", __name__)


@bp.route("/customers/segments", methods=["GET"])
def get_segments():
    """Retrieve customer segments breakdown."""
    service = current_app.extensions["customer_service"]
    return success_response(service.get_segments())


@bp.route("/customers/segmentation-matrix", methods=["GET"])
def get_segmentation_matrix():
    """Retrieve multi-dimensional customer segmentation telemetry."""
    service = current_app.extensions["customer_service"]
    return success_response(service.get_segmentation_matrix())


@bp.route("/customers/diurnal-curves", methods=["GET"])
def get_diurnal_curves():
    """Retrieve 24-hour diurnal curves across customer classes."""
    service = current_app.extensions["customer_service"]
    return success_response(service.get_diurnal_curves())
