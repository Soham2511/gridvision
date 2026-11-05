"""Tests for the Commercial terminal chat entry point."""

from __future__ import annotations

from pathlib import Path

from ai.commercial.cli import check_groq_connection, run_chat
from ai.commercial.graph import WorkflowExecutionError


def test_terminal_chat_prints_response_and_execution_trace(
    monkeypatch,
    capsys,
) -> None:
    class Workflow:
        def invoke(self, request: dict) -> dict:
            assert request["factory_id"] == "automotive-parts-demo"
            assert request["user_goal"] == "How can I reduce air leaks?"
            return {
                "final_response": {
                    "summary": "Analysis completed.",
                    "findings": ["Inspect compressed-air connections."],
                    "errors": [],
                },
                "execution_trace": [
                    {
                        "node_id": "operations",
                        "status": "completed",
                        "duration_ms": 3.5,
                    }
                ],
            }

    prompts = iter(["How can I reduce air leaks?", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))

    run_chat(Workflow())

    output = capsys.readouterr()
    assert "Assistant: Analysis completed." in output.out
    assert "Inspect compressed-air connections." in output.out
    assert "Working... Press Ctrl+C to cancel" in output.err
    assert "operations: completed (3.5 ms)" in output.err


def test_terminal_chat_keeps_last_four_successful_exchanges(
    monkeypatch,
) -> None:
    requests: list[dict] = []

    class Workflow:
        def invoke(self, request: dict) -> dict:
            requests.append(request)
            return {
                "final_response": {
                    "summary": f"Response to {request['user_goal']}.",
                    "findings": [],
                    "errors": [],
                },
                "execution_trace": [],
            }

    prompts = iter([f"Question {index}" for index in range(5)] + ["quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))

    run_chat(Workflow())

    assert [len(request["conversation_history"]) for request in requests] == [
        0,
        2,
        4,
        6,
        8,
    ]
    assert requests[-1]["conversation_history"][0].content == "Question 0"
    assert requests[-1]["conversation_history"][-1].content == (
        "Response to Question 3."
    )


def test_groq_connection_check_sends_one_planner_request_and_hides_key(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    from ai.commercial.config.settings import CommercialSettings

    key_file = tmp_path / "groq.key"
    key_file.write_text("secret-test-key", encoding="utf-8")
    calls: list[tuple[str, str, float]] = []

    class Planner:
        endpoint_url = "https://api.groq.com/openai/v1/chat/completions"

        def __init__(self, *, api_key_file, base_url, model, timeout_seconds):
            calls.append((str(api_key_file), base_url, timeout_seconds))
            assert model == "openai/gpt-oss-20b"

        def select_specialists(self, goal: str, conversation_history=None):
            assert goal == "Which specialist handles factory maintenance documents?"
            assert conversation_history is None
            return ["operations"]

    monkeypatch.setattr("ai.commercial.cli.GroqPlanner", Planner)
    settings = CommercialSettings(
        llm_provider="groq",
        groq_api_key_file=key_file,
    )

    assert check_groq_connection(settings) == 0
    output = capsys.readouterr()

    assert len(calls) == 1
    assert "Groq connection check passed." in output.out
    assert "Groq endpoint: https://api.groq.com/openai/v1/chat/completions" in output.out
    assert "operations" in output.out
    assert str(key_file) in output.out
    assert "secret-test-key" not in output.out
    assert output.err == ""


def test_groq_connection_check_reports_safe_provider_error(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    from ai.commercial.agents.planner import GroqPlannerError
    from ai.commercial.config.settings import CommercialSettings

    key_file = tmp_path / "groq.key"
    key_file.write_text("secret-test-key", encoding="utf-8")

    class Planner:
        endpoint_url = "https://api.groq.com/openai/v1/chat/completions"

        def __init__(self, **_kwargs):
            pass

        def select_specialists(self, _goal: str, conversation_history=None):
            raise GroqPlannerError(
                "Groq returned HTTP 403. Provider detail: model access denied."
            )

    monkeypatch.setattr("ai.commercial.cli.GroqPlanner", Planner)
    settings = CommercialSettings(
        llm_provider="groq",
        groq_api_key_file=key_file,
    )

    assert check_groq_connection(settings) == 1
    output = capsys.readouterr()

    assert "HTTP 403" in output.err
    assert "model access denied" in output.err
    assert "secret-test-key" not in output.out + output.err


def test_terminal_chat_shows_workflow_failure_and_continues(
    monkeypatch,
    capsys,
) -> None:
    class Workflow:
        def invoke(self, _request: dict) -> dict:
            raise WorkflowExecutionError(
                failed_node="operations",
                error_type="TimeoutError",
                execution_trace=[
                    {
                        "node_id": "operations",
                        "status": "error",
                        "duration_ms": 8.0,
                        "message": "Node failed with TimeoutError.",
                    }
                ],
            )

    prompts = iter(["Check the handbook.", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))

    run_chat(Workflow())

    output = capsys.readouterr()
    assert "Workflow failed at operations (TimeoutError)." in output.err
    assert "operations: error (8.0 ms)" in output.err


def test_terminal_chat_ctrl_c_during_request_exits_cleanly(
    monkeypatch,
    capsys,
) -> None:
    class Workflow:
        def invoke(self, _request: dict) -> dict:
            raise KeyboardInterrupt

    prompts = iter(["Check the handbook."])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))

    run_chat(Workflow())

    output = capsys.readouterr()
    assert "Request cancelled." in output.err


def test_terminal_chat_ctrl_c_at_prompt_exits_cleanly(
    monkeypatch,
    capsys,
) -> None:
    def interrupt(_prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)

    run_chat(object())

    assert "Chat interrupted." in capsys.readouterr().out
