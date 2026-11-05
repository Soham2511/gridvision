"""Isolated environment configuration; disabled and provider-free by default."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be in [1, {maximum}]")
    return value


@dataclass(frozen=True)
class AgentSettings:
    enabled: bool = False
    llm_provider: str = "none"
    model_name: str = ""
    timeout_seconds: float = 20.0
    max_tool_calls: int = 6
    max_graph_steps: int = 10
    session_ttl_seconds: int = 1800
    max_message_chars: int = 4000
    langsmith_tracing: bool = False

    @classmethod
    def from_env(cls):
        provider = os.getenv("GRIDVISION_RETRIEVAL_LLM_PROVIDER", "none").strip().lower()
        if provider not in {"none", "huggingface", "hosted"}:
            raise ValueError("GRIDVISION_RETRIEVAL_LLM_PROVIDER must be none, huggingface, or hosted")
        timeout = float(os.getenv("GRIDVISION_RETRIEVAL_TIMEOUT_SECONDS", "20"))
        if not 0 < timeout <= 120:
            raise ValueError("GRIDVISION_RETRIEVAL_TIMEOUT_SECONDS must be in (0, 120]")
        return cls(
            enabled=os.getenv("GRIDVISION_RETRIEVAL_ENABLED", "false").lower() in {"1", "true", "yes"},
            llm_provider=provider,
            model_name=os.getenv("GRIDVISION_RETRIEVAL_MODEL", "").strip(),
            timeout_seconds=timeout,
            max_tool_calls=_int("GRIDVISION_RETRIEVAL_MAX_TOOL_CALLS", 6, 20),
            max_graph_steps=_int("GRIDVISION_RETRIEVAL_MAX_GRAPH_STEPS", 10, 30),
            session_ttl_seconds=_int("GRIDVISION_RETRIEVAL_SESSION_TTL_SECONDS", 1800, 86400),
            max_message_chars=_int("GRIDVISION_RETRIEVAL_MAX_MESSAGE_CHARS", 4000, 20000),
            langsmith_tracing=os.getenv("GRIDVISION_RETRIEVAL_LANGSMITH_TRACING", "false").lower() in {"1", "true", "yes"},
        )

