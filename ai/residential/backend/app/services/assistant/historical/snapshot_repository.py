"""Historical Snapshot Repository for GridVision Residential Assistant.

Provides persistent JSON sidecar storage, versioning, staleness detection,
and strict meter-isolated retrieval for household historical profiles.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import BaseConfig
from app.services.assistant.historical.snapshot_builder import (
    CALCULATION_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    HistoricalSnapshotBuilder,
)

logger = logging.getLogger("gridvision.assistant.historical.repository")


class HistoricalSnapshotRepository:
    """Manages persistent sidecar storage and retrieval for historical profiles."""

    def __init__(
        self,
        storage_dir: Path | str | None = None,
        source_manifest_path: Path | str | None = None,
    ) -> None:
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = (
                BaseConfig.PROJECT_ROOT
                / "data"
                / "metadata"
                / "historical_snapshots"
            )

        if source_manifest_path:
            self.source_manifest_path = Path(source_manifest_path)
        else:
            self.source_manifest_path = (
                BaseConfig.PROJECT_ROOT
                / "data"
                / "metadata"
                / "dataset_versions"
                / "customer_silver"
                / "latest.json"
            )

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_snapshot_path(self, meter_id: str) -> Path:
        """Derive the deterministic filename for a given meter ID / OBJECTID."""
        clean_id = (meter_id or "").strip().upper()
        num_part = clean_id.replace("METER-", "")
        f_raw = self.storage_dir / f"{num_part}.json"
        if f_raw.is_file():
            return f_raw
        return self.storage_dir / f"METER-{num_part}.json"

    def get_source_data_version(self) -> str:
        """Read the active customer_silver dataset version from its manifest."""
        if self.source_manifest_path.is_file():
            try:
                manifest = json.loads(self.source_manifest_path.read_text(encoding="utf-8"))
                return manifest.get("dataset_version", "untracked")
            except Exception as exc:
                logger.warning("Could not read silver manifest: %s", exc)
        return "latest"

    def save_snapshot(self, meter_id: str, snapshot: dict[str, Any]) -> Path:
        """Validate and write the historical profile snapshot to storage."""
        HistoricalSnapshotBuilder.validate_snapshot(snapshot)

        # Enforce meter isolation
        profile = snapshot.get("historicalProfile", {})
        profile["meterId"] = meter_id

        target_path = self._get_snapshot_path(meter_id)
        target_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        logger.info("Saved historical snapshot for meter %s to %s", meter_id, target_path)
        return target_path

    def generate_snapshot_if_missing(self, meter_id: str) -> bool:
        """Build and persist a current snapshot from verified observations when needed."""
        if self.get_snapshot(meter_id) is not None:
            return False

        from app.services.assistant.historical.analytics_service import (
            HistoricalAnalyticsService,
        )
        from app.services.assistant.historical.observation_reader import (
            HistoricalObservationReader,
        )

        observations = HistoricalObservationReader().read_observations_for_meter(
            meter_id
        )
        if not observations:
            logger.info(
                "No historical observations available to build a snapshot for meter %s",
                meter_id,
            )
            return False

        analytics = HistoricalAnalyticsService()
        daily_records = analytics.aggregate_daily_consumption(observations)
        if not daily_records:
            logger.info(
                "No valid daily observations available to build a snapshot for meter %s",
                meter_id,
            )
            return False

        snapshot = HistoricalSnapshotBuilder(analytics).build_snapshot_from_records(
            meter_id=meter_id,
            daily_records=daily_records,
            total_observations_count=len(observations),
            source_data_version=self.get_source_data_version(),
        )
        self.save_snapshot(meter_id, snapshot)
        return True

    def get_snapshot(self, meter_id: str) -> dict[str, Any] | None:
        """Retrieve and validate the latest snapshot for an authorized meter.

        Returns None if missing, corrupted, outdated, or belonging to another meter.
        """
        clean_id = (meter_id or "").strip().upper()
        if not clean_id:
            return None

        path = self._get_snapshot_path(clean_id)
        if not path.is_file():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Corrupted historical snapshot at %s: %s", path, exc)
            return None

        # Validate schema
        try:
            HistoricalSnapshotBuilder.validate_snapshot(data)
        except ValueError as exc:
            logger.warning("Invalid snapshot schema at %s: %s", path, exc)
            return None

        profile = data.get("historicalProfile", {})

        # Verify meter ownership
        stored_meter = profile.get("meterId", "").upper()
        num_stored = stored_meter.replace("METER-", "")
        num_requested = clean_id.replace("METER-", "")
        if num_stored != num_requested:
            logger.warning(
                "Cross-meter isolation violation! Stored '%s' does not match requested '%s'",
                stored_meter,
                clean_id,
            )
            return None

        # Staleness check
        if self.is_stale(clean_id, data):
            logger.info("Snapshot for meter %s is stale; returning None", clean_id)
            return None

        return data

    def is_stale(self, meter_id: str, snapshot: dict[str, Any] | None = None) -> bool:
        """Check whether the snapshot has outdated calculation or source version."""
        if snapshot is None:
            data = self.get_snapshot(meter_id)
            if data is None:
                return True
            snapshot = data

        profile = snapshot.get("historicalProfile", {})
        meta = profile.get("snapshotMetadata", {})

        # Check schema and calculation version
        if meta.get("schemaVersion") != SNAPSHOT_SCHEMA_VERSION:
            return True
        if meta.get("calculationVersion") != CALCULATION_VERSION:
            return True

        # Check source dataset version if manifest exists
        active_source_version = self.get_source_data_version()
        stored_source_version = meta.get("sourceDataVersion")
        if (
            active_source_version != "latest"
            and stored_source_version
            and stored_source_version != "latest"
            and stored_source_version != active_source_version
        ):
            return True

        return False

    def invalidate(self, meter_id: str) -> bool:
        """Delete an existing snapshot for a meter upon source invalidation."""
        path = self._get_snapshot_path(meter_id)
        if path.is_file():
            path.unlink()
            logger.info("Invalidated historical snapshot for meter %s", meter_id)
            return True
        return False
