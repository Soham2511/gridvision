"""Catalog of model packages served by GridVision."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelDefinition:
    """Public metadata for one independently deployable model."""

    model_id: str
    name: str
    domain: str
    task: str
    description: str

    def as_dict(self) -> dict[str, str]:
        values = asdict(self)
        values["modelId"] = values.pop("model_id")
        return values


MODEL_REGISTRY = {
    "customer-bill-prediction": ModelDefinition(
        model_id="customer-bill-prediction",
        name="Customer Bill Prediction",
        domain="customer",
        task="monthly_energy_prediction",
        description=(
            "Predicts full-month customer energy use from cutoff-time meter "
            "features in the versioned gold dataset."
        ),
    ),
    "government-load-forecasting": ModelDefinition(
        model_id="government-load-forecasting",
        name="Government Grid Load Forecaster",
        domain="government",
        task="grid_load_forecasting",
        description=(
            "Dual LightGBM hybrid model predicting multi-horizon regional grid energy demand "
            "with dynamic per-grid routing."
        ),
    ),
}
