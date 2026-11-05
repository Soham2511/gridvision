"""Tests for the Ollama domain router without requiring a running Ollama server."""

from __future__ import annotations

import json
from importlib import import_module

from ai.govt import router
from ai.anamoly.agents.query_router import route_prompt


class _OllamaResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_route_query_uses_compact_prompt_and_prior_context(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _OllamaResponse(
            {
                "message": {
                    "content": json.dumps(
                        {"assistant": "government", "reason": "redistribution plan"}
                    )
                }
            }
        )

    monkeypatch.setattr(router.urllib.request, "urlopen", fake_urlopen)

    selected = router.route_query(
        "Show the plan for the next day",
        model="router-test",
        ollama_url="http://ollama.test",
        prior_context="user: Show the plan for 2018-09-24",
    )

    assert selected == router.AssistantRoute("government", "redistribution plan")
    payload = captured["payload"]
    assert isinstance(payload, dict)
    user_message = payload["messages"][1]["content"]
    assert "Show the plan for the next day" in user_message
    assert "2018-09-24" in user_message
    assert payload["options"]["num_ctx"] == 4096
    assert payload["options"]["num_predict"] == 128
    assert payload["think"] is False


def test_government_page_uses_fast_domain_default(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("A clear Government-page route should not call Ollama routing")

    monkeypatch.setattr(router.urllib.request, "urlopen", fail_if_called)

    assert router.route_query(
        "Show the next day's government demand",
        default_assistant="government",
    ) == router.AssistantRoute(
        "government", "The question explicitly asks about government-grid data."
    )
    assert router.route_query(
        "Analyze the latest voltage anomaly",
        default_assistant="government",
    ).assistant == "anomaly"
    assert router.route_query("Show the redistribution plan").assistant == "government"


def test_route_query_rejects_unknown_assistant(monkeypatch):
    monkeypatch.setattr(
        router.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _OllamaResponse(
            {"message": {"content": '{"assistant":"forecast","reason":"no"}'}}
        ),
    )

    try:
        router.route_query("question")
    except RuntimeError as exc:
        assert "invalid assistant route" in str(exc)
    else:
        raise AssertionError("Unknown assistant routes must be rejected")


def test_anomaly_run_request_is_classified_as_explicit_model_inference():
    selected = route_prompt("Run anomaly analysis for 2019-05-03")

    assert selected["intent"] == "analysis_execution"
    assert selected["start_date"] == "2019-05-03"
    assert selected["end_date"] == "2019-05-03"


def test_government_explanation_falls_back_when_model_includes_numbers():
    government_assistant = import_module(
        "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
    )

    class NumericExplanationModel:
        def complete(self, _messages, *, json_mode=False):
            assert json_mode
            return json.dumps(
                {
                    "overview": "Grid 9 sends energy to Grid 10.",
                    "limitations": "This is synthetic.",
                }
            )

    context = {
        "validated_request": {"intent": "plan"},
        "python_calculated_summary": {
            "remaining_surplus_total_kwh": 5.0,
            "unmet_demand_total_kwh": 3.0,
        },
        "largest_selected_transfer_examples": [{"from_grid": 9, "to_grid": 10}],
    }

    answer = government_assistant.generate_explanation(
        context,
        NumericExplanationModel(),
    )

    assert "some demand remains unmet" in answer
    assert "synthetic assumptions" in answer
    assert not any(character.isdigit() for character in answer)


def test_government_analysis_overview_keeps_verified_report_when_model_includes_numbers():
    government_assistant = import_module(
        "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
    )

    class NumericExplanationModel:
        def complete(self, _messages, *, json_mode=False):
            assert json_mode
            return json.dumps(
                {
                    "overview": "Grid 9 had a demand of 20 units.",
                    "limitations": "Observed on 24 March.",
                }
            )

    answer = government_assistant._generate_analysis_overview(
        "Show redistribution plan", {"verified": True}, NumericExplanationModel()
    )

    assert "verified analysis results are summarized below" in answer
    assert "exact figures" in answer


def test_dmy_redistribution_image_request_uses_selected_day_plan():
    government_assistant = import_module(
        "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
    )
    request = government_assistant.QueryRequest(
        intent="historical_analysis",
        forecast_date=None,
        start_timestamp=None,
        duration_hours=None,
        grid_ids=[],
        output_formats=["text"],
        needs_clarification=False,
        clarification_question=None,
    )

    grounded = government_assistant._ground_explicit_query_details(
        "give me energy redistribution plan image for 24-09-2018", request
    )

    assert grounded.intent == "summary"
    assert grounded.forecast_date == "2018-09-24"
    assert grounded.duration_hours == 24
    assert grounded.output_formats == ["image"]
