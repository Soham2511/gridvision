"""Tests for local Ollama planner configuration and strict JSON output."""

from __future__ import annotations

import json
from io import BytesIO
from urllib.error import URLError

import pytest
from pydantic import ValidationError

from ai.commercial.agents.planner import OllamaPlanner, PlannerSelection
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.graph import build_commercial_graph


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content.encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.content if size < 0 else self.content[:size]


def _envelope(content: str) -> str:
    return json.dumps({"message": {"content": content}})


def _planner() -> OllamaPlanner:
    return OllamaPlanner(
        base_url="http://localhost:11434/",
        primary_model="qwen3:8b",
        fallback_model="gemma3:4b",
        timeout_seconds=5,
    )


def test_ollama_planner_posts_json_schema_and_validates_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(_envelope('{"specialists":["operations"]}'))

    monkeypatch.setattr("ai.commercial.agents.planner.urlopen", fake_urlopen)

    assert _planner().select_specialists("Inspect a machine.") == ["operations"]

    request, timeout = requests[0]
    payload = json.loads(request.data)
    assert request.full_url == "http://localhost:11434/api/chat"
    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["format"] == PlannerSelection.model_json_schema()
    assert payload["options"]["temperature"] == 0
    assert timeout == 5


def test_ollama_planner_uses_gemma_when_qwen_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models: list[str] = []

    def fake_urlopen(request, timeout):
        del timeout
        payload = json.loads(request.data)
        models.append(payload["model"])
        if payload["model"] == "qwen3:8b":
            raise URLError("primary model unavailable")
        return FakeResponse(_envelope('{"specialists":["renewable"]}'))

    monkeypatch.setattr("ai.commercial.agents.planner.urlopen", fake_urlopen)

    assert _planner().select_specialists("Estimate rooftop solar.") == ["renewable"]
    assert models == ["qwen3:8b", "gemma3:4b"]


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
def test_ollama_planner_rejects_empty_or_invalid_response(
    content: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai.commercial.agents.planner.urlopen",
        lambda *_args, **_kwargs: FakeResponse(_envelope(content)),
    )

    with pytest.raises(ValueError, match="Ollama planning failed"):
        _planner().select_specialists("Check factory operations.")


def test_ollama_planner_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = _envelope("x" * (OllamaPlanner.MAX_RESPONSE_CHARACTERS + 1))
    monkeypatch.setattr(
        "ai.commercial.agents.planner.urlopen",
        lambda *_args, **_kwargs: FakeResponse(oversized),
    )

    with pytest.raises(ValueError, match="Ollama planning failed"):
        _planner().select_specialists("Check factory operations.")


def test_ollama_mode_does_not_require_api_credentials() -> None:
    settings = CommercialSettings(
        llm_provider="ollama",
        ollama_base_url="http://ollama:11434",
    )

    assert settings.ollama_base_url == "http://ollama:11434"
    assert settings.ollama_primary_model == "qwen3:8b"
    assert settings.ollama_fallback_model == "gemma3:4b"


def test_environment_defaults_to_local_ollama_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMMERCIAL_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("COMMERCIAL_OLLAMA_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("COMMERCIAL_OLLAMA_FALLBACK_MODEL", raising=False)

    settings = CommercialSettings.from_env()

    assert settings.llm_provider == "ollama"
    assert settings.ollama_primary_model == "qwen3:8b"
    assert settings.ollama_fallback_model == "gemma3:4b"

    monkeypatch.setenv("COMMERCIAL_LLM_PROVIDER", "auto")
    assert CommercialSettings.from_env().llm_provider == "ollama"
    monkeypatch.setenv("COMMERCIAL_LLM_PROVIDER", "groq")
    assert CommercialSettings.from_env().llm_provider == "ollama"


def test_ollama_workflow_uses_configured_planner_and_tracks_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai.commercial.graph as graph_module

    settings = CommercialSettings(
        llm_provider="ollama",
        ollama_base_url="http://ollama:11434",
    )

    class FakePlanner:
        def __init__(self, **kwargs) -> None:
            assert kwargs == {
                "base_url": "http://ollama:11434",
                "primary_model": "qwen3:8b",
                "fallback_model": "gemma3:4b",
                "timeout_seconds": 180.0,
            }

        def select_specialists(self, goal: str) -> list[str]:
            assert goal == "What does the handbook say about production constraints?"
            return ["operations"]

    monkeypatch.setattr(graph_module, "OllamaPlanner", FakePlanner)
    workflow = build_commercial_graph(settings=settings)
    result = workflow.invoke(
        {
            "request_id": "ollama-planner-test",
            "factory_id": "factory-test",
            "user_goal": "What does the handbook say about production constraints?",
        }
    )

    assert result["llm_call_count"] == 1
    assert [item.specialist for item in result["assignments"]] == ["operations"]
    assert result["validation_status"].status == "passed"


def test_ollama_planning_failure_escalates_without_mock_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai.commercial.graph as graph_module

    settings = CommercialSettings(llm_provider="ollama")

    class FailedPlanner:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def select_specialists(self, goal: str) -> list[str]:
            del goal
            raise TimeoutError("test-only failure")

    monkeypatch.setattr(graph_module, "OllamaPlanner", FailedPlanner)
    workflow = build_commercial_graph(settings=settings)
    result = workflow.invoke(
        {
            "request_id": "ollama-failure-test",
            "factory_id": "factory-test",
            "user_goal": "explain the facility",
        }
    )

    assert result["llm_call_count"] == 1
    assert result["tool_call_count"] == 0
    assert result["assignments"] == []
    assert result["validation_status"].status == "escalated"
    assert result["errors"] == ["OLLAMA_PLANNING_FAILED: TimeoutError"]
    assert "test-only failure" not in str(result["final_response"])
    supervisor_trace = next(
        event
        for event in result["execution_trace"]
        if event["node_id"] == "supervisor"
    )
    assert supervisor_trace["status"] == "error"
    assert supervisor_trace["message"] == "OLLAMA_PLANNING_FAILED: TimeoutError"


def test_planner_contract_rejects_malformed_specialist_types() -> None:
    with pytest.raises(ValidationError):
        PlannerSelection.model_validate({"specialists": ["peak", "operations"]})
