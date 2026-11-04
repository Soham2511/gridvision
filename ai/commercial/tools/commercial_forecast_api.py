"""Bounded local API adapter for trained Commercial building forecasts."""

from __future__ import annotations

import ipaddress
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ai.commercial.schemas.communication import (
    AgentError,
    EvidenceRef,
    ToolObservation,
)

MAX_RESPONSE_BYTES = 2_000_000
BUILDING_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,15}$")


class ForecastAPIError(Exception):
    """A bounded backend error with a safe, user-facing tool status."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status: str = "unavailable",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request,
        response,
        code,
        message,
        headers,
        new_url,
    ):
        del request, response, code, message, headers, new_url
        return None


class CommercialForecastAPITools:
    """Read-only client for the loopback Commercial forecast API."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = self._validate_base_url(base_url)
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError(
                "Forecast API timeout must be greater than 0 and at most 30 seconds."
            )
        self._timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )

    @staticmethod
    def _validate_base_url(base_url: str) -> str:
        try:
            parsed = urllib.parse.urlsplit(base_url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Commercial forecast API URL is invalid.") from exc

        if (
            parsed.scheme != "http"
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.rstrip("/").endswith("/api/v1")
        ):
            raise ValueError(
                "Commercial forecast API must be an HTTP loopback /api/v1 URL."
            )
        try:
            is_loopback = host.lower() == "localhost" or ipaddress.ip_address(
                host
            ).is_loopback
        except ValueError:
            is_loopback = False
        if not is_loopback:
            raise ValueError(
                "Commercial forecast API must resolve to localhost or a loopback IP."
            )
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Commercial forecast API port is invalid.")
        return base_url.rstrip("/")

    def _get_data(self, path: str) -> Any:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener.open(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                status_code = response.status
        except urllib.error.HTTPError as exc:
            code = "BACKEND_NOT_FOUND" if exc.code == 404 else "BACKEND_HTTP_ERROR"
            raise ForecastAPIError(
                code,
                f"Commercial forecast backend returned HTTP {exc.code}.",
                retryable=exc.code >= 500,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ForecastAPIError(
                "BACKEND_UNAVAILABLE",
                "Commercial forecast backend is unavailable or timed out.",
                retryable=True,
            ) from exc

        if status_code != 200:
            raise ForecastAPIError(
                "BACKEND_HTTP_ERROR",
                f"Commercial forecast backend returned HTTP {status_code}.",
                retryable=status_code >= 500,
            )
        if len(body) > MAX_RESPONSE_BYTES:
            raise ForecastAPIError(
                "BACKEND_RESPONSE_TOO_LARGE",
                "Commercial forecast backend response exceeded the size limit.",
                status="failed",
            )
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ForecastAPIError(
                "BACKEND_RESPONSE_INVALID",
                "Commercial forecast backend returned invalid JSON.",
                status="failed",
            ) from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ForecastAPIError(
                "BACKEND_RESPONSE_INVALID",
                "Commercial forecast backend returned an invalid response envelope.",
                status="failed",
            )
        if "data" not in payload:
            raise ForecastAPIError(
                "BACKEND_RESPONSE_INVALID",
                "Commercial forecast backend response has no data field.",
                status="failed",
            )
        return payload["data"]

    @staticmethod
    def _error_observation(error: ForecastAPIError) -> ToolObservation:
        return ToolObservation(
            status=error.status,
            error=AgentError(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
            ),
        )

    def _model_status(self) -> dict[str, Any]:
        data = self._get_data("/models/commercial-building-forecast/status")
        if not isinstance(data, dict):
            raise ForecastAPIError(
                "BACKEND_RESPONSE_INVALID",
                "Commercial model status response is malformed.",
                status="failed",
            )
        if (
            data.get("status") != "ready"
            or data.get("is_demo") is not False
            or not isinstance(data.get("dataset"), dict)
            or data["dataset"].get("available") is not True
            or not isinstance(data["dataset"].get("name"), str)
            or not 1 <= len(data["dataset"]["name"]) <= 250
            or not isinstance(data.get("model_name"), str)
            or not 1 <= len(data["model_name"]) <= 250
            or not isinstance(data.get("model_version"), str)
            or not 1 <= len(data["model_version"]) <= 128
            or data["model_version"] in {"unknown", "not_deployed"}
            or not isinstance(data.get("provider"), str)
            or not 1 <= len(data["provider"]) <= 128
            or data["provider"] == "development_mock_v1"
            or not isinstance(data.get("model_alias"), str)
            or not 1 <= len(data["model_alias"]) <= 128
        ):
            error_message = data.get("error")
            if not isinstance(error_message, str) or not error_message:
                error_message = (
                    "A trained Commercial forecast model and dataset are required."
                )
            raise ForecastAPIError(
                "MODEL_UNAVAILABLE",
                error_message[:1000],
            )
        return data

    def get_commercial_buildings(self, limit: int = 20) -> ToolObservation:
        if isinstance(limit, bool) or not 1 <= limit <= 50:
            return self._error_observation(
                ForecastAPIError(
                    "TOOL_INPUT_INVALID",
                    "Building list limit must be between 1 and 50.",
                    status="failed",
                )
            )
        try:
            model = self._model_status()
            buildings = self._get_data("/entities/commercial")
        except ForecastAPIError as exc:
            return self._error_observation(exc)
        if not isinstance(buildings, list):
            return self._error_observation(
                ForecastAPIError(
                    "BACKEND_RESPONSE_INVALID",
                    "Commercial building list response is malformed.",
                    status="failed",
                )
            )
        items = [
            {
                "building_id": building.get("buildingId"),
                "site_id": building.get("siteId"),
                "building_type": building.get("buildingType"),
                "primary_space_usage": building.get("primarySpaceUsage"),
                "last_timestamp": building.get("lastTimestamp"),
            }
            for building in buildings[:limit]
            if isinstance(building, dict)
            and isinstance(building.get("buildingId"), str)
            and BUILDING_ID_PATTERN.fullmatch(building["buildingId"])
        ]
        if not items:
            return ToolObservation(
                status="unavailable",
                error=AgentError(
                    code="DATA_NOT_AVAILABLE",
                    message="No Commercial buildings are available in the forecast dataset.",
                ),
            )
        return ToolObservation(
            status="available",
            findings=(
                f"Found {len(items)} Commercial building(s) in the configured forecast dataset.",
            ),
            data={"buildings": items},
            evidence_refs=(
                EvidenceRef(
                    source_id=model["model_name"],
                    source_type="trained_forecast_model",
                    locator=(
                        f"version:{model['model_version']};"
                        f"alias:{model['model_alias']}"
                    ),
                    excerpt=(
                        "This registered Commercial model supports the listed "
                        "dataset building identifiers."
                    ),
                ),
                EvidenceRef(
                    source_id=model["dataset"]["name"],
                    source_type="commercial_forecast_dataset",
                    locator="bounded serving sample",
                    excerpt=(
                        f"{len(items)} building identifiers returned from the "
                        "Commercial forecast dataset."
                    ),
                ),
            ),
            assumptions=(
                "These dataset building IDs are not factory IDs or a tenant registry.",
            ),
        )

    def get_peak_forecast(
        self,
        factory_id: str | None,
        goal: str,
        building_id: str | None = None,
    ) -> ToolObservation:
        del factory_id, goal
        if building_id is None or not BUILDING_ID_PATTERN.fullmatch(building_id):
            return self._error_observation(
                ForecastAPIError(
                    "BUILDING_ID_REQUIRED",
                    "Provide a valid Commercial building ID; factory_id is not a building ID.",
                )
            )
        try:
            model = self._model_status()
            forecast = self._get_data(
                "/dashboard/commercial?"
                + urllib.parse.urlencode(
                    {
                        "tab": "building",
                        "time_range": "1D",
                        "building_id": building_id,
                    }
                )
            )
        except ForecastAPIError as exc:
            return self._error_observation(exc)

        if not isinstance(forecast, dict):
            return self._error_observation(
                ForecastAPIError(
                    "BACKEND_RESPONSE_INVALID",
                    "Commercial forecast response is malformed.",
                    status="failed",
                )
            )
        predicted_peak = forecast.get("predictedPeak")
        if (
            isinstance(predicted_peak, bool)
            or not isinstance(predicted_peak, (int, float))
            or not math.isfinite(predicted_peak)
            or predicted_peak < 0
            or forecast.get("buildingId") != building_id
            or forecast.get("unit") != "kW"
            or not isinstance(forecast.get("predictedPeakTimestamp"), str)
            or not 1 <= len(forecast["predictedPeakTimestamp"]) <= 100
            or not isinstance(forecast.get("dataPeriod"), str)
            or not 1 <= len(forecast["dataPeriod"]) <= 1000
        ):
            return self._error_observation(
                ForecastAPIError(
                    "INVALID_MODEL_OUTPUT",
                    "Commercial forecast response did not match the expected building, unit, and peak fields.",
                    status="failed",
                )
            )

        dataset = model["dataset"]
        model_version = model["model_version"]
        dataset_name = dataset.get("name")
        if (
            not isinstance(dataset_name, str)
            or not 1 <= len(dataset_name) <= 250
        ):
            return self._error_observation(
                ForecastAPIError(
                    "BACKEND_RESPONSE_INVALID",
                    "Commercial forecast provenance metadata is incomplete.",
                    status="failed",
                )
            )

        model_summary = (
            f"{model['model_name']} "
            f"version {model_version} via {model.get('provider', 'unknown provider')}."
        )
        dataset_summary = (
            f"{dataset_name}; {forecast['dataPeriod']} "
            "This is a historical dataset replay, not live telemetry."
        )
        return ToolObservation(
            status="available",
            findings=(
                f"Building {building_id} predicted peak: {predicted_peak:g} kW "
                f"at {forecast['predictedPeakTimestamp']}. {forecast['dataPeriod']}",
            ),
            data={
                "building_id": building_id,
                "prediction_scope": "historical_gold_replay",
                "predicted_peak_kw": predicted_peak,
                "predicted_peak_timestamp": forecast["predictedPeakTimestamp"],
                "forecast_window": forecast["dataPeriod"],
                "model": {
                    "name": model.get("model_name"),
                    "version": model_version,
                    "alias": model.get("model_alias"),
                    "provider": model.get("provider"),
                },
                "dataset": {
                    "name": dataset_name,
                    "available": True,
                },
                "is_live": False,
            },
            evidence_refs=(
                EvidenceRef(
                    source_id=model["model_name"],
                    source_type="trained_forecast_model",
                    locator=f"version:{model_version};alias:{model.get('model_alias')}",
                    excerpt=model_summary,
                ),
                EvidenceRef(
                    source_id=dataset_name,
                    source_type="commercial_forecast_dataset",
                    locator=f"building:{building_id}",
                    excerpt=dataset_summary,
                ),
            ),
            assumptions=(
                "Forecast values are a historical replay from the configured Gold dataset and are not current live telemetry.",
            ),
        )
