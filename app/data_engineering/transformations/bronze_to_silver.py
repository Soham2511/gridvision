"""Create source-faithful Bronze and quality-flagged customer Silver data."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

EXPECTED_INTERVAL = pd.Timedelta(minutes=15)
INTERVALS_PER_DAY = 96


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_bronze_snapshot(source: Path, destination: Path, overwrite: bool) -> None:
    """Copy an immutable raw Parquet snapshot into the Bronze layer."""
    if not source.is_file():
        raise FileNotFoundError(f"Customer source dataset does not exist: {source}")
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"Bronze output already exists: {destination}. "
            "Use --overwrite to replace it."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _timestamp_profile(parquet: pq.ParquetFile) -> dict[str, Any]:
    """Validate timestamp ordering and summarize observed interval cadence."""
    if "timestamp" not in parquet.schema_arrow.names:
        raise ValueError("Customer snapshot must contain a 'timestamp' column.")
    timestamps = parquet.read(columns=["timestamp"]).column("timestamp").to_pandas()
    if timestamps.isna().any():
        raise ValueError("Customer snapshot contains null timestamps.")
    if timestamps.duplicated().any():
        raise ValueError("Customer snapshot contains duplicate timestamps.")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("Customer snapshot timestamps must be ordered.")

    gaps = timestamps.diff().dropna()
    return {
        "row_count": len(timestamps),
        "first_timestamp": timestamps.iloc[0].isoformat(),
        "last_timestamp": timestamps.iloc[-1].isoformat(),
        "timestamp_ordered": True,
        "duplicate_timestamps": 0,
        "expected_interval": str(EXPECTED_INTERVAL),
        "nonstandard_interval_count": int(gaps.ne(EXPECTED_INTERVAL).sum()),
        "interval_counts": {
            str(value): int(count)
            for value, count in gaps.value_counts().head(10).items()
        },
    }


def _meter_columns(parquet: pq.ParquetFile) -> list[str]:
    """Return numeric meter columns and reject unsupported source schemas."""
    names = parquet.schema_arrow.names
    if not names or names[0] != "timestamp":
        raise ValueError("Expected 'timestamp' as the first source column.")
    meter_columns = names[1:]
    if not meter_columns:
        raise ValueError("Customer snapshot has no meter columns.")
    non_numeric = [
        field.name
        for field in parquet.schema_arrow
        if field.name != "timestamp"
        and not pa.types.is_integer(field.type)
        and not pa.types.is_floating(field.type)
    ]
    if non_numeric:
        raise ValueError(f"Meter columns must be numeric: {non_numeric[:10]}")
    return meter_columns


def _sampled_global_quantile(
    parquet: pq.ParquetFile,
    meter_columns: list[str],
    batch_size: int,
    quantile: float = 0.999,
) -> tuple[float, int]:
    """Estimate a global value quantile using a deterministic every-31st sample."""
    samples: list[np.ndarray] = []
    for batch in parquet.iter_batches(
        batch_size=batch_size, columns=["timestamp", *meter_columns]
    ):
        frame = batch.to_pandas()
        values = frame[meter_columns].to_numpy(dtype=np.float64, copy=False)
        sample = values.ravel()[::31]
        samples.append(sample[np.isfinite(sample)])
    if not samples or not any(sample.size for sample in samples):
        raise ValueError("Customer readings contain no finite numeric values.")
    sampled_values = np.concatenate(samples)
    return float(np.quantile(sampled_values, quantile)), int(sampled_values.size)


def create_customer_silver(
    source_path: Path,
    destination_path: Path,
    batch_size: int = 2048,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Melt the wide interval snapshot into a chunk-written, flagged Silver table.

    Negative readings are retained in Silver and marked; zeros remain valid
    measurements. A sampled global p99.9 threshold is used only as an audit flag,
    not to discard or modify readings.
    """
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Customer source dataset does not exist: {source_path}"
        )
    if destination_path.exists() and not overwrite:
        raise FileExistsError(
            f"Silver output already exists: {destination_path}. "
            "Use --overwrite to replace it."
        )
    parquet = pq.ParquetFile(source_path)
    timestamp_profile = _timestamp_profile(parquet)
    meter_columns = _meter_columns(parquet)
    threshold, sample_count = _sampled_global_quantile(
        parquet, meter_columns, batch_size
    )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_suffix(destination_path.suffix + ".tmp")
    writer: pq.ParquetWriter | None = None
    missing_total = negative_total = zero_total = extreme_total = 0
    try:
        for batch in parquet.iter_batches(
            batch_size=batch_size, columns=["timestamp", *meter_columns]
        ):
            frame = batch.to_pandas()
            timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
            values = frame[meter_columns].to_numpy(dtype=np.float64, copy=False)
            flattened = values.ravel()
            missing = np.isnan(flattened)
            negative = flattened < 0
            extreme = np.isfinite(flattened) & (flattened > threshold)
            long_frame = pd.DataFrame(
                {
                    "timestamp": np.repeat(timestamps.to_numpy(), len(meter_columns)),
                    "household_id": np.tile(
                        np.asarray(meter_columns, dtype=object), len(timestamps)
                    ),
                    "interval_kwh": flattened,
                    "is_missing": missing,
                    "is_negative": negative,
                    "is_extreme_sampled_p99_9": extreme,
                }
            )
            arrow_table = pa.Table.from_pandas(long_frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(
                    temporary,
                    arrow_table.schema,
                    compression="zstd",
                    compression_level=3,
                )
            writer.write_table(arrow_table, row_group_size=250_000)
            missing_total += int(missing.sum())
            negative_total += int(negative.sum())
            zero_total += int(np.count_nonzero(flattened == 0))
            extreme_total += int(extreme.sum())
        if writer is None:
            raise ValueError("Customer snapshot is empty.")
        writer.close()
        writer = None
        temporary.replace(destination_path)
    finally:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)

    return {
        **timestamp_profile,
        "meter_count": len(meter_columns),
        "interval_reading_count": timestamp_profile["row_count"] * len(meter_columns),
        "missing_readings": missing_total,
        "negative_readings": negative_total,
        "zero_readings": zero_total,
        "extreme_sampled_p99_9_readings": extreme_total,
        "sampled_p99_9_threshold_kwh": threshold,
        "quantile_sample_count": sample_count,
        "quantile_method": "deterministic every-31st-value sample; audit flag only",
        "silver_path": str(destination_path),
    }
