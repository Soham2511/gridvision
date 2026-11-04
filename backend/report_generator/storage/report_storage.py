"""Report lifecycle metadata in the existing AI database."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class ReportStorageError(RuntimeError):
    """Safe report metadata persistence error."""


class ReportRepository:
    TABLE = "json_report_generator_reports"

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(Path(database_path).expanduser())

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        try:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    f"""CREATE TABLE IF NOT EXISTS {self.TABLE} (
                        report_id TEXT PRIMARY KEY,
                        owner_key TEXT NOT NULL,
                        title TEXT,
                        status TEXT NOT NULL,
                        generated_at TEXT NOT NULL,
                        html_artifact_id TEXT,
                        pdf_artifact_id TEXT,
                        error_code TEXT,
                        limitations_json TEXT NOT NULL DEFAULT '[]'
                    )"""
                )
                connection.execute(
                    f"CREATE INDEX IF NOT EXISTS json_report_owner_idx ON {self.TABLE}(owner_key, generated_at)"
                )
            if os.name == "posix":
                os.chmod(self.database_path, 0o600)
        except (OSError, sqlite3.Error) as exc:
            raise ReportStorageError("Report metadata storage is unavailable") from exc

    def create_pending(self, report_id: str, owner_key: str, generated_at: str) -> None:
        self.initialize()
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    f"INSERT INTO {self.TABLE} (report_id, owner_key, status, generated_at) VALUES (?, ?, 'generating', ?)",
                    (report_id, owner_key, generated_at),
                )
        except sqlite3.Error as exc:
            raise ReportStorageError("Unable to record report generation") from exc

    def finish(
        self,
        report_id: str,
        owner_key: str,
        *,
        title: str,
        status: str,
        html_artifact_id: str | None,
        pdf_artifact_id: str | None,
        error_code: str | None,
        limitations: list[str],
    ) -> None:
        self.initialize()
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    f"""UPDATE {self.TABLE} SET title=?, status=?, html_artifact_id=?,
                    pdf_artifact_id=?, error_code=?, limitations_json=?
                    WHERE report_id=? AND owner_key=?""",
                    (title, status, html_artifact_id, pdf_artifact_id, error_code,
                     json.dumps(limitations), report_id, owner_key),
                )
                if cursor.rowcount != 1:
                    raise ReportStorageError("Report metadata record is unavailable")
        except sqlite3.Error as exc:
            raise ReportStorageError("Unable to update report metadata") from exc

    def fail(self, report_id: str, owner_key: str, error_code: str) -> None:
        self.initialize()
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    f"UPDATE {self.TABLE} SET status='failed', error_code=? WHERE report_id=? AND owner_key=?",
                    (error_code, report_id, owner_key),
                )
        except sqlite3.Error as exc:
            raise ReportStorageError("Unable to record report failure") from exc

    def get(self, report_id: str, owner_key: str) -> dict[str, Any] | None:
        self.initialize()
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    f"SELECT report_id, title, status, generated_at, html_artifact_id, pdf_artifact_id, error_code, limitations_json FROM {self.TABLE} WHERE report_id=? AND owner_key=?",
                    (report_id, owner_key),
                ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["limitations"] = json.loads(result.pop("limitations_json"))
            return result
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise ReportStorageError("Unable to read report metadata") from exc
