"""Base protocol for Large Language Model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMInferenceError(RuntimeError):
    """Raised when an LLM provider fails to generate a completion."""


class BaseLLMProvider(ABC):
    """Abstract base class for LLM inference providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and available for inference."""
        ...

    @abstractmethod
    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        """Generate conversational response given a list of chat messages."""
        ...
