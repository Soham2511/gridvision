"""Energy insights and algorithmic recommendation service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class InsightService:
    """Delivers targeted, quantified takeaways for efficiency and peak shaving."""

    def __init__(self, data_provider: BaseDataProvider) -> None:
        self.data_provider = data_provider

    def get_insights(
        self,
        category: str | None = None,
        sector: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.data_provider.get_business_insights(
            category=category,
            sector=sector,
        )
