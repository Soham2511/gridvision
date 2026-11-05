"""Tests for Groq Commercial planner configuration and strict JSON output."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError
from pydantic import ValidationError

import ai.commercial.agents.planner as planner_module
from ai.commercial.agents.planner import (
    GroqPlanner,
    GroqPlannerError,
    PlannerSelection,
)
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.graph import build_commercial_graph
from ai.commercial.schemas.communication import (
    CommercialConversationMessage,
    EvidenceRef,
)


def _planner(key_file: Path) -> GroqPlanner:
    return GroqPlanner(
        api_key_file=key_file,
        base_url="https://api.groq.com/openai/v1/",
        model="openai/gpt-oss-20b",
        timeout_seconds=5,
    )


def _mock_groq(
    monkeypatch: pytest.MonkeyPatch,
    content: str | None = None,
    *,
    error: Exception | None = None,
) -> tuple[list[dict], list[dict]]:
    client_options: list[dict] = []
    requests: list[dict] = []

    class FakeGroq:
        def __init__(self, **kwargs) -> None:
            client_options.append(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def __enter__(self) -> FakeGroq:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def _create(self, **kwargs):
            requests.append(kwargs)
            if error is not None:
                raise error
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=content)
                    )
                ]
            )

    monkeypatch.setattr(planner_module, "Groq", FakeGroq)
    return client_options, requests


def _status_error(
    status_code: int,
    body: str | dict,
    *,
    content_type: str = "application/json",
    request_id: str | None = None,
) -> APIStatusError:
    headers = {"Content-Type": content_type}
    if request_id:
        headers["x-request-id"] = request_id
    response = httpx.Response(
        status_code,
        headers=headers,
        json=body if isinstance(body, dict) else None,
        content=body if isinstance(body, str) else None,
        request=httpx.Request(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
        ),
    )
    return APIStatusError("Groq request failed", response=response, body=body)


def test_groq_planner_uses_sdk_and_validates_strict_json_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key\n", encoding="utf-8")
    client_options, requests = _mock_groq(
        monkeypatch,
        '{"specialists":["operations"]}',
    )
    planner = _planner(key_file)
    history = [
        CommercialConversationMessage(
            role="user",
            content="What production constraints are in the handbook?",
        ),
        CommercialConversationMessage(
            role="assistant",
            content="The handbook describes maintenance windows.",
        ),
    ]

    assert planner.select_specialists(
        "What about those?",
        history,
    ) == ["operations"]
    assert planner.endpoint_url == (
        "https://api.groq.com/openai/v1/chat/completions"
    )

    assert client_options == [
        {
            "api_key": "test-groq-key",
            "base_url": "https://api.groq.com",
            "timeout": 5,
            "max_retries": 0,
            "default_headers": {"User-Agent": "gridvision-commercial/1.0"},
        }
    ]
    payload = requests[0]
    schema_config = payload["response_format"]["json_schema"]
    specialist_schema = schema_config["schema"]["properties"]["specialists"]
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["max_completion_tokens"] == 256
    assert schema_config["strict"] is True
    assert schema_config["schema"]["additionalProperties"] is False
    assert "minItems" not in specialist_schema
    assert "maxItems" not in specialist_schema
    system_prompt = payload["messages"][0]["content"]
    assert "peak_prediction" in system_prompt
    assert "operations" in system_prompt
    assert "renewable" in system_prompt
    assert "cost_optimization" in system_prompt
    assert "Require an explicit supported Commercial `building_id`" in system_prompt
    user_content = json.loads(payload["messages"][1]["content"])
    assert user_content["current_goal"] == "What about those?"
    assert user_content["recent_conversation"] == [
        message.model_dump(mode="json") for message in history
    ]
    assert "api_key" not in payload


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not-json",
        '{"specialists":["unknown_agent"]}',
        '{"specialists":["operations"],"tool":"write_to_factory"}',
        '{"specialists":[]}',
    ],
)
def test_groq_planner_rejects_empty_or_invalid_response(
    content: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key", encoding="utf-8")
    _mock_groq(monkeypatch, content)

    with pytest.raises(ValueError):
        _planner(key_file).select_specialists("Check factory operations.")


def test_groq_planner_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key", encoding="utf-8")
    _mock_groq(
        monkeypatch,
        "x" * (GroqPlanner.MAX_RESPONSE_CHARACTERS + 1),
    )

    with pytest.raises(ValueError, match="output limit"):
        _planner(key_file).select_specialists("Check factory operations.")


def test_groq_planner_fails_explicitly_when_key_file_is_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="API key file does not exist"):
        _planner(tmp_path / "missing.key").select_specialists(
            "Inspect a machine."
        )


def test_groq_planner_includes_sanitized_sdk_error_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key", encoding="utf-8")
    _mock_groq(
        monkeypatch,
        error=_status_error(
            403,
            {
                "error": {
                    "message": "Project is not authorized to use this model.",
                    "code": "model_access_denied",
                }
            },
            request_id="req-test-403",
        ),
    )

    with pytest.raises(GroqPlannerError, match="HTTP 403") as error:
        _planner(key_file).select_specialists("Inspect a machine.")

    assert "model_access_denied" in str(error.value)
    assert "not authorized to use this model" in str(error.value)
    assert "request-id=req-test-403" in str(error.value)
    assert "test-groq-key" not in str(error.value)


def test_groq_planner_redacts_plain_text_gateway_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key", encoding="utf-8")
    _mock_groq(
        monkeypatch,
        error=_status_error(
            403,
            "Access denied for test-groq-key by gateway policy.",
            content_type="text/plain; charset=UTF-8",
        ),
    )

    with pytest.raises(GroqPlannerError, match="HTTP 403") as error:
        _planner(key_file).select_specialists("Inspect a machine.")

    diagnostic = str(error.value)
    assert "Access denied" in diagnostic
    assert "gateway policy" in diagnostic
    assert "test-groq-key" not in diagnostic
    assert "[redacted]" in diagnostic


def test_groq_planner_synthesizes_cited_answer_from_tool_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key", encoding="utf-8")
    client_options, requests = _mock_groq(
        monkeypatch,
        json.dumps(
            {
                "answer": (
                    "Energy measures consumption over time, while demand "
                    "measures the rate of use [1]."
                )
            }
        ),
    )
    reference = EvidenceRef(
        source_id="energy-handbook.pdf",
        source_type="uploaded_document",
        locator="page:1;section:Electricity costs",
        excerpt=(
            "Energy (kWh) measures electricity consumed over time. Demand "
            "(kW) measures the rate of electricity use."
        ),
        synthetic=True,
    )

    answer, answer_refs = _planner(key_file).synthesize_answer(
        question="Explain the difference between energy and demand.",
        conversation_history=[],
        specialist_results=[
            {
                "specialist": "operations",
                "status": "completed",
                "findings": [],
                "data": {},
            }
        ],
        evidence_refs=[reference],
        assumptions=[],
        conflicts=[],
        status="passed",
    )

    assert answer == (
        "Energy measures consumption over time, while demand measures the "
        "rate of use [1]."
    )
    assert answer_refs == [reference]
    assert client_options[0]["default_headers"] == {
        "User-Agent": "gridvision-commercial/1.0"
    }
    request = requests[0]
    assert request["response_format"]["json_schema"]["strict"] is True
    answer_context = json.loads(request["messages"][1]["content"])
    assert answer_context["question"] == (
        "Explain the difference between energy and demand."
    )
    assert answer_context["sources"][0]["citation"] == 1
    assert answer_context["sources"][0]["excerpt"] == reference.excerpt


def test_groq_planner_rejects_answer_with_unknown_citation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api.key"
    key_file.write_text("test-groq-key", encoding="utf-8")
    _mock_groq(monkeypatch, '{"answer":"Unsupported citation [2]."}')
    reference = EvidenceRef(
        source_id="energy-handbook.pdf",
        source_type="uploaded_document",
        locator="page:1",
        excerpt="A documented fact.",
        synthetic=True,
    )

    from ai.commercial.agents.planner import GroqAnswerError

    with pytest.raises(GroqAnswerError, match="citation"):
        _planner(key_file).synthesize_answer(
            question="What is documented?",
            conversation_history=[],
            specialist_results=[],
            evidence_refs=[reference],
            assumptions=[],
            conflicts=[],
            status="passed",
        )


def test_environment_defaults_to_groq_with_configured_key_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMMERCIAL_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("COMMERCIAL_GROQ_API_KEY_FILE", raising=False)
    monkeypatch.delenv("COMMERCIAL_GROQ_MODEL", raising=False)

    settings = CommercialSettings.from_env()

    assert settings.llm_provider == "groq"
    assert settings.groq_api_key_file == (
        CommercialSettings.model_fields["groq_api_key_file"].default
    )
    assert settings.groq_model == "openai/gpt-oss-20b"
    assert settings.groq_timeout_seconds == 60


def test_environment_uses_configured_groq_model_and_key_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "custom-groq.key"
    monkeypatch.setenv("COMMERCIAL_LLM_PROVIDER", "groq")
    monkeypatch.setenv("COMMERCIAL_GROQ_API_KEY_FILE", str(key_file))
    monkeypatch.setenv("COMMERCIAL_GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("COMMERCIAL_GROQ_TIMEOUT_SECONDS", "42")

    settings = CommercialSettings.from_env()

    assert settings.groq_api_key_file == key_file
    assert settings.groq_model == "openai/gpt-oss-20b"
    assert settings.groq_timeout_seconds == 42


def test_commercial_settings_reject_ollama_provider() -> None:
    with pytest.raises(ValidationError):
        CommercialSettings(llm_provider="ollama")


def test_groq_workflow_uses_configured_planner_and_tracks_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import ai.commercial.graph as graph_module

    settings = CommercialSettings(
        llm_provider="groq",
        groq_api_key_file=tmp_path / "groq.key",
    )

    class FakePlanner:
        def __init__(self, **kwargs) -> None:
            assert kwargs == {
                "api_key_file": tmp_path / "groq.key",
                "base_url": "https://api.groq.com",
                "model": "openai/gpt-oss-20b",
                "timeout_seconds": 60.0,
            }

        def select_specialists(
            self,
            goal: str,
            conversation_history=None,
        ) -> list[str]:
            assert goal == "What does the handbook say about production constraints?"
            assert conversation_history == []
            return ["operations"]

        def synthesize_answer(self, **kwargs):
            return "A grounded operations answer [1].", kwargs["evidence_refs"]

    monkeypatch.setattr(graph_module, "GroqPlanner", FakePlanner)
    result = build_commercial_graph(settings=settings).invoke(
        {
            "request_id": "groq-planner-test",
            "factory_id": "factory-test",
            "user_goal": "What does the handbook say about production constraints?",
        }
    )

    assert result["llm_call_count"] == 2
    assert [item.specialist for item in result["assignments"]] == ["operations"]


def test_groq_planning_failure_is_reported_without_mock_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai.commercial.graph as graph_module

    class FailedPlanner:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def select_specialists(
            self,
            goal: str,
            conversation_history=None,
        ) -> list[str]:
            del goal
            del conversation_history
            raise TimeoutError("test-only failure")

    monkeypatch.setattr(graph_module, "GroqPlanner", FailedPlanner)
    result = build_commercial_graph(
        settings=CommercialSettings(llm_provider="groq")
    ).invoke(
        {
            "request_id": "groq-failure-test",
            "factory_id": "factory-test",
            "user_goal": "explain the facility",
        }
    )

    assert result["llm_call_count"] == 1
    assert result["tool_call_count"] == 0
    assert result["assignments"] == []
    assert result["errors"] == ["GROQ_PLANNING_FAILED: TimeoutError"]
    supervisor_trace = next(
        event
        for event in result["execution_trace"]
        if event["node_id"] == "supervisor"
    )
    assert supervisor_trace["message"] == "GROQ_PLANNING_FAILED: TimeoutError"


def test_groq_planner_safe_diagnostic_is_visible_in_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai.commercial.graph as graph_module

    class FailedPlanner:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def select_specialists(
            self,
            goal: str,
            conversation_history=None,
        ) -> list[str]:
            del goal, conversation_history
            raise GroqPlannerError(
                "Groq returned HTTP 401 for model 'openai/gpt-oss-20b'."
            )

    monkeypatch.setattr(graph_module, "GroqPlanner", FailedPlanner)
    result = build_commercial_graph(
        settings=CommercialSettings(llm_provider="groq")
    ).invoke(
        {
            "request_id": "groq-diagnostic-test",
            "factory_id": "factory-test",
            "user_goal": "explain the facility",
        }
    )

    expected_error = (
        "GROQ_PLANNING_FAILED: GroqPlannerError: "
        "Groq returned HTTP 401 for model 'openai/gpt-oss-20b'."
    )
    assert result["errors"] == [expected_error]
    supervisor_trace = next(
        event
        for event in result["execution_trace"]
        if event["node_id"] == "supervisor"
    )
    assert supervisor_trace["message"] == expected_error


def test_planner_contract_rejects_malformed_specialist_types() -> None:
    with pytest.raises(ValidationError):
        PlannerSelection.model_validate({"specialists": ["peak", "operations"]})
