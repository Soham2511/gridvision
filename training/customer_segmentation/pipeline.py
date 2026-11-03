"""Top-level segmentation workflow orchestration helpers."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, TypeVar

import pyarrow.parquet as pq

from .clustering import fit_and_publish
from .config import SegmentationSettings
from .data_pipeline import (
    _atomic_json,
    generate_building_features,
    load_or_validate_source_profile,
)
from .geospatial import publish_geospatial_outputs

logger = logging.getLogger("gridvision.segmentation")
T = TypeVar("T")


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _run_stage(
    name: str,
    index: int,
    total: int,
    operation: Callable[[], T],
    pipeline_started: float,
    completed_durations: list[float],
) -> tuple[T, float]:
    stage_started = time.monotonic()
    average_stage_seconds = (
        sum(completed_durations) / len(completed_durations)
        if completed_durations
        else None
    )
    if average_stage_seconds is None:
        eta = "not available until a stage completes"
    else:
        eta = _format_duration(average_stage_seconds * (total - index + 1))
    logger.info(
        "Progress %d/%d | Starting: %s | elapsed %s | rough ETA %s "
        "(estimated from completed stages; stage durations vary)",
        index,
        total,
        name,
        _format_duration(stage_started - pipeline_started),
        eta,
    )

    finished = threading.Event()

    def report_heartbeat() -> None:
        while not finished.wait(30):
            elapsed = time.monotonic() - stage_started
            if average_stage_seconds is None:
                eta_text = "pending first completed stage"
            else:
                remaining = max(
                    0,
                    average_stage_seconds * (total - index + 1) - elapsed,
                )
                eta_text = _format_duration(remaining)
            logger.info(
                "Progress %d/%d | Still working: %s | stage elapsed %s | "
                "rough ETA %s",
                index,
                total,
                name,
                _format_duration(elapsed),
                eta_text,
            )

    heartbeat = threading.Thread(target=report_heartbeat, daemon=True)
    heartbeat.start()
    try:
        result = operation()
    except Exception:
        logger.exception(
            "Progress %d/%d | Failed: %s after %s",
            index,
            total,
            name,
            _format_duration(time.monotonic() - stage_started),
        )
        raise
    finally:
        finished.set()
        heartbeat.join()

    duration = time.monotonic() - stage_started
    completed_durations.append(duration)
    average_stage_seconds = sum(completed_durations) / len(completed_durations)
    remaining_stages = total - index
    eta = _format_duration(average_stage_seconds * remaining_stages)
    logger.info(
        "Progress %d/%d | Completed: %s in %s | total elapsed %s | rough ETA %s",
        index,
        total,
        name,
        _format_duration(duration),
        _format_duration(time.monotonic() - pipeline_started),
        eta,
    )
    return result, duration


def validate_outputs(settings: SegmentationSettings) -> dict[str, Any]:
    required = (
        "consumer_assignments.parquet",
        "cluster_profiles.parquet",
        "segment_distribution.parquet",
        "region_summary_coarse.parquet",
        "region_summary_finer.parquet",
        "survey_priority.parquet",
        "cluster_hourly_profile.parquet",
        "cluster_daily_profile.parquet",
        "cluster_monthly_profile.parquet",
        "model_metadata.json",
    )
    missing = [
        name
        for name in required
        if not (settings.output_dir / name).is_file()
        or (settings.output_dir / name).stat().st_size == 0
    ]
    required_reports = (
        "source_profile.json",
        "feature_generation.json",
        "geospatial_summary.json",
        "model_selection_report.json",
        "feature_diagnostics.json",
    )
    missing.extend(
        f"reports/{name}"
        for name in required_reports
        if not (settings.reports_dir / name).is_file()
        or (settings.reports_dir / name).stat().st_size == 0
    )
    if not settings.feature_path.is_file() or settings.feature_path.stat().st_size == 0:
        missing.append(str(settings.feature_path))
    if missing:
        raise FileNotFoundError(f"Segmentation outputs are incomplete: {missing}")
    metadata = json.loads((settings.output_dir / "model_metadata.json").read_text())
    if metadata.get("assignment_count", 0) <= 0:
        raise ValueError("Segmentation produced no building assignments")
    parquet_rows = {
        name: pq.ParquetFile(settings.output_dir / name).metadata.num_rows
        for name in required
        if name.endswith(".parquet")
    }
    parquet_rows[settings.feature_path.name] = (
        pq.ParquetFile(settings.feature_path).metadata.num_rows
    ) if settings.feature_path.is_file() else 0
    for name, row_count in parquet_rows.items():
        if row_count <= 0:
            raise ValueError(f"Segmentation output is empty: {name}")
    if parquet_rows["consumer_assignments.parquet"] != int(metadata["assignment_count"]):
        raise ValueError("Assignment row count does not match model metadata")
    if metadata.get("unassigned_feature_buildings", 0) != 0:
        raise ValueError("Every eligible building feature row must have a segmentation assignment")
    missing_models = [
        model["model_category"]
        for model in metadata.get("trained_models", [])
        if (
            not (
                settings.model_dir
                / f"{model['model_category'].lower()}_model.joblib"
            ).is_file()
            or (
                settings.model_dir
                / f"{model['model_category'].lower()}_model.joblib"
            ).stat().st_size
            == 0
        )
    ]
    if missing_models:
        raise FileNotFoundError(f"Segmentation model bundles are missing: {missing_models}")
    report = {
        "status": "complete",
        "output_dir": str(settings.output_dir.resolve()),
        "feature_path": str(settings.feature_path.resolve()),
        "model_dir": str(settings.model_dir.resolve()),
        "reports_dir": str(settings.reports_dir.resolve()),
        "required_outputs": list(required),
        "model_version": metadata.get("model_version"),
        "assignment_count": metadata.get("assignment_count"),
        "unassigned_feature_buildings": metadata.get("unassigned_feature_buildings"),
        "parquet_row_counts": parquet_rows,
        "model_categories": [
            model["model_category"] for model in metadata.get("trained_models", [])
        ],
    }
    logger.info("Validated segmentation outputs: %s", report)
    return report


def write_execution_summary(settings: SegmentationSettings, summary: dict[str, Any]) -> Path:
    """Atomically publish a JSON summary for CLI or Airflow executions."""
    summary_path = settings.reports_dir / "execution_summary.json"
    _atomic_json(summary_path, summary)
    logger.info("Published segmentation execution summary: %s", summary_path)
    return summary_path


def run_pipeline(settings: SegmentationSettings, *, register_mlflow: bool = True) -> dict[str, Any]:
    settings.validate()
    logger.info("Starting segmentation pipeline settings=%s", asdict(settings))
    pipeline_started = time.monotonic()
    stage_durations: list[float] = []
    total_stages = 6 if register_mlflow else 5
    source_report, _ = _run_stage(
        "Profile and validate source dataset",
        1,
        total_stages,
        lambda: load_or_validate_source_profile(settings),
        pipeline_started,
        stage_durations,
    )
    feature_report, _ = _run_stage(
        "Generate building-level features",
        2,
        total_stages,
        lambda: generate_building_features(settings),
        pipeline_started,
        stage_durations,
    )
    model_report, _ = _run_stage(
        "Cluster buildings and write segment assignments",
        3,
        total_stages,
        lambda: fit_and_publish(settings.feature_path, settings),
        pipeline_started,
        stage_durations,
    )
    geo_report, _ = _run_stage(
        "Generate regional and time-series outputs",
        4,
        total_stages,
        lambda: publish_geospatial_outputs(settings),
        pipeline_started,
        stage_durations,
    )
    output_validation, _ = _run_stage(
        "Validate all published outputs",
        5,
        total_stages,
        lambda: validate_outputs(settings),
        pipeline_started,
        stage_durations,
    )
    mlflow_result = None
    if register_mlflow:
        from .registration import register_models

        mlflow_result, _ = _run_stage(
            "Register segmentation models in MLflow",
            6,
            total_stages,
            lambda: register_models(settings),
            pipeline_started,
            stage_durations,
        )
    summary = {
        "source_profile": source_report,
        "feature_generation": feature_report,
        "models": model_report,
        "geospatial": geo_report,
        "mlflow": mlflow_result,
        "output_validation": output_validation,
        "progress": {
            "total_elapsed_seconds": round(time.monotonic() - pipeline_started, 3),
            "stage_durations_seconds": [
                round(duration, 3) for duration in stage_durations
            ],
        },
        "execution_summary_path": str(
            (settings.reports_dir / "execution_summary.json").resolve()
        ),
    }
    write_execution_summary(settings, summary)
    logger.info("Segmentation pipeline complete: %s", output_validation)
    return summary
