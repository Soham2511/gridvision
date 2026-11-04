from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient

from ai.commercial.graph import WorkflowExecutionError


def _auth_headers(username: str = "demo", password: str = "secret") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class _UploadIndex:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    def indexed_documents(self) -> list[dict[str, object]]:
        return self.documents

    def index_counts(self) -> dict[str, int]:
        return {"documents": len(self.documents), "chunks": len(self.documents)}


class _UploadRetriever:
    def __init__(self, upload_root: Path) -> None:
        self.upload_root = upload_root
        self.index = _UploadIndex()

    def index_documents(self) -> dict[str, object]:
        reports = []
        for path in self.upload_root.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            self.index.documents.append(
                {
                    "source_id": path.name,
                    "path": str(path.resolve()),
                    "size_bytes": path.stat().st_size,
                    "page_count": 1,
                }
            )
            reports.append(
                {
                    "source_id": path.name,
                    "status": "indexed",
                    "page_count": 1,
                    "chunk_count": 1,
                }
            )
        return {"documents": reports, "index_counts": self.index.index_counts()}


def test_commercial_session_requires_demo_credentials(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")

    unauthorized = client.post("/api/v1/commercial/session", json={})
    authorized = client.post(
        "/api/v1/commercial/session",
        json={},
        headers=_auth_headers(),
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json["data"]["factory_id"] == "automotive-parts-demo"


def test_commercial_auth_preflight_does_not_require_credentials(
    client: FlaskClient,
) -> None:
    response = client.options(
        "/api/v1/commercial/session",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == (
        "http://localhost:5173"
    )


def test_authenticated_workflow_returns_master_agent_evidence(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")

    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "user_goal": (
                "How can compressed air leaks be reduced in the demo factory?"
            ),
            "factory_id": "automotive-parts-demo",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    result = response.json["data"]
    assert result["status"] == "passed"
    assert "operations" in result["specialist_results"]
    assert result["evidence_refs"]
    assert result["execution_trace"]
    assert result["execution_trace"][0]["node_id"] == "validate_request"
    assert response.json["meta"]["tool_call_count"] >= 1


def test_workflow_node_failure_returns_safe_execution_trace(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")

    class FailedWorkflow:
        def invoke(self, _request: dict) -> dict:
            raise WorkflowExecutionError(
                failed_node="operations",
                error_type="TimeoutError",
                execution_trace=[
                    {
                        "node_id": "validate_request",
                        "status": "completed",
                        "duration_ms": 1.0,
                    },
                    {
                        "node_id": "operations",
                        "status": "error",
                        "duration_ms": 4.0,
                        "message": "Node failed with TimeoutError.",
                    },
                ],
            )

    monkeypatch.setitem(
        client.application.extensions,
        "commercial_workflow",
        FailedWorkflow(),
    )
    response = client.post(
        "/api/v1/commercial/workflow",
        json={"user_goal": "Check motors."},
        headers=_auth_headers(),
    )

    assert response.status_code == 500
    assert response.json["error"]["code"] == "WORKFLOW_STEP_FAILED"
    details = response.json["error"]["details"]
    assert details["failed_node"] == "operations"
    assert details["execution_trace"][-1]["status"] == "error"
    assert response.headers["X-Request-ID"]


def test_invalid_schedule_returns_json_validation_details_not_internal_error(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")

    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "user_goal": "Optimize the schedule.",
            "optimization_inputs": {
                "horizon_hours": 1,
                "prices_inr_per_kwh": [1],
                "jobs": [
                    {
                        "job_id": "job-1",
                        "machine_id": "press",
                        "power_kw": 1,
                        "duration_hours": 1,
                        "deadline_hour": 1,
                    }
                ],
                "battery": {
                    "capacity_kwh": 10,
                    "initial_soc_kwh": 5,
                    "terminal_soc_kwh": 11,
                    "max_charge_kw": 1,
                    "max_discharge_kw": 1,
                    "charge_efficiency": 1,
                    "discharge_efficiency": 1,
                },
            },
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    assert response.json["error"]["code"] == "VALIDATION_ERROR"
    issue = response.json["error"]["details"][0]
    assert issue["loc"][-1] == "battery"
    assert "Terminal state of charge" in issue["msg"]
    assert "ctx" not in issue
    assert "input" not in issue
    assert response.headers["X-Request-ID"]


def test_authenticated_text_upload_is_safely_named_and_indexed(
    app: Flask,
    client: FlaskClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    app.extensions["commercial_rag_retriever"] = _UploadRetriever(upload_root)

    response = client.post(
        "/api/v1/commercial/rag/documents",
        data={"file": (BytesIO(b"Factory maintenance notes.",), "../../notes.txt")},
        content_type="multipart/form-data",
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    source_id = response.json["data"]["source_id"]
    assert source_id.endswith("_notes.txt")
    assert (upload_root / source_id).read_bytes() == b"Factory maintenance notes."


def test_authenticated_upload_rejects_unsupported_document_type(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")

    response = client.post(
        "/api/v1/commercial/rag/documents",
        data={"file": (BytesIO(b"executable"), "payload.exe")},
        content_type="multipart/form-data",
        headers=_auth_headers(),
    )

    assert response.status_code == 415
    assert response.json["error"]["code"] == "UPLOAD_FORMAT_NOT_SUPPORTED"
