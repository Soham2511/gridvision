"""Loopback-only runner for manually testing the generic report UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT))


def _local_report_identity(_request) -> str:
    # One fixed owner exists only inside this explicitly enabled local runner.
    return "local-report-generator-test-user"


if os.getenv("GRIDVISION_REPORT_LOCAL_DEV_AUTH", "").strip().lower() != "true":
    raise SystemExit(
        "Set GRIDVISION_REPORT_LOCAL_DEV_AUTH=true to enable this loopback-only test runner."
    )

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402


class LocalReportConfig(DevelopmentConfig):
    REPORT_GENERATOR_IDENTITY_RESOLVER = staticmethod(_local_report_identity)


if __name__ == "__main__":
    application = create_app(LocalReportConfig)
    application.run(host="127.0.0.1", port=5000, debug=False)
