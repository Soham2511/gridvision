from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from ..paths import (
    GROQ_API_KEY_PATH,
    OLLAMA_API_KEY_PATH,
    OPENROUTER_API_KEY_PATH,
    PROJECT_ROOT,
    configured_path,
)

WORKSPACE_ROOT = PROJECT_ROOT
DEFAULT_GROQ_KEY_PATH = GROQ_API_KEY_PATH
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_OPENROUTER_KEY_PATH = OPENROUTER_API_KEY_PATH
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_QUERY_MODEL = "openai/gpt-oss-120b"
DEFAULT_RESPONSE_MODEL = "openai/gpt-oss-20b"
DEFAULT_OPENROUTER_QUERY_MODEL = "openai/gpt-oss-120b"
DEFAULT_OPENROUTER_RESPONSE_MODEL = "openai/gpt-oss-20b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_KEY_PATH = OLLAMA_API_KEY_PATH
DEFAULT_OLLAMA_QUERY_MODEL = "qwen3:1.7b"
DEFAULT_OLLAMA_RESPONSE_MODEL = "batiai/gemma4-e2b:q4"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 180
REQUEST_TIMEOUT_SECONDS = 45


class LLMProviderError(RuntimeError):
    """Sanitized provider, authentication, availability, or response failure."""


def _create_ssl_context() -> ssl.SSLContext:
    """Create a verified TLS context, optionally trusting an extra CA bundle."""
    context = ssl.create_default_context()
    ca_bundle_path = os.environ.get("ENERGY_ASSISTANT_CA_BUNDLE", "").strip()
    if ca_bundle_path:
        path = Path(ca_bundle_path).expanduser()
        if not path.is_file():
            raise LLMProviderError(
                f"Configured CA bundle does not exist or is not a file: {path}"
            )
        try:
            context.load_verify_locations(cafile=str(path))
        except (OSError, ssl.SSLError) as exc:
            raise LLMProviderError(
                f"Unable to load configured CA bundle: {path}"
            ) from exc
    return context


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str: ...


def _read_key_file(key_path: str | Path | None = None) -> str:
    environment_key = os.environ.get("GROQ_API_KEY", "").strip()
    if environment_key:
        return environment_key
    path = (
        Path(key_path).expanduser()
        if key_path is not None
        else configured_path("GROQ_API_KEY_FILE", DEFAULT_GROQ_KEY_PATH)
    )
    if not path.is_file():
        raise LLMProviderError(
            "Groq API key not found. Set GROQ_API_KEY or provide a readable "
            "key file with GROQ_API_KEY_FILE."
        )
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LLMProviderError(f"Unable to read Groq API key file: {path}") from exc
    if not key:
        raise LLMProviderError(f"Groq API key file is empty: {path}")
    return key


def _read_openai_compatible_key() -> str:
    key = os.environ.get("ENERGY_LLM_API_KEY", "").strip()
    if not key:
        raise LLMProviderError(
            "Set ENERGY_LLM_API_KEY when using the openai-compatible provider."
        )
    return key


def _read_openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    path = configured_path("OPENROUTER_API_KEY_FILE", DEFAULT_OPENROUTER_KEY_PATH)
    if not path.is_file():
        raise LLMProviderError(
            "OpenRouter API key not found. Set OPENROUTER_API_KEY or provide a "
            "readable key file with OPENROUTER_API_KEY_FILE."
        )
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LLMProviderError(
            f"Unable to read OpenRouter API key file: {path}"
        ) from exc
    if not key:
        raise LLMProviderError(f"OpenRouter API key file is empty: {path}")
    return key


def _read_ollama_key() -> str:
    key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if key:
        return key
    path = configured_path("OLLAMA_API_KEY_FILE", DEFAULT_OLLAMA_KEY_PATH)
    if not path.is_file():
        raise LLMProviderError(
            "Remote Ollama requires OLLAMA_API_KEY or a readable "
            "key file with OLLAMA_API_KEY_FILE."
        )
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LLMProviderError(f"Unable to read Ollama API key file: {path}") from exc
    if not key:
        raise LLMProviderError(f"Ollama API key file is empty: {path}")
    return key


class OpenAICompatibleProvider:
    """Reusable adapter for providers exposing the OpenAI chat/model endpoints."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        if not self.model.strip():
            raise ValueError(f"{self.provider} model ID must not be empty")
        if not self.base_url.startswith("https://"):
            raise ValueError("LLM provider endpoint must use HTTPS.")
        self.ssl_context = _create_ssl_context()
        self.verify_model_available()

    def _request(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=self.ssl_context,
            ) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                message = f"{self.provider} rejected the configured API key (HTTP 401)."
            elif exc.code == 403:
                if endpoint.rstrip("/") == "models":
                    message = (
                        f"{self.provider} denied access to its model list (HTTP 403). "
                        "Check that this API key is active and allowed to list models."
                    )
                else:
                    message = (
                        f"{self.provider} denied access to the requested model or "
                        f"endpoint '{endpoint}' (HTTP 403). Check model access and "
                        "the API key's project/organization permissions."
                    )
            elif exc.code == 402 and self.provider == "openrouter":
                message = (
                    f"OpenRouter requires payment or credits for endpoint "
                    f"'{endpoint}' (HTTP 402). Check your OpenRouter account "
                    "credits and whether the selected model requires paid usage."
                )
            elif exc.code == 404:
                message = f"{self.provider} endpoint or configured model was not found (HTTP 404)."
            elif exc.code == 429:
                delay = exc.headers.get("Retry-After")
                message = (
                    f"{self.provider} rate limit reached for endpoint '{endpoint}' "
                    "(HTTP 429)"
                )
                if delay:
                    message += f"; retry after {delay} seconds"
                elif self.provider == "openrouter":
                    message += (
                        "; wait before retrying or select another currently "
                        "available model"
                    )
                message += "."
            else:
                message = f"{self.provider} request failed (HTTP {exc.code})."
            raise LLMProviderError(message) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderError(
                f"Unable to reach {self.provider} API: {exc.reason}"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"{self.provider} returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError(f"{self.provider} returned an invalid response object.")
        return decoded

    def verify_model_available(self) -> None:
        response = self._request("models")
        models = response.get("data")
        if not isinstance(models, list):
            raise LLMProviderError(
                f"{self.provider} model-list response is missing model data."
            )
        model_ids = {
            entry.get("id")
            for entry in models
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        if self.model not in model_ids:
            raise LLMProviderError(
                f"Configured {self.provider} model '{self.model}' is not available "
                "for this account. Check the active model list and configure "
                "ENERGY_QUERY_MODEL or ENERGY_RESPONSE_MODEL."
            )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1 if json_mode else 0.25,
            "max_tokens": 1600,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = self._request("chat/completions", payload)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderError(f"{self.provider} returned no completion choices.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError(f"{self.provider} returned an empty completion.")
        return content.strip()


class GroqProvider(OpenAICompatibleProvider):
    """Groq adapter, loading credentials from the configured vault file."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = DEFAULT_GROQ_BASE_URL,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            provider="groq",
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter adapter using its OpenAI-compatible API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = DEFAULT_OPENROUTER_BASE_URL,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            provider="openrouter",
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )


class OllamaProvider:
    """Ollama native chat adapter; local hosts never receive cloud credentials."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_OLLAMA_HOST,
        timeout_seconds: int | None = None,
    ) -> None:
        self.provider = "ollama"
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        if timeout_seconds is None:
            configured_timeout = os.environ.get(
                "OLLAMA_TIMEOUT_SECONDS",
                str(DEFAULT_OLLAMA_TIMEOUT_SECONDS),
            )
            try:
                timeout_seconds = int(configured_timeout)
            except ValueError as exc:
                raise ValueError("OLLAMA_TIMEOUT_SECONDS must be an integer.") from exc
        if timeout_seconds <= 0:
            raise ValueError("Ollama request timeout must be greater than zero.")
        self.timeout_seconds = timeout_seconds
        self.api_key: str | None = None
        parsed = urlparse(self.base_url)
        if not self.model:
            raise ValueError("Ollama model ID must not be empty.")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("OLLAMA_HOST must be an HTTP(S) URL.")
        hostname = parsed.hostname.lower()
        self.is_local = (
            hostname in {
                "localhost",
                "127.0.0.1",
                "::1",
                "host.docker.internal",
                "gateway.docker.internal",
            }
            or hostname.endswith(".internal")
            or hostname.endswith(".local")
        )
        if self.is_local and parsed.scheme != "http":
            raise ValueError("Local Ollama should use HTTP on its loopback host.")
        if not self.is_local:
            if parsed.scheme != "https":
                raise ValueError("Remote Ollama hosts must use HTTPS.")
            self.api_key = _read_ollama_key()
        self.ssl_context = _create_ssl_context() if parsed.scheme == "https" else None
        self.verify_model_available()

    def _request(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            if self.ssl_context is None:
                response_context = urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                )
            else:
                response_context = urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                    context=self.ssl_context,
                )
            with response_context as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                message = "Ollama rejected the configured remote API key (HTTP 401)."
            elif exc.code == 404:
                message = (
                    f"Ollama endpoint or model '{self.model}' was not found "
                    f"(HTTP 404)."
                )
            elif exc.code == 429:
                delay = exc.headers.get("Retry-After")
                message = f"Ollama rate limit reached for endpoint '{endpoint}' (HTTP 429)"
                if delay:
                    message += f"; retry after {delay} seconds"
                message += "."
            else:
                message = f"Ollama request failed for endpoint '{endpoint}' (HTTP {exc.code})."
            raise LLMProviderError(message) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderError(
                f"Unable to reach Ollama at {self.base_url}: {exc.reason}"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Ollama returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise LLMProviderError("Ollama returned an invalid response object.")
        return decoded

    def verify_model_available(self) -> None:
        response = self._request("api/tags")
        models = response.get("models")
        if not isinstance(models, list):
            raise LLMProviderError("Ollama model-list response is missing model data.")
        model_names = {
            name
            for entry in models
            if isinstance(entry, dict)
            for name in (entry.get("name"), entry.get("model"))
            if isinstance(name, str)
        }
        if self.model not in model_names:
            model_list = ", ".join(sorted(model_names)) or "none"
            raise LLMProviderError(
                f"Ollama model '{self.model}' is not downloaded or available at "
                f"{self.base_url}. Available models: {model_list}. Run "
                f"'ollama pull {self.model}' or configure OLLAMA_QUERY_MODEL/"
                "OLLAMA_RESPONSE_MODEL."
            )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.0 if json_mode else 0.25},
        }
        if self.model.lower().startswith("qwen3"):
            # Qwen3's hidden reasoning can consume a short structured-output
            # budget and leave `message.content` empty. The assistant uses the
            # returned content as JSON, so request a direct answer for this
            # constrained interpreter call.
            payload["think"] = False
        if response_schema is not None:
            payload["format"] = response_schema
        elif json_mode:
            payload["format"] = "json"
        response = self._request("api/chat", payload)
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("Ollama returned an empty completion.")
        return content.strip()


def initialize_llm(
    provider: str,
    model: str,
    *,
    api_key_path: str | Path | None = None,
) -> LLMClient:
    """Create a provider adapter and verify its selected model is available."""
    provider_name = provider.strip().lower()
    if provider_name == "groq":
        base_url = os.environ.get("GROQ_BASE_URL", DEFAULT_GROQ_BASE_URL)
        return GroqProvider(
            model=model,
            api_key=_read_key_file(api_key_path),
            base_url=base_url,
        )
    if provider_name == "openrouter":
        base_url = os.environ.get(
            "OPENROUTER_BASE_URL",
            DEFAULT_OPENROUTER_BASE_URL,
        )
        return OpenRouterProvider(
            model=model,
            api_key=_read_openrouter_key(),
            base_url=base_url,
        )
    if provider_name == "ollama":
        base_url = (
            os.environ.get("OLLAMA_HOST")
            or os.environ.get("GRIDVISION_ROUTER_OLLAMA_URL")
            or os.environ.get("GRIDVISION_ANOMALY_OLLAMA_BASE_URL")
            or DEFAULT_OLLAMA_HOST
        )
        return OllamaProvider(
            model=model,
            base_url=base_url,
        )
    if provider_name == "openai-compatible":
        base_url = os.environ.get("ENERGY_LLM_BASE_URL", "").strip()
        if not base_url:
            raise LLMProviderError(
                "Set ENERGY_LLM_BASE_URL to use the openai-compatible provider."
            )
        return OpenAICompatibleProvider(
            provider=provider_name,
            model=model,
            api_key=_read_openai_compatible_key(),
            base_url=base_url,
        )
    raise ValueError(
        f"Unsupported LLM provider '{provider}'. Currently supported: "
        "ollama, groq, openrouter, and openai-compatible."
    )
