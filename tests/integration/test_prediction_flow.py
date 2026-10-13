"""End-to-end checks against the supplied local model artifacts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.main import create_app
from app.models.registry import ModelRegistry
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def api_client() -> Iterator[TestClient]:
    """Start the API with its normal artifact-verification lifespan."""
    with TestClient(create_app(PROJECT_ROOT)) as client:
        yield client


def _valid_payload(model_name: str) -> dict[str, Any]:
    """Build a type-valid one-row request from the model's actual feature schema."""
    bundle = ModelRegistry(PROJECT_ROOT).get(model_name)
    features: dict[str, Any] = {name: 0.0 for name in bundle.features}
    if model_name == "commercial":
        for name, palette in zip(
            bundle.metadata["categorical_features"],
            bundle.estimator.booster_.pandas_categorical,
            strict=True,
        ):
            features[name] = palette[0]
    payload: dict[str, Any] = {
        "entity_id": "test-entity",
        "forecast_timestamp": "2017-12-31T23:00:00",
        "features": features,
        "context": "retrospective_gold_replay",
    }
    if model_name == "residential":
        payload["actual_kwh_so_far"] = 0.0
    return payload


@pytest.mark.parametrize("model_name", ["residential", "commercial", "government"])
def test_prediction_routes_load_and_infer(
    api_client: TestClient, model_name: str
) -> None:
    """Each endpoint returns a finite prediction and honest model status."""
    response = api_client.post(
        f"/api/v1/{model_name}/predict", json=_valid_payload(model_name)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["prediction"], float)
    assert body["model_version"].startswith("unversioned (sha256:")
    assert body["evaluation_status"] == "not_evaluated"
    assert body["context"] == "retrospective_gold_replay"
    assert body["prediction_status"] in {"valid", "invalid_negative_energy"}


def test_prediction_rejects_missing_features(api_client: TestClient) -> None:
    """Feature omissions fail validation rather than returning defaults."""
    payload = _valid_payload("commercial")
    payload["features"].pop("sqm")

    response = api_client.post("/api/v1/commercial/predict", json=payload)

    assert response.status_code == 422
    assert "sqm" in response.json()["detail"]


def test_prediction_rejects_unseen_categories(api_client: TestClient) -> None:
    """Commercial predictions cannot silently map unknown categories."""
    payload = _valid_payload("commercial")
    payload["features"]["building_id"] = "unseen-building"

    response = api_client.post("/api/v1/commercial/predict", json=payload)

    assert response.status_code == 422
    assert "Unsupported category" in response.json()["detail"]


def test_readiness_requires_all_verified_models(api_client: TestClient) -> None:
    """Readiness reports all three loaded artifacts."""
    response = api_client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["models_loaded"] == [
        "commercial",
        "government",
        "residential",
    ]
