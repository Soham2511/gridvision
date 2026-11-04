"""Tests for energy insights and AI domain assistant."""

from __future__ import annotations

from pathlib import Path

from pathlib import Path

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from flask import g
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
    """The deterministic assistant does not invent telemetry or tariffs."""
    tariff_prompt = {"prompt": "How is my month-end bill calculated?", "persona": "household"}
    res_tariff = client.post("/api/v1/assistant/chat", json=tariff_prompt)
    assert res_tariff.status_code == 200
    tariff_data = res_tariff.get_json()["data"]
    assert tariff_data["status"] == "success"
    assert tariff_data["availability"] == "unavailable"
    assert "no approved data source" in tariff_data["answer"]
    assert "₹10" not in tariff_data["answer"]

    peak_prompt = {"prompt": "What is our current reserve margin?", "persona": "government"}
    res_peak = client.post("/api/v1/assistant/chat", json=peak_prompt)
    assert res_peak.status_code == 200
    peak_data = res_peak.get_json()["data"]
    assert peak_data["availability"] == "unavailable"
    assert "Current Active Load" not in peak_data["answer"]


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


def test_government_assistant_routes_and_serves_generated_artifacts(
    app, client: FlaskClient, monkeypatch, tmp_path: Path
):
    import importlib

    from ai.govt import router as govt_router

    govt_module = importlib.import_module(
        "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
    )
    image_path = tmp_path / "redistribution.png"
    csv_path = tmp_path / "redistribution.csv"
    image_path.write_bytes(b"png-test-content")
    csv_path.write_text("from_grid,to_grid\n9,10\n", encoding="utf-8")
    monkeypatch.setattr(govt_router, "route_query", lambda query, **_: govt_router.AssistantRoute("government", "grid plan"))
    monkeypatch.setattr(govt_module, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(govt_module, "_read_history", lambda path: {"turns": [], "last_successful_request": None})
    monkeypatch.setattr(
        govt_module,
        "handle_user_query",
        lambda query, **kwargs: SimpleNamespace(
            text="Plan created.",
            image_path=image_path,
            csv_path=csv_path,
            request=None,
        ),
    )
    app.extensions["assistant_service"].route_government_queries = True

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Show the redistribution plan for 2018-09-24",
            "persona": "government",
            "conversation_id": "government-artifacts-test",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["assistantRoute"] == "government"
    assert body["answer"] == "Plan created."
    assert body["downloads"][0]["format"] == "csv"
    assert body["artifacts"][0]["format"] == "png"
    image_response = client.get(body["artifacts"][0]["url"])
    csv_response = client.get(body["downloads"][0]["url"])
    assert image_response.status_code == 200
    assert image_response.data == b"png-test-content"
    assert csv_response.status_code == 200
    assert csv_response.data == b"from_grid,to_grid\n9,10\n"


class _FakeAnomalyService:
    def __init__(self) -> None:
        self.summary_calls = 0
        self.analysis_calls = 0
        self.analysis_store = self
        self.runs = []

    def get_summary(self):
        self.summary_calls += 1
        return {
            "dataset": {
                "startDate": "2019-01-01",
                "endDate": "2019-12-31",
            }
        }

    def list_runs(self, limit=25):
        return self.runs[:limit]

    def get_run(self, run_id):
        return next(
            (run for run in self.runs if run["analysis_id"] == run_id), None
        )

    def get(self, run_id):
        return self.get_run(run_id)

    def run_analysis(self, request):
        self.analysis_calls += 1
        return {
            "run_id": "b" * 32,
            "status": "completed",
            "request": request,
            "metadata": {"customer_batch_count": 2},
            "metrics": {
                "selected_customer_count": 100,
                "anomaly_window_count": 3,
                "localized_event_count": 2,
                "anomaly_type_counts": {"spike": 2, "zero_block": 1},
                "event_scope_counts": {
                    "SINGLE_CUSTOMER": 1,
                    "MULTI_AREA": 1,
                },
            },
            "events": [],
            "anomaly_windows": [],
        }


class _TestMemory:
    def __init__(self) -> None:
        self.threads = {}

    def load(self, principal, conversation_id, persona):
        return list(self.threads.get((principal, conversation_id, persona), []))

    def append(
        self,
        principal,
        conversation_id,
        persona,
        user_text,
        assistant_text,
        **metadata,
    ):
        messages = self.load(principal, conversation_id, persona)
        messages.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
        self.threads[(principal, conversation_id, persona)] = messages[-40:]


def _trusted_test_identity(app, persona="household"):
    @app.before_request
    def set_test_identity():
        g.authenticated_user_id = "assistant-test-user"
        g.authenticated_persona = persona
        g.authenticated_customer_ids = [1001]


def _disable_assistant_external_services(monkeypatch, orchestrator):
    monkeypatch.setattr(
        orchestrator,
        "get_settings",
        lambda: SimpleNamespace(
            tavily_api_key=None,
            langsmith_tracing=False,
            langsmith_api_key=None,
        ),
    )
    from app.services import assistant_service

    monkeypatch.setattr(assistant_service, "ConversationMemory", _TestMemory)


def test_assistant_chat_answers_general_anomaly_question_without_date_guard(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.graph import graph_retriever
    from ai.anamoly.tools import web_search_tools

    _disable_assistant_external_services(monkeypatch, orchestrator)
    tavily_calls = []
    monkeypatch.setattr(
        orchestrator,
        "get_settings",
        lambda: SimpleNamespace(
            tavily_api_key="test-key",
            langsmith_tracing=False,
            langsmith_api_key=None,
        ),
    )
    monkeypatch.setattr(
        web_search_tools,
        "_tavily_search",
        lambda arguments, context: tavily_calls.append(arguments["query"]) or {"items": []},
    )
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service

    class FakeKnowledgeRetriever:
        def search(self, query, limit=5):
            return [
                {
                    "id": "flatline-guide",
                    "text": "A flatline is a sustained identical meter reading.",
                    "metadata": {"title": "Meter anomaly guide"},
                    "citation": {
                        "title": "Meter anomaly guide",
                        "sourceUrl": None,
                        "page": None,
                        "publisher": None,
                    },
                }
            ]

    monkeypatch.setattr(
        graph_retriever, "KnowledgeRetriever", FakeKnowledgeRetriever
    )
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: (
            "A flatline anomaly is a sustained identical or nearly identical "
            "consumption reading, possibly caused by a stuck meter or telemetry issue."
        ),
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "What does a flatline anomaly mean in an energy time series?",
            "persona": "household",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert "flatline anomaly" in body["answer"].lower()
    assert body["citations"][0]["title"] == "Meter anomaly guide"
    assert anomaly_service.summary_calls == 0
    assert tavily_calls == []


def test_assistant_sends_unclassified_general_questions_to_ollama_and_rag(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.graph import graph_retriever

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    monkeypatch.setattr(
        graph_retriever,
        "KnowledgeRetriever",
        lambda: type("EmptyRetriever", (), {"search": lambda self, query, limit=5: []})(),
    )
    model_questions = []
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: model_questions.append(messages[-1]["content"])
        or "I can help explain the service.",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={"prompt": "Can you help me understand this service?"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["answer"] == "I can help explain the service."
    assert model_questions
    assert anomaly_service.summary_calls == 0


def test_assistant_chat_routes_explicit_trained_model_request_to_inference(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.tools import web_search_tools

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")
    tavily_calls = []
    monkeypatch.setattr(
        orchestrator,
        "get_settings",
        lambda: SimpleNamespace(
            tavily_api_key="test-key",
            langsmith_tracing=False,
            langsmith_api_key=None,
        ),
    )
    monkeypatch.setattr(
        web_search_tools,
        "_tavily_search",
        lambda arguments, context: tavily_calls.append(arguments["query"]) or {"items": []},
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": (
                "Run the trained anomaly model for 1-Jan-2019 to 4-Jan-2019"
            ),
            "persona": "government",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert "Analysis for 2019-01-01 through 2019-01-04 is complete." in body["answer"]
    assert body["runReferences"] == ["b" * 32]
    assert anomaly_service.analysis_calls == 1
    assert tavily_calls == []


def test_assistant_event_classification_uses_saved_event_context(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    anomaly_service.runs = [
        {
            "analysis_id": "c" * 32,
            "status": "completed",
            "request": {
                "start_date": "2019-01-01",
                "end_date": "2019-01-04",
            },
            "events": [
                {
                    "event_id": "EVT_001",
                    "event_scope": "MULTI_AREA",
                    "dominant_anomaly_type": "zero_block",
                    "spatial_cluster_count": 2,
                }
            ],
        }
    ]
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")
    model_context = []
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: model_context.append(messages[-1]["content"])
        or "The saved event was classified as MULTI_AREA because it spans separate clusters.",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Why was event EVT_001 classified as MULTI_AREA?",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["runReferences"] == ["c" * 32]
    assert "MULTI_AREA" in model_context[0]
    assert "spatial_cluster_count" in model_context[0]


def test_current_guidance_uses_local_sources_and_tavily(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.vector_store import retriever
    from ai.anamoly.tools import web_search_tools

    _disable_assistant_external_services(monkeypatch, orchestrator)
    monkeypatch.setattr(
        orchestrator,
        "get_settings",
        lambda: SimpleNamespace(
            tavily_api_key="test-key",
            langsmith_tracing=False,
            langsmith_api_key=None,
        ),
    )
    monkeypatch.setattr(
        retriever,
        "KnowledgeRetriever",
        lambda: type(
            "KnowledgeRetriever",
            (),
            {
                "search": lambda self, query, limit=5: [
                    {
                        "id": "local-guideline",
                        "text": "Local outage safety note.",
                        "metadata": {"title": "Local safety note"},
                        "citation": {
                            "title": "Local safety note",
                            "sourceUrl": None,
                            "page": None,
                            "publisher": None,
                        },
                    }
                ]
            },
        )(),
    )
    tavily_calls = []
    monkeypatch.setattr(
        web_search_tools,
        "_tavily_search",
        lambda arguments, context: tavily_calls.append(arguments["query"])
        or {
            "source": "external_web",
            "items": [
                {
                    "title": "Current US safety guidance",
                    "url": "https://example.test/guidance",
                    "content": "Current public guidance.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: "Here is the latest guidance.",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Find the latest US electrical safety guidelines",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    assert tavily_calls == ["Find the latest US electrical safety guidelines"]
    titles = {citation["title"] for citation in response.get_json()["data"]["citations"]}
    assert titles == {"Local safety note", "Current US safety guidance"}


def test_assistant_chat_looks_up_seven_day_period_then_asks_before_new_analysis(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.graph import graph_retriever

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")
    monkeypatch.setattr(
        graph_retriever,
        "KnowledgeRetriever",
        lambda: type("EmptyRetriever", (), {"search": lambda self, query, limit=5: []})(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: "No saved events were found.",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Show anomalies from 03/04/2019 to 09/04/2019",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    answer = response.get_json()["data"]["answer"]
    assert "2019-04-03 through 2019-04-09" in answer
    assert "Would you like" in answer
    assert anomaly_service.analysis_calls == 0

    single_day = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Show anomalies on 15/04/2019",
            "persona": "government",
        },
    )
    assert single_day.status_code == 200
    assert "2019-04-15 through 2019-04-15" in single_day.get_json()["data"]["answer"]
    assert anomaly_service.analysis_calls == 0


def test_assistant_chat_reuses_completed_run_covering_requested_period(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.graph import graph_retriever

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    anomaly_service.runs = [
        {
            "analysis_id": "a" * 32,
            "status": "completed",
            "created_at": "2019-04-10T00:00:00",
            "request": {
                "start_date": "2019-04-03",
                "end_date": "2019-04-09",
                "customer_ids": [1001],
            },
            "events": [
                {
                    "event_id": "evt-1",
                    "event_start": "2019-04-05T10:00:00",
                    "event_end": "2019-04-05T11:00:00",
                    "customer_ids": [1001],
                    "event_scope": "localized",
                }
            ],
            "anomaly_windows": [],
        }
    ]
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")
    monkeypatch.setattr(
        graph_retriever,
        "KnowledgeRetriever",
        lambda: type("EmptyRetriever", (), {"search": lambda self, query, limit=5: []})(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: "The saved run contains one localized event.",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Show anomalies from 03/04/2019 to 09/04/2019",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["runReferences"] == ["a" * 32]
    assert "found 1 localized events" in body["answer"]
    assert "2019-04-03 through 2019-04-09" in body["answer"]
    assert "a" * 32 in body["answer"]
    assert anomaly_service.analysis_calls == 0


def test_assistant_natural_prediction_question_reuses_saved_run(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    anomaly_service.runs = [
        {
            "analysis_id": "d" * 32,
            "status": "completed",
            "created_at": "2026-11-04T08:18:48",
            "request": {
                "start_date": "2019-01-01",
                "end_date": "2019-01-04",
                "h3_resolution": 8,
                "spatial_radius_km": 5.0,
                "maximum_start_time_difference_minutes": 30,
                "minimum_temporal_overlap": 0.25,
                "maximum_interval_gap_minutes": 60,
            },
            "events": [
                {
                    "event_id": "EVT_000001",
                    "event_start": "2019-01-02T10:00:00",
                    "event_end": "2019-01-02T11:00:00",
                    "event_scope": "SINGLE_CUSTOMER",
                    "customer_ids": [1001],
                    "anomaly_type_distribution": {"spike": 1},
                }
            ],
            "anomaly_windows": [
                {
                    "event_id": "EVT_000001",
                    "anomaly_start": "2019-01-02T10:00:00",
                    "anomaly_type": "spike",
                    "customer_id": 1001,
                }
            ],
        }
    ]
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: (_ for _ in ()).throw(
            AssertionError("Saved historical results must not be sent to web/RAG.")
        ),
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "tell me about anamoly prediction between 1-jan-2019 to 4-jan-2019",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["runReferences"] == ["d" * 32]
    assert "2019-01-01 through 2019-01-04" in body["answer"]
    assert "1 localized events" in body["answer"]
    assert anomaly_service.analysis_calls == 0


def test_assistant_stream_allows_local_government_test_mode_without_auth(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator

    _disable_assistant_external_services(monkeypatch, orchestrator)
    app.config.update(
        DEBUG=True,
        TESTING=False,
        ASSISTANT_ALLOW_UNAUTHENTICATED_GOVERNMENT=True,
    )
    anomaly_service = _FakeAnomalyService()
    anomaly_service.runs = [
        {
            "analysis_id": "e" * 32,
            "status": "completed",
            "created_at": "2026-11-04T08:18:48",
            "request": {
                "start_date": "2019-01-01",
                "end_date": "2019-01-04",
                "h3_resolution": 8,
                "spatial_radius_km": 5.0,
                "maximum_start_time_difference_minutes": 30,
                "minimum_temporal_overlap": 0.25,
                "maximum_interval_gap_minutes": 60,
            },
            "events": [
                {
                    "event_id": "EVT_000001",
                    "event_start": "2019-01-02T10:00:00",
                    "event_end": "2019-01-02T11:00:00",
                    "event_scope": "SINGLE_CUSTOMER",
                    "customer_ids": [1001],
                    "anomaly_type_distribution": {"spike": 1},
                }
            ],
            "anomaly_windows": [],
        }
    ]
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: (_ for _ in ()).throw(
            AssertionError("Saved historical results must not use web/RAG.")
        ),
    )

    response = client.post(
        "/api/v1/assistant/chat/stream",
        json={
            "prompt": "Tell me about anomaly prediction between 1-Jan-2019 to 4-Jan-2019",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]
    completed = next(event for event in events if event["type"] == "complete")
    assert completed["data"]["runReferences"] == ["e" * 32]
    assert "2019-01-01 through 2019-01-04" in completed["data"]["answer"]
    assert anomaly_service.analysis_calls == 0


def test_assistant_local_test_mode_rejects_non_loopback_requests(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator

    _disable_assistant_external_services(monkeypatch, orchestrator)
    app.config.update(
        DEBUG=True,
        TESTING=False,
        ASSISTANT_ALLOW_UNAUTHENTICATED_GOVERNMENT=True,
    )
    app.extensions["assistant_service"].anomaly_service = _FakeAnomalyService()

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Tell me about anomaly prediction between 1-Jan-2019 to 4-Jan-2019",
            "persona": "government",
        },
        environ_base={"REMOTE_ADDR": "198.51.100.10"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ASSISTANT_FORBIDDEN"


def test_assistant_chat_runs_analysis_only_after_follow_up_confirmation(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator
    from ai.anamoly.graph import graph_retriever

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")
    monkeypatch.setattr(
        graph_retriever,
        "KnowledgeRetriever",
        lambda: type("EmptyRetriever", (), {"search": lambda self, query, limit=5: []})(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_ollama_chat",
        lambda messages, on_token=None: "The analysis has completed.",
    )

    first_response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Show anomalies from 03/04/2019 to 09/04/2019",
            "persona": "government",
            "conversation_id": "analysis-confirmation",
        },
    )
    assert first_response.status_code == 200
    assert "Would you like" in first_response.get_json()["data"]["answer"]
    assert anomaly_service.analysis_calls == 0

    confirmed_response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "yes",
            "persona": "government",
            "conversation_id": "analysis-confirmation",
        },
    )

    assert confirmed_response.status_code == 200
    assert confirmed_response.get_json()["data"]["runReferences"] == ["b" * 32]
    assert anomaly_service.analysis_calls == 1


def test_assistant_chat_returns_natural_analysis_summary_and_csv_link(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app, persona="government")

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "prompt": "Run analysis for 03/04/2019",
            "persona": "government",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert "Analysis for 2019-04-03 is complete." in body["answer"]
    assert "3 anomaly windows across 2 localized events" in body["answer"]
    assert "2 spike, 1 zero block" in body["answer"]
    assert "1 multi area, 1 single customer" in body["answer"]
    assert "processed in 2 batches" in body["answer"]
    assert body["downloads"][0]["url"].endswith("/download/events.csv")
    assert anomaly_service.analysis_calls == 1


def test_assistant_chat_rejects_long_out_of_range_and_relative_periods(
    app, client: FlaskClient, monkeypatch
):
    from ai.anamoly.agents import orchestrator, query_router
    from ai.anamoly.graph import graph_retriever

    _disable_assistant_external_services(monkeypatch, orchestrator)
    anomaly_service = _FakeAnomalyService()
    app.extensions["assistant_service"].anomaly_service = anomaly_service
    _trusted_test_identity(app)
    monkeypatch.setattr(
        graph_retriever,
        "KnowledgeRetriever",
        lambda: type("EmptyRetriever", (), {"search": lambda self, query, limit=5: []})(),
    )
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 4)

    monkeypatch.setattr(query_router, "date", FixedDate)

    for prompt, expected in (
        ("Analyse 01/04/2019 to 10/04/2019", "at most 7 days"),
        ("Show anomalies on 15/04/2020", "2019-01-01 through 2019-12-31"),
        ("What happened yesterday?", "2019-01-01 through 2019-12-31"),
    ):
        response = client.post(
            "/api/v1/assistant/chat",
            json={"prompt": prompt, "persona": "household"},
        )
        assert response.status_code == 200
        assert expected in response.get_json()["data"]["answer"]

    assert anomaly_service.analysis_calls == 0
