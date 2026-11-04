"""Disabled-by-default AI orchestration with bounded calls and validated output."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from app.ai.contracts import AIOutput, GenerationAuditEvent, GenerationRequest
from app.ai.policy import AIPolicyError, validate_grounded_output
from app.ai.prompts import PROMPT_REGISTRY, PromptRenderError
from app.ai.providers import (
    AIProviderError,
    GenerationProvider,
    RetryableAIProviderError,
)

logger = logging.getLogger("gridvision.ai")


class AIUnavailableError(RuntimeError):
    pass


class AIOutputRejectedError(RuntimeError):
    pass


class AIService:
    def __init__(
        self,
        *,
        enabled: bool = False,
        generation_provider: GenerationProvider | None = None,
        timeout_seconds: float = 20,
        max_retries: int = 1,
        max_output_chars: int = 5000,
        audit_repository: Any | None = None,
        embedding_provider: Any | None = None,
    ) -> None:
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("AI timeout must be between 1 and 120 seconds.")
        if not 0 <= max_retries <= 3:
            raise ValueError("AI retries must be between 0 and 3.")
        if not 1 <= max_output_chars <= 5000:
            raise ValueError("AI output limit must be between 1 and 5000 characters.")
        self.enabled = enabled
        self.generation_provider = generation_provider
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_output_chars = max_output_chars
        self.audit_repository = audit_repository
        self.embedding_provider = embedding_provider

    @classmethod
    def from_config(cls, config: Any, *, audit_repository: Any | None = None) -> "AIService":
        return cls(
            enabled=bool(config.get("AI_ENABLED", False)),
            # No provider plugin is registered in the core application.
            generation_provider=None,
            embedding_provider=None,
            audit_repository=audit_repository,
            timeout_seconds=float(config.get("AI_TIMEOUT_SECONDS", 20)),
            max_retries=int(config.get("AI_MAX_RETRIES", 1)),
            max_output_chars=int(config.get("AI_MAX_OUTPUT_CHARS", 5000)),
        )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "generation_provider": (
                getattr(self.generation_provider, "provider_id", "unconfigured")
            ),
            "embedding_provider": getattr(self.embedding_provider, "provider_id", "unconfigured"),
            "external_calls_enabled": bool(
                self.enabled and (self.generation_provider or self.embedding_provider)
            ),
        }

    async def generate(self, request: GenerationRequest) -> AIOutput:
        if not self.enabled:
            raise AIUnavailableError("AI features are disabled.")
        if self.generation_provider is None:
            raise AIUnavailableError("No generation provider is configured.")
        prompt_definition = PROMPT_REGISTRY.get(request.prompt_key)
        if prompt_definition is None:
            raise AIUnavailableError("The requested prompt is not registered.")
        variables = dict(request.variables)
        variables["evidence_json"] = json.dumps(
            request.evidence.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        variables.setdefault("task", "Explain the supplied evidence cautiously.")
        try:
            prompt = prompt_definition.render(variables)
        except PromptRenderError as exc:
            raise AIUnavailableError(str(exc)) from exc

        started = time.monotonic()
        outcome = "failed"
        error_code = "AI_PROVIDER_ERROR"
        output_chars = 0
        attempts = 0
        try:
            while True:
                attempts += 1
                try:
                    raw = await asyncio.wait_for(
                        self.generation_provider.generate(
                            prompt,
                            timeout_seconds=self.timeout_seconds,
                            max_output_chars=min(
                                self.max_output_chars,
                                prompt_definition.max_output_chars,
                            ),
                        ),
                        timeout=self.timeout_seconds,
                    )
                    output = AIOutput.model_validate(raw)
                    if len(output.narrative) > self.max_output_chars:
                        raise AIPolicyError("AI output exceeded the configured size limit.")
                    validate_grounded_output(output, request.evidence)
                    outcome = "succeeded"
                    error_code = None
                    output_chars = len(output.narrative)
                    return output
                except RetryableAIProviderError:
                    if attempts > self.max_retries:
                        error_code = "AI_RETRIES_EXHAUSTED"
                        raise AIUnavailableError(
                            "The AI provider remained unavailable after bounded retries."
                        )
                except AIProviderError as exc:
                    error_code = "AI_PROVIDER_ERROR"
                    raise AIUnavailableError("The AI provider is unavailable.") from exc
                except asyncio.TimeoutError as exc:
                    outcome = "timed_out"
                    error_code = "AI_TIMEOUT"
                    raise AIUnavailableError("The AI provider timed out.") from exc
                except (ValidationError, AIPolicyError) as exc:
                    outcome = "rejected"
                    error_code = "AI_OUTPUT_REJECTED"
                    raise AIOutputRejectedError(str(exc)) from exc
        finally:
            self._write_audit(
                request,
                prompt_definition.version,
                outcome,
                time.monotonic() - started,
                output_chars,
                error_code,
            )

    def _write_audit(
        self,
        request: GenerationRequest,
        prompt_version: str,
        outcome: str,
        duration: float,
        output_chars: int,
        error_code: str | None,
    ) -> None:
        event = GenerationAuditEvent(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            workflow=request.prompt_key,
            prompt_key=request.prompt_key,
            prompt_version=prompt_version,
            provider=getattr(self.generation_provider, "provider_id", "unconfigured"),
            outcome=outcome,
            source_ids=[source.source_id for source in request.evidence.sources],
            duration_ms=min(max(duration, 0) * 1000, 3_600_000),
            output_chars=output_chars,
            error_code=error_code,
        )
        # Logs and audit records contain identifiers and counters only, never prompt,
        # evidence values, generated text, credentials, or entity identifiers.
        logger.info(
            "ai_generation",
            extra={"event": event.model_dump(mode="json")},
        )
        if self.audit_repository is not None:
            try:
                self.audit_repository.record(event)
            except Exception:
                # Do not include exception text or traceback: provider/storage
                # exceptions can contain credentials, paths, or request content.
                logger.error(
                    "AI audit persistence failed",
                    extra={"event": {"request_id": request.request_id, "outcome": outcome}},
                )

