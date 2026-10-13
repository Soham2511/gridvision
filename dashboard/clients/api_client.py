"""Typed-enough HTTP boundary for Streamlit-to-FastAPI requests."""

from __future__ import annotations

from typing import Any

import requests
from app.api.v1.schemas import PredictionResponse
from dashboard.clients.errors import APIClientError
from pydantic import ValidationError


class APIClient:
    """Call the configured GridVision API with timeouts and explicit errors."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        """Return API readiness, raising a user-displayable error if unavailable."""
        return self._get("/api/v1/health/ready")

    def predict(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit one validated feature row to an allow-listed prediction route."""
        if model not in {"residential", "commercial", "government"}:
            raise ValueError(f"Unsupported model identifier: {model}")
        body = self._post(f"/api/v1/{model}/predict", payload)
        try:
            return PredictionResponse.model_validate(body).model_dump(mode="json")
        except ValidationError as error:
            raise APIClientError(
                "GridVision API returned a response that violates "
                "its prediction contract."
            ) from error

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.base_url}{path}", timeout=self.timeout_seconds
            )
        except requests.RequestException as error:
            raise APIClientError(
                f"Could not connect to the GridVision API: {error}"
            ) from error
        return self._parse_response(response)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}{path}",
                json=_to_json_value(payload),
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as error:
            raise APIClientError(
                f"Could not connect to the GridVision API: {error}"
            ) from error
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: requests.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except requests.JSONDecodeError as error:
            raise APIClientError(
                f"GridVision API returned invalid JSON (HTTP {response.status_code})."
            ) from error
        if not response.ok:
            detail = body.get("detail", body) if isinstance(body, dict) else body
            raise APIClientError(
                f"GridVision API HTTP {response.status_code}: {detail}"
            )
        if not isinstance(body, dict):
            raise APIClientError("GridVision API response must be a JSON object.")
        return body


def _to_json_value(value: Any) -> Any:
    """Convert common pandas/numpy scalar values to JSON-compatible Python types."""
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    if hasattr(value, "item"):
        value = value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value
