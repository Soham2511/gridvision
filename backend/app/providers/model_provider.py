"""Abstract base class interface for model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class PredictionOutput(BaseModel):
    """Standardized output schema for all model inferences."""

    model_config = ConfigDict(extra="ignore")

    entity_id: str
    prediction: float = Field(allow_inf_nan=False)
    target_name: str
    target_unit: str
    model_name: str
    model_version: str
    is_demo: bool = False
    provider: str
    evaluation_status: str
    prediction_status: str = "valid"
    actual_kwh_so_far: float | None = None
    estimated_month_end_kwh: float | None = None
    estimated_month_end_bill_inr: float | None = None
    tariff_inr_per_kwh: float | None = None
    caveats: list[str] = Field(default_factory=list)


class BaseModelProvider(ABC):
    """Abstract model provider interface."""

    @abstractmethod
    def predict(
        self,
        model_name: str,
        entity_id: str,
        features: dict[str, Any],
        actual_kwh_so_far: float | None = None,
        context: str = "future_forecast",
    ) -> PredictionOutput:
        """Run single-record inference for a designated model."""

    @abstractmethod
    def predict_horizon(
        self,
        sector: str,
        entity_id: str,
        horizon_count: int = 24,
    ) -> list[dict[str, Any]]:
        """Run multi-step horizon inference returning TimeSeriesPoint list."""

    @abstractmethod
    def get_model_status(self) -> dict[str, Any]:
        """Report provider health, active models, and readiness status."""
