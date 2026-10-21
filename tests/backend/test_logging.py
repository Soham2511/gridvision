from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from flask.testing import FlaskClient

from app.utils.logging import JsonLogFormatter


def test_json_log_formatter_includes_request_event_fields():
    record = logging.LogRecord(
        name="gridvision.endpoints",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="api_request",
        args=(),
        exc_info=None,
    )
    record.event = {
        "request_id": "request-test",
        "method": "GET",
        "path": "/api/v1/health",
        "status_code": 200,
        "duration_ms": 1.25,
    }

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["message"] == "api_request"
    assert payload["request_id"] == "request-test"
    assert payload["status_code"] == 200
    assert payload["timestamp"].endswith("+00:00")


def test_api_request_is_written_as_jsonl(client: FlaskClient):
    response = client.get("/api/v1/health")
    request_id = response.headers["X-Request-ID"]
    default_log_root = Path(__file__).resolve().parents[2] / "logs"
    log_root = Path(os.getenv("GRIDVISION_LOG_DIR", default_log_root)).resolve()
    endpoint_log = log_root / "endpoints" / "api.jsonl"
    events = [
        json.loads(line)
        for line in endpoint_log.read_text(encoding="utf-8").splitlines()
    ]
    request_event = next(
        event for event in events if event.get("request_id") == request_id
    )

    assert request_event["method"] == "GET"
    assert request_event["path"] == "/api/v1/health"
    assert request_event["status_code"] == 200
