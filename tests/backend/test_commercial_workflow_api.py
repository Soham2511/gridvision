from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient

from ai.commercial.graph import WorkflowExecutionError
from ai.commercial.schemas.communication import AgentError, AgentResult, ToolObservation


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

    def remove_document(self, source_id: str) -> None:
        self.documents = [
            document
            for document in self.documents
            if document["source_id"] != source_id
        ]


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

    def remove_uploaded_document(self, source_id: str) -> bool:
        document = next(
            (
                item
                for item in self.index.documents
                if item["source_id"] == source_id
            ),
            None,
        )
        if document is None:
            return False
        Path(str(document["path"])).unlink(missing_ok=True)
        self.index.remove_document(source_id)
        return True


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
    assert result["web_search_offer"] is False
    assert response.json["meta"]["tool_call_count"] >= 1


def test_rag_miss_offers_web_search_without_searching_automatically(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")
    operation = AgentResult(
        task_id="rag-miss:operations",
        specialist="operations",
        status="unavailable",
        error=AgentError(
            code="DATA_NOT_AVAILABLE",
            message="The provided documents do not contain matching information.",
        ),
    )

    class MissingRAGWorkflow:
        def invoke(self, _request: dict) -> dict:
            return {
                "final_response": {
                    "request_id": "rag-miss",
                    "factory_id": "automotive-parts-demo",
                    "status": "incomplete",
                    "summary": "The workflow could not complete an analysis.",
                    "findings": [],
                    "evidence_refs": [],
                    "assumptions": [],
                    "conflicts": [],
                    "validation": {
                        "status": "incomplete",
                        "issues": [],
                        "evidence_count": 0,
                    },
                    "errors": [],
                },
                "execution_trace": [],
                "specialist_results": {operation.task_id: operation},
            }

    monkeypatch.setitem(
        client.application.extensions,
        "commercial_workflow",
        MissingRAGWorkflow(),
    )
    web_search_calls: list[str] = []

    def search_web(query: str) -> ToolObservation:
        web_search_calls.append(query)
        return ToolObservation(status="available")

    monkeypatch.setitem(
        client.application.extensions,
        "commercial_web_search",
        search_web,
    )
    response = client.post(
        "/api/v1/commercial/workflow",
        json={"user_goal": "How do industrial motors reduce energy use?"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json["data"]["web_search_offer"] is True
    assert response.json["data"]["summary"] == (
        "The query information is missing from the RAG documents. "
        "Would you like an answer from web sources instead?"
    )
    assert web_search_calls == []


def test_confirmed_web_search_returns_answer_and_source_citations(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")
    received_queries: list[str] = []

    def search_web(query: str) -> ToolObservation:
        received_queries.append(query)
        return ToolObservation(
            status="available",
            findings=("Answer based on web sources.",),
            data={
                "results": [
                    {
                        "title": "Motor efficiency guide",
                        "url": "https://example.com/motors",
                        "content": "Use efficient motors and maintain them.",
                    }
                ]
            },
        )

    monkeypatch.setitem(
        client.application.extensions,
        "commercial_web_search",
        search_web,
    )
    query = "How can industrial motors save energy?"
    response = client.post(
        "/api/v1/commercial/web-search",
        json={"query": query},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert received_queries == [query]
    assert response.json["data"]["answer"] == "Answer based on web sources."
    assert response.json["data"]["citations"] == [
        {
            "title": "Motor efficiency guide",
            "url": "https://example.com/motors",
            "excerpt": "Use efficient motors and maintain them.",
        }
    ]


def test_authenticated_workflow_forwards_bounded_conversation_history(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "secret")
    captured_request: dict[str, object] = {}

    class CapturingWorkflow:
        def invoke(self, workflow_request: dict) -> dict:
            captured_request.update(workflow_request)
            return {
                "final_response": {
                    "request_id": "history-test",
                    "factory_id": "automotive-parts-demo",
                    "status": "passed",
                    "summary": "History-aware response.",
                    "findings": [],
                    "evidence_refs": [],
                    "assumptions": [],
                    "conflicts": [],
                    "validation": {
                        "status": "passed",
                        "issues": [],
                        "evidence_count": 0,
                    },
                    "errors": [],
                },
                "execution_trace": [],
                "specialist_results": {},
            }

    monkeypatch.setitem(
        client.application.extensions,
        "commercial_workflow",
        CapturingWorkflow(),
    )
    history = [
        {"role": "user", "content": "What maintenance constraints are documented?"},
        {"role": "assistant", "content": "The handbook includes maintenance windows."},
    ]

    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "user_goal": "What about those?",
            "conversation_history": history,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert captured_request["conversation_history"] == history


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

    delete_response = client.delete(
        f"/api/v1/commercial/rag/documents/{source_id}",
        headers=_auth_headers(),
    )

    assert delete_response.status_code == 200
    assert delete_response.json["data"] == {
        "deleted": True,
        "source_id": source_id,
    }
    assert not (upload_root / source_id).exists()

    missing_response = client.delete(
        f"/api/v1/commercial/rag/documents/{source_id}",
        headers=_auth_headers(),
    )
    assert missing_response.status_code == 404
    assert missing_response.json["error"]["code"] == "RAG_DOCUMENT_NOT_FOUND"


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
