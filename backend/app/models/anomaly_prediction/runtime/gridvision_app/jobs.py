"""Persistent, single-process analysis job storage."""

from __future__ import annotations

import json
import logging
import math
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from gridvision_event_localization import (
    ANOMALY_COLUMNS,
    EVENT_SUMMARY_COLUMNS,
    EventLocalizationConfig,
)
from gridvision_app.inference import InferenceService, json_safe

logger = logging.getLogger(__name__)
EARTH_RADIUS_KM = 6371.0088


def _event_geojson(events: list[dict[str, Any]]) -> dict[str, Any]:
    features = []
    for event in events:
        latitude = math.radians(float(event["latitude_center"]))
        longitude = math.radians(float(event["longitude_center"]))
        radius = max(0.0, float(event["spatial_extent_km"])) / (2 * EARTH_RADIUS_KM)
        if radius == 0:
            geometry = {
                "type": "Point",
                "coordinates": [
                    float(event["longitude_center"]),
                    float(event["latitude_center"]),
                ],
            }
        else:
            ring = []
            for bearing_degrees in range(0, 361, 10):
                bearing = math.radians(bearing_degrees)
                target_latitude = math.asin(
                    math.sin(latitude) * math.cos(radius)
                    + math.cos(latitude) * math.sin(radius) * math.cos(bearing)
                )
                target_longitude = longitude + math.atan2(
                    math.sin(bearing) * math.sin(radius) * math.cos(latitude),
                    math.cos(radius) - math.sin(latitude) * math.sin(target_latitude),
                )
                ring.append(
                    [
                        math.degrees(target_longitude),
                        math.degrees(target_latitude),
                    ]
                )
            ring[-1] = ring[0]
            geometry = {"type": "Polygon", "coordinates": [ring]}
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": event,
            }
        )
    return {"type": "FeatureCollection", "features": features}


class AnalysisStore:
    """Persist run status, result payloads, and downloadable CSV summaries."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._execution_lock = threading.Lock()
        for manifest_path in self.directory.glob("*/analysis.json"):
            manifest = self._read_json(manifest_path)
            if manifest.get("status") in {"queued", "running"}:
                analysis_directory = manifest_path.parent
                required_results = (
                    "events.json",
                    "anomaly_windows.json",
                    "affected_customer_ids.json",
                    "metrics.json",
                    "metadata.json",
                    "analysis_result.json",
                )
                if all((analysis_directory / name).is_file() for name in required_results):
                    manifest.update(
                        status="completed",
                        metrics=self._read_json(analysis_directory / "metrics.json"),
                        metadata=self._read_json(analysis_directory / "metadata.json"),
                        error=None,
                    )
                else:
                    manifest["status"] = "failed"
                    manifest["error"] = (
                        "The application restarted before this analysis completed."
                    )
                manifest["updated_at"] = self._now()
                self._write_json(manifest_path, manifest)

    def create(self, request: dict[str, Any]) -> dict[str, Any]:
        analysis_id = uuid.uuid4().hex
        analysis_directory = self._directory(analysis_id)
        analysis_directory.mkdir(parents=True, exist_ok=False)
        manifest = {
            "analysis_id": analysis_id,
            "status": "queued",
            "created_at": self._now(),
            "updated_at": self._now(),
            "request": request,
            "error": None,
        }
        self._write_json(analysis_directory / "analysis.json", manifest)
        return manifest

    def run(
        self,
        service: InferenceService,
        analysis_id: str,
        request: dict[str, Any],
    ) -> None:
        with self._execution_lock:
            self._execute(service, analysis_id, request)

    def _execute(
        self,
        service: InferenceService,
        analysis_id: str,
        request: dict[str, Any],
    ) -> None:
        manifest_path = self._manifest_path(analysis_id)
        with self._lock:
            manifest = self._read_json(manifest_path)
            manifest.update(status="running", updated_at=self._now())
            self._write_json(manifest_path, manifest)
        logger.info(
            "Starting analysis %s for %s customer IDs",
            analysis_id,
            len(request["customer_ids"]) if request["customer_ids"] else "all",
        )
        try:
            config = EventLocalizationConfig(
                h3_resolution=request["h3_resolution"],
                spatial_radius_km=request["spatial_radius_km"],
                maximum_start_time_difference=pd.Timedelta(
                    minutes=request["maximum_start_time_difference_minutes"]
                ),
                minimum_temporal_overlap=request["minimum_temporal_overlap"],
                maximum_interval_gap=pd.Timedelta(
                    minutes=request["maximum_interval_gap_minutes"]
                ),
            )
            result = service.analyze(
                customer_ids=request["customer_ids"],
                start_date=datetime.fromisoformat(request["start_date"]).date(),
                end_date=datetime.fromisoformat(request["end_date"]).date(),
                localization=config,
            )
            analysis_directory = self._directory(analysis_id)
            self._write_json(analysis_directory / "events.json", result["events"])
            self._write_json(
                analysis_directory / "anomaly_windows.json",
                result["anomaly_windows"],
            )
            self._write_json(
                analysis_directory / "affected_customer_ids.json",
                result["affected_customer_ids"],
            )
            self._write_json(analysis_directory / "metrics.json", result["metrics"])
            self._write_json(
                analysis_directory / "metadata.json", json_safe(result["metadata"])
            )
            self._write_json(
                analysis_directory / "analysis_result.json",
                json_safe(
                    {
                        "run_id": analysis_id,
                        "status": "completed",
                        "request": request,
                        **result,
                    }
                ),
            )
            evaluation = service.model_metadata().get(
                "saved_evaluation_metrics", {}
            )
            self._write_json(
                analysis_directory / "evaluation_metrics.json", evaluation
            )
            self._write_json(
                analysis_directory / "events.geojson",
                _event_geojson(result["events"]),
            )
            pd.DataFrame(result["events"], columns=EVENT_SUMMARY_COLUMNS).to_csv(
                analysis_directory / "events.csv", index=False
            )
            pd.DataFrame(result["anomaly_windows"], columns=ANOMALY_COLUMNS).to_csv(
                analysis_directory / "anomaly_windows.csv", index=False
            )
            anomaly_records = pd.DataFrame(result["anomaly_windows"])
            if anomaly_records.empty:
                pd.DataFrame(columns=ANOMALY_COLUMNS).to_csv(
                    analysis_directory / "anomaly_records.csv", index=False
                )
                pd.DataFrame(
                    columns=[
                        "event_id",
                        "spatial_cluster_id",
                        "customer_count",
                        "latitude_center",
                        "longitude_center",
                        "event_start",
                        "event_end",
                    ]
                ).to_csv(analysis_directory / "geographic_clusters.csv", index=False)
            else:
                anomaly_records.to_csv(
                    analysis_directory / "anomaly_records.csv", index=False
                )
                anomaly_records.groupby(
                    ["event_id", "event_spatial_cluster_id"],
                    dropna=False,
                    sort=True,
                ).agg(
                    customer_count=("customer_id", "nunique"),
                    latitude_center=("latitude", "mean"),
                    longitude_center=("longitude", "mean"),
                    event_start=("anomaly_start", "min"),
                    event_end=("anomaly_end", "max"),
                ).reset_index().rename(
                    columns={"event_spatial_cluster_id": "spatial_cluster_id"}
                ).to_csv(analysis_directory / "geographic_clusters.csv", index=False)
            localization_evaluation = evaluation.get(
                "spatial_event_localization", {}
            )
            self._write_json(
                analysis_directory / "event_localization_evaluation.json",
                localization_evaluation,
            )
            manifest.update(
                status="completed",
                updated_at=self._now(),
                metrics=result["metrics"],
                metadata=json_safe(result["metadata"]),
            )
            self._write_json(manifest_path, manifest)
            logger.info(
                "Analysis %s completed: input_rows=%s anomaly_windows=%s "
                "localized_events=%s affected_customers=%s",
                analysis_id,
                result["metrics"]["input_rows_scored"],
                result["metrics"]["anomaly_window_count"],
                result["metrics"]["localized_event_count"],
                result["metrics"]["affected_customer_count"],
            )
        except Exception as error:
            logger.exception("Analysis %s failed", analysis_id)
            manifest.update(
                status="failed",
                updated_at=self._now(),
                error=str(error),
            )
            self._write_json(manifest_path, manifest)

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        path = self._manifest_path(analysis_id)
        return self._read_json(path) if path.is_file() else None

    def result(self, analysis_id: str) -> dict[str, Any] | None:
        path = self._directory(analysis_id) / "analysis_result.json"
        return self._read_json(path) if path.is_file() else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        manifests = [
            self._read_json(path)
            for path in self.directory.glob("*/analysis.json")
        ]
        return sorted(
            manifests, key=lambda manifest: manifest.get("created_at", ""), reverse=True
        )[:limit]

    def events(
        self, analysis_id: str, offset: int = 0, limit: int = 100
    ) -> dict[str, Any] | None:
        path = self._directory(analysis_id) / "events.json"
        if not path.is_file():
            return None
        records = self._read_json(path)
        return {
            "items": records[offset : offset + limit],
            "offset": offset,
            "limit": limit,
            "total": len(records),
        }

    def anomaly_windows(
        self, analysis_id: str, offset: int = 0, limit: int = 500
    ) -> dict[str, Any] | None:
        path = self._directory(analysis_id) / "anomaly_windows.json"
        if not path.is_file():
            return None
        records = self._read_json(path)
        return {
            "items": records[offset : offset + limit],
            "offset": offset,
            "limit": limit,
            "total": len(records),
        }

    def affected_customers(self, analysis_id: str) -> list[int] | None:
        path = self._directory(analysis_id) / "affected_customer_ids.json"
        return self._read_json(path) if path.is_file() else None

    def event_detail(
        self, analysis_id: str, event_id: str
    ) -> dict[str, Any] | None:
        events_path = self._directory(analysis_id) / "events.json"
        windows_path = self._directory(analysis_id) / "anomaly_windows.json"
        if not events_path.is_file() or not windows_path.is_file():
            return None
        event = next(
            (
                item
                for item in self._read_json(events_path)
                if item["event_id"] == event_id
            ),
            None,
        )
        if event is None:
            return None
        windows = [
            record
            for record in self._read_json(windows_path)
            if record["event_id"] == event_id
        ]
        return {"event": event, "anomaly_windows": windows}

    def result_file(self, analysis_id: str, name: str) -> Path | None:
        allowed_files = {
            "anomaly_records.csv",
            "events.csv",
            "anomaly_windows.csv",
            "spatial_temporal_events.csv",
            "geographic_clusters.csv",
            "events.json",
            "anomaly_windows.json",
            "analysis.json",
            "analysis_result.json",
            "metrics.json",
            "metadata.json",
            "evaluation_metrics.json",
            "event_localization_evaluation.json",
            "events.geojson",
        }
        if name not in allowed_files:
            return None
        aliases = {
            "spatial_temporal_events.csv": "events.csv",
            "anomaly_records.csv": "anomaly_records.csv",
        }
        path = self._directory(analysis_id) / aliases.get(name, name)
        if path.is_file():
            return path
        if name in {"anomaly_records.csv", "geographic_clusters.csv"}:
            windows_path = self._directory(analysis_id) / "anomaly_windows.json"
            if not windows_path.is_file():
                return None
            records = self._read_json(windows_path)
            frame = pd.DataFrame(records)
            if name == "anomaly_records.csv":
                if frame.empty:
                    frame = pd.DataFrame(columns=ANOMALY_COLUMNS)
                frame.to_csv(path, index=False)
            elif frame.empty:
                pd.DataFrame(
                    columns=[
                        "event_id",
                        "spatial_cluster_id",
                        "customer_count",
                        "latitude_center",
                        "longitude_center",
                        "event_start",
                        "event_end",
                    ]
                ).to_csv(path, index=False)
            else:
                frame.groupby(
                    ["event_id", "event_spatial_cluster_id"],
                    dropna=False,
                    sort=True,
                ).agg(
                    customer_count=("customer_id", "nunique"),
                    latitude_center=("latitude", "mean"),
                    longitude_center=("longitude", "mean"),
                    event_start=("anomaly_start", "min"),
                    event_end=("anomaly_end", "max"),
                ).reset_index().rename(
                    columns={"event_spatial_cluster_id": "spatial_cluster_id"}
                ).to_csv(path, index=False)
            return path
        if name == "events.geojson":
            events_path = self._directory(analysis_id) / "events.json"
            if not events_path.is_file():
                return None
            events = self._read_json(events_path)
            self._write_json(path, _event_geojson(events))
            return path
        if name == "analysis_result.json":
            manifest = self.get(analysis_id)
            events = self._read_json(self._directory(analysis_id) / "events.json") if (
                self._directory(analysis_id) / "events.json"
            ).is_file() else []
            windows_path = self._directory(analysis_id) / "anomaly_windows.json"
            windows = self._read_json(windows_path) if windows_path.is_file() else []
            affected_path = self._directory(analysis_id) / "affected_customer_ids.json"
            affected = self._read_json(affected_path) if affected_path.is_file() else []
            if manifest is None:
                return None
            self._write_json(
                path,
                {
                    "run_id": analysis_id,
                    "status": manifest.get("status"),
                    "request": manifest.get("request", {}),
                    "metadata": manifest.get("metadata", {}),
                    "metrics": manifest.get("metrics", {}),
                    "events": events,
                    "anomaly_windows": windows,
                    "affected_customer_ids": affected,
                },
            )
            return path
        return None

    def _directory(self, analysis_id: str) -> Path:
        try:
            uuid.UUID(hex=analysis_id)
        except ValueError as error:
            raise ValueError("Invalid analysis ID.") from error
        return self.directory / analysis_id

    def _manifest_path(self, analysis_id: str) -> Path:
        return self._directory(analysis_id) / "analysis.json"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _read_json(path: Path) -> Any:
        with path.open(encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(json_safe(payload), file, allow_nan=False)
        temporary.replace(path)
