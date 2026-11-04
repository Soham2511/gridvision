"""Persistent thread memory, keyed by principal and conversation thread."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from ai.anamoly.config.settings import ANOMALY_ROOT


class ConversationMemory:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ANOMALY_ROOT / "memory" / "storage" / "conversations.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_threads (
                    owner_key TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    messages_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner_key, conversation_id, persona)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _owner_key(principal: str | None) -> str | None:
        # In this demo, the frontend's random conversation ID isolates anonymous threads.
        owner = principal or "gridvision-demo-anonymous"
        return hashlib.sha256(owner.encode("utf-8")).hexdigest()

    def load(
        self, principal: str | None, conversation_id: str, persona: str
    ) -> list[dict[str, Any]]:
        owner_key = self._owner_key(principal)
        if owner_key is None:
            return []
        with self._connect() as connection:
            row = connection.execute(
                "SELECT messages_json FROM conversation_threads "
                "WHERE owner_key = ? AND conversation_id = ? AND persona = ?",
                (owner_key, conversation_id, persona),
            ).fetchone()
        return json.loads(row["messages_json"]) if row else []

    def latest_structured_context(
        self, principal: str | None, conversation_id: str, persona: str
    ) -> dict[str, Any]:
        for message in reversed(self.load(principal, conversation_id, persona)):
            value = message.get("structured_context")
            if isinstance(value, dict):
                return value
        return {}

    def append(
        self,
        principal: str | None,
        conversation_id: str,
        persona: str,
        user_text: str,
        assistant_text: str,
        *,
        current_run_id: str | None = None,
        selected_event_id: str | None = None,
        run_ids: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        structured_context: dict[str, Any] | None = None,
    ) -> None:
        owner_key = self._owner_key(principal)
        if owner_key is None:
            return
        messages = self.load(principal, conversation_id, persona)
        messages.extend(
            [
                {"role": "user", "content": user_text},
                {
                    "role": "assistant",
                    "content": assistant_text,
                    "run_id": current_run_id,
                    "event_id": selected_event_id,
                    "run_ids": run_ids or ([current_run_id] if current_run_id else []),
                    "start_date": start_date,
                    "end_date": end_date,
                    "structured_context": structured_context or {},
                },
            ]
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_threads
                    (owner_key, conversation_id, persona, messages_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(owner_key, conversation_id, persona)
                DO UPDATE SET messages_json = excluded.messages_json,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (
                    owner_key,
                    conversation_id,
                    persona,
                    json.dumps(messages[-40:], ensure_ascii=False),
                ),
            )
