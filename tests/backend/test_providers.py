"""Tests for provider behavior, demo annotations, and MLflow adapter safety."""

from __future__ import annotations

import pytest
from app.providers.mock_model_provider import DevelopmentModelProvider
from app.providers.mlflow_adapter import MLflowModelAdapter, MLflowIntegrationError


def test_development_provider_explicit_demo():
    """Verify development provider explicitly annotates demo mode."""
    provider = DevelopmentModelProvider()
    res = provider.predict(
        model_name="residential",
        entity_id="METER-1000",
        features={"elapsed_days": 19, "daily_avg_kwh": 15.0},
        actual_kwh_so_far=280.0,
    )
    assert res.is_demo is True
    assert res.provider == "development_mock_v1"
    assert any("DEMO PREDICTION" in c for c in res.caveats)


def test_mlflow_adapter_unconfigured_error():
    """Verify MLflow adapter does not silently fall back to mock data when server is unavailable."""
    adapter = MLflowModelAdapter(tracking_uri="")
    assert adapter.is_configured() is False
    assert adapter.get_model_status()["status"] == "unavailable"

    with pytest.raises(MLflowIntegrationError) as exc_info:
        adapter.predict(
            model_name="commercial",
            entity_id="Panther_office_1",
            features={},
        )
    assert "MLflow is not configured" in str(exc_info.value)


def test_mlflow_adapter_customer_prediction_contract():
    """Verify the adapter converts predicted month energy into remaining energy."""
    class FakeModel:
        def predict(self, frame):
            assert frame.iloc[0]["cumulative_energy_kwh"] == 42.0
            return [120.0]

    adapter = MLflowModelAdapter(
        tracking_uri="http://mlflow.example",
        model_name="customer-bill-prediction",
        tariff_inr_per_kwh=2.5,
    )
    adapter._model = FakeModel()
    adapter._model_version = "7"
    adapter._input_names = ["cumulative_energy_kwh"]

    result = adapter.predict(
        model_name="residential",
        entity_id="building-1",
        features={"cumulative_energy_kwh": 42.0},
    )

    assert result.prediction == 78.0
    assert result.estimated_month_end_kwh == 120.0
    assert result.estimated_month_end_bill_inr == 300.0
    assert result.model_version == "7"
    assert result.is_demo is False


def test_mlflow_adapter_rejects_other_model_scopes():
    adapter = MLflowModelAdapter(tracking_uri="http://mlflow.example")
    with pytest.raises(MLflowIntegrationError, match="customer bill predictions only"):
        adapter.predict("commercial", "building-1", {})
