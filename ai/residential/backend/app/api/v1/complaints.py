"""REST API endpoints for the GridVision Complaint Management system."""

from __future__ import annotations

import logging
from flask import Blueprint, current_app, jsonify, request

from app.application.complaints.get_complaints import (
    GetComplaintDetailUseCase,
    GetCustomerComplaintsUseCase,
)
from app.application.complaints.submit_complaint import (
    SubmitComplaintRequest,
    SubmitComplaintUseCase,
)
from app.domain.complaints.categories import get_categories_for_segment
from app.services.assistant.auth import (
    AuthenticationError,
    AuthorizationError,
    HouseholdAuthService,
    UserPrincipal,
)
from app.utils.responses import error_response, success_response

logger = logging.getLogger("gridvision.api.v1.complaints")

bp = Blueprint("complaints", __name__, url_prefix="/complaints")


def _authorize_request(req) -> tuple[UserPrincipal, str]:
    """Helper to authenticate and extract the authorized principal and meter ID."""
    principal = HouseholdAuthService.resolve_principal(req)
    if principal.persona.lower() != "residential":
        raise AuthorizationError(f"Access denied: Persona '{principal.persona}' cannot access residential complaints.")
    req_json = req.get_json(silent=True) or {}
    requested_meter = (
        req_json.get("meter_id")
        or req_json.get("entity_id")
        or req.args.get("meter_id")
        or req.args.get("entity_id")
    )
    meter_id = HouseholdAuthService.authorize_meter_access(principal, requested_meter)
    return principal, meter_id


@bp.route("/categories", methods=["GET"])
def get_categories():
    """Retrieve available complaint categories for the customer segment."""
    segment = request.args.get("segment", "RESIDENTIAL")
    categories = get_categories_for_segment(segment)
    return success_response([c.model_dump() for c in categories])


@bp.route("", methods=["POST"])
def submit_complaint():
    """Submit a complaint for validation and severity scoring."""
    try:
        principal, meter_id = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    payload = request.get_json(force=True, silent=False) or {}
    try:
        req_obj = SubmitComplaintRequest.model_validate(payload)
    except Exception as exc:
        return error_response(message=f"Invalid complaint payload: {exc}", code="INVALID_INPUT", status_code=400)

    customer_care_phone = current_app.config.get("CUSTOMER_CARE_PHONE")
    use_case = SubmitComplaintUseCase(customer_care_contact=customer_care_phone)

    try:
        complaint = use_case.execute(
            customer_id=principal.user_id,
            meter_id=meter_id,
            request=req_obj,
        )
        return success_response(complaint.model_dump(), status_code=201)
    except ValueError as exc:
        return error_response(message=str(exc), code="VALIDATION_ERROR", status_code=400)
    except Exception as exc:
        logger.error("Failed to process complaint: %s", exc, exc_info=True)
        return error_response(message="Failed to process complaint submission.", code="INTERNAL_ERROR", status_code=500)


@bp.route("", methods=["GET"])
def list_complaints():
    """List all complaints belonging to the authenticated customer."""
    try:
        principal, _ = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    status_filter = request.args.get("status")
    use_case = GetCustomerComplaintsUseCase()
    complaints = use_case.execute(customer_id=principal.user_id, status_filter=status_filter)

    return success_response([c.model_dump() for c in complaints])


@bp.route("/<complaint_id>", methods=["GET"])
def get_complaint(complaint_id: str):
    """Retrieve details for a specific complaint with ownership check."""
    try:
        principal, _ = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    use_case = GetComplaintDetailUseCase()
    try:
        complaint = use_case.execute(complaint_id=complaint_id, customer_id=principal.user_id)
        return success_response(complaint.model_dump())
    except KeyError as exc:
        return error_response(message=str(exc), code="NOT_FOUND", status_code=404)
    except PermissionError as exc:
        return error_response(message=str(exc), code="FORBIDDEN", status_code=403)

