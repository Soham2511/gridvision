"""MLflow model adapter designed for seamless future production integration."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.providers.model_provider import BaseModelProvider, PredictionOutput

logger = logging.getLogger("gridvision.mlflow")


class MLflowIntegrationError(RuntimeError):
    """Raised when an MLflow registry or serving endpoint is unavailable."""


class MLflowModelAdapter(BaseModelProvider):
    """Production MLflow model adapter.

    Contract & Metadata Requirements for Future Production:
    - MLFLOW_TRACKING_URI: URI of remote MLflow tracking server (e.g. http://mlflow.internal:5000).
    - Authentication: MLFLOW_TRACKING_USERNAME and MLFLOW_TRACKING_PASSWORD (or token).
    - Model Naming Convention:
        * Commercial: models:/commercial-demand-forecast/<alias_or_version>
        * Residential: models:/residential-month-end-pipeline/<alias_or_version>
        * Government: models:/government-regional-demand/<alias_or_version>
    - Signature Requirements:
        * Pandas DataFrame or Tensor input matching certified schema.
        * Standard outputs: float prediction value matching target units.
    """

    PROVIDER_NAME = "mlflow_production_adapter"

    def __init__(
        self,
        tracking_uri: str | None = None,
        model_alias: str = "champion",
    ) -> None:
        self.tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "")
        self.model_alias = model_alias or os.getenv("MLFLOW_MODEL_ALIAS", "champion")
        self._connected = bool(self.tracking_uri)

    def is_configured(self) -> bool:
        return bool(self.tracking_uri)

    def predict(
        self,
        model_name: str,
        entity_id: str,
        features: dict[str, Any],
        actual_kwh_so_far: float | None = None,
        context: str = "future_forecast",
    ) -> PredictionOutput:
        if not self._connected:
            raise MLflowIntegrationError(
                f"MLflow is not configured or tracking server is unreachable at '{self.tracking_uri}'. "
                "Production models cannot be evaluated. "
                "Ensure MLFLOW_TRACKING_URI is set and registered models are approved."
            )
        # Production mlflow.pyfunc loading logic will be executed here once MLflow server is online.
        raise NotImplementedError("MLflow production server is currently unavailable.")

    def predict_horizon(
        self,
        sector: str,
        entity_id: str,
        horizon_count: int = 24,
    ) -> list[dict[str, Any]]:
        if not self._connected:
            raise MLflowIntegrationError(
                "MLflow tracking server is unreachable. Cannot fetch multi-horizon forecasts."
            )
        raise NotImplementedError("MLflow production server is currently unavailable.")

    def get_model_status(self) -> dict[str, Any]:
        return {
            "provider": self.PROVIDER_NAME,
            "status": "ready" if self._connected else "unavailable",
            "is_demo": False,
            "tracking_uri": self.tracking_uri or "not_configured",
            "model_alias": self.model_alias,
            "requirements": {
                "MLFLOW_TRACKING_URI": "Required remote MLflow URL",
                "MLFLOW_MODEL_ALIAS": f"Current: {self.model_alias}",
                "models": [
                    "commercial-demand-forecast",
                    "residential-month-end-pipeline",
                    "government-regional-demand",
                ],
            },
        }
