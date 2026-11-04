from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from ai.assistant import assistant, tavily


class FakeLLM:
    provider = "fake"
    model = "test"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)

    def complete(
        self,
        _messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str:
        return self.outputs.pop(0)


def test_tavily_search_uses_key_without_returning_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    requests: list[urllib.request.Request] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "Energy report",
                            "url": "https://example.test/energy",
                            "content": "A verified public source snippet.",
                        },
                        {
                            "title": "Duplicate URL",
                            "url": "https://example.test/energy",
                            "content": "Should not be duplicated.",
                        },
                    ]
                }
            ).encode()

    def fake_urlopen(request: urllib.request.Request, **_kwargs: Any) -> Response:
        requests.append(request)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sources = tavily.search_web("energy demand", max_results=3)
    sent_payload = json.loads(requests[0].data)

    assert sent_payload["api_key"] == "test-tavily-key"
    assert sent_payload["query"] == "energy demand"
    assert len(sources) == 1
    assert "test-tavily-key" not in repr(sources)


def test_external_query_returns_cited_sources_and_separates_internal_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [
        {
            "title": "Public energy outlook",
            "url": "https://example.test/outlook",
            "content": "The report discusses energy demand forecasting.",
        }
    ]
    monkeypatch.setattr(assistant, "search_web", lambda _query: sources)
    query_llm = FakeLLM(
        [
            json.dumps(
                {
                    "intent": "external_knowledge",
                    "forecast_date": None,
                    "start_timestamp": None,
                    "duration_hours": None,
                    "grid_ids": [],
                    "output_formats": ["text"],
                    "needs_clarification": False,
                    "clarification_question": None,
                }
            ),
        ]
    )
    response_llm = FakeLLM(
        [
            json.dumps(
                {
                    "overview": "The supplied public source discusses demand forecasting.",
                    "limitations": "This external context does not replace internal energy data.",
                }
            )
        ]
    )
    result = assistant.handle_user_query(
        "Search the web for an energy demand forecast outlook",
        query_llm=query_llm,
        response_llm=response_llm,
        simulations_dir=tmp_path / "no-plans",
        history_path=tmp_path / "history.json",
        log_path=tmp_path / "assistant.log",
    )

    assert "[1] Public energy outlook" in result.text
    assert "https://example.test/outlook" in result.text
    assert "internal 2018 energy data" in result.text
    assert result.csv_path is None
    assert result.image_path is None


def test_tavily_key_file_errors_do_not_echo_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_path = tmp_path / "api.key"
    key_path.write_text("", encoding="utf-8")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY_FILE", str(key_path))

    with pytest.raises(tavily.TavilyError, match="key file is empty"):
        tavily.search_web("test")
