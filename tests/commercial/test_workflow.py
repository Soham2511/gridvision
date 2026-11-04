"""Focused tests for the Commercial LangGraph skeleton."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.graph import WorkflowExecutionError, build_commercial_graph
from ai.commercial.schemas.communication import (
    AgentError,
    TaskAssignment,
    ToolObservation,
)
from ai.commercial.tools.mock_tools import MockCommercialTools, synthetic_fixture
from ai.commercial.agents.operations import run_operations


def _request(goal: str) -> dict[str, object]:
    return {
        "request_id": "test-request",
        "factory_id": "test-factory",
        "user_goal": goal,
    }


def _invoke(goal: str, tools: MockCommercialTools | None = None) -> dict:
    graph = build_commercial_graph(tools=tools)
    return graph.invoke(_request(goal))


def test_missing_document_evidence_does_not_invent_data_or_savings() -> None:
    result = _invoke("ZQX991 quantum chronometer unobtanium")

    assert result["validation_status"].status == "incomplete"
    assert result["tool_call_count"] == 1
    assert result["final_response"]["findings"] == []
    assert (
        "No unsupported numeric results or savings"
        in result["final_response"]["summary"]
    )
    operation_result = next(iter(result["specialist_results"].values()))
    assert operation_result.status == "unavailable"
    assert operation_result.error.code == "DATA_NOT_AVAILABLE"
    assert operation_result.data["query"]["search_text"] == (
        "ZQX991 quantum chronometer unobtanium"
    )
    assert operation_result.data["query"]["topics"] == []


def test_greeting_returns_helpful_response_without_running_specialists() -> None:
    result = _invoke("hii")

    assert result["final_response"]["status"] == "passed"
    assert "uploaded documents" in result["final_response"]["summary"]
    assert result["assignments"] == []
    assert result["tool_call_count"] == 0
    assert result["final_response"]["evidence_refs"] == []
    assert [event["node_id"] for event in result["execution_trace"]] == [
        "validate_request",
        "supervisor",
        "greeting",
    ]
    assert all(
        event["status"] == "completed"
        and event["duration_ms"] >= 0
        for event in result["execution_trace"]
    )


def test_graph_failure_preserves_completed_steps_and_failed_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai.commercial.graph as graph_module

    def fail_operations(*_args, **_kwargs):
        raise TimeoutError("private backend detail")

    monkeypatch.setattr(graph_module, "run_operations", fail_operations)
    graph = build_commercial_graph(tools=MockCommercialTools())

    with pytest.raises(WorkflowExecutionError) as error:
        graph.invoke(_request("What does the handbook say about motors?"))

    assert error.value.failed_node == "operations"
    assert error.value.error_type == "TimeoutError"
    assert "private backend detail" not in str(error.value)
    assert error.value.execution_trace[-1]["node_id"] == "operations"
    assert error.value.execution_trace[-1]["status"] == "error"
    assert any(
        event["node_id"] == "supervisor"
        for event in error.value.execution_trace
    )


def test_supervisor_routes_independent_specialists_and_optimizer() -> None:
    result = _invoke(
        "Optimize the factory production schedule using peak demand, "
        "machine constraints, solar, and battery storage."
    )

    selected = {assignment.specialist for assignment in result["assignments"]}
    assert selected == {
        "peak_prediction",
        "operations",
        "renewable",
        "cost_optimization",
    }
    assert result["tool_call_count"] == 3
    assert result["optimization_input"] == {}
    assert (
        result["optimization_result"].error.code
        == "OPTIMIZATION_INPUT_UNAVAILABLE"
    )
    assert result["validation_status"].status == "incomplete"
    assert result["final_response"]["status"] == "incomplete"


def test_optimizer_receives_only_explicit_user_supplied_schedule() -> None:
    fixtures = {
        specialist: synthetic_fixture(
            source_id=f"fixture:{specialist}",
            finding=f"Synthetic test fixture for {specialist}.",
        )
        for specialist in (
            "peak_prediction",
            "operations",
            "renewable",
            "cost_optimization",
        )
    }

    class CapturingTools(MockCommercialTools):
        def __init__(self) -> None:
            super().__init__(fixtures)
            self.optimization_inputs: dict | None = None

        def optimize(
            self, factory_id: str | None, inputs: dict
        ) -> ToolObservation:
            del factory_id
            self.optimization_inputs = inputs
            return self._observation("cost_optimization")

    tools = CapturingTools()
    request = _request(
        "Optimize the factory schedule using peak demand, machine constraints, "
        "solar, and battery."
    )
    request["optimization_inputs"] = {
        "horizon_hours": 2,
        "prices_inr_per_kwh": [10, 2],
        "jobs": [
            {
                "job_id": "job-1",
                "machine_id": "line-1",
                "power_kw": 5,
                "duration_hours": 1,
                "deadline_hour": 2,
            }
        ],
    }
    result = build_commercial_graph(tools=tools).invoke(request)

    assert tools.optimization_inputs is not None
    assert tools.optimization_inputs["horizon_hours"] == 2
    assert tuple(tools.optimization_inputs["prices_inr_per_kwh"]) == (10, 2)
    assert result["tool_call_count"] == 4
    assert result["validation_status"].status == "passed"
    assert all(
        reference["synthetic"]
        for reference in result["final_response"]["evidence_refs"]
    )


def test_unrelated_machine_question_does_not_run_attached_schedule() -> None:
    request = _request(
        "How many machines are working according to the uploaded document?"
    )
    request["optimization_inputs"] = {
        "horizon_hours": 1,
        "prices_inr_per_kwh": [10],
        "jobs": [
            {
                "job_id": "job-1",
                "machine_id": "press-1",
                "power_kw": 5,
                "duration_hours": 1,
                "deadline_hour": 1,
            }
        ],
    }

    result = build_commercial_graph(tools=MockCommercialTools()).invoke(request)

    assert {
        assignment.specialist for assignment in result["assignments"]
    } == {"operations"}
    assert result.get("optimization_result") is None
    assert result["tool_call_count"] == 1


def test_explicit_synthetic_fixture_is_cited_and_labeled() -> None:
    tools = MockCommercialTools(
        {
            "renewable": synthetic_fixture(
                source_id="fixture:renewables:1",
                finding="Synthetic test fixture: scenario input is available.",
                data={"scenario_name": "test-only"},
            )
        }
    )
    result = _invoke("Compare a solar renewable scenario.", tools)

    assert result["validation_status"].status == "passed"
    assert result["final_response"]["findings"] == [
        "Synthetic test fixture: scenario input is available."
    ]
    assert result["final_response"]["evidence_refs"][0]["synthetic"] is True
    assert result["final_response"]["evidence_refs"][0]["source_id"] == (
        "fixture:renewables:1"
    )


def test_peak_specialist_receives_explicit_commercial_building_id() -> None:
    class CapturingPeakTools(MockCommercialTools):
        def __init__(self) -> None:
            super().__init__(
                {
                    "peak_prediction": synthetic_fixture(
                        source_id="fixture:peak",
                        finding="Synthetic test fixture: peak forecast available.",
                    )
                }
            )
            self.building_id: str | None = None

        def get_peak_forecast(
            self,
            factory_id: str | None,
            goal: str,
            building_id: str | None = None,
        ) -> ToolObservation:
            del factory_id, goal
            self.building_id = building_id
            return self._observation("peak_prediction")

    tools = CapturingPeakTools()
    request = {
        **_request("Forecast peak demand for this building."),
        "building_id": "101",
    }

    result = build_commercial_graph(tools=tools).invoke(request)

    assert tools.building_id == "101"
    assert result["final_response"]["status"] == "passed"
    assert result["specialist_results"]["test-request:peak_prediction"].status == (
        "completed"
    )


def test_rework_is_bounded_and_retries_only_the_failed_specialist() -> None:
    class RetryOnceTools(MockCommercialTools):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def retrieve_operational_context(
            self, factory_id: str | None, goal: str
        ) -> ToolObservation:
            del factory_id, goal
            self.calls += 1
            if self.calls == 1:
                return ToolObservation(
                    status="failed",
                    error=AgentError(
                        code="TEMPORARY_FAILURE",
                        message="Temporary test failure.",
                        retryable=True,
                    ),
                )
            return synthetic_fixture(
                source_id="fixture:operations:retry",
                finding="Synthetic test fixture: operational record recovered.",
            )

    tools = RetryOnceTools()
    result = _invoke("Inspect the factory machine maintenance records.", tools)

    assert tools.calls == 2
    assert result["rework_count"] == 1
    assert result["tool_call_count"] == 2
    assert result["validation_status"].status == "passed"
    assert (
        result["specialist_results"]["test-request:operations"].status
        == "completed"
    )


def test_plan_exceeding_tool_budget_escalates_without_calls() -> None:
    settings = CommercialSettings(
        max_graph_steps=16,
        max_tool_calls=2,
        max_rework_attempts=1,
    )
    graph = build_commercial_graph(settings=settings)
    result = graph.invoke(
        _request(
            "Optimize the factory schedule using peak demand, production "
            "constraints, solar, and battery."
        ),
        config={"recursion_limit": settings.max_graph_steps},
    )

    assert result["tool_call_count"] == 0
    assert result["assignments"] == []
    assert result["validation_status"].status == "escalated"
    assert result["final_response"]["errors"][0].startswith(
        "PLAN_EXCEEDS_TOOL_BUDGET:"
    )


def test_invalid_request_is_rejected() -> None:
    graph = build_commercial_graph()

    with pytest.raises(ValidationError, match="user_goal"):
        graph.invoke({"request_id": "missing-goal"})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        graph.invoke(
            {
                **_request("Check factory operations."),
                "assignments": [],
            }
        )


def test_agent_cannot_call_tool_outside_assignment_allowlist() -> None:
    assignment = TaskAssignment(
        task_id="restricted-task",
        specialist="operations",
        goal="Read maintenance context.",
        scope="test factory",
        allowed_tools=(),
        expected_output="Operational evidence",
    )

    with pytest.raises(PermissionError, match="not allowed"):
        run_operations(
            {
                "assignments": [assignment],
                "factory_id": "test-factory",
            },
            MockCommercialTools(),
        )
