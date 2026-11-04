"""Provider-neutral interfaces; concrete external providers are separate plugins."""

from __future__ import annotations

from typing import Any, Protocol

from app.ai.contracts import AIOutput


class AIProviderError(RuntimeError):
    """Base error from a configured AI provider."""


class RetryableAIProviderError(AIProviderError):
    """A provider failure eligible for the configured bounded retry."""


class GenerationProvider(Protocol):
    provider_id: str

    async def generate(
        self,
        prompt: str,
        *,
        timeout_seconds: float,
        max_output_chars: int,
    ) -> AIOutput | dict[str, Any]: ...


class EmbeddingProvider(Protocol):
    provider_id: str

    async def embed(
        self, texts: list[str], *, timeout_seconds: float
    ) -> list[list[float]]: ...

