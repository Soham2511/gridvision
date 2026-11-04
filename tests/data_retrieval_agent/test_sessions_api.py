"""Session ownership, expiry, and unauthenticated API boundary tests."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from flask import Flask

from data_retrieval_agent.api import bp
from data_retrieval_agent.context import AuthenticatedRequestContext, Persona
from data_retrieval_agent.memory.session_manager import SessionManager


def _context(user="user-1"):
    return AuthenticatedRequestContext(
        principal_id=user,
        persona=Persona.RESIDENTIAL,
        permissions=frozenset(),
        entity_scopes={},
        request_id="req-1",
    )


def test_session_is_private_and_expiring(monkeypatch):
    deleted = []
    manager = SessionManager(ttl_seconds=10, on_delete=deleted.append)
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(manager, "_now", lambda: current)
    session = manager.start(_context())
    assert manager.get(session.session_id, _context()) is session
    assert manager.get(session.session_id, _context("user-2")) is None
    current += timedelta(seconds=11)
    assert manager.get(session.session_id, _context()) is None
    assert deleted == [session.session_id]


def test_api_rejects_when_trusted_identity_adapter_is_missing():
    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix="/api/v1/data-retrieval-agent")
    response = app.test_client().post("/api/v1/data-retrieval-agent/sessions", json={})
    assert response.status_code == 401
    assert response.json["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_api_session_lifecycle_is_owner_scoped():
    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix="/api/v1/data-retrieval-agent")
    agent = SimpleNamespace(ready=True, sessions=SessionManager())
    app.extensions["data_retrieval_agent"] = agent
    principal = {"user": "user-1"}
    app.extensions["data_retrieval_identity_resolver"] = lambda _request: _context(principal["user"])
    client = app.test_client()

    started = client.post("/api/v1/data-retrieval-agent/sessions", json={})
    assert started.status_code == 201
    session_id = started.json["data"]["session_id"]
    assert client.get(f"/api/v1/data-retrieval-agent/sessions/{session_id}").status_code == 200

    principal["user"] = "user-2"
    assert client.get(f"/api/v1/data-retrieval-agent/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/v1/data-retrieval-agent/sessions/{session_id}").status_code == 404

    principal["user"] = "user-1"
    assert client.delete(f"/api/v1/data-retrieval-agent/sessions/{session_id}").json["data"]["status"] == "ended"
