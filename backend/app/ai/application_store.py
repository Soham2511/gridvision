"""Versioned SQLite repositories for AI reports and inbox items."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ApplicationStoreError(RuntimeError):
    pass


class AIApplicationStore:
    VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if self.path.name.casefold() in {"mlflow.db", "mlflow.sqlite", "mlflow.sqlite3"}:
            raise ValueError("AI application data must use a database separate from MLflow.")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with closing(sqlite3.connect(self.path, timeout=5)) as raw, raw:
                raw.execute("PRAGMA foreign_keys=ON")
                raw.execute("CREATE TABLE IF NOT EXISTS ai_app_schema (version INTEGER NOT NULL)")
                versions = [row[0] for row in raw.execute("SELECT version FROM ai_app_schema")]
                if not versions:
                    raw.execute("INSERT INTO ai_app_schema(version) VALUES (?)", (self.VERSION,))
                elif set(versions) != {self.VERSION}:
                    raise ApplicationStoreError("Unsupported AI application schema version.")
                raw.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS ai_reports (
                        report_id TEXT PRIMARY KEY,
                        report_type TEXT NOT NULL,
                        context TEXT NOT NULL,
                        source_refs_json TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        artifact_id TEXT,
                        idempotency_key TEXT UNIQUE,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS ai_notifications (
                        notification_id TEXT PRIMARY KEY,
                        recipient_context TEXT NOT NULL,
                        event_key TEXT NOT NULL,
                        notification_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        body TEXT NOT NULL,
                        read_at TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(recipient_context, event_key)
                    );
                    CREATE INDEX IF NOT EXISTS ai_notifications_recipient_idx
                        ON ai_notifications(recipient_context, created_at);
                    CREATE TABLE IF NOT EXISTS anomaly_workflow_executions (
                        execution_id TEXT PRIMARY KEY,
                        event_id TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        persona TEXT NOT NULL,
                        customer_id TEXT,
                        overall_status TEXT NOT NULL,
                        json_status TEXT NOT NULL,
                        report_status TEXT NOT NULL,
                        email_status TEXT NOT NULL,
                        notification_status TEXT NOT NULL,
                        report_id TEXT,
                        pdf_artifact_id TEXT,
                        notification_id TEXT,
                        email_recipient TEXT,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(event_id, run_id)
                    );
                    CREATE INDEX IF NOT EXISTS anomaly_workflow_executions_run_idx
                        ON anomaly_workflow_executions(run_id);
                    CREATE INDEX IF NOT EXISTS anomaly_workflow_executions_event_idx
                        ON anomaly_workflow_executions(event_id);
                    """
                )
            import os
            if os.name == "posix":
                os.chmod(self.path, 0o600)
        except (OSError, sqlite3.Error) as exc:
            raise ApplicationStoreError("Unable to initialize AI application storage.") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def create_report(
        self,
        report_type: str,
        context: str,
        source_refs: list[dict[str, Any]],
        payload: dict[str, Any],
        artifact_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        report_id = uuid.uuid4().hex
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """INSERT OR IGNORE INTO ai_reports
                    (report_id, report_type, context, source_refs_json, payload_json,
                     artifact_id, idempotency_key, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (report_id, report_type, context, json.dumps(source_refs),
                     json.dumps(payload), artifact_id, idempotency_key, self._now()),
                )
                row = connection.execute(
                    "SELECT * FROM ai_reports WHERE idempotency_key = ?"
                    if idempotency_key else "SELECT * FROM ai_reports WHERE report_id = ?",
                    (idempotency_key or report_id,),
                ).fetchone()
                if row is None:
                    raise ApplicationStoreError("Unable to persist report metadata.")
                return self._report_dict(row)
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to persist report metadata.") from exc

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT * FROM ai_reports WHERE report_id=?", (report_id,)).fetchone()
                return self._report_dict(row) if row else None
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to read report metadata.") from exc

    def list_reports(self, context: str, limit: int = 50) -> list[dict[str, Any]]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT * FROM ai_reports WHERE context=? ORDER BY created_at DESC LIMIT ?",
                    (context, max(1, min(100, limit))),
                ).fetchall()
                return [self._report_dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to list report metadata.") from exc

    @staticmethod
    def _report_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["source_refs"] = json.loads(result.pop("source_refs_json"))
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def notify(
        self, recipient_context: str, event_key: str, notification_type: str,
        title: str, body: str,
    ) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """INSERT OR IGNORE INTO ai_notifications
                    (notification_id, recipient_context, event_key, notification_type,
                     title, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (identifier, recipient_context, event_key, notification_type,
                     title, body, self._now()),
                )
                row = connection.execute(
                    "SELECT * FROM ai_notifications WHERE recipient_context=? AND event_key=?",
                    (recipient_context, event_key),
                ).fetchone()
                return dict(row)
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to persist notification.") from exc

    def list_notifications(self, recipient_context: str, limit: int = 100) -> list[dict[str, Any]]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT * FROM ai_notifications WHERE recipient_context=? ORDER BY created_at DESC LIMIT ?",
                    (recipient_context, max(1, min(200, limit))),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to list notifications.") from exc

    def mark_notification_read(self, recipient_context: str, notification_id: str) -> dict[str, Any] | None:
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    "UPDATE ai_notifications SET read_at=COALESCE(read_at, ?) WHERE notification_id=? AND recipient_context=?",
                    (self._now(), notification_id, recipient_context),
                )
                row = connection.execute(
                    "SELECT * FROM ai_notifications WHERE notification_id=? AND recipient_context=?",
                    (notification_id, recipient_context),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to update notification.") from exc

    def delete_notification(self, recipient_context: str, notification_id: str) -> bool:
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM ai_notifications WHERE notification_id=? AND (recipient_context=? OR recipient_context LIKE ?)",
                    (notification_id, recipient_context, f"{recipient_context}%"),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to delete notification.") from exc

    def clear_all_notifications(self, recipient_context: str) -> int:
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM ai_notifications WHERE recipient_context=? OR recipient_context LIKE ?",
                    (recipient_context, f"{recipient_context}%"),
                )
                return cursor.rowcount
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to clear notifications.") from exc

    def record_workflow_execution(
        self,
        event_id: str,
        run_id: str,
        persona: str,
        customer_id: str | None = None,
        overall_status: str = "PENDING",
        json_status: str = "PENDING",
        report_status: str = "PENDING",
        email_status: str = "PENDING",
        notification_status: str = "PENDING",
    ) -> dict[str, Any]:
        execution_id = uuid.uuid4().hex
        now = self._now()
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """INSERT OR IGNORE INTO anomaly_workflow_executions
                    (execution_id, event_id, run_id, persona, customer_id,
                     overall_status, json_status, report_status, email_status,
                     notification_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        execution_id,
                        event_id,
                        run_id,
                        persona,
                        str(customer_id) if customer_id is not None else None,
                        overall_status,
                        json_status,
                        report_status,
                        email_status,
                        notification_status,
                        now,
                        now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM anomaly_workflow_executions WHERE event_id = ? AND run_id = ?",
                    (event_id, run_id),
                ).fetchone()
                if row is None:
                    row = connection.execute(
                        "SELECT * FROM anomaly_workflow_executions WHERE event_id = ?",
                        (event_id,),
                    ).fetchone()
                if row is None:
                    raise ApplicationStoreError("Unable to persist workflow execution record.")
                return dict(row)
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to persist workflow execution record.") from exc

    def update_workflow_execution(
        self,
        event_id: str,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        valid_fields = {
            "overall_status",
            "json_status",
            "report_status",
            "email_status",
            "notification_status",
            "report_id",
            "pdf_artifact_id",
            "notification_id",
            "email_recipient",
            "error_message",
            "retry_count",
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return self.get_workflow_execution(event_id, run_id=run_id)

        now = self._now()
        updates["updated_at"] = now
        set_clauses = [f"{k} = ?" for k in updates.keys()]
        where_clause = "WHERE event_id = ? AND run_id = ?" if run_id else "WHERE event_id = ?"
        where_values = [event_id, run_id] if run_id else [event_id]
        values = list(updates.values()) + where_values

        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    f"UPDATE anomaly_workflow_executions SET {', '.join(set_clauses)} {where_clause}",
                    values,
                )
                row = connection.execute(
                    f"SELECT * FROM anomaly_workflow_executions {where_clause} ORDER BY created_at DESC LIMIT 1",
                    where_values,
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to update workflow execution record.") from exc

    def get_workflow_execution(
        self, event_id: str, run_id: str | None = None
    ) -> dict[str, Any] | None:
        try:
            with closing(self._connect()) as connection:
                if run_id:
                    row = connection.execute(
                        "SELECT * FROM anomaly_workflow_executions WHERE event_id = ? AND run_id = ?",
                        (event_id, run_id),
                    ).fetchone()
                else:
                    row = connection.execute(
                        "SELECT * FROM anomaly_workflow_executions WHERE event_id = ? ORDER BY created_at DESC LIMIT 1",
                        (event_id,),
                    ).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to read workflow execution record.") from exc

    def list_workflow_executions(
        self, run_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        try:
            with closing(self._connect()) as connection:
                if run_id:
                    rows = connection.execute(
                        "SELECT * FROM anomaly_workflow_executions WHERE run_id = ? ORDER BY created_at DESC LIMIT ?",
                        (run_id, max(1, min(200, limit))),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT * FROM anomaly_workflow_executions ORDER BY created_at DESC LIMIT ?",
                        (max(1, min(200, limit)),),
                    ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise ApplicationStoreError("Unable to list workflow executions.") from exc
