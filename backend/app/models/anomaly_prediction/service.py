"""Saved-model anomaly detection integration for the GridVision platform."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.models.registry import MODEL_REGISTRY

logger = logging.getLogger("gridvision.anomaly.inference")


def estimate_workload_rows(
    customer_count: int,
    start_date: date,
    end_date: date,
    source_start: date,
    source_end: date,
) -> int:
    requested_hours = (end_date - start_date).days * 24 + 24
    history_hours = min(168, max(0, (start_date - source_start).days * 24))
    post_event_hours = min(12, max(0, (source_end - end_date).days * 24))
    return customer_count * (requested_hours + history_hours + post_event_hours)


class AnomalyPredictionError(RuntimeError):
    """Raised when the saved anomaly bundle is unavailable or invalid."""


class AnomalyPredictionService:
    """Wraps the independent GridVision anomaly detector for backend model routes."""

    def __init__(
        self,
        dataset_path: str | Path,
        model_path: str | Path,
        project_root: str | Path,
        runs_path: str | Path | None = None,
    ) -> None:
        self.dataset_path = Path(dataset_path)
        self.model_path = Path(model_path)
        self.project_root = Path(project_root)
        self.runs_path = Path(
            runs_path
            or self.project_root
            / "reports"
            / "anomaly_prediction"
            / "application_runs"
        )
        self._inference: Any | None = None
        self._analysis_store: Any | None = None

    @property
    def analysis_store(self) -> Any:
        if self._analysis_store is None:
            self._source_path()
            from gridvision_app.jobs import AnalysisStore

            self._analysis_store = AnalysisStore(self.runs_path)
        return self._analysis_store

    def _source_path(self) -> Path:
        resolved = Path(__file__).resolve().parent / "runtime"
        if resolved.is_dir() and str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
        return resolved

    def _load_inference(self) -> Any:
        if self._inference is not None:
            return self._inference
        self._source_path()
        try:
            from gridvision_app.inference import InferenceService  # type: ignore
        except ImportError as exc:  # pragma: no cover - surfaced as configuration errors
            raise AnomalyPredictionError(
                "Anomaly prediction dependencies are not available: "
                f"{exc}"
            ) from exc
        try:
            self._inference = InferenceService(self.dataset_path, self.model_path)
        except (FileNotFoundError, ImportError, OSError, ValueError) as exc:
            raise AnomalyPredictionError(
                f"Unable to initialize the anomaly prediction bundle: {exc}"
            ) from exc
        return self._inference

    def _dataset_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "name": self.dataset_path.stem,
            "rows": 0,
            "customers": 0,
            "sourceStart": None,
            "sourceEnd": None,
        }
        if not self.dataset_path.is_file():
            return summary
        try:
            parquet = pq.ParquetFile(self.dataset_path)
            summary["rows"] = int(parquet.metadata.num_rows)
        except Exception as exc:
            raise AnomalyPredictionError(
                f"Unable to inspect anomaly dataset {self.dataset_path}: {exc}"
            ) from exc
        return summary

    def get_summary(self) -> dict[str, Any]:
        definition = MODEL_REGISTRY["anomaly-prediction"].as_dict()
        try:
            inference = self._load_inference()
            metadata = inference.model_metadata()
            dataset = self._dataset_summary()
            return {
                **definition,
                "status": "configured",
                "provider": "local_bundle",
                "modelVersion": metadata.get("saved_evaluation_metrics", {}).get(
                    "model_version", "saved_bundle"
                ),
                "selectedModel": "gridvision_anomaly_model",
                "dataset": {
                    "name": dataset.get("name", "synthetic_2019_normal"),
                    "rows": int(dataset.get("rows") or metadata.get("source_rows", 0)),
                    "customers": int(dataset.get("customers") or metadata.get("source_customer_count", 0)),
                    "startDate": metadata.get("source_start") or dataset.get("sourceStart"),
                    "endDate": metadata.get("source_end") or dataset.get("sourceEnd"),
                },
                "testMetrics": metadata.get("saved_evaluation_metrics", {}),
                "features": metadata.get("point_features", []),
                "threshold": metadata.get("detector_threshold"),
                "anomalyTypes": metadata.get("anomaly_types", []),
            }
        except AnomalyPredictionError as exc:
            dataset = self._dataset_summary()
            return {
                **definition,
                "status": "unavailable",
                "provider": "local_bundle",
                "modelVersion": "not_deployed",
                "selectedModel": "not_deployed",
                "dataset": {
                    "name": dataset.get("name", "synthetic_2019_normal"),
                    "rows": int(dataset.get("rows", 0)),
                    "customers": int(dataset.get("customers", 0)),
                    "startDate": dataset.get("sourceStart"),
                    "endDate": dataset.get("sourceEnd"),
                },
                "testMetrics": {},
                "features": [],
                "error": str(exc),
            }

    def get_model_metadata(self) -> dict[str, Any]:
        return self._load_inference().model_metadata()

    def get_model_catalog(self) -> list[dict[str, Any]]:
        return [self.get_summary()]

    def get_entities(
        self,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        inference = self._load_inference()
        result = inference.customer_page(query=query, offset=offset, limit=limit)
        return {
            "items": result.get("items", []),
            "offset": offset,
            "limit": limit,
            "total": int(result.get("total", 0)),
        }

    def analyze(
        self,
        *,
        customer_ids: list[int] | None = None,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        localization: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        inference = self._load_inference()
        from gridvision_event_localization import EventLocalizationConfig

        config = EventLocalizationConfig(
            h3_resolution=int(localization.get("h3_resolution", 8)) if localization else 8,
            spatial_radius_km=float(localization.get("spatial_radius_km", 5.0)) if localization else 5.0,
            maximum_start_time_difference_minutes=int(localization.get("maximum_start_time_difference_minutes", 30)) if localization else 30,
            minimum_temporal_overlap=float(localization.get("minimum_temporal_overlap", 0.25)) if localization else 0.25,
            maximum_interval_gap_minutes=int(localization.get("maximum_interval_gap_minutes", 60)) if localization else 60,
        )
        if start_date is None or end_date is None:
            raise AnomalyPredictionError("Both start_date and end_date are required.")
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
        if end < start:
            raise ValueError("end_date must be on or after start_date.")
        if (end - start).days + 1 > 7:
            raise ValueError("Each anomaly analysis run may cover at most 7 days.")
        return inference.analyze(
            customer_ids=customer_ids,
            start_date=start,
            end_date=end,
            localization=config,
        )

    def run_analysis(self, request: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "customer_ids": request.get("customer_ids"),
            "start_date": str(request["start_date"]),
            "end_date": str(request["end_date"]),
            "h3_resolution": int(request.get("h3_resolution", 8)),
            "spatial_radius_km": float(request.get("spatial_radius_km", 5.0)),
            "maximum_start_time_difference_minutes": int(
                request.get("maximum_start_time_difference_minutes", 30)
            ),
            "minimum_temporal_overlap": float(
                request.get("minimum_temporal_overlap", 0.25)
            ),
            "maximum_interval_gap_minutes": int(
                request.get("maximum_interval_gap_minutes", 60)
            ),
        }
        inference = self._load_inference()
        start = date.fromisoformat(normalized["start_date"])
        end = date.fromisoformat(normalized["end_date"])
        source_start = inference.start_time.normalize().date()
        source_end = inference.end_time.date()
        if end < start:
            raise ValueError("end_date must be on or after start_date.")
        if (end - start).days + 1 > 7:
            raise ValueError("Each anomaly analysis run may cover at most 7 days.")
        if start < source_start or end > source_end:
            raise ValueError(
                f"Requested dates must be within {source_start} and {source_end}."
            )
        selected_ids = normalized["customer_ids"]
        if selected_ids is not None:
            if not selected_ids:
                raise ValueError("Provide at least one customer ID or omit customer_ids.")
            unknown_ids = sorted(set(selected_ids) - inference.customer_ids)
            if unknown_ids:
                raise ValueError(f"Unknown customer IDs: {unknown_ids[:20]}")
        manifest = self.analysis_store.create(normalized)
        self.analysis_store.run(inference, manifest["analysis_id"], normalized)
        completed = self.analysis_store.get(manifest["analysis_id"])
        if completed is None or completed.get("status") != "completed":
            detail = completed.get("error") if completed else "Run record was not created."
            logger.error(
                "model_inference_failed",
                extra={
                    "event": {
                        "model_name": "gridvision_anomaly_model",
                        "model_version": inference.model_metadata()
                        .get("saved_evaluation_metrics", {})
                        .get("model_version", "saved_bundle"),
                        "run_id": manifest["analysis_id"],
                        "start_date": normalized["start_date"],
                        "end_date": normalized["end_date"],
                        "input_record_count": None,
                        "detected_anomaly_count": None,
                        "localized_event_count": None,
                        "status": "failed",
                    }
                },
            )
            raise AnomalyPredictionError(f"Anomaly analysis failed: {detail}")
        metrics = completed.get("metrics", {})
        model_version = inference.model_metadata().get(
            "saved_evaluation_metrics", {}
        ).get("model_version", "saved_bundle")
        logger.info(
            "model_inference_completed",
            extra={
                "event": {
                    "model_name": "gridvision_anomaly_model",
                    "model_version": model_version,
                    "run_id": manifest["analysis_id"],
                    "start_date": normalized["start_date"],
                    "end_date": normalized["end_date"],
                    "input_record_count": metrics.get("input_rows_scored"),
                    "detected_anomaly_count": metrics.get("anomaly_window_count"),
                    "localized_event_count": metrics.get("localized_event_count"),
                    "status": completed["status"],
                }
            },
        )
        return {
            "run_id": manifest["analysis_id"],
            "status": completed["status"],
            "request": completed["request"],
            "metadata": completed.get("metadata", {}),
            "metrics": completed.get("metrics", {}),
            "events": self.analysis_store.events(manifest["analysis_id"])["items"],
            "anomaly_windows": self.analysis_store.anomaly_windows(
                manifest["analysis_id"], limit=1000
            )["items"],
            "affected_customer_ids": self.analysis_store.affected_customers(
                manifest["analysis_id"]
            ),
        }

    def list_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        return self.analysis_store.list(limit)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.analysis_store.get(run_id)
        if run and run.get("status") == "completed":
            result = self.analysis_store.result(run_id)
            if result:
                run.update(
                    events=result["events"],
                    anomaly_windows=result["anomaly_windows"],
                    affected_customer_ids=result["affected_customer_ids"],
                )
        return run

    def get_run_file(self, run_id: str, filename: str) -> Path | None:
        path = self.analysis_store.result_file(run_id, filename)
        if path is not None or filename not in {
            "evaluation_metrics.json",
            "event_localization_evaluation.json",
        }:
            return path
        run = self.analysis_store.get(run_id)
        if run is None or run.get("status") != "completed":
            return None
        self._source_path()
        from gridvision_app.inference import json_safe

        evaluation = self.get_model_metadata().get("saved_evaluation_metrics", {})
        if filename == "event_localization_evaluation.json":
            evaluation = evaluation.get("spatial_event_localization", {})
        target = self.runs_path / run_id / filename
        target.write_text(
            json.dumps(json_safe(evaluation), allow_nan=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target
