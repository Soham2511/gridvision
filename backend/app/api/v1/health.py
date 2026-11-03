"""Health and readiness routes."""

from __future__ import annotations

from flask import Blueprint, current_app
from app.utils.responses import success_response, error_response

bp = Blueprint("health", __name__)


@bp.route("/health", methods=["GET"])
@bp.route("/health/live", methods=["GET"])
def health_live():
    """Liveness probe reporting process status."""
    service = current_app.extensions["health_service"]
    return success_response(service.get_liveness())


@bp.route("/ready", methods=["GET"])
@bp.route("/health/ready", methods=["GET"])
def health_ready():
    """Readiness probe reporting model and data provider status."""
    service = current_app.extensions["health_service"]
    readiness = service.get_readiness()
    status_code = 200 if readiness["status"] == "ready" else 503
    return success_response(readiness, status_code=status_code)


@bp.route("/platform/health", methods=["GET"])
def platform_health():
    """Platform data and model telemetry summary."""
    service = current_app.extensions["health_service"]
    return success_response(service.get_platform_health())
