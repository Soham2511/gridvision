"""Local audit store for human review of Commercial schedule proposals."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


class ScheduleApprovalStore:
    """Persist immutable proposal snapshots and one demo-user decision."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level="IMMEDIATE",
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    factory_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('pending', 'approved', 'rejected')),
                    proposal_json TEXT NOT NULL,
                    proposal_sha256 TEXT NOT NULL,
                    decided_by TEXT,
                    decided_at TEXT,
                    decision_note TEXT
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def create_proposal(
        self,
        *,
        request_id: str,
        factory_id: str,
        actor_id: str,
        proposal: dict[str, Any],
    ) -> dict[str, str]:
        """Store a proposal as an immutable snapshot awaiting human review."""
        encoded = json.dumps(
            proposal,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        proposal_id = str(uuid.uuid4())
        proposal_sha256 = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO schedule_proposals (
                    proposal_id, request_id, factory_id, created_by, created_at,
                    status, proposal_json, proposal_sha256
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    proposal_id,
                    request_id,
                    factory_id,
                    actor_id,
                    created_at,
                    encoded,
                    proposal_sha256,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return {
            "proposal_id": proposal_id,
            "status": "pending",
            "proposal_sha256": proposal_sha256,
            "created_by": actor_id,
        }

    def decide(
        self,
        proposal_id: str,
        *,
        actor_id: str,
        decision: Literal["approved", "rejected"],
        note: str | None = None,
    ) -> dict[str, str] | None:
        """Record one decision; proposals cannot be edited or decided twice."""
        decided_at = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, proposal_sha256, decided_by
                FROM schedule_proposals
                WHERE proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "pending":
                return {
                    "proposal_id": proposal_id,
                    "status": str(row["status"]),
                    "proposal_sha256": str(row["proposal_sha256"]),
                    "decided_by": str(row["decided_by"]),
                    "already_decided": "true",
                }
            connection.execute(
                """
                UPDATE schedule_proposals
                SET status = ?, decided_by = ?, decided_at = ?, decision_note = ?
                WHERE proposal_id = ? AND status = 'pending'
                """,
                (decision, actor_id, decided_at, note, proposal_id),
            )
            connection.commit()
            return {
                "proposal_id": proposal_id,
                "status": decision,
                "proposal_sha256": str(row["proposal_sha256"]),
                "decided_by": actor_id,
            }
        finally:
            connection.close()
