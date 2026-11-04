"""Isolated Flask API; requires a server-injected trusted identity resolver."""

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError
from .context import AuthenticatedRequestContext
from .schemas import AgentMessageResponse, MessageRequest, StartSessionRequest

bp = Blueprint("data_retrieval_agent", __name__)


class AgentAPIError(Exception):
    def __init__(self, message: str, code: str, status_code: int):
        super().__init__(message)
        self.message, self.code, self.status_code = message, code, status_code


@bp.errorhandler(AgentAPIError)
def _agent_error(error: AgentAPIError):
    return jsonify({"success": False, "error": {"code": error.code, "message": error.message}}), error.status_code


@bp.errorhandler(ValidationError)
def _validation_error(error: ValidationError):
    return jsonify({"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Request body failed contract validation.", "details": error.errors()}}), 422


def _success(data, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def _context():
    resolver = current_app.extensions.get("data_retrieval_identity_resolver")
    if not callable(resolver):
        raise AgentAPIError("Authenticated identity is not configured for the agent.", "AUTHENTICATION_REQUIRED", 401)
    try:
        context = resolver(request)
    except Exception as exc:
        raise AgentAPIError("Authenticated identity could not be verified.", "AUTHENTICATION_REQUIRED", 401) from exc
    if not isinstance(context, AuthenticatedRequestContext):
        raise AgentAPIError("Identity resolver did not return a trusted context.", "AUTHENTICATION_REQUIRED", 401)
    return context


def _agent():
    agent = current_app.extensions.get("data_retrieval_agent")
    if agent is None:
        raise AgentAPIError("The data retrieval agent is unavailable.", "AGENT_UNAVAILABLE", 503)
    return agent


@bp.route("/sessions", methods=["POST"])
def start_session():
    context, agent = _context(), _agent()
    if not agent.ready:
        raise AgentAPIError("The agent or its LLM provider is not configured.", "AGENT_UNAVAILABLE", 503)
    StartSessionRequest.model_validate(request.get_json(force=True, silent=False) or {})
    session = agent.sessions.start(context)
    return _success(agent.sessions.as_dict(session), status_code=201)


@bp.route("/sessions/<session_id>/messages", methods=["POST"])
def send_message(session_id: str):
    context, agent = _context(), _agent()
    payload = MessageRequest.model_validate(request.get_json(force=True, silent=False) or {})
    try:
        result = agent.respond(session_id, payload.message, context)
    except KeyError as exc:
        raise AgentAPIError("Session was not found or is not owned by this user.", "SESSION_NOT_FOUND", 404) from exc
    except ValueError as exc:
        raise AgentAPIError(str(exc), "INVALID_INPUT", 422) from exc
    except TimeoutError as exc:
        raise AgentAPIError("The retrieval request exceeded its time limit.", "AGENT_TIMEOUT", 504) from exc
    except RuntimeError as exc:
        raise AgentAPIError("The agent is unavailable.", "AGENT_UNAVAILABLE", 503) from exc
    validated = AgentMessageResponse.model_validate(result)
    return _success(validated.model_dump(mode="json"))


@bp.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id: str):
    context, agent = _context(), _agent()
    session = agent.sessions.get(session_id, context)
    if session is None:
        raise AgentAPIError("Session was not found or is not owned by this user.", "SESSION_NOT_FOUND", 404)
    return _success(agent.sessions.as_dict(session))


@bp.route("/sessions/<session_id>", methods=["DELETE"])
def end_session(session_id: str):
    context, agent = _context(), _agent()
    if not agent.sessions.end(session_id, context):
        raise AgentAPIError("Session was not found or is not owned by this user.", "SESSION_NOT_FOUND", 404)
    return _success({"session_id": session_id, "status": "ended"})
