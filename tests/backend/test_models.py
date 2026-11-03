"""Tests for the model catalog and gold-backed customer bill inference."""

from __future__ import annotations

from flask.testing import FlaskClient

from app import create_app
from app.config import TestingConfig
from app.providers.trained_forecast_provider import TrainedForecastProvider


def test_model_catalog_reports_gold_dataset(client: FlaskClient):
    response = client.get("/api/v1/models")

    assert response.status_code == 200
    models = response.get_json()["data"]["models"]
    model = models[0]
    assert model["modelId"] == "customer-bill-prediction"
    assert model["dataset"]["rows"] == 3600
    assert model["dataset"]["entities"] == 100
    assert model["status"] == "configured"
    segmentation = next(
        model
        for model in models
        if model["modelId"] == "government-customer-segmentation"
    )
    assert [
        model["modelId"]
        for model in models
        if model["modelId"] == "government-customer-segmentation"
    ] == ["government-customer-segmentation"]
    assert segmentation["status"] in {"configured", "unavailable"}
    assert segmentation["provider"] == "published_artifacts"
    forecasts = {
        model["modelId"]: model
        for model in models
        if model["modelId"]
        in {"commercial-building-forecast", "government-load-forecast"}
    }
    assert set(forecasts) == {
        "commercial-building-forecast",
        "government-load-forecast",
    }
    assert all(
        model["provider"] == "development_mock_v1"
        and "Not connected to MLflow" in model["error"]
        for model in forecasts.values()
    )


def test_model_catalog_uses_trained_forecast_provider(monkeypatch):
    class MLflowTestingConfig(TestingConfig):
        MODEL_PROVIDER = "mlflow"
        MLFLOW_TRACKING_URI = "http://mlflow.test"

    monkeypatch.setattr(
        TrainedForecastProvider,
        "get_horizon_model_status",
        lambda self: {
            "commercial": {
                "status": "ready",
                "provider": "mlflow_registered_alias",
                "model_version": "3",
                "model_alias": "champion",
            },
            "government": {
                "status": "ready",
                "provider": "mlflow_registered_alias+local_bundle",
                "model_version": "7",
                "model_alias": "champion",
            },
        },
    )
    app = create_app(config_class=MLflowTestingConfig)

    response = app.test_client().get("/api/v1/models")

    assert response.status_code == 200
    forecasts = {
        model["modelId"]: model
        for model in response.get_json()["data"]["models"]
        if model["modelId"]
        in {"commercial-building-forecast", "government-load-forecast"}
    }
    assert forecasts["commercial-building-forecast"]["status"] == "configured"
    assert forecasts["commercial-building-forecast"]["modelVersion"] == "3"
    assert forecasts["commercial-building-forecast"]["selectedModel"] == "champion"
    assert forecasts["government-load-forecast"]["status"] == "configured"
    assert forecasts["government-load-forecast"]["modelVersion"] == "7"
    assert forecasts["government-load-forecast"]["selectedModel"] == "champion"


def test_model_catalog_includes_government_customer_segmentation(
    client: FlaskClient,
):
    response = client.get("/api/v1/models")

    assert response.status_code == 200
    models = response.get_json()["data"]["models"]
    model_ids = [model["modelId"] for model in models]
    assert model_ids == [
        "customer-bill-prediction",
        "commercial-building-forecast",
        "government-load-forecast",
        "government-customer-segmentation",
        "anomaly-prediction",
    ]
    segmentation = next(
        model
        for model in models
        if model["modelId"] == "government-customer-segmentation"
    )
    assert segmentation["name"] == "Government Customer Segmentation"
    assert segmentation["status"] in {"configured", "unavailable"}
    if segmentation["status"] == "configured":
        assert segmentation["assignmentCount"] > 0
        assert segmentation["trainedModelCount"] > 0
        assert segmentation["modelVersion"].startswith("segmentation-v1-")
    else:
        assert segmentation["error"]


def test_model_catalog_uses_forecast_provider_status(
    client: FlaskClient, monkeypatch
):
    monkeypatch.setattr(
        client.application.extensions["model_provider"],
        "get_model_status",
        lambda: {
            "models": {
                "commercial": {
                    "status": "ready",
                    "model_version": "19",
                    "provider": "mlflow_registered_alias",
                    "test_metrics": {"rmse_kwh": 30.2},
                },
                "government": {
                    "status": "ready",
                    "model_version": "20",
                    "provider": "mlflow_registered_alias",
                    "test_metrics": {"rmse_kwh": 1068.8},
                },
            },
        },
    )

    response = client.get("/api/v1/models")

    assert response.status_code == 200
    models = {
        model["modelId"]: model
        for model in response.get_json()["data"]["models"]
    }
    assert models["commercial-building-forecast"]["status"] == "configured"
    assert models["commercial-building-forecast"]["modelVersion"] == "19"
    assert models["government-load-forecast"]["status"] == "configured"
    assert models["government-load-forecast"]["modelVersion"] == "20"


def test_customer_bill_model_replays_gold_record(client: FlaskClient):
    records_response = client.get(
        "/api/v1/models/customer-bill-prediction/records?limit=1"
    )
    assert records_response.status_code == 200
    record = records_response.get_json()["data"]["items"][0]

    months_response = client.get(
        f"/api/v1/models/customer-bill-prediction/records/{record['entityId']}"
    )
    assert months_response.status_code == 200
    months = months_response.get_json()["data"]
    assert len(months) == 36

    prediction_response = client.post(
        "/api/v1/models/customer-bill-prediction/predict",
        json={
            "entity_id": record["entityId"],
            "month_start": record["monthStart"],
            "cutoff_day": record["cutoffDay"],
        },
    )
    assert prediction_response.status_code == 200
    prediction = prediction_response.get_json()["data"]
    assert prediction["isDemo"] is False
    assert prediction["provider"] == "local_artifact"
    assert prediction["predictedMonthEndKwh"] > 0
    assert prediction["actualMonthEndKwh"] == record["actualMonthKwh"]
    assert prediction["absoluteErrorKwh"] >= 0


def test_residential_building_profile_returns_dataset_identity_fields(
    client: FlaskClient,
):
    record = client.get(
        "/api/v1/models/customer-bill-prediction/records?limit=1"
    ).get_json()["data"]["items"][0]
    profile = client.get(
        f"/api/v1/models/customer-bill-prediction/profile/{record['entityId']}"
    )

    assert profile.status_code == 200
    data = profile.get_json()["data"]
    assert data["entityId"] == record["entityId"]
    assert data["buildingType"]
    assert data["buildingAreaM2"] > 0


def test_customer_bill_model_validates_inputs(client: FlaskClient):
    response = client.post(
        "/api/v1/models/customer-bill-prediction/predict",
        json={"entity_id": 1, "month_start": "not-a-month", "cutoff_day": 7},
    )

    assert response.status_code == 422
    assert response.get_json()["success"] is False


def test_residential_gold_history_uses_latest_monthly_cutoff(client: FlaskClient):
    response = client.get(
        "/api/v1/models/customer-bill-prediction/history?time_range=ALL"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["monthsReturned"] == 12
    assert data["entityCount"] == 100
    assert data["dataset"]["sourceRows"] == 3600
    assert data["dataset"]["cutoffDay"] == 21
    assert data["model"]["name"] == "naive_month_projection"
    assert len(data["model"]["features"]) == 25
    assert len(data["history"]) == 12
    assert all(point["entityCount"] == 100 for point in data["history"])
    assert all(point["averageActualKwh"] > 0 for point in data["history"])


def test_residential_gold_history_filters_to_selected_entity(client: FlaskClient):
    records_response = client.get(
        "/api/v1/models/customer-bill-prediction/records?limit=1"
    )
    entity_id = records_response.get_json()["data"]["items"][0]["entityId"]

    response = client.get(
        f"/api/v1/models/customer-bill-prediction/history"
        f"?time_range=ALL&entity_id={entity_id}"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["entityId"] == entity_id
    assert data["entityCount"] == 1
    assert len(data["history"]) == data["monthsReturned"] == 12
    assert all(point["entityCount"] == 1 for point in data["history"])

    entity_months = client.get(
        f"/api/v1/models/customer-bill-prediction/records/{entity_id}"
    ).get_json()["data"]
    latest_by_month = {}
    for record in entity_months:
        current = latest_by_month.get(record["monthStart"])
        if current is None or record["cutoffDay"] > current["cutoffDay"]:
            latest_by_month[record["monthStart"]] = record
    assert data["history"][-1]["averageActualKwh"] == latest_by_month[
        data["history"][-1]["monthStart"]
    ]["actualMonthKwh"]


def test_residential_gold_history_range_validation(client: FlaskClient):
    response = client.get(
        "/api/v1/models/customer-bill-prediction/history?time_range=30D"
    )

    assert response.status_code == 422
    assert response.get_json()["success"] is False


def test_residential_gold_history_filters_to_selected_months(client: FlaskClient):
    all_response = client.get(
        "/api/v1/models/customer-bill-prediction/history?time_range=ALL"
    )
    assert all_response.status_code == 200
    all_history = all_response.get_json()["data"]["history"]
    assert all_history[0]["monthOverMonthChangePercent"] is None
    months = {point["monthStart"]: point for point in all_history}
    september = months["2018-09-01"]["averageActualKwh"]
    october = months["2018-10-01"]["averageActualKwh"]
    expected_change = (october - september) / september * 100

    response = client.get(
        "/api/v1/models/customer-bill-prediction/history?time_range=3M"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["monthsReturned"] == 3
    assert data["history"][0]["monthStart"] == "2018-10-01"
    assert data["history"][-1]["monthStart"] == "2018-12-01"
    assert (
        abs(
            data["history"][0]["monthOverMonthChangePercent"]
            - expected_change
        )
        < 1e-8
    )
