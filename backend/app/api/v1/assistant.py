"""AI domain assistant route."""

from __future__ import annotations

import logging
from flask import Blueprint, current_app, request
from app.services.assistant.auth import (
    AuthenticationError,
    AuthorizationError,
    HouseholdAuthService,
)
from app.utils.responses import error_response, success_response
from app.utils.validation import AssistantChatRequestModel

logger = logging.getLogger("gridvision.assistant")
bp = Blueprint("assistant", __name__)


@bp.route("/assistant/chat", methods=["POST"])
def assistant_chat():
    """Contextual domain query handler for AiAssistantPage."""
    data = request.get_json(force=True, silent=False) or {}
    validated = AssistantChatRequestModel.model_validate(data)

    # 1. Resolve trusted identity and authorize household meter
    try:
        principal = HouseholdAuthService.resolve_principal(request)
        if not principal.authorized_meters:
            # User account has no smart meter linked: return conversational guidance instead of crashing with 403
            return success_response({
                "answer": (
                    "Hello! Your user account currently has no smart meter provisioned. "
                    "To view live telemetry, consumption patterns, and bill forecasts, please link an authorized smart meter "
                    "or sign in with a verified account (such as `resident`). "
                    "In the meantime, I can assist you with general energy conservation tips and standard tariff explanations."
                ),
                "persona": validated.persona,
                "entityId": None,
                "customerName": principal.username or "Residential Customer",
                "status": "success",
                "isLlmGenerated": False,
            })

        try:
            authorized_meter_id = HouseholdAuthService.authorize_meter_access(
                principal, validated.entity_id
            )
        except AuthorizationError:
            # Fall back to principal's primary authorized meter instead of a hard chat interruption
            authorized_meter_id = principal.authorized_meters[0]
            logger.info(
                "Scoped assistant query for user '%s' to primary authorized meter '%s' (requested: '%s')",
                principal.user_id,
                authorized_meter_id,
                validated.entity_id,
            )
    except AuthenticationError as exc:
        return error_response(
            message=str(exc),
            code="AUTHENTICATION_REQUIRED",
            status_code=401,
        )
    except AuthorizationError as exc:
        return error_response(
            message=str(exc),
            code="UNAUTHORIZED_ENTITY",
            status_code=403,
        )

    # 2. Execute assistant query scoped strictly to authorized meter
    service = current_app.extensions["assistant_service"]
    result = service.answer_query(
        prompt=validated.prompt,
        persona=validated.persona,
        entity_id=authorized_meter_id,
        history=[m.model_dump() for m in validated.history],
    )
    if result.get("status") == "unauthorized":
        return error_response(
            message=result.get("answer", "Access denied to the requested meter."),
            code="UNAUTHORIZED_ENTITY",
            status_code=403,
        )
    return success_response(result)
