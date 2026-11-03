import os
import time
import logging
from typing import Any
from app.providers.llm.base import BaseLLMProvider, LLMInferenceError

logger = logging.getLogger("gridvision.providers.llm.groq")


class GroqLLMAdapter(BaseLLMProvider):
    """Integrates with Groq's high-speed inference engine with retry resilience."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Any = None
        self._last_initialized_key: str | None = None

    @property
    def effective_api_key(self) -> str:
        return (self.api_key or os.getenv("GROQ_API_KEY") or "").strip()

    @property
    def effective_base_url(self) -> str:
        return (
            self.base_url
            or os.getenv("GROQ_BASE_URL")
            or "https://api.groq.com/openai/v1"
        ).strip()

    @property
    def effective_model(self) -> str:
        return (
            self.model
            or os.getenv("GROQ_MODEL")
            or "openai/gpt-oss-20b"
        ).strip()

    def _get_client(self) -> Any:
        current_key = self.effective_api_key
        if not current_key:
            return None

        if self._client is None or self._last_initialized_key != current_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=current_key,
                    base_url=self.effective_base_url,
                    timeout=self.timeout,
                )
                self._last_initialized_key = current_key
            except Exception as exc:
                logger.error("Failed to initialize OpenAI client for Groq: %s", exc)
                self._client = None
        return self._client

    def is_available(self) -> bool:
        """Return True if an API key is configured."""
        return bool(self.effective_api_key and len(self.effective_api_key) > 5)

    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        """Generate a chat completion using Groq with retry resilience."""
        if not self.is_available():
            raise LLMInferenceError("Groq API key is not configured.")

        client = self._get_client()
        if not client:
            raise LLMInferenceError("Groq client could not be initialized.")

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.effective_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                choice = response.choices[0]
                content = choice.message.content or ""
                return content.strip()
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_token_overflow = "limit" in err_str and ("requested" in err_str or "itpm" in err_str or "tpm" in err_str)
                if is_token_overflow:
                    logger.warning("Groq input token rate limit overflow detected. Aborting retry loop immediately.")
                    break

                is_transient = any(
                    k in err_str
                    for k in ["rate limit", "429", "timeout", "connection", "503", "temporarily"]
                )
                if is_transient and attempt < self.max_retries:
                    backoff = 0.5 * (2**attempt)
                    logger.warning(
                        "Groq inference attempt %d/%d encountered transient error. Retrying in %.1fs: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)
                    continue
                break

        logger.error(
            "Groq chat completion failed for model '%s': %s",
            self.effective_model,
            last_exc,
        )
        raise LLMInferenceError(f"Groq API error: {last_exc}") from last_exc
