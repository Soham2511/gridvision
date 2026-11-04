"""REST API endpoints for Residential Energy Intelligence Platform features."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict
from flask import Blueprint, current_app, jsonify, request

from app.application.residential.analyze_appliance import AnalyzeApplianceScenarioUseCase
from app.application.residential.manage_cost import ManageEnergyCostUseCase
from app.application.residential.plan_house_energy import PlanHouseEnergyUseCase
from app.domain.residential.questionnaires import QUESTIONNAIRE_REGISTRY
from app.domain.residential.schemas import (
    ApplianceScenarioRequest,
    CostManagementRequest,
    HouseEnergyPlanningRequest,
)
from app.services.assistant.auth import (
    AuthenticationError,
    AuthorizationError,
    HouseholdAuthService,
)
from app.utils.responses import error_response, success_response

logger = logging.getLogger("gridvision.api.v1.residential_features")

bp = Blueprint("residential_features", __name__)

# In-memory store for active feature sessions (scoped by session_id and meter_id)
_FEATURE_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _authorize_request(req) -> tuple[UserPrincipal, str]:
    """Helper to authenticate and extract the authorized principal and meter ID."""
    principal = HouseholdAuthService.resolve_principal(req)
    if principal.persona.lower() != "residential":
        raise AuthorizationError(f"Access denied: Persona '{principal.persona}' cannot access residential features.")
    req_json = req.get_json(silent=True) or {}
    requested_meter = (
        req_json.get("meter_id")
        or req_json.get("entity_id")
        or req.args.get("meter_id")
        or req.args.get("entity_id")
    )
    meter_id = HouseholdAuthService.authorize_meter_access(principal, requested_meter)
    return principal, meter_id


@bp.route("/residential/questionnaires/<feature_id>", methods=["GET"])
def get_questionnaire(feature_id: str):
    """Retrieve the authoritative questionnaire definition for a specific residential feature."""
    clean_id = (feature_id or "").strip().lower()
    if clean_id not in QUESTIONNAIRE_REGISTRY:
        return error_response(
            message=f"Feature questionnaire '{clean_id}' not found. Available features: {list(QUESTIONNAIRE_REGISTRY.keys())}",
            code="QUESTIONNAIRE_NOT_FOUND",
            status_code=404,
        )

    questionnaire = QUESTIONNAIRE_REGISTRY[clean_id]
    return success_response(questionnaire.model_dump())


@bp.route("/residential/plan-house-energy", methods=["POST"])
def plan_house_energy():
    """Execute New House Energy Planning use case for authorized customer."""
    try:
        _, meter_id = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    payload = request.get_json(force=True, silent=False) or {}
    try:
        plan_req = HouseEnergyPlanningRequest.model_validate(payload)
    except Exception as exc:
        return error_response(message=f"Invalid planning request: {exc}", code="INVALID_INPUT", status_code=400)

    tariff = current_app.config.get("CUSTOMER_TARIFF_INR_PER_KWH", 10.0)
    use_case = PlanHouseEnergyUseCase(tariff_rate=tariff)
    response = use_case.execute(meter_id=meter_id, request=plan_req)

    return success_response(response.model_dump())


@bp.route("/residential/analyze-appliance", methods=["POST"])
def analyze_appliance():
    """Execute Appliance Scenario Analysis use case for authorized customer."""
    try:
        _, meter_id = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    payload = request.get_json(force=True, silent=False) or {}
    try:
        app_req = ApplianceScenarioRequest.model_validate(payload)
    except Exception as exc:
        return error_response(message=f"Invalid appliance scenario request: {exc}", code="INVALID_INPUT", status_code=400)

    tariff = current_app.config.get("CUSTOMER_TARIFF_INR_PER_KWH", 10.0)
    use_case = AnalyzeApplianceScenarioUseCase(tariff_rate=tariff)
    response = use_case.execute(meter_id=meter_id, request=app_req)

    return success_response(response.model_dump())


@bp.route("/residential/manage-cost", methods=["POST"])
def manage_cost():
    """Execute Personalized Energy Cost Management use case for authorized customer."""
    try:
        _, meter_id = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    payload = request.get_json(force=True, silent=False) or {}
    try:
        cost_req = CostManagementRequest.model_validate(payload)
    except Exception as exc:
        return error_response(message=f"Invalid cost management request: {exc}", code="INVALID_INPUT", status_code=400)

    tariff = current_app.config.get("CUSTOMER_TARIFF_INR_PER_KWH", 10.0)
    use_case = ManageEnergyCostUseCase(tariff_rate=tariff)
    response = use_case.execute(meter_id=meter_id, request=cost_req)

    return success_response(response.model_dump())


@bp.route("/residential/sessions", methods=["POST"])
def create_session():
    """Initialize a dedicated feature conversation session."""
    try:
        _, meter_id = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    payload = request.get_json(force=True, silent=False) or {}
    feature_id = payload.get("feature_id", "general_chat")

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session_data = {
        "sessionId": session_id,
        "meterId": meter_id,
        "featureId": feature_id,
        "status": "questionnaire_active" if feature_id != "general_chat" else "chat_active",
        "inputs": {},
        "results": None,
        "messages": [],
    }
    _FEATURE_SESSIONS[session_id] = session_data

    return success_response(session_data)


@bp.route("/residential/sessions/<session_id>", methods=["GET", "PUT"])
def manage_session(session_id: str):
    """Retrieve or update state of a feature session."""
    try:
        principal, meter_id = _authorize_request(request)
    except (AuthenticationError, AuthorizationError) as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    if session_id not in _FEATURE_SESSIONS:
        return error_response(message=f"Session '{session_id}' not found", code="NOT_FOUND", status_code=404)

    session_data = _FEATURE_SESSIONS[session_id]
    if not principal.is_meter_authorized(session_data["meterId"]):
        return error_response(message="Access denied to session", code="FORBIDDEN", status_code=403)

    if request.method == "PUT":
        payload = request.get_json(force=True, silent=False) or {}
        if "inputs" in payload:
            session_data["inputs"].update(payload["inputs"])
        if "status" in payload:
            session_data["status"] = payload["status"]
        if "results" in payload:
            session_data["results"] = payload["results"]
        if "messages" in payload:
            session_data["messages"] = payload["messages"]

    return success_response(session_data)

