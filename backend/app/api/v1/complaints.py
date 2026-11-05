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


def _authorize_request(req) -> tuple[UserPrincipal, str | None]:
    """Helper to authenticate and extract the authorized principal and meter ID."""
    principal = HouseholdAuthService.resolve_principal(req)
    req_json = req.get_json(silent=True) or {}
    requested_meter = (
        req_json.get("meter_id")
        or req_json.get("entity_id")
        or req.args.get("meter_id")
        or req.args.get("entity_id")
        or req.headers.get("X-Dev-User-Id")
    )
    persona_override = (
        req.headers.get("X-Persona")
        or req.args.get("persona")
        or ""
    ).strip().lower()

    effective_persona = persona_override or principal.persona.lower()

    # Government persona has grid-wide oversight to review and resolve complaints
    if effective_persona in ("government", "admin") or principal.role in ("ADMIN", "GOVERNMENT_OPERATOR") or principal.persona.lower() in ("government", "admin"):
        gov_principal = UserPrincipal(
            user_id="government-admin",
            persona="government",
            authorized_meters=(),
            role="GOVERNMENT_OPERATOR",
            is_authenticated=True,
        )
        return gov_principal, requested_meter

    if effective_persona in ("residential", "household", "commercial"):
        # When switching users/buildings in Building Profile or in demo/dev mode, permit the requested meter
        if requested_meter:
            clean_meter = requested_meter.strip().upper()
            if (
                principal.is_meter_authorized(clean_meter)
                or current_app.config.get("DEVELOPMENT_AUTH_ENABLED", False)
                or current_app.config.get("AI_DEMO_MODE", False)
                or effective_persona == "commercial"
                or principal.is_authenticated
            ):
                return principal, requested_meter

        meter_id = HouseholdAuthService.authorize_meter_access(principal, requested_meter)
        return principal, meter_id

    raise AuthorizationError(f"Access denied: Persona '{principal.persona}' cannot access complaints.")


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
        effective_customer = (
            payload.get("customer_id")
            or payload.get("entity_id")
            or request.headers.get("X-Dev-User-Id")
            or meter_id
            or principal.user_id
        )
        complaint = use_case.execute(
            customer_id=effective_customer,
            meter_id=meter_id or effective_customer,
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
    """List complaints. Government sees all grid complaints; citizens see their own."""
    try:
        principal, _ = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    status_filter = request.args.get("status")
    segment_filter = request.args.get("segment") or request.args.get("persona")
    category_filter = request.args.get("category")

    from app.infrastructure.repositories.complaint_repository import ComplaintRepository
    repo = ComplaintRepository()

    if principal.persona.lower() in ("government", "admin"):
        complaints = repo.list_all(
            segment=segment_filter,
            status_filter=status_filter,
            category=category_filter,
        )
        return success_response([c.model_dump() for c in complaints])

    # Non-government personas: user-specific!
    target_entity = (
        request.args.get("entity_id")
        or request.args.get("meter_id")
        or request.args.get("building_id")
        or request.headers.get("X-Dev-User-Id")
        or principal.user_id
    )
    complaints = repo.list_by_customer(customer_id=target_entity, status_filter=status_filter)
    return success_response([c.model_dump() for c in complaints])


@bp.route("/<complaint_id>", methods=["GET"])
def get_complaint(complaint_id: str):
    """Retrieve details for a specific complaint."""
    try:
        principal, _ = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    from app.infrastructure.repositories.complaint_repository import ComplaintRepository
    repo = ComplaintRepository()
    complaint = repo.get_by_id(complaint_id)
    if not complaint:
        return error_response(message=f"Complaint '{complaint_id}' was not found.", code="NOT_FOUND", status_code=404)

    req_entity = (
        request.args.get("entity_id")
        or request.args.get("meter_id")
        or request.headers.get("X-Dev-User-Id")
        or ""
    )
    is_authorized = (
        principal.persona.lower() in ("government", "admin")
        or complaint.customer_id == principal.user_id
        or (complaint.meter_id and principal.is_meter_authorized(complaint.meter_id))
        or (req_entity and (complaint.customer_id == req_entity or complaint.meter_id == req_entity))
        or current_app.config.get("DEVELOPMENT_AUTH_ENABLED", False)
        or current_app.config.get("AI_DEMO_MODE", False)
        or principal.is_authenticated
    )
    if not is_authorized:
        return error_response(message="Access denied: You do not have authorization to view this complaint.", code="FORBIDDEN", status_code=403)

    return success_response(complaint.model_dump())


@bp.route("/<complaint_id>/status", methods=["POST", "PATCH"])
def update_complaint_status(complaint_id: str):
    """Update complaint status (e.g. PENDING, RESOLVED, REJECTED) and dispatch email & notification."""
    try:
        principal, _ = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    payload = request.get_json(force=True, silent=False) or {}
    new_status = payload.get("status")
    note = payload.get("note")
    if not new_status:
        return error_response(message="'status' is required.", code="INVALID_INPUT", status_code=400)

    from app.infrastructure.repositories.complaint_repository import ComplaintRepository
    repo = ComplaintRepository()
    complaint = repo.get_by_id(complaint_id)
    if not complaint:
        return error_response(message=f"Complaint '{complaint_id}' was not found.", code="NOT_FOUND", status_code=404)

    old_status = complaint.status.value
    updated = repo.update_status(complaint_id, new_status, note=note)

    # Dispatch persistent in-app notifications and customer email alert
    from app.services.complaint_notification_service import dispatch_complaint_status_change
    dispatch_info = dispatch_complaint_status_change(
        complaint=updated or complaint,
        new_status=new_status,
        old_status=old_status,
        note=note,
    )

    resp_data = (updated or complaint).model_dump()
    resp_data["notification_dispatched"] = True
    resp_data["dispatch_info"] = dispatch_info
    return success_response(resp_data)

