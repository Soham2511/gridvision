"""Tests for provider behavior, demo annotations, and MLflow adapter safety."""

from __future__ import annotations

import unittest
from app.providers.mock_model_provider import DevelopmentModelProvider
from app.providers.mlflow_adapter import MLflowModelAdapter, MLflowIntegrationError


class TestProviders(unittest.TestCase):
    def test_development_provider_explicit_demo(self):
        """Verify development provider explicitly annotates demo mode."""
        provider = DevelopmentModelProvider()
        res = provider.predict(
            model_name="residential",
            entity_id="METER-1000",
            features={"elapsed_days": 19, "daily_avg_kwh": 15.0},
            actual_kwh_so_far=280.0,
        )
        self.assertTrue(res.is_demo)
        self.assertEqual(res.provider, "development_mock_v1")
        self.assertTrue(any("DEMO PREDICTION" in c for c in res.caveats))

    def test_mlflow_adapter_unconfigured_error(self):
        """Verify MLflow adapter does not silently fall back to mock data when server is unavailable."""
        adapter = MLflowModelAdapter(tracking_uri="")
        self.assertFalse(adapter.is_configured())
        self.assertEqual(adapter.get_model_status()["status"], "unavailable")

        with self.assertRaises(MLflowIntegrationError) as ctx:
            adapter.predict(
                model_name="commercial",
                entity_id="Panther_office_1",
                features={},
            )
        self.assertIn("MLflow is not configured", str(ctx.exception))

    def test_mlflow_adapter_customer_prediction_contract(self):
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

        self.assertEqual(result.prediction, 78.0)
        self.assertEqual(result.estimated_month_end_kwh, 120.0)
        self.assertEqual(result.estimated_month_end_bill_inr, 300.0)
        self.assertEqual(result.model_version, "7")
        self.assertFalse(result.is_demo)

    def test_mlflow_adapter_rejects_other_model_scopes(self):
        adapter = MLflowModelAdapter(tracking_uri="http://mlflow.example")
        with self.assertRaises(MLflowIntegrationError):
            adapter.predict("commercial", "building-1", {})


if __name__ == "__main__":
    unittest.main()

