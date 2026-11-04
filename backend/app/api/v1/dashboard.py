"""Persona dashboard routes for commercial, household, and government grid."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.services.assistant.auth import (
    AuthenticationError,
    AuthorizationError,
    HouseholdAuthService,
)
from app.utils.responses import error_response, success_response

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
    try:
        principal = HouseholdAuthService.resolve_principal(request)
        if principal.persona.lower() != "residential":
            return error_response(
                f"Access denied: Persona '{principal.persona}' cannot access residential dashboard.",
                code="FORBIDDEN_PERSONA",
                status_code=403,
            )
        # If a specific household_id was requested, strictly authorize it
        if household_id:
            meter_id = HouseholdAuthService.authorize_meter_access(principal, household_id)
        elif not principal.authorized_meters:
            # Clean isolated state for users with no assigned meter yet
            return success_response({
                "householdId": None,
                "customerName": principal.username or "Residential Customer",
                "status": "NO_METER_LINKED",
                "message": "No smart meter is currently provisioned for this account.",
                "currentCycleKwh": 0.0,
                "projectedCycleKwh": 0.0,
                "projectedBillInr": 0.0,
                "activeAppliances": 0,
                "consumptionCurve": [],
                "recentAnomalies": [],
            })
        else:
            meter_id = HouseholdAuthService.authorize_meter_access(principal, None)
    except AuthenticationError as exc:
        return error_response(str(exc), code="UNAUTHENTICATED", status_code=401)
    except AuthorizationError as exc:
        return error_response(str(exc), code="UNAUTHORIZED", status_code=403)

    service = current_app.extensions["dashboard_service"]
    data = service.get_household_overview(household_id=meter_id)
    return success_response(data)


@bp.route("/dashboard/government/regions", methods=["GET"])
def government_regions():
    """List historical grid regions with recent demand and forecast metrics."""
    time_range = request.args.get("time_range", "1D")
    service = current_app.extensions["dashboard_service"]
    data = service.get_government_regions(time_range=time_range)
    return success_response(data)


@bp.route("/dashboard/government", methods=["GET"])
def government_dashboard():
    """Regional and system-wide telemetry for Government & Utilities."""
    view_type = request.args.get("view_type", "overall")
    region_id = request.args.get("region_id")
    time_range = request.args.get("time_range", "1D")

    service = current_app.extensions["dashboard_service"]
    data = service.get_government_dashboard(
        view_type=view_type,
        region_id=region_id,
        time_range=time_range,
    )
    return success_response(data)
