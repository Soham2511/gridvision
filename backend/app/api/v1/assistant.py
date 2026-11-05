"""AI domain assistant route."""

from __future__ import annotations

import importlib
import ipaddress
import json
import logging
import queue
import threading
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    request,
    send_from_directory,
    stream_with_context,
)

from app.api.error_handlers import AppError
from app.services.assistant.auth import (
    AuthenticationError,
    AuthorizationError,
    HouseholdAuthService,
)
from app.utils.responses import error_response, success_response
from app.utils.validation import AssistantChatRequestModel

bp = Blueprint("assistant", __name__)
logger = logging.getLogger("gridvision.assistant")


@bp.route("/assistant/government-artifacts/<path:filename>", methods=["GET"])
def government_assistant_artifact(filename: str):
    """Serve generated government PNG/CSV artifacts from the assistant output dir."""
    module = importlib.import_module(
        "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
    )
    root = Path(module.DEFAULT_ARTIFACTS_DIR).expanduser().resolve()
    artifact = (root / filename).resolve()
    if (
        Path(filename).name != filename
        or artifact.parent != root
        or artifact.suffix.lower() not in {".png", ".csv"}
        or not artifact.is_file()
    ):
        raise AppError("Government assistant artifact was not found.", status_code=404)
    return send_from_directory(root, filename, as_attachment=False)


def _assistant_identity(persona: str) -> tuple[str | None, str | None, list[int]]:
    principal = getattr(g, "authenticated_user_id", None)
    if principal is None:
        principal = getattr(g, "user_id", None)
    user = getattr(g, "user", None)
    if principal is None:
        principal = (
            user.get("id")
            if isinstance(user, dict)
            else getattr(user, "id", None)
        )

    authenticated_persona = getattr(g, "authenticated_persona", None)
    if authenticated_persona is None:
        authenticated_persona = (
            user.get("persona")
            if isinstance(user, dict)
            else getattr(user, "persona", None)
        )

    remote_addr = request.remote_addr
    try:
        is_loopback = bool(
            remote_addr and ipaddress.ip_address(remote_addr).is_loopback
        )
    except ValueError:
        is_loopback = False

    local_government_test_mode = (
        current_app.config.get("ASSISTANT_ALLOW_UNAUTHENTICATED_GOVERNMENT", False)
        and current_app.debug
        and not current_app.testing
        and persona == "government"
        and principal is None
        and authenticated_persona is None
        and is_loopback
    )
    if local_government_test_mode:
        principal = "local-government-assistant-test"
        authenticated_persona = "government"

    trusted_ids = getattr(g, "authenticated_customer_ids", [])
    return (
        str(principal) if principal is not None else None,
        authenticated_persona,
        list(trusted_ids) if trusted_ids else [],
    )


def _reject_remote_local_government_test_request(persona: str) -> None:
    """Keep the development-only unauthenticated assistant bound to loopback."""
    if not (
        current_app.debug
        and current_app.config.get("ASSISTANT_ALLOW_UNAUTHENTICATED_GOVERNMENT", False)
        and persona == "government"
        and getattr(g, "authenticated_user_id", None) is None
        and getattr(g, "user_id", None) is None
        and getattr(g, "authenticated_persona", None) is None
    ):
        return
    remote_addr = request.remote_addr
    try:
        is_loopback = bool(
            remote_addr and ipaddress.ip_address(remote_addr).is_loopback
        )
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise AppError(
            "Unauthenticated Government assistant access is limited to loopback requests.",
            code="ASSISTANT_FORBIDDEN",
            status_code=403,
        )


@bp.route("/assistant/chat", methods=["POST"])
def assistant_chat():
    """Run a local-model, tool-registry-backed assistant query."""
    data = request.get_json(force=True, silent=False) or {}
    validated = AssistantChatRequestModel.model_validate(data)

    service = current_app.extensions["assistant_service"]
    _reject_remote_local_government_test_request(validated.persona)

    principal, authenticated_persona, trusted_ids = _assistant_identity(
        validated.persona
    )

    # Resolve residential principal when applicable
    if validated.persona in ("household", "residential"):
        try:
            h_principal = HouseholdAuthService.resolve_principal(request)
            if h_principal:
                if not h_principal.authorized_meters:
                    return success_response({
                        "answer": (
                            "Hello! Your user account currently has no smart meter provisioned. "
                            "To view live telemetry, consumption patterns, and bill forecasts, please link an authorized smart meter "
                            "or sign in with a verified account (such as `resident`). "
                            "In the meantime, I can assist you with general energy conservation tips and standard tariff explanations."
                        ),
                        "persona": validated.persona,
                        "entityId": None,
                        "customerName": h_principal.username or "Residential Customer",
                        "status": "success",
                        "isLlmGenerated": False,
                    })
                try:
                    authorized_meter_id = HouseholdAuthService.authorize_meter_access(
                        h_principal, validated.entity_id
                    )
                except AuthorizationError:
                    authorized_meter_id = h_principal.authorized_meters[0]
                validated.entity_id = authorized_meter_id
                principal = h_principal.user_id
        except Exception as exc:
            logger.debug("Household auth resolution skipped: %s", exc)

    result = service.answer_query(
        prompt=validated.prompt,
        persona=validated.persona,
        entity_id=validated.entity_id,
        conversation_id=validated.conversation_id or validated.session_id,
        principal=principal,
        authenticated_persona=authenticated_persona,
        authorized_customer_ids=trusted_ids,
        history=[m.model_dump() for m in validated.history] if validated.history else None,
        user_id=principal,
    )
    if result.get("status") == "unauthorized":
        return error_response(
            message=result.get("answer", "Access denied to the requested meter."),
            code="UNAUTHORIZED_ENTITY",
            status_code=403,
        )
    if result.get("status") == "forbidden":
        raise AppError(
            result["answer"], code="ASSISTANT_FORBIDDEN", status_code=403
        )
    if result.get("status") == "error":
        raise AppError(
            result["answer"], code="ASSISTANT_TOOL_ERROR", status_code=503
        )
    return success_response(result)


@bp.route("/assistant/chat/stream", methods=["POST"])
def assistant_chat_stream():
    """Stream Ollama answer tokens and a final citations/run metadata event."""
    data = request.get_json(force=True, silent=False) or {}
    validated = AssistantChatRequestModel.model_validate(data)
    service = current_app.extensions["assistant_service"]
    _reject_remote_local_government_test_request(validated.persona)
    principal, authenticated_persona, trusted_ids = _assistant_identity(
        validated.persona
    )
    output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
    request_values = {
        "prompt": validated.prompt,
        "persona": validated.persona,
        "entity_id": validated.entity_id,
        "conversation_id": validated.conversation_id or validated.session_id,
        "principal": principal,
        "authenticated_persona": authenticated_persona,
        "authorized_customer_ids": trusted_ids,
        "history": [m.model_dump() for m in validated.history] if validated.history else None,
        "user_id": principal,
    }

    def run_assistant() -> None:
        try:
            result = service.answer_query(
                **request_values,
                stream_callback=lambda token: output_queue.put(("token", token)),
            )
            if result.get("status") == "forbidden":
                output_queue.put(("error", {"code": "ASSISTANT_FORBIDDEN", "message": result["answer"]}))
            elif result.get("status") == "error":
                output_queue.put(("error", {"code": "ASSISTANT_TOOL_ERROR", "message": result["answer"]}))
            else:
                output_queue.put(("complete", result))
        except Exception as exc:
            logger.exception("Streaming assistant request failed.")
            output_queue.put(
                ("error", {"code": "ASSISTANT_ERROR", "message": str(exc)})
            )
        finally:
            output_queue.put(("done", None))

    worker = threading.Thread(target=run_assistant, daemon=True)
    worker.start()

    @stream_with_context
    def generate():
        yield f"data: {json.dumps({'type': 'started'})}\n\n"
        while True:
            kind, payload = output_queue.get()
            if kind == "done":
                break
            yield f"data: {json.dumps({'type': kind, 'data': payload}, default=str)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/assistant/tools", methods=["GET"])
def assistant_tools():
    """Expose available tool metadata without exposing handlers or credentials."""
    service = current_app.extensions["assistant_service"]
    assistant = service._assistant()
    return success_response({"items": assistant.registry.describe()})


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
