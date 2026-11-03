"""Customer analytics, segmentation, and load profiling service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class CustomerService:
    """Provides behavioral segmentation and diurnal load profiling."""

    def __init__(self, data_provider: BaseDataProvider) -> None:
        self.data_provider = data_provider

    def get_segments(self) -> list[dict[str, Any]]:
        return self.data_provider.get_customer_segments()

    def get_segmentation_matrix(self) -> dict[str, Any]:
        return self.data_provider.get_customer_segmentation_matrix()

    def get_diurnal_curves(self) -> list[dict[str, Any]]:
        return self.data_provider.get_diurnal_curves()
