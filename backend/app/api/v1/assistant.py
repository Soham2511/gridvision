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
from app.utils.responses import success_response
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
    """Run a local-model, tool-registry-backed anomaly assistant query."""
    data = request.get_json(force=True, silent=False) or {}
    validated = AssistantChatRequestModel.model_validate(data)

    service = current_app.extensions["assistant_service"]
    _reject_remote_local_government_test_request(validated.persona)
    principal, authenticated_persona, trusted_ids = _assistant_identity(
        validated.persona
    )
    result = service.answer_query(
        prompt=validated.prompt,
        persona=validated.persona,
        entity_id=validated.entity_id,
        conversation_id=validated.conversation_id,
        principal=principal,
        authenticated_persona=authenticated_persona,
        authorized_customer_ids=trusted_ids,
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
        "conversation_id": validated.conversation_id,
        "principal": principal,
        "authenticated_persona": authenticated_persona,
        "authorized_customer_ids": trusted_ids,
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
