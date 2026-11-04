"""Bounded request contract for arbitrary JSON report inputs."""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)


class InputError(ValueError):
    """Safe, user-correctable report input error."""


class GenerateReportRequest(BaseModel):
    """A JSON value plus optional trusted user instructions and formats."""

    model_config = ConfigDict(extra="forbid", strict=True)

    data: Any
    instructions: str | None = Field(default=None, max_length=20_000)
    output_formats: list[Literal["html", "pdf"]] = Field(
        default_factory=lambda: ["html", "pdf"], min_length=1, max_length=2
    )

    @field_validator("data")
    @classmethod
    def data_is_json_compatible(cls, value: Any, info: ValidationInfo) -> Any:
        context = info.context or {}
        _validate_json_value(
            value,
            max_depth=context.get("max_depth", 32),
            max_nodes=context.get("max_nodes", 50_000),
            max_string_chars=context.get("max_string_chars", 100_000),
        )
        return value

    @field_validator("instructions")
    @classmethod
    def instructions_are_nonempty_when_supplied(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("instructions must not be blank")
        limit = (info.context or {}).get("max_instruction_chars", 4_000)
        if value is not None and len(value) > limit:
            raise ValueError("instructions exceed the configured size limit")
        return value

    @field_validator("output_formats")
    @classmethod
    def output_formats_are_unique(
        cls, value: list[str]
    ) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("output_formats must not contain duplicates")
        return value


def _reject_constant(value: str) -> None:
    raise InputError(f"Invalid JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError("JSON object keys must be unique")
        result[key] = value
    return result


def parse_request_bytes(
    raw: bytes,
    *,
    max_bytes: int = 1_000_000,
    max_depth: int = 32,
    max_nodes: int = 50_000,
    max_string_chars: int = 100_000,
    max_instruction_chars: int = 4_000,
) -> GenerateReportRequest:
    """Parse and validate UTF-8 JSON bytes with explicit resource bounds.

    This helper is transport-independent so the later Flask layer can reuse it
    without coupling input validation to Flask request objects.
    """
    if not isinstance(raw, bytes):
        raise TypeError("raw request body must be bytes")
    if len(raw) > max_bytes:
        raise InputError("JSON request exceeds the configured size limit")
    try:
        text = raw.decode("utf-8")
        parsed = json.loads(
            text,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError("Request body must contain valid UTF-8 JSON") from exc

    if not isinstance(parsed, dict) or "data" not in parsed:
        raise InputError("Request JSON must be an object containing a data field")
    _validate_json_value(
        parsed["data"],
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_string_chars=max_string_chars,
    )
    try:
        return GenerateReportRequest.model_validate(
            parsed,
            context={
                "max_instruction_chars": max_instruction_chars,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "max_string_chars": max_string_chars,
            },
        )
    except ValidationError as exc:
        # Pydantic's detailed error may echo user-provided values. The API layer
        # can use this safe wrapper as its public validation boundary.
        raise InputError("Request JSON does not match the report generation schema") from exc


def _validate_json_value(
    root: Any,
    *,
    max_depth: int,
    max_nodes: int,
    max_string_chars: int,
) -> None:
    if max_depth < 0 or max_nodes < 1 or max_string_chars < 1:
        raise ValueError("JSON limits must be positive")
    node_count = 0
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        value, depth = stack.pop()
        node_count += 1
        if node_count > max_nodes:
            raise InputError("JSON request contains too many values")
        if depth > max_depth:
            raise InputError("JSON request exceeds the configured nesting limit")
        if value is None or isinstance(value, (bool, int)):
            continue
        if isinstance(value, float):
            if not math.isfinite(value):
                raise InputError("JSON numeric values must be finite")
            continue
        if isinstance(value, str):
            if len(value) > max_string_chars:
                raise InputError("JSON string exceeds the configured size limit")
            continue
        if isinstance(value, list):
            stack.extend((item, depth + 1) for item in reversed(value))
            continue
        if isinstance(value, dict):
            for key, item in reversed(list(value.items())):
                if not isinstance(key, str):
                    raise InputError("JSON object keys must be strings")
                if len(key) > max_string_chars:
                    raise InputError("JSON object key exceeds the configured size limit")
                stack.append((item, depth + 1))
            continue
        raise InputError("Request contains a value that is not valid JSON")
