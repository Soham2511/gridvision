import os
import time
import logging
from typing import Any
from app.providers.llm.base import BaseLLMProvider, LLMInferenceError

logger = logging.getLogger("gridvision.providers.llm.groq")

FALLBACK_MODELS = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "allam-2-7b",
    "meta-llama/llama-prompt-guard-2-22m",
    "meta-llama/llama-prompt-guard-2-86m",
]


def configured_fallback_models() -> list[str]:
    """Return the residential Groq fallback chain in configured order."""
    configured = os.getenv("RESIDENTIAL_GROQ_FALLBACK_MODELS")
    source = configured.split(",") if configured is not None else FALLBACK_MODELS
    return list(dict.fromkeys(model.strip() for model in source if model.strip()))


def ordered_model_candidates(
    primary_model: str | None = None,
    fallback_models: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Keep 120B third even when older environment settings list it first."""
    models = list(
        dict.fromkeys(
            model.strip()
            for model in (
                fallback_models
                if fallback_models is not None
                else configured_fallback_models()
            )
            if model.strip()
        )
    )
    if primary_model and primary_model not in models:
        models.insert(0, primary_model)
    if "openai/gpt-oss-120b" in models:
        models.remove("openai/gpt-oss-120b")
        models.insert(min(2, len(models)), "openai/gpt-oss-120b")
    return models


class GroqLLMAdapter(BaseLLMProvider):
    """Integrates with Groq's high-speed inference engine with retry resilience."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 2,
        fallback_models: list[str] | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.fallback_models = tuple(
            configured_fallback_models() if fallback_models is None else fallback_models
        )
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

    @property
    def effective_api_key_2(self) -> str:
        return os.getenv("GROQ_API_KEY_2", "").strip()

    def _get_client(self, api_key: str | None = None) -> Any:
        current_key = (api_key or self.effective_api_key).strip()
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
        """Return True if either residential Groq key is configured."""
        return any(
            key and len(key) > 5
            for key in (self.effective_api_key, self.effective_api_key_2)
        )

    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
        model_override: str | None = None,
    ) -> str:
        """Generate a chat completion using Groq with multi-model failover resilience."""
        if not self.is_available():
            raise LLMInferenceError("Groq API key is not configured.")

        primary_model = (model_override or self.effective_model).strip()
        candidate_models = ordered_model_candidates(primary_model, self.fallback_models)
        candidate_keys = list(
            dict.fromkeys(
                key
                for key in (self.effective_api_key, self.effective_api_key_2)
                if key
            )
        )

        last_exc: Exception | None = None
        for cand_model in candidate_models:
            for api_key in candidate_keys:
                client = self._get_client(api_key)
                if not client:
                    last_exc = LLMInferenceError(
                        "Groq client could not be initialized for a configured key."
                    )
                    continue
                for attempt in range(self.max_retries + 1):
                    try:
                        response = client.chat.completions.create(
                            model=cand_model,
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
                        is_token_overflow = any(
                            marker in err_str
                            for marker in (
                                "rate limit",
                                "429",
                                "itpm",
                                "tpd",
                                "tokens per day",
                                "rate_limit_exceeded",
                            )
                        )
                        if is_token_overflow:
                            logger.warning(
                                "Groq request for model '%s' was rate limited; "
                                "trying the next configured key/model.",
                                cand_model,
                            )
                            break

                        is_transient = any(
                            marker in err_str
                            for marker in ("timeout", "connection", "503", "temporarily")
                        )
                        if is_transient and attempt < self.max_retries:
                            time.sleep(0.3)
                            continue
                        break

        logger.error(
            "Groq chat completion failed across all configured model/key attempts %s: %s",
            candidate_models,
            last_exc,
        )
        raise LLMInferenceError(f"Groq API error: {last_exc}") from last_exc
