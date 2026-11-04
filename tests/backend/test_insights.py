"""Tests for energy insights and AI domain assistant."""

from __future__ import annotations

from pathlib import Path

from flask.testing import FlaskClient

from ai.commercial.approvals import ScheduleApprovalStore
from ai.commercial.schemas.communication import (
    AgentResult,
    EvidenceRef,
    ToolObservation,
)


def test_energy_insights(client: FlaskClient):
    """Test retrieving energy insights and filtering."""
    response = client.get("/api/v1/energy-insights")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 4

    res_peak = client.get("/api/v1/energy-insights?category=peak_shaving")
    assert res_peak.status_code == 200
    for ins in res_peak.get_json()["data"]:
        assert ins["category"] == "peak_shaving"

    res_sector = client.get("/api/v1/energy-insights?sector=commercial")
    assert res_sector.status_code == 200
    for ins in res_sector.get_json()["data"]:
        assert ins["sector"] in ("commercial", "all")


def test_assistant_chat(client: FlaskClient):
    """Test AI assistant prompt answering."""
    tariff_prompt = {"prompt": "How is my month-end bill calculated?", "persona": "household"}
    res_tariff = client.post("/api/v1/assistant/chat", json=tariff_prompt)
    assert res_tariff.status_code == 200
    assert "Billing Computation" in res_tariff.get_json()["data"]["answer"]

    peak_prompt = {"prompt": "What is our current reserve margin?", "persona": "government"}
    res_peak = client.post("/api/v1/assistant/chat", json=peak_prompt)
    assert res_peak.status_code == 200
    assert "Reserve Status" in res_peak.get_json()["data"]["answer"]


def test_assistant_renewable_estimate_includes_sources_and_peak_context(
    client: FlaskClient,
) -> None:
    class RenewableFixture:
        def get_renewable_scenarios(
            self, factory_id: str | None, goal: str
        ) -> ToolObservation:
            del factory_id, goal
            return ToolObservation(
                status="available",
                findings=("Solar generation estimate: 6,570 kWh/year.",),
                evidence_refs=(
                    EvidenceRef(
                        source_id="https://example.com/solar",
                        source_type="web_search",
                        locator="https://example.com/solar",
                    ),
                ),
            )

    service = client.application.extensions["assistant_service"]
    service.renewable_tools = RenewableFixture()
    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Estimate solar generation and compare it with the peak demand forecast.",
            "persona": "commercial",
        },
    )

    assert response.status_code == 200
    answer = response.get_json()["data"]["answer"]
    assert "6,570 kWh/year" in answer
    assert "expected system peak" in answer
    assert "https://example.com/solar" in answer


def test_assistant_renewables_asks_for_inputs_instead_of_assuming_savings(
    client: FlaskClient,
) -> None:
    response = client.post(
        "/api/v1/assistant/chat",
        json={"prompt": "Estimate rooftop solar savings.", "persona": "commercial"},
    )

    assert response.status_code == 200
    answer = response.get_json()["data"]["answer"]
    assert "Provide system capacity, usable roof area, or annual energy" in answer
    assert "₹" not in answer


def test_commercial_workflow_endpoint_passes_typed_request_and_trace_metadata(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "automotive-demo")
    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")

    class WorkflowFixture:
        def invoke(self, request: dict) -> dict:
            assert request["request_id"]
            assert request["factory_id"] == "automotive-parts-demo"
            assert request["building_id"] is None
            assert request["user_goal"] == "Summarize peak demand."
            assert request["optimization_inputs"] is None
            return {
                "final_response": {
                    "request_id": request["request_id"],
                    "status": "incomplete",
                    "summary": "No trained forecast was configured.",
                },
                "step_count": 4,
                "tool_call_count": 0,
                "llm_call_count": 0,
            }

    client.application.extensions["commercial_workflow"] = WorkflowFixture()
    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "factory_id": "automotive-parts-demo",
            "user_goal": "Summarize peak demand.",
        },
        auth=("automotive-demo", "test-only-password"),
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result["data"]["status"] == "incomplete"
    assert result["meta"]["tool_call_count"] == 0


def test_commercial_workflow_endpoint_rejects_unknown_request_fields(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "automotive-demo")
    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")
    response = client.post(
        "/api/v1/commercial/workflow",
        json={"user_goal": "Inspect the factory.", "extra": "not allowed"},
        auth=("automotive-demo", "test-only-password"),
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_commercial_workflow_endpoint_requires_demo_credentials(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "automotive-demo")
    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")

    response = client.post(
        "/api/v1/commercial/workflow",
        json={"user_goal": "Summarize the automotive-parts demo."},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic ")


def test_commercial_workflow_endpoint_reports_missing_demo_configuration(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEMO_USER_ID", raising=False)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)

    response = client.post(
        "/api/v1/commercial/workflow",
        json={"user_goal": "Summarize the automotive-parts demo."},
    )

    assert response.status_code == 503
    assert (
        response.get_json()["error"]["code"]
        == "DEMO_AUTH_NOT_CONFIGURED"
    )


def test_commercial_workflow_endpoint_rejects_other_factory_scopes(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "automotive-demo")
    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")

    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "factory_id": "another-factory",
            "user_goal": "Summarize the automotive-parts demo.",
        },
        auth=("automotive-demo", "test-only-password"),
    )

    assert response.status_code == 403
    assert (
        response.get_json()["error"]["code"]
        == "DEMO_FACTORY_SCOPE_VIOLATION"
    )


def test_commercial_workflow_endpoint_does_not_query_unscoped_buildings(
    client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "automotive-demo")
    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")

    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "building_id": "101",
            "user_goal": "Forecast the building peak.",
        },
        auth=("automotive-demo", "test-only-password"),
    )

    assert response.status_code == 403
    assert (
        response.get_json()["error"]["code"]
        == "DEMO_BUILDING_SCOPE_UNAVAILABLE"
    )


def test_schedule_proposal_requires_and_records_human_approval(
    client: FlaskClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEMO_USER_ID", "automotive-demo")
    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")
    client.application.extensions["commercial_schedule_approvals"] = (
        ScheduleApprovalStore(tmp_path / "approvals.sqlite3")
    )

    class WorkflowFixture:
        def invoke(self, request: dict) -> dict:
            assert request["factory_id"] == "automotive-parts-demo"
            return {
                "final_response": {
                    "request_id": request["request_id"],
                    "factory_id": "automotive-parts-demo",
                    "status": "passed",
                    "summary": "Schedule proposal ready for review.",
                },
                "optimization_result": AgentResult(
                    task_id="cost_optimization",
                    specialist="cost_optimization",
                    status="completed",
                    data={
                        "status": "optimal",
                        "schedule": [
                            {
                                "job_id": "press-job",
                                "machine_id": "press-1",
                                "start_hour": 1,
                                "end_hour": 2,
                            }
                        ],
                        "calculated_cost_inr": 12.5,
                    },
                ),
                "step_count": 1,
                "tool_call_count": 1,
                "llm_call_count": 0,
            }

    client.application.extensions["commercial_workflow"] = WorkflowFixture()
    response = client.post(
        "/api/v1/commercial/workflow",
        json={
            "user_goal": "Optimize the supplied demo schedule.",
            "optimization_inputs": {
                "horizon_hours": 2,
                "prices_inr_per_kwh": [1, 2],
                "jobs": [
                    {
                        "job_id": "press-job",
                        "machine_id": "press-1",
                        "power_kw": 5,
                        "duration_hours": 1,
                        "deadline_hour": 2,
                    }
                ],
            },
        },
        auth=("automotive-demo", "test-only-password"),
    )

    proposal = response.get_json()["data"]["schedule_proposal"]
    assert response.status_code == 200
    assert proposal["status"] == "pending"
    assert proposal["approval_required_before_use"] is True
    assert proposal["equipment_controlled"] is False
    assert proposal["created_by"] == "automotive-demo"

    approval_url = (
        "/api/v1/commercial/schedules/"
        f"{proposal['proposal_id']}/approval"
    )
    approved = client.post(
        approval_url,
        json={"decision": "approved", "note": "Reviewed demo proposal."},
        auth=("automotive-demo", "test-only-password"),
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["status"] == "approved"
    assert approved.get_json()["data"]["equipment_controlled"] is False
    assert approved.get_json()["data"]["decided_by"] == "automotive-demo"

    duplicate = client.post(
        approval_url,
        json={"decision": "approved"},
        auth=("automotive-demo", "test-only-password"),
    )
    assert duplicate.status_code == 409
    assert (
        duplicate.get_json()["error"]["code"]
        == "SCHEDULE_PROPOSAL_ALREADY_DECIDED"
    )
