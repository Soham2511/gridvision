from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def use_mock_planner_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMMERCIAL_LLM_PROVIDER", "mock")
