"""Tests for the trained Commercial forecast backend adapter."""

from __future__ import annotations

import json
import urllib.error

import pytest

from ai.commercial.tools.commercial_forecast_api import (
    CommercialForecastAPITools,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.status = 200
        self._body = json.dumps(
            {"success": True, "data": payload}
        ).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._body[:size]


class FakeOpener:
    def __init__(self, responses: list[object]) -> None:
        self._responses = iter(responses)
        self.requests: list[tuple[str, float]] = []

    def open(self, request, timeout: float) -> FakeResponse:
        self.requests.append((request.full_url, timeout))
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def _ready_status() -> dict:
    return {
        "status": "ready",
        "model_name": "gridvision-commercial-building-forecast",
        "model_version": "3",
        "model_alias": "champion",
        "provider": "mlflow_registered_alias",
        "is_demo": False,
        "dataset": {
            "name": "commercial_gold.parquet",
            "available": True,
        },
    }


def _forecast() -> dict:
    return {
        "buildingId": "101",
        "predictedPeak": 82.4,
        "predictedPeakTimestamp": "01 Jan 2018, 02:00 PM",
        "unit": "kW",
        "dataPeriod": (
            "Gold history: 01 Jan 2018 – 31 Dec 2018; "
            "Next 24 hours forecast through 01 Jan 2019."
        ),
    }


def _tools(
    monkeypatch,
    responses: list[object],
) -> tuple[CommercialForecastAPITools, FakeOpener]:
    opener = FakeOpener(responses)
    monkeypatch.setattr(
        "ai.commercial.tools.commercial_forecast_api.urllib.request.build_opener",
        lambda *handlers: opener,
    )
    return (
        CommercialForecastAPITools(
            "http://127.0.0.1:5000/api/v1",
            timeout_seconds=2.5,
        ),
        opener,
    )


def test_peak_forecast_returns_trained_model_dataset_and_replay_provenance(
    monkeypatch,
) -> None:
    tools, opener = _tools(monkeypatch, [_ready_status(), _forecast()])

    result = tools.get_peak_forecast(None, "Forecast next peak.", "101")

    assert result.status == "available"
    assert result.data["predicted_peak_kw"] == 82.4
    assert result.data["prediction_scope"] == "historical_gold_replay"
    assert result.data["model"]["version"] == "3"
    assert result.data["dataset"]["name"] == "commercial_gold.parquet"
    assert result.data["is_live"] is False
    assert "not current live telemetry" in result.assumptions[0]
    assert [ref.source_type for ref in result.evidence_refs] == [
        "trained_forecast_model",
        "commercial_forecast_dataset",
    ]
    assert "building_id=101" in opener.requests[1][0]
    assert all(timeout == 2.5 for _, timeout in opener.requests)


def test_building_list_is_bounded_and_uses_only_model_dataset_entities(
    monkeypatch,
) -> None:
    tools, opener = _tools(
        monkeypatch,
        [
            _ready_status(),
            [
                {
                    "buildingId": "101",
                    "siteId": "Grid 4",
                    "buildingType": "Office",
                    "primarySpaceUsage": "Office",
                    "lastTimestamp": "2018-12-31T23:00:00",
                    "latitude": 1.0,
                },
                {"buildingId": "102", "siteId": "Grid 5"},
            ],
        ],
    )

    result = tools.get_commercial_buildings(limit=1)

    assert result.status == "available"
    assert result.data["buildings"] == [
        {
            "building_id": "101",
            "site_id": "Grid 4",
            "building_type": "Office",
            "primary_space_usage": "Office",
            "last_timestamp": "2018-12-31T23:00:00",
        }
    ]
    assert [ref.source_type for ref in result.evidence_refs] == [
        "trained_forecast_model",
        "commercial_forecast_dataset",
    ]
    assert "not factory IDs" in result.assumptions[0]
    assert len(opener.requests) == 2
    assert "status" in opener.requests[0][0]
    assert "entities/commercial" in opener.requests[1][0]


def test_development_model_is_refused_before_forecast_request(monkeypatch) -> None:
    demo_status = {
        **_ready_status(),
        "status": "unavailable",
        "is_demo": True,
        "error": "Development mock provider is active.",
    }
    tools, opener = _tools(monkeypatch, [demo_status])

    result = tools.get_peak_forecast(None, "Forecast peak.", "101")

    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.code == "MODEL_UNAVAILABLE"
    assert "mock provider" in result.error.message
    assert len(opener.requests) == 1


def test_missing_building_id_is_explicit_and_does_not_call_backend(monkeypatch) -> None:
    tools, opener = _tools(monkeypatch, [])

    result = tools.get_peak_forecast("factory-1", "Forecast peak.")

    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.code == "BUILDING_ID_REQUIRED"
    assert not opener.requests


def test_backend_timeout_is_reported_as_retryable(monkeypatch) -> None:
    tools, _ = _tools(
        monkeypatch,
        [urllib.error.URLError(TimeoutError("timeout"))],
    )

    result = tools.get_peak_forecast(None, "Forecast peak.", "101")

    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.code == "BACKEND_UNAVAILABLE"
    assert result.error.retryable


def test_unknown_building_returns_unavailable_without_mock_fallback(
    monkeypatch,
) -> None:
    missing = urllib.error.HTTPError(
        "http://127.0.0.1:5000/api/v1/dashboard/commercial",
        404,
        "not found",
        {},
        None,
    )
    tools, opener = _tools(monkeypatch, [_ready_status(), missing])

    result = tools.get_peak_forecast(None, "Forecast peak.", "999")

    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.code == "BACKEND_NOT_FOUND"
    assert len(opener.requests) == 2


def test_invalid_or_remote_api_urls_are_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        "ai.commercial.tools.commercial_forecast_api.urllib.request.build_opener",
        lambda *handlers: FakeOpener([]),
    )

    for url in (
        "https://127.0.0.1/api/v1",
        "http://example.com/api/v1",
        "http://127.0.0.1/private",
        "http://127.0.0.1@attacker.com/api/v1",
    ):
        with pytest.raises(ValueError):
            CommercialForecastAPITools(url)


def test_malformed_model_output_does_not_become_a_success(monkeypatch) -> None:
    tools, _ = _tools(
        monkeypatch,
        [_ready_status(), {**_forecast(), "predictedPeak": float("nan")}],
    )

    result = tools.get_peak_forecast(None, "Forecast peak.", "101")

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_MODEL_OUTPUT"
