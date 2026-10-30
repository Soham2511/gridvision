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
    "commercial-building-forecast": ModelDefinition(
        model_id="commercial-building-forecast",
        name="Commercial Building Forecast",
        domain="commercial",
        task="24_hour_building_energy_forecast",
        description="Predicts hourly commercial building demand using the persisted chronological holdout model.",
    ),
    "government-load-forecast": ModelDefinition(
        model_id="government-load-forecast",
        name="Government Grid Load Forecast",
        domain="government",
        task="24_hour_grid_energy_forecast",
        description="Predicts hourly coarse-grid demand using the per-grid routed hybrid model.",
    ),
}
