"""Historical observation reader for GridVision residential meters.

Retrieves verified, meter-scoped historical observations from underlying
parquet datasets (customer_silver.parquet) with zero crossover.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from app.config import BaseConfig

logger = logging.getLogger("gridvision.assistant.historical.reader")

# Mapping of residential accounts / meters to primary OBJECTID entities in customer_silver.parquet
# Physical primary key in Parquet: OBJECTID (integer)
DEV_METER_BUILDING_MAP: dict[str, int] = {
    # Real physical OBJECTID mappings
    "2254213": 2254213,
    "METER-2254213": 2254213,
    "293861": 293861,
    "METER-293861": 293861,
    "537421": 537421,
    "METER-537421": 537421,
    "679900": 679900,
    "METER-679900": 679900,
    # Legacy alias mappings for backward compatibility
    "1000": 2254213,
    "METER-1000": 2254213,
    "1001": 293861,
    "METER-1001": 293861,
    "1002": 537421,
    "METER-1002": 537421,
    "1003": 679900,
    "METER-1003": 679900,
}


class HistoricalObservationReader:
    """Reads isolated historical hourly telemetry for a given authorized meter."""

    def __init__(self, dataset_path: Path | str | None = None) -> None:
        if dataset_path:
            self.dataset_path = Path(dataset_path)
        else:
            self.dataset_path = (
                BaseConfig.PROJECT_ROOT / "data" / "silver" / "customer_silver.parquet"
            )

    def resolve_entity_id(self, meter_id: str) -> int | None:
        """Resolve a formatted meter ID (e.g. 'METER-1000' or '285520') to an integer entity ID."""
        clean = (meter_id or "").strip().upper()
        if not clean:
            return None

        # Check explicit benchmark mapping
        if clean in DEV_METER_BUILDING_MAP:
            return DEV_METER_BUILDING_MAP[clean]

        # Check numeric part
        num_str = clean.replace("METER-", "")
        if num_str.isdigit():
            val = int(num_str)
            # If it's 1000..1003
            f_key = f"METER-{num_str}"
            if f_key in DEV_METER_BUILDING_MAP:
                return DEV_METER_BUILDING_MAP[f_key]
            return val

        return None

    def read_observations_for_meter(
        self, meter_id: str
    ) -> list[dict[str, Any]]:
        """Read and filter observations strictly for the authorized meter from customer_silver.

        Returns a list of dicts:
        [
            {"timestamp": datetime, "consumption_kwh": float, "is_predicted": False},
            ...
        ]
        """
        entity_id = self.resolve_entity_id(meter_id)
        if entity_id is None:
            logger.warning("Could not resolve entity ID for meter '%s'", meter_id)
            return []

        if not self.dataset_path.is_file():
            logger.warning(
                "Historical dataset does not exist at %s", self.dataset_path
            )
            return []

        try:
            # Use PyArrow filter pushdown to load only the authorized entity's rows and needed columns
            table = pq.read_table(
                str(self.dataset_path),
                columns=["OBJECTID", "timestamp", "normalized_building_energy_kwh"],
                filters=[("OBJECTID", "=", entity_id)],
            )
            if table.num_rows == 0:
                logger.info("Zero historical records found for entity %d (%s)", entity_id, meter_id)
                return []

            df = table.to_pandas()
            # Sort chronologically
            df = df.sort_values("timestamp")

            observations = []
            for row in df.itertuples():
                ts = row.timestamp
                if isinstance(ts, str):
                    ts = pd.to_datetime(ts).to_pydatetime()
                elif hasattr(ts, "to_pydatetime"):
                    ts = ts.to_pydatetime()

                val = getattr(row, "normalized_building_energy_kwh", None)
                if val is not None and not pd.isna(val) and val >= 0:
                    observations.append({
                        "timestamp": ts,
                        "consumption_kwh": float(val),
                        "is_predicted": False,
                    })

            return observations

        except Exception as exc:
            logger.error(
                "Error reading historical observations for meter %s (entity %s): %s",
                meter_id,
                entity_id,
                exc,
            )
            return []
