"""Household energy data access repository for GridVision.

Encapsulates data retrieval for authorized household meters, abstracting underlying
storage formats (Parquet, DuckDB, memory) from domain and application layers.
Enforces strict meter isolation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.config import BaseConfig
from app.infrastructure.analytics.duckdb_adapter import DuckDBAnalyticalAdapter
from app.services.assistant.historical.observation_reader import DEV_METER_BUILDING_MAP

logger = logging.getLogger("gridvision.infrastructure.repositories.household")


class BaseHouseholdEnergyRepository(ABC):
    """Abstract interface for household energy telemetry retrieval."""

    @abstractmethod
    def resolve_entity_id(self, meter_id: str) -> int | None:
        """Resolve a meter identifier to an integer entity ID."""
        ...

    @abstractmethod
    def get_meter_intervals(
        self,
        meter_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve interval observations for an authorized household."""
        ...

    @abstractmethod
    def get_available_date_range(
        self, meter_id: str
    ) -> tuple[str | None, str | None]:
        """Return the min and max observation dates available for a meter."""
        ...

    @abstractmethod
    def get_gold_monthly_billing(
        self, meter_id: str, billing_month: str
    ) -> dict[str, Any] | None:
        """Retrieve authoritative gold monthly billing and consumption record."""
        ...

    @abstractmethod
    def get_feeder_grid_status(
        self, id_grid_coarse: int, start_time: str, end_time: str
    ) -> dict[str, Any] | None:
        """Query coarse feeder-level energy to check for regional outages."""
        ...

    @abstractmethod
    def get_meter_communication_status(
        self, meter_id: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]:
        """Check whether meter telemetry is actively streaming intervals without drop."""
        ...


class HouseholdEnergyRepository(BaseHouseholdEnergyRepository):
    """Concrete repository reading isolated household records using DuckDB on Parquet."""

    def __init__(
        self,
        dataset_path: Path | str | None = None,
        gold_dataset_path: Path | str | None = None,
        grid_dataset_path: Path | str | None = None,
        duckdb_adapter: DuckDBAnalyticalAdapter | None = None,
    ) -> None:
        if dataset_path:
            self.dataset_path = Path(dataset_path)
        else:
            self.dataset_path = (
                BaseConfig.PROJECT_ROOT / "data" / "silver" / "customer_silver.parquet"
            )

        if gold_dataset_path:
            self.gold_dataset_path = Path(gold_dataset_path)
        else:
            self.gold_dataset_path = (
                BaseConfig.PROJECT_ROOT / "data" / "gold" / "customer_gold.parquet"
            )

        if grid_dataset_path:
            self.grid_dataset_path = Path(grid_dataset_path)
        else:
            self.grid_dataset_path = (
                BaseConfig.PROJECT_ROOT / "data" / "airflow" / "government" / "grid_level_energy.parquet"
            )

        self.adapter = duckdb_adapter or DuckDBAnalyticalAdapter()

    def resolve_entity_id(self, meter_id: str) -> int | None:
        """Resolve canonical meter ID to the underlying database entity ID."""
        clean = (meter_id or "").strip().upper()
        if not clean:
            return None

        # Check explicit benchmark development mapping
        if clean in DEV_METER_BUILDING_MAP:
            return DEV_METER_BUILDING_MAP[clean]

        num_str = clean.replace("METER-", "")
        if num_str.isdigit():
            f_key = f"METER-{num_str}"
            if f_key in DEV_METER_BUILDING_MAP:
                return DEV_METER_BUILDING_MAP[f_key]
            return int(num_str)

        return None

    def get_meter_intervals(
        self,
        meter_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query isolated interval energy records strictly for the authorized meter."""
        entity_id = self.resolve_entity_id(meter_id)
        if entity_id is None:
            logger.warning("Repository cannot resolve entity for meter '%s'", meter_id)
            return []

        if not self.dataset_path.is_file():
            logger.warning("Dataset file missing at '%s'", self.dataset_path)
            return []

        return self.adapter.query_intervals_for_entity(
            parquet_path=self.dataset_path,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
        )

    def get_available_date_range(
        self, meter_id: str
    ) -> tuple[str | None, str | None]:
        """Query boundary dates for an authorized household."""
        entity_id = self.resolve_entity_id(meter_id)
        if entity_id is None or not self.dataset_path.is_file():
            return None, None

        min_ts, max_ts, _ = self.adapter.get_date_bounds_for_entity(
            parquet_path=self.dataset_path,
            entity_id=entity_id,
        )
        min_date = min_ts.split(" ")[0] if min_ts else None
        max_date = max_ts.split(" ")[0] if max_ts else None
        return min_date, max_date

    def get_gold_monthly_billing(
        self, meter_id: str, billing_month: str
    ) -> dict[str, Any] | None:
        """Query authoritative gold monthly billing and consumption record."""
        entity_id = self.resolve_entity_id(meter_id)
        if entity_id is None or not self.gold_dataset_path.is_file():
            return None

        # Normalize billing_month into YYYY-MM-01
        month_start = self._normalize_month_start(billing_month)
        if not month_start:
            return None

        return self.adapter.query_gold_monthly_billing(
            parquet_path=self.gold_dataset_path,
            entity_id=entity_id,
            month_start=month_start,
        )

    def get_feeder_grid_status(
        self, id_grid_coarse: int, start_time: str, end_time: str
    ) -> dict[str, Any] | None:
        """Query coarse feeder-level energy to check for regional outages."""
        if not self.grid_dataset_path.is_file():
            return None

        return self.adapter.query_grid_feeder_status(
            parquet_path=self.grid_dataset_path,
            id_grid_coarse=id_grid_coarse,
            start_time=start_time,
            end_time=end_time,
        )

    def get_meter_communication_status(
        self, meter_id: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]:
        """Check whether meter telemetry is actively streaming intervals without drop."""
        entity_id = self.resolve_entity_id(meter_id)
        if entity_id is None or not self.dataset_path.is_file():
            return {
                "active_telemetry": False,
                "intervals_recorded": 0,
                "data_coverage": "unavailable",
            }

        intervals = self.get_meter_intervals(meter_id, start_date=start_date, end_date=end_date)
        count = len(intervals)
        return {
            "active_telemetry": count > 0,
            "intervals_recorded": count,
            "data_coverage": "complete" if count >= 12 else ("partial" if count > 0 else "unavailable"),
        }

    @staticmethod
    def _normalize_month_start(raw_str: str) -> str | None:
        """Parse diverse user month inputs into canonical YYYY-MM-01."""
        import re
        from datetime import datetime

        if not raw_str:
            return None
        s = raw_str.strip()

        m = re.match(r"^(\d{4})-(\d{1,2})", s)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-01"

        m2 = re.match(r"^(\d{1,2})[/-](\d{4})", s)
        if m2:
            return f"{int(m2.group(2)):04d}-{int(m2.group(1)):02d}-01"

        for fmt in ("%B %Y", "%b %Y", "%Y %B", "%Y %b"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%Y-%m-01")
            except ValueError:
                pass
        return None
