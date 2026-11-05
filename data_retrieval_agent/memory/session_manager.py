"""Owner-bound expiring sessions; no cross-session memory."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..context import AuthenticatedRequestContext


@dataclass
class Session:
    session_id: str
    owner_id: str
    persona: str
    created_at: datetime
    expires_at: datetime
    turns: list[dict[str, str]] = field(default_factory=list)
    status: str = "active"


class SessionManager:
    def __init__(self, ttl_seconds: int = 1800, absolute_ttl_seconds: int = 86400, on_delete: Callable[[str], None] | None = None):
        self.ttl_seconds, self.absolute_ttl_seconds = ttl_seconds, absolute_ttl_seconds
        self.on_delete = on_delete
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    def cleanup(self) -> int:
        with self._lock:
            now = self._now()
            expired = [sid for sid, session in self._sessions.items() if session.expires_at <= now]
            for sid in expired:
                del self._sessions[sid]
                if self.on_delete:
                    self.on_delete(sid)
            return len(expired)

    def start(self, context: AuthenticatedRequestContext) -> Session:
        now = self._now()
        session = Session(secrets.token_urlsafe(32), context.principal_id, context.persona.value, now, now + timedelta(seconds=self.ttl_seconds))
        with self._lock:
            self.cleanup()
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str, context: AuthenticatedRequestContext) -> Session | None:
        self.cleanup()
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.owner_id != context.principal_id or session.persona != context.persona.value:
                return None
            return session

    def append_turns(self, session_id: str, context: AuthenticatedRequestContext, user: str, assistant: str) -> Session:
        with self._lock:
            session = self.get(session_id, context)
            if session is None:
                raise KeyError("Session does not exist or is not owned by this user.")
            session.turns.extend([{"role": "user", "content": user}, {"role": "assistant", "content": assistant}])
            session.turns = session.turns[-20:]
            absolute = session.created_at + timedelta(seconds=self.absolute_ttl_seconds)
            session.expires_at = min(self._now() + timedelta(seconds=self.ttl_seconds), absolute)
            return session

    def end(self, session_id: str, context: AuthenticatedRequestContext) -> bool:
        with self._lock:
            if self.get(session_id, context) is None:
                return False
            del self._sessions[session_id]
            if self.on_delete:
                self.on_delete(session_id)
            return True

    @staticmethod
    def as_dict(session: Session) -> dict:
        return {"session_id": session.session_id, "created_at": session.created_at, "expires_at": session.expires_at, "status": session.status}
