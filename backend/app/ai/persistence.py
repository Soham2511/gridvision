"""Explicit-path SQLite audit repository. It stores no prompt or evidence content."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai.contracts import GenerationAuditEvent


class PersistenceUnavailableError(RuntimeError):
    pass


class SQLiteAuditRepository:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        database_path: str | Path,
        *,
        forbidden_paths: tuple[str | Path, ...] = (),
    ) -> None:
        if str(database_path) == ":memory:":
            raise ValueError("Use an explicit temporary file for repository tests.")
        self.database_path = Path(database_path).expanduser().resolve()
        self._validate_path(self.database_path, forbidden_paths)

    @staticmethod
    def _validate_path(path: Path, forbidden_paths: tuple[str | Path, ...]) -> None:
        if path.name.casefold() in {"mlflow.db", "mlflow.sqlite", "mlflow.sqlite3"}:
            raise ValueError("AI persistence must be separate from MLflow tracking storage.")
        for forbidden in forbidden_paths:
            forbidden_path = Path(forbidden).expanduser().resolve()
            if (
                path == forbidden_path
                or forbidden_path in path.parents
                or path in forbidden_path.parents
            ):
                raise ValueError("AI database path is inside a protected data or static directory.")

    def initialize(self) -> None:
        """Create a minimal audit schema at the explicitly supplied path."""
        try:
            self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with closing(self._connect()) as connection, connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS ai_schema_version "
                    "(version INTEGER NOT NULL)"
                )
                rows = connection.execute(
                    "SELECT version FROM ai_schema_version"
                ).fetchall()
                if not rows:
                    connection.execute(
                        "INSERT INTO ai_schema_version(version) VALUES (?)",
                        (self.SCHEMA_VERSION,),
                    )
                elif max(row[0] for row in rows) != self.SCHEMA_VERSION:
                    raise PersistenceUnavailableError(
                        "Unsupported AI persistence schema version."
                    )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS ai_audit_events (
                        request_id TEXT PRIMARY KEY,
                        idempotency_key TEXT UNIQUE,
                        created_at TEXT NOT NULL,
                        workflow TEXT NOT NULL,
                        prompt_key TEXT NOT NULL,
                        prompt_version TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        source_ids_json TEXT NOT NULL,
                        duration_ms REAL NOT NULL,
                        output_chars INTEGER NOT NULL,
                        error_code TEXT
                    )"""
                )
            if os.name == "posix":
                os.chmod(self.database_path, 0o600)
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceUnavailableError("Unable to initialize AI audit storage.") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def record(self, event: GenerationAuditEvent) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """INSERT OR IGNORE INTO ai_audit_events (
                        request_id, idempotency_key, created_at, workflow, prompt_key,
                        prompt_version, provider, outcome, source_ids_json, duration_ms,
                        output_chars, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.request_id,
                        event.idempotency_key,
                        created_at,
                        event.workflow,
                        event.prompt_key,
                        event.prompt_version,
                        event.provider,
                        event.outcome,
                        json.dumps(event.source_ids, separators=(",", ":")),
                        event.duration_ms,
                        event.output_chars,
                        event.error_code,
                    ),
                )
                selector = (
                    "idempotency_key = ?"
                    if event.idempotency_key
                    else "request_id = ?"
                )
                value = event.idempotency_key or event.request_id
                row = connection.execute(
                    f"SELECT * FROM ai_audit_events WHERE {selector}", (value,)
                ).fetchone()
                if row is None:
                    raise PersistenceUnavailableError("Unable to read back the audit record.")
                return self._to_dict(row)
        except sqlite3.Error as exc:
            raise PersistenceUnavailableError("Unable to record AI audit metadata.") from exc

    def get(self, request_id: str) -> dict[str, Any] | None:
        try:
            with closing(self._connect()) as connection, connection:
                row = connection.execute(
                    "SELECT * FROM ai_audit_events WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                return self._to_dict(row) if row is not None else None
        except sqlite3.Error as exc:
            raise PersistenceUnavailableError("Unable to read AI audit metadata.") from exc

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["source_ids"] = json.loads(record.pop("source_ids_json"))
        return record

