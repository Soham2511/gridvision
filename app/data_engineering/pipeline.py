"""Build reproducible customer Bronze, Silver, and Gold Parquet layers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from app.data_engineering.transformations.bronze_to_silver import (
    copy_bronze_snapshot,
    create_customer_silver,
    sha256_file,
)
from app.data_engineering.transformations.silver_to_gold import build_customer_gold


def _silver_daily_batches(path: Path, batch_size: int = 250_000) -> list[pd.DataFrame]:
    """Aggregate bounded Silver batches to partial household-day records."""
    partials: list[pd.DataFrame] = []
    parquet = pq.ParquetFile(path)
    columns = [
        "timestamp",
        "household_id",
        "interval_kwh",
        "is_missing",
        "is_negative",
        "is_extreme_sampled_p99_9",
    ]
    for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
        frame = batch.to_pandas()
        frame["date"] = pd.to_datetime(frame["timestamp"]).dt.floor("D")
        valid_reading = frame["interval_kwh"].where(
            ~frame["is_missing"] & ~frame["is_negative"]
        )
        frame["valid_kwh"] = valid_reading
        partial = frame.groupby(
            ["household_id", "date"],
            as_index=False,
            observed=True,
            sort=False,
        ).agg(
            daily_kwh=("valid_kwh", lambda values: values.sum(min_count=1)),
            valid_intervals=("valid_kwh", "count"),
            rows_seen=("interval_kwh", "size"),
            missing_flags=("is_missing", "sum"),
            negative_flags=("is_negative", "sum"),
            extreme_flags=("is_extreme_sampled_p99_9", "sum"),
        )
        partials.append(partial)
    if not partials:
        raise ValueError(f"Silver dataset is empty: {path}")
    return partials


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write an indented JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(data, indent=2, default=str, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    """Atomically write a compressed Parquet dataset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        frame.to_parquet(
            temporary,
            index=False,
            engine="pyarrow",
            compression="zstd",
            compression_level=3,
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_customer_data(
    project_root: Path,
    batch_size: int = 2048,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Materialize customer Parquet layers and data lineage/quality reports."""
    raw_path = project_root / "data" / "raw" / "raw_source_snapshot.parquet"
    bronze_path = project_root / "data" / "bronze" / "customer_readings.parquet"
    silver_path = (
        project_root / "data" / "silver" / "customer_interval_readings.parquet"
    )
    gold_path = project_root / "data" / "gold" / "customer_daily_features.parquet"
    latest_path = project_root / "data" / "gold" / "customer_latest_features.parquet"
    targets = [bronze_path, silver_path, gold_path, latest_path]
    if not raw_path.is_file():
        raise FileNotFoundError(f"Customer raw snapshot not found: {raw_path}")
    existing = [str(path) for path in targets if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Customer outputs already exist: "
            + ", ".join(existing)
            + ". Use --overwrite to replace them."
        )

    started_at = datetime.now(timezone.utc).isoformat()
    source_checksum = sha256_file(raw_path)
    copy_bronze_snapshot(raw_path, bronze_path, overwrite=overwrite)
    silver_info = create_customer_silver(
        raw_path,
        silver_path,
        batch_size=batch_size,
        overwrite=overwrite,
    )
    partials = _silver_daily_batches(silver_path)
    gold = build_customer_gold(partials)
    _write_parquet(gold_path, gold)

    eligible = gold.loc[gold["is_prediction_eligible"]].copy()
    latest = (
        eligible.sort_values(["household_id", "date"])
        .groupby("household_id", sort=False, observed=True)
        .tail(1)
        .reset_index(drop=True)
    )
    _write_parquet(latest_path, latest)

    finished_at = datetime.now(timezone.utc).isoformat()
    report = {
        "dataset": "customer_interval_readings",
        "generated_at_utc": finished_at,
        "source": str(raw_path.relative_to(project_root)),
        "source_sha256": source_checksum,
        "source_bytes": raw_path.stat().st_size,
        "source_rows": silver_info["row_count"],
        "household_count": silver_info["meter_count"],
        "interval_reading_count": silver_info["interval_reading_count"],
        "date_range": {
            "start": silver_info["first_timestamp"],
            "end": silver_info["last_timestamp"],
        },
        "expected_interval": silver_info["expected_interval"],
        "timestamp_quality": {
            "timestamp_ordered": silver_info["timestamp_ordered"],
            "duplicate_timestamps": silver_info["duplicate_timestamps"],
            "nonstandard_interval_count": silver_info["nonstandard_interval_count"],
            "interval_counts": silver_info["interval_counts"],
        },
        "reading_quality": {
            "missing": silver_info["missing_readings"],
            "negative": silver_info["negative_readings"],
            "zero": silver_info["zero_readings"],
            "zero_is_missing": False,
            "extreme_sampled_p99_9": silver_info["extreme_sampled_p99_9_readings"],
            "p99_9_threshold_kwh": silver_info["sampled_p99_9_threshold_kwh"],
            "threshold_method": silver_info["quantile_method"],
            "quantile_sample_count": silver_info["quantile_sample_count"],
            "invalid_values_are_retained_in_silver": True,
        },
        "gold": {
            "row_count": len(gold),
            "column_count": len(gold.columns),
            "training_example_count": int(gold["is_training_example"].sum()),
            "prediction_eligible_count": int(gold["is_prediction_eligible"].sum()),
            "latest_prediction_entity_count": len(latest),
            "date_start": gold["date"].min().isoformat(),
            "date_end": gold["date"].max().isoformat(),
            "feature_columns": [
                column
                for column in gold.columns
                if column
                in {
                    "lag_1d",
                    "lag_7d",
                    "lag_14d",
                    "rolling_mean_3d",
                    "rolling_mean_7d",
                    "rolling_mean_14d",
                    "rolling_std_7d",
                    "rolling_mean_30d",
                    "rolling_std_30d",
                    "recent_vs_month_mean",
                    "recent_vs_prior_week",
                    "history_mean",
                    "history_median",
                    "history_p90",
                    "actual_cycle_kwh_so_far",
                    "elapsed_days",
                    "days_remaining",
                    "day_of_week",
                    "is_weekend",
                    "month_num",
                    "day_of_year",
                    "year",
                    "sin_doy",
                    "cos_doy",
                    "coverage_today",
                    "coverage_7d_mean",
                    "valid_intervals_7d",
                }
            ],
        },
        "outputs": {
            "bronze": str(bronze_path.relative_to(project_root)),
            "silver": str(silver_path.relative_to(project_root)),
            "gold": str(gold_path.relative_to(project_root)),
            "latest_gold_features": str(latest_path.relative_to(project_root)),
        },
        "started_at_utc": started_at,
        "status": "completed",
    }
    reports = project_root / "data" / "reports"
    _write_json(reports / "data_profile" / "customer_profile.json", report)
    _write_json(reports / "data_quality" / "customer_quality.json", report)
    _write_json(
        reports / "lineage" / "customer_lineage.json",
        {
            "dataset": "customer_interval_readings",
            "source": str(raw_path.relative_to(project_root)),
            "source_sha256": source_checksum,
            "transform": "app.data_engineering.pipeline.prepare_customer_data",
            "started_at_utc": started_at,
            "completed_at_utc": finished_at,
            "outputs": report["outputs"],
        },
    )
    markdown = [
        "# Customer dataset profile",
        "",
        f"- Status: {report['status']}",
        f"- Source: `{report['source']}`",
        f"- Source SHA-256: `{source_checksum}`",
        f"- Source timestamps: {report['source_rows']:,}",
        f"- Households/meters: {report['household_count']:,}",
        f"- Interval records in Silver: {report['interval_reading_count']:,}",
        f"- Gold customer-day rows: {len(gold):,}",
        f"- Training-eligible rows: {report['gold']['training_example_count']:,}",
        f"- Prediction-eligible rows: {report['gold']['prediction_eligible_count']:,}",
        f"- Missing readings: {report['reading_quality']['missing']:,}",
        f"- Negative readings: {report['reading_quality']['negative']:,}",
        f"- Zero readings retained as valid: {report['reading_quality']['zero']:,}",
        f"- Sampled global p99.9 audit threshold: "
        f"{report['reading_quality']['p99_9_threshold_kwh']:.6g} kWh",
        "",
        "The sampled extreme-value flag is for review only; it does not modify or "
        "exclude readings. The trained-model inference features are calculated "
        "causally from data available through each forecast-origin date.",
    ]
    (reports / "data_profile").mkdir(parents=True, exist_ok=True)
    (reports / "data_profile" / "customer_profile.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
    return report
