"""Tests for the model catalog and gold-backed customer bill inference."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_model_catalog_reports_gold_dataset(client: FlaskClient):
    response = client.get("/api/v1/models")

    assert response.status_code == 200
    model = response.get_json()["data"]["models"][0]
    assert model["modelId"] == "customer-bill-prediction"
    assert model["dataset"]["rows"] == 3600
    assert model["dataset"]["entities"] == 100
    assert model["status"] == "configured"


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


def test_residential_gold_history_range_validation(client: FlaskClient):
    response = client.get(
        "/api/v1/models/customer-bill-prediction/history?time_range=30D"
    )

    assert response.status_code == 422
    assert response.get_json()["success"] is False


def test_residential_gold_history_filters_to_selected_months(client: FlaskClient):
    response = client.get(
        "/api/v1/models/customer-bill-prediction/history?time_range=3M"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["monthsReturned"] == 3
    assert data["history"][0]["monthStart"] == "2018-10-01"
    assert data["history"][-1]["monthStart"] == "2018-12-01"
