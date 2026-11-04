"""Planner interface and bounded local Ollama supervisor classifier."""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai.commercial.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from ai.commercial.schemas.communication import SpecialistName

logger = logging.getLogger("gridvision.commercial.planner")


class PlannerSelection(BaseModel):
    """Strictly validated specialist selection returned by the LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    specialists: list[SpecialistName] = Field(min_length=1, max_length=4)


class CommercialPlanner(Protocol):
    """Interface for selecting specialists without granting tool access."""

    def select_specialists(self, goal: str) -> list[SpecialistName]:
        """Return the validated specialist names required by a user goal."""


class OllamaPlanner:
    """Classify requests with a local primary model and bounded fallback."""

    MAX_RESPONSE_CHARACTERS = 4096
    MAX_RESPONSE_BYTES = 16_384

    def __init__(
        self,
        *,
        base_url: str,
        primary_model: str,
        fallback_model: str,
        timeout_seconds: float,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Ollama base URL must use HTTP or HTTPS.")
        if not primary_model.strip() or not fallback_model.strip():
            raise ValueError("Ollama primary and fallback models are required.")
        self._base_url = base_url.rstrip("/")
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._timeout_seconds = timeout_seconds

    def _select_with_model(self, model: str, goal: str) -> list[SpecialistName]:
        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"goal": goal},
                            ensure_ascii=True,
                        ),
                    },
                ],
                "stream": False,
                "format": PlannerSelection.model_json_schema(),
                "options": {"temperature": 0, "num_predict": 256},
            }
        ).encode("utf-8")
        request = Request(
            f"{self._base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw_response = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ValueError(
                f"Ollama returned HTTP {exc.code} for model {model!r}."
            ) from exc
        except URLError as exc:
            raise OSError(
                f"Ollama could not be reached at {self._base_url}."
            ) from exc
        if len(raw_response) > self.MAX_RESPONSE_BYTES:
            raise ValueError("Ollama response exceeded the configured byte limit.")
        try:
            envelope = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Ollama returned an invalid response envelope."
            ) from exc
        if not isinstance(envelope, dict):
            raise ValueError("Ollama returned an invalid response envelope.")
        if envelope.get("error"):
            raise ValueError(
                f"Ollama request failed for model {model!r}."
            )
        message = envelope.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty planner response.")
        if len(content) > self.MAX_RESPONSE_CHARACTERS:
            raise ValueError("Ollama planner response exceeded the output limit.")
        try:
            parsed = PlannerSelection.model_validate_json(content)
        except ValueError as exc:
            raise ValueError(
                "Ollama returned an invalid specialist selection."
            ) from exc
        return list(dict.fromkeys(parsed.specialists))

    def select_specialists(self, goal: str) -> list[SpecialistName]:
        """Use the primary model and retry with the configured local fallback."""
        try:
            return self._select_with_model(self._primary_model, goal)
        except (OSError, TimeoutError, ValueError) as primary_error:
            logger.warning(
                "ollama_primary_model_failed",
                extra={
                    "event": {
                        "model": self._primary_model,
                        "error_type": type(primary_error).__name__,
                        "fallback_model": self._fallback_model,
                    }
                },
            )
        try:
            return self._select_with_model(self._fallback_model, goal)
        except (OSError, TimeoutError, ValueError) as fallback_error:
            raise ValueError(
                "Ollama planning failed for both configured local models "
                f"({self._primary_model}, {self._fallback_model})."
            ) from fallback_error
