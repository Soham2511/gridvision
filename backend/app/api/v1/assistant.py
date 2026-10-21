"""AI domain assistant route."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.utils.responses import success_response
from app.utils.validation import AssistantChatRequestModel

bp = Blueprint("assistant", __name__)


@bp.route("/assistant/chat", methods=["POST"])
def assistant_chat():
    """Contextual domain query handler for AiAssistantPage."""
    data = request.get_json(force=True, silent=False) or {}
    validated = AssistantChatRequestModel.model_validate(data)

    service = current_app.extensions["assistant_service"]
    result = service.answer_query(
        prompt=validated.prompt,
        persona=validated.persona,
        entity_id=validated.entity_id,
    )
    return success_response(result)
