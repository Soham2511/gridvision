"""MLflow adapter for the registered customer bill prediction model."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

from app.providers.model_provider import BaseModelProvider, PredictionOutput

logger = logging.getLogger("gridvision.mlflow")


class MLflowIntegrationError(RuntimeError):
    """Raised when an MLflow registry or serving endpoint is unavailable."""


class MLflowModelAdapter(BaseModelProvider):
    """Load the customer bill model from its MLflow registry alias."""

    PROVIDER_NAME = "mlflow_production_adapter"

    def __init__(
        self,
        tracking_uri: str | None = None,
        model_alias: str = "champion",
        model_name: str | None = None,
        tariff_inr_per_kwh: float | None = None,
    ) -> None:
        self.tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "")
        self.model_alias = model_alias or os.getenv("MLFLOW_MODEL_ALIAS", "champion")
        self.model_name = model_name or os.getenv(
            "MLFLOW_MODEL_NAME", "customer-bill-prediction"
        )
        self.tariff_inr_per_kwh = tariff_inr_per_kwh or float(
            os.getenv("CUSTOMER_TARIFF_INR_PER_KWH", "10.0")
        )
        self._model: Any | None = None
        self._model_version: str | None = None
        self._run_id: str | None = None
        self._input_names: list[str] | None = None
        self._input_types: dict[str, str] = {}

    def get_current_run_id(self) -> str | None:
        """Return the MLflow run ID associated with the active champion model."""
        try:
            self._load_model()
            return self._run_id
        except Exception:
            return None

    def _load_model(self, force_reload: bool = False) -> Any:
        if not self.tracking_uri:
            raise MLflowIntegrationError(
                "MLflow is not configured: MLFLOW_TRACKING_URI is required to load "
                "the registered customer bill model."
            )
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            mlflow.set_tracking_uri(self.tracking_uri)
            client = MlflowClient()
            version = client.get_model_version_by_alias(
                self.model_name, self.model_alias
            )
            target_version_str = str(version.version)

            if (
                not force_reload
                and self._model is not None
                and self._model_version == target_version_str
            ):
                return self._model

            model_uri = f"models:/{self.model_name}@{self.model_alias}"
            model = mlflow.pyfunc.load_model(model_uri)
            schema = model.metadata.get_input_schema()
            if schema is None:
                raise MLflowIntegrationError(
                    f"Registered model {model_uri} has no input signature."
                )
            self._input_names = schema.input_names()
            self._input_types = {
                field.name: field.type.name for field in schema.inputs
            }
            self._model_version = target_version_str
            self._run_id = getattr(version, "run_id", None)
            self._model = model
            return model
        except MLflowIntegrationError:
            raise
        except Exception as exc:
            raise MLflowIntegrationError(
                f"Unable to load MLflow model {self.model_name}@{self.model_alias}: {exc}"
            ) from exc

    def is_configured(self) -> bool:
        return bool(self.tracking_uri and self.model_name and self.model_alias)

    def predict(
        self,
        model_name: str,
        entity_id: str,
        features: dict[str, Any],
        actual_kwh_so_far: float | None = None,
        context: str = "future_forecast",
    ) -> PredictionOutput:
        if not self.tracking_uri:
            raise MLflowIntegrationError(
                "MLflow is not configured: MLFLOW_TRACKING_URI is required."
            )
        if model_name.lower().replace("-", "_") not in {
            "residential",
            "customer_bill",
            "customer_bill_prediction",
        }:
            raise MLflowIntegrationError(
                "The configured MLflow model serves customer bill predictions only."
            )
        model = self._load_model()
        if self._input_names is None:
            raise MLflowIntegrationError("MLflow model input schema was not loaded.")
        missing = [name for name in self._input_names if name not in features]
        if missing:
            raise MLflowIntegrationError(
                f"Prediction input is missing model features: {missing}"
            )
        model_input = pd.DataFrame(
            [{name: features[name] for name in self._input_names}],
            columns=self._input_names,
        )
        numeric_types = {
            "integer": np.int32,
            "long": np.int64,
            "float": np.float32,
            "double": np.float64,
        }
        for name, input_type in self._input_types.items():
            if input_type in numeric_types:
                try:
                    model_input[name] = pd.to_numeric(
                        model_input[name], errors="raise"
                    ).astype(numeric_types[input_type])
                except (TypeError, ValueError, OverflowError) as exc:
                    raise MLflowIntegrationError(
                        f"Prediction feature {name!r} cannot be converted to "
                        f"the registered {input_type} input type."
                    ) from exc
        try:
            predicted_month_total = float(model.predict(model_input)[0])
        except Exception as exc:
            raise MLflowIntegrationError(f"MLflow prediction failed: {exc}") from exc
        observed = (
            actual_kwh_so_far
            if actual_kwh_so_far is not None
            else features.get("cumulative_energy_kwh")
        )
        observed_kwh = float(observed) if observed is not None else None
        predicted_remaining = (
            max(0.0, predicted_month_total - observed_kwh)
            if observed_kwh is not None
            else predicted_month_total
        )
        return PredictionOutput(
            entity_id=entity_id,
            prediction=predicted_remaining,
            target_name="target_remaining_kwh",
            target_unit="kWh",
            model_name=self.model_name,
            model_version=self._model_version or "unknown",
            is_demo=False,
            provider=self.PROVIDER_NAME,
            evaluation_status="mlflow_registered_champion",
            prediction_status="valid",
            actual_kwh_so_far=observed_kwh,
            estimated_month_end_kwh=predicted_month_total,
            estimated_month_end_bill_inr=round(
                predicted_month_total * self.tariff_inr_per_kwh, 2
            ),
            tariff_inr_per_kwh=self.tariff_inr_per_kwh,
            caveats=[
                "Estimated from monthly energy labels and a configured flat tariff.",
                "The source data does not contain customer billing-cycle dates or tariff plans.",
            ],
        )

    def predict_horizon(
        self,
        sector: str,
        entity_id: str,
        horizon_count: int = 24,
    ) -> list[dict[str, Any]]:
        from app.providers.mock_model_provider import DevelopmentModelProvider

        return DevelopmentModelProvider().predict_horizon(
            sector=sector,
            entity_id=entity_id,
            horizon_count=horizon_count,
        )

    def get_model_status(self) -> dict[str, Any]:
        status = {
            "provider": self.PROVIDER_NAME,
            "status": "configured" if self.is_configured() else "unavailable",
            "is_demo": False,
            "tracking_uri": self.tracking_uri or "not_configured",
            "model_name": self.model_name,
            "model_alias": self.model_alias,
            "model_version": self._model_version,
            "requirements": {
                "MLFLOW_TRACKING_URI": "Required MLflow tracking server URI",
                "MLFLOW_MODEL_NAME": f"Current: {self.model_name}",
                "MLFLOW_MODEL_ALIAS": f"Current: {self.model_alias}",
            },
        }
        if not self.is_configured():
            status["error"] = "MLFLOW_TRACKING_URI is not configured."
            return status
        try:
            self._load_model()
            status["status"] = "ready"
            status["model_version"] = self._model_version
        except MLflowIntegrationError as exc:
            logger.warning("MLflow customer model is not ready: %s", exc)
            status["status"] = "unavailable"
            status["error"] = str(exc)
        return status
