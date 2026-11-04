"""Explicit dependency bundle for existing non-AI GridVision services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ServiceAdapters:
    customer_bill_prediction: Any
    customer_silver_history: Any
    commercial_silver_history: Any
    commercial_history: Any
    model_provider: Any
    segmentation: Any
    anomaly_prediction: Any
    paths: dict[str, Any]

    @classmethod
    def from_mapping(cls, services: dict[str, Any]) -> "ServiceAdapters":
        return cls(
            customer_bill_prediction=services.get("customer_bill_prediction_service"),
            customer_silver_history=services.get("customer_silver_history_service"),
            commercial_silver_history=services.get("commercial_silver_history_service"),
            commercial_history=services.get("commercial_history_provider"),
            model_provider=services.get("model_provider"),
            segmentation=services.get("government_segmentation_service"),
            anomaly_prediction=services.get("anomaly_prediction_service"),
            paths={key: value for key, value in services.items() if key.endswith("_path") or key.endswith("_dir")},
        )

    def service(self, name: str):
        mapping = {
            "customer_bill_prediction_service": self.customer_bill_prediction,
            "customer_silver_history_service": self.customer_silver_history,
            "commercial_silver_history_service": self.commercial_silver_history,
            "commercial_history_provider": self.commercial_history,
            "model_provider": self.model_provider,
            "government_segmentation_service": self.segmentation,
            "anomaly_prediction_service": self.anomaly_prediction,
        }
        return mapping.get(name)
