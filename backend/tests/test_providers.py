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
