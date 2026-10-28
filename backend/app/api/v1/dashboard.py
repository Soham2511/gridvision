"""Persona dashboard routes for commercial, household, and government grid."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.utils.responses import success_response

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard/commercial", methods=["GET"])
def commercial_dashboard():
    """Telemetry and actual vs predicted curves for Commercial Facilities."""
    tab = request.args.get("tab", "building")
    time_range = request.args.get("time_range", "1D")
    building_id = request.args.get("building_id", "Panther_office_1")

    service = current_app.extensions["dashboard_service"]
    data = service.get_commercial_dashboard(
        tab=tab,
        time_range=time_range,
        building_id=building_id,
    )
    return success_response(data)


@bp.route("/dashboard/household", methods=["GET"])
def household_dashboard():
    """Consumption overview and daily curve for Household / Residential."""
    household_id = request.args.get("household_id")
    service = current_app.extensions["dashboard_service"]
    data = service.get_household_overview(household_id=household_id)
    return success_response(data)


@bp.route("/dashboard/government/regions", methods=["GET"])
def government_regions():
    """List of 6 regional zones with sparklines and delta stats."""
    service = current_app.extensions["dashboard_service"]
    data = service.get_government_regions()
    return success_response(data)


@bp.route("/dashboard/government", methods=["GET"])
def government_dashboard():
    """Regional and system-wide telemetry for Government & Utilities."""
    view_type = request.args.get("view_type") or request.args.get("view", "overall")
    region_id = request.args.get("region_id") or request.args.get("regionId")
    time_range = request.args.get("time_range") or request.args.get("range", "1D")

    service = current_app.extensions["dashboard_service"]
    data = service.get_government_dashboard(
        view_type=view_type,
        region_id=region_id,
        time_range=time_range,
    )
    return success_response(data)
