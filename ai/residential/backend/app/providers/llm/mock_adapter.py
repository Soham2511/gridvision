"""Deterministic mock LLM adapter for testing and deterministic fallbacks."""

from __future__ import annotations

from app.providers.llm.base import BaseLLMProvider


class MockLLMAdapter(BaseLLMProvider):
    """Provides deterministic mock responses without external network calls."""

    def __init__(self, canned_response: str | None = None) -> None:
        self.canned_response = canned_response

    def is_available(self) -> bool:
        return True

    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        if self.canned_response:
            return self.canned_response

        # Find latest user prompt
        user_prompt = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_prompt = m.get("content", "")
                break

        return (
            f"Based on your verified household telemetry, your consumption is tracking normally. "
            f"Your current daily usage and billing calculations reflect your active meter data."
        )
