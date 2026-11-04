"""Fail-closed runtime provider behavior and test-only fixture selection."""

from __future__ import annotations

from app import create_app
from app.config import DevelopmentConfig, TestingConfig


def test_development_runtime_does_not_select_sample_or_mock_providers():
    app = create_app(DevelopmentConfig)

    assert type(app.extensions["data_provider"]).__name__ == "UnavailableDataProvider"
    assert type(app.extensions["model_provider"]).__name__ == "UnavailableModelProvider"


def test_runtime_sample_setting_is_rejected_without_failing_startup():
    class UnsafeRuntimeConfig(DevelopmentConfig):
        DATA_PROVIDER = "sample"
        MODEL_PROVIDER = "development"

    app = create_app(UnsafeRuntimeConfig)

    assert type(app.extensions["data_provider"]).__name__ == "UnavailableDataProvider"
    assert type(app.extensions["model_provider"]).__name__ == "UnavailableModelProvider"
    assert app.test_client().get("/api/v1/health/live").status_code == 200


def test_unavailable_provider_preserves_envelope_and_does_not_block_health():
    client = create_app(DevelopmentConfig).test_client()

    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.get_json()["data"]["status"] == "alive"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    ready_data = ready.get_json()["data"]
    assert ready_data["status"] == "ready"
    assert ready_data["optional_dependencies_ready"] is False
    assert ready_data["data_availability"] == "degraded"

    response = client.get("/api/v1/entities/residential")
    assert response.status_code == 503
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "DATA_SOURCE_UNAVAILABLE"
    assert body["error"]["details"]["availability"] == "unavailable"


def test_optional_data_failure_does_not_break_source_independent_health_summary():
    client = create_app(DevelopmentConfig).test_client()

    response = client.get("/api/v1/platform/health")
    assert response.status_code == 200
    assert response.get_json()["data"]["availability"]["status"] == "unavailable"


def test_forecast_and_unapproved_dataset_routes_return_typed_unavailable_errors():
    class NoApprovedSourcesConfig(DevelopmentConfig):
        APPROVED_DATA_SOURCES = ()

    client = create_app(NoApprovedSourcesConfig).test_client()

    for path in (
        "/api/v1/forecast/residential/382",
        "/api/v1/models/customer-bill-prediction/records?limit=1",
        "/api/v1/government/segmentation/overview",
    ):
        response = client.get(path)
        assert response.status_code == 503
        error = response.get_json()["error"]
        assert error["code"] == "DATA_SOURCE_UNAVAILABLE"
        assert error["details"]["availability"] in {
            "unavailable",
            "provenance_unverified",
        }


def test_sample_and_development_providers_remain_isolated_to_testing_config():
    app = create_app(TestingConfig)
    assert type(app.extensions["data_provider"]).__name__ == "SampleDataProvider"
    assert type(app.extensions["model_provider"]).__name__ == "DevelopmentModelProvider"


def test_runtime_anomaly_path_is_restricted_to_the_approved_synthetic_dataset():
    class UnapprovedAnomalyConfig(DevelopmentConfig):
        APPROVED_DATA_SOURCES = ("anomaly_synthetic_2019",)
        ANOMALY_DATASET_PATH = "/private/tmp/unverified_anomaly_source.parquet"

    response = create_app(UnapprovedAnomalyConfig).test_client().get(
        "/api/v1/models/anomaly-prediction"
    )
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "DATA_SOURCE_UNAVAILABLE"
    assert response.get_json()["error"]["details"]["availability"] == "provenance_unverified"
