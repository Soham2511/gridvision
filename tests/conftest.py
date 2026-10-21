"""Shared pytest configuration for backend and training tests."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

_RUN_STARTED_AT = time.perf_counter()


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,
    config: Any,
) -> None:
    """Persist a structured summary and test-case results for each pytest run."""
    del config
    log_root = Path(
        os.getenv(
            "GRIDVISION_LOG_DIR",
            Path(__file__).resolve().parents[1] / "logs",
        )
    ).expanduser()
    testing_log_dir = log_root / "testing"
    testing_log_dir.mkdir(parents=True, exist_ok=True)

    outcomes = ("passed", "failed", "skipped", "xfailed", "xpassed")
    test_results = []
    for outcome in outcomes:
        for report in terminalreporter.stats.get(outcome, []):
            if outcome == "passed" and report.when != "call":
                continue
            result = {
                "node_id": report.nodeid,
                "outcome": outcome,
                "phase": report.when,
                "duration_seconds": round(report.duration, 6),
            }
            if outcome == "failed":
                result["failure"] = report.longreprtext
            test_results.append(result)

    logged_at = datetime.now(timezone.utc)
    payload = {
        "schema_version": 1,
        "logged_at_utc": logged_at.isoformat(),
        "duration_seconds": round(time.perf_counter() - _RUN_STARTED_AT, 6),
        "exit_status": int(exitstatus),
        "summary": {
            outcome: len(terminalreporter.stats.get(outcome, []))
            for outcome in outcomes
        },
        "warnings": [
            str(warning)
            for warning in terminalreporter.stats.get("warnings", [])
        ],
        "tests": test_results,
    }
    filename = logged_at.strftime("pytest-%Y%m%dT%H%M%S.%fZ.json")
    (testing_log_dir / filename).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
