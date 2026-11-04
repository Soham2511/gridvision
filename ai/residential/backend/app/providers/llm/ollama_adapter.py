"""Ollama LLM Provider Adapter for local model execution (e.g. qwen3:8b).

Implements BaseLLMProvider using Ollama's local runtime, providing structured
and chat completion capabilities with clear, actionable diagnostics on server/model unavailability.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
import urllib.request
import json

from app.config import BaseConfig
from app.providers.llm.base import BaseLLMProvider, LLMInferenceError

logger = logging.getLogger("gridvision.providers.llm.ollama")


def normalize_ollama_base_url(base_url: str) -> str:
    """Normalize native Ollama URLs, including OpenAI-compatible URLs ending in /v1."""
    url = base_url.strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3].rstrip("/")
    return url


class OllamaLLMAdapter(BaseLLMProvider):
    """Integrates with local Ollama runtime hosting qwen3:8b."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 1,
    ) -> None:
        self.base_url = (base_url or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout if timeout is not None else getattr(BaseConfig, "ASSISTANT_TIMEOUT_SECONDS", 60.0)
        self.max_retries = max_retries

    @property
    def effective_base_url(self) -> str:
        return normalize_ollama_base_url(
            self.base_url
            or os.getenv("OLLAMA_BASE_URL")
            or getattr(BaseConfig, "OLLAMA_BASE_URL", "http://localhost:11434")
            or "http://localhost:11434"
        )

    @property
    def effective_model(self) -> str:
        return (
            self.model
            or os.getenv("OLLAMA_MODEL")
            or getattr(BaseConfig, "OLLAMA_MODEL", "qwen3:8b")
            or "qwen3:8b"
        ).strip()

    def is_available(self, timeout: float = 2.0, force_live: bool = False) -> bool:
        """Check whether local Ollama server is reachable and responsive."""
        import os
        is_testing = (
            getattr(BaseConfig, "TESTING", False)
            or os.getenv("FLASK_ENV") == "testing"
            or bool(os.getenv("PYTEST_CURRENT_TEST"))
        )
        try:
            from flask import current_app
            if current_app and current_app.config.get("TESTING"):
                is_testing = True
        except Exception:
            pass
        if is_testing and not force_live and not os.getenv("TEST_REAL_OLLAMA"):
            return False

        try:
            req = urllib.request.Request(
                f"{self.effective_base_url}/api/tags",
                headers={"User-Agent": "GridVision-HealthCheck"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_installed_models(self, timeout: float = 3.0) -> List[str]:
        """Retrieve list of model names currently available in Ollama."""
        try:
            req = urllib.request.Request(
                f"{self.effective_base_url}/api/tags",
                headers={"User-Agent": "GridVision"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return [m.get("name", "") for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Could not list Ollama models: %s", exc)
        return []

    def is_model_installed(self, model_name: Optional[str] = None) -> bool:
        """Verify whether the requested model is pulled and ready in Ollama."""
        target = (model_name or self.effective_model).lower()
        target_base = target.split(":")[0]
        installed = [m.lower() for m in self.list_installed_models()]
        return any(target in m or target_base in m.split(":")[0] for m in installed)

    def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
        model_override: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Generate a chat completion using local Ollama without Groq fallback."""
        model_name = (model_override or self.effective_model).strip()
        base_url = self.effective_base_url

        if not self.is_available():
            raise LLMInferenceError(
                f"Ollama server is not reachable at '{base_url}'. "
                f"Please ensure Ollama is running and model '{model_name}' is loaded "
                f"(e.g., 'ollama serve' and 'ollama run {model_name}')."
            )

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        req_data = json.dumps(payload).encode("utf-8")
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    f"{base_url}/api/chat",
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        res_json = json.loads(resp.read().decode("utf-8"))
                        msg = res_json.get("message", {})
                        content = msg.get("content", "")
                        if not isinstance(content, str) or not content.strip():
                            raise LLMInferenceError(
                                f"Ollama returned an empty completion for model '{model_name}'."
                            )
                        return content.strip()
                    raise LLMInferenceError(f"Ollama HTTP error {resp.status}")
            except Exception as exc:
                last_exc = exc
                logger.warning("Ollama invocation attempt %d failed: %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    time.sleep(0.5)

        logger.error("Ollama completion failed after retries: %s", last_exc)
        raise LLMInferenceError(
            f"Ollama inference failed on model '{model_name}' at '{base_url}': {last_exc}. "
            f"Please verify model availability."
        ) from last_exc
