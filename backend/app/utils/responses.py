"""Standardized JSON response formatting."""

from __future__ import annotations

from typing import Any
from flask import jsonify, Response


def success_response(
    data: Any,
    meta: dict[str, Any] | None = None,
    status_code: int = 200,
) -> tuple[Response, int]:
    """Return a consistent successful JSON response."""
    payload: dict[str, Any] = {
        "success": True,
        "data": data,
    }
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status_code


def error_response(
    message: str,
    code: str = "ERROR",
    details: Any = None,
    status_code: int = 400,
) -> tuple[Response, int]:
    """Return a consistent error JSON response."""
    payload: dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status_code
