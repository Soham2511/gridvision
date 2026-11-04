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

    # 2. Execute assistant query scoped strictly to authorized meter and authenticated user
    service = current_app.extensions["assistant_service"]
    result = service.answer_query(
        prompt=validated.prompt,
        persona=validated.persona,
        entity_id=authorized_meter_id,
        history=[m.model_dump() for m in validated.history],
        user_id=principal.user_id,
        conversation_id=validated.conversation_id or validated.session_id,
    )
    if result.get("status") == "unauthorized":
        return error_response(
            message=result.get("answer", "Access denied to the requested meter."),
            code="UNAUTHORIZED_ENTITY",
            status_code=403,
        )
    return success_response(result)


# -------------------------------------------------------------------------
# Conversation Management & Session Endpoints (ChatGPT-Style Lifecycle)
# -------------------------------------------------------------------------

@bp.route("/assistant/conversations", methods=["GET"])
def list_conversations():
    """List conversations for the authenticated customer ordered by most recently active first."""
    try:
        principal = HouseholdAuthService.resolve_principal(request)
    except AuthenticationError as exc:
        return error_response(message=str(exc), code="AUTHENTICATION_REQUIRED", status_code=401)
    except AuthorizationError as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    include_archived = request.args.get("include_archived", "false").lower() == "true"
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit, offset = 50, 0

    from app.infrastructure.repositories.conversation_memory_repository import ConversationMemoryRepository
    repo = ConversationMemoryRepository()
    sessions = repo.list_sessions(
        user_id=principal.user_id,
        persona="residential",
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return success_response([s.to_dict() for s in sessions])


@bp.route("/assistant/conversations", methods=["POST"])
def create_conversation():
    """Create a new independent conversation session with clean pending state."""
    try:
        principal = HouseholdAuthService.resolve_principal(request)
    except AuthenticationError as exc:
        return error_response(message=str(exc), code="AUTHENTICATION_REQUIRED", status_code=401)
    except AuthorizationError as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "New Chat").strip()
    meter_id = data.get("meter_id") or (principal.authorized_meters[0] if principal.authorized_meters else "2254213")

    from app.infrastructure.repositories.conversation_memory_repository import ConversationMemoryRepository
    repo = ConversationMemoryRepository()
    session = repo.create_session(
        user_id=principal.user_id,
        meter_id=meter_id,
        title=title,
        persona="residential",
    )
    return success_response(session.to_dict(), status_code=201)


@bp.route("/assistant/conversations/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id: str):
    """Retrieve full conversation details, active state, and message history validating customer ownership."""
    try:
        principal = HouseholdAuthService.resolve_principal(request)
    except AuthenticationError as exc:
        return error_response(message=str(exc), code="AUTHENTICATION_REQUIRED", status_code=401)
    except AuthorizationError as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    from app.infrastructure.repositories.conversation_memory_repository import ConversationMemoryRepository
    repo = ConversationMemoryRepository()
    session = repo.get_session(conversation_id=conversation_id, user_id=principal.user_id)
    if not session or not session.is_active:
        return error_response(
            message=f"Conversation '{conversation_id}' not found or access denied.",
            code="CONVERSATION_NOT_FOUND",
            status_code=404,
        )

    messages = repo.get_session_messages(conversation_id=conversation_id, user_id=principal.user_id, limit=200)
    return success_response({
        "session": session.to_dict(),
        "messages": messages,
    })


@bp.route("/assistant/conversations/<conversation_id>", methods=["PATCH"])
def update_conversation(conversation_id: str):
    """Rename or archive a conversation ensuring customer ownership."""
    try:
        principal = HouseholdAuthService.resolve_principal(request)
    except AuthenticationError as exc:
        return error_response(message=str(exc), code="AUTHENTICATION_REQUIRED", status_code=401)
    except AuthorizationError as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    data = request.get_json(silent=True) or {}
    from app.infrastructure.repositories.conversation_memory_repository import ConversationMemoryRepository
    repo = ConversationMemoryRepository()

    # 1. Update Title if provided
    if "title" in data:
        new_title = str(data["title"]).strip()
        if not new_title or len(new_title) > 100:
            return error_response(
                message="Conversation title must be between 1 and 100 characters.",
                code="INVALID_TITLE",
                status_code=400,
            )
        try:
            success = repo.update_session_title(
                conversation_id=conversation_id,
                user_id=principal.user_id,
                title=new_title,
                is_custom=True,
            )
            if not success:
                return error_response(
                    message=f"Conversation '{conversation_id}' not found or access denied.",
                    code="CONVERSATION_NOT_FOUND",
                    status_code=404,
                )
        except PermissionError as exc:
            return error_response(message=str(exc), code="FORBIDDEN", status_code=403)

    # 2. Archive / Unarchive if provided
    if "is_archived" in data:
        is_archived = bool(data["is_archived"])
        success = repo.archive_session(
            conversation_id=conversation_id,
            user_id=principal.user_id,
            is_archived=is_archived,
        )
        if not success:
            return error_response(
                message=f"Conversation '{conversation_id}' not found or access denied.",
                code="CONVERSATION_NOT_FOUND",
                status_code=404,
            )

    updated = repo.get_session(conversation_id=conversation_id, user_id=principal.user_id)
    if not updated:
        return error_response(
            message=f"Conversation '{conversation_id}' not found.",
            code="CONVERSATION_NOT_FOUND",
            status_code=404,
        )
    return success_response(updated.to_dict())


@bp.route("/assistant/conversations/<conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id: str):
    """Soft-delete a conversation verifying ownership. Does not delete persistent customer memory."""
    try:
        principal = HouseholdAuthService.resolve_principal(request)
    except AuthenticationError as exc:
        return error_response(message=str(exc), code="AUTHENTICATION_REQUIRED", status_code=401)
    except AuthorizationError as exc:
        return error_response(message=str(exc), code="UNAUTHORIZED", status_code=403)

    from app.infrastructure.repositories.conversation_memory_repository import ConversationMemoryRepository
    repo = ConversationMemoryRepository()
    success = repo.delete_session(conversation_id=conversation_id, user_id=principal.user_id)
    if not success:
        return error_response(
            message=f"Conversation '{conversation_id}' not found or access denied.",
            code="CONVERSATION_NOT_FOUND",
            status_code=404,
        )
    return success_response({"deleted": True, "conversation_id": conversation_id})
