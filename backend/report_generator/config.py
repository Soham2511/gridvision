"""Environment-based, bounded settings for JSON report generation."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bounded_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not lower <= value <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return value


@dataclass(frozen=True)
class ReportGeneratorSettings:
    enabled: bool = False
    max_request_bytes: int = 1_000_000
    max_json_depth: int = 32
    max_json_nodes: int = 50_000
    max_string_chars: int = 100_000
    max_instruction_chars: int = 4_000
    max_prompt_chars: int = 1_500_000
    provider: str = "none"
    provider_timeout_seconds: float = 30.0
    max_provider_retries: int = 1
    max_output_chars: int = 40_000
    max_artifact_bytes: int = 25_000_000

    @classmethod
    def from_env(
        cls, *, default_provider: str = "none", default_enabled: bool = False
    ) -> "ReportGeneratorSettings":
        provider = os.getenv("GRIDVISION_REPORT_LLM_PROVIDER", default_provider).strip().lower()
        if provider not in {"none", "hosted", "huggingface", "ollama"}:
            raise ValueError(
                "GRIDVISION_REPORT_LLM_PROVIDER must be none, hosted, huggingface, or ollama"
            )
        try:
            timeout = float(os.getenv("GRIDVISION_REPORT_LLM_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise ValueError("GRIDVISION_REPORT_LLM_TIMEOUT_SECONDS must be numeric") from exc
        if not 0 < timeout <= 120:
            raise ValueError("GRIDVISION_REPORT_LLM_TIMEOUT_SECONDS must be in (0, 120]")
        return cls(
            enabled=os.getenv("GRIDVISION_REPORT_GENERATOR_ENABLED", str(default_enabled).lower()).lower()
            in {"1", "true", "yes"},
            max_request_bytes=_bounded_int(
                "GRIDVISION_REPORT_MAX_REQUEST_BYTES", 1_000_000, 1_024, 10_000_000
            ),
            max_json_depth=_bounded_int("GRIDVISION_REPORT_MAX_JSON_DEPTH", 32, 1, 128),
            max_json_nodes=_bounded_int("GRIDVISION_REPORT_MAX_JSON_NODES", 50_000, 1, 500_000),
            max_string_chars=_bounded_int(
                "GRIDVISION_REPORT_MAX_STRING_CHARS", 100_000, 1, 1_000_000
            ),
            max_instruction_chars=_bounded_int(
                "GRIDVISION_REPORT_MAX_INSTRUCTION_CHARS", 4_000, 1, 20_000
            ),
            max_prompt_chars=_bounded_int(
                "GRIDVISION_REPORT_MAX_PROMPT_CHARS", 1_500_000, 10_000, 5_000_000
            ),
            provider=provider,
            provider_timeout_seconds=timeout,
            max_provider_retries=_bounded_int(
                "GRIDVISION_REPORT_MAX_PROVIDER_RETRIES", 1, 0, 3
            ),
            max_output_chars=_bounded_int(
                "GRIDVISION_REPORT_MAX_OUTPUT_CHARS", 40_000, 1_000, 200_000
            ),
            max_artifact_bytes=_bounded_int(
                "GRIDVISION_REPORT_MAX_ARTIFACT_BYTES", 25_000_000, 1_024, 25_000_000
            ),
        )
