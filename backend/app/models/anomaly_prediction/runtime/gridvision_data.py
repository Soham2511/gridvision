"""Streaming bronze/silver/gold data layers for GridVision."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from gridvision_pipeline import CUSTOMER, ENERGY, INPUT_COLUMNS, LATITUDE, LONGITUDE

MODEL_INPUT_SCHEMA = pa.schema(
    [
        (CUSTOMER, pa.int64()),
        ("timestamp", pa.timestamp("ns")),
        (ENERGY, pa.float32()),
        (LATITUDE, pa.float64()),
        (LONGITUDE, pa.float64()),
    ]
)
NUMERIC_MODEL_COLUMNS = (ENERGY, LATITUDE, LONGITUDE)
GOLD_BASE_COLUMNS = INPUT_COLUMNS + ["baseline"]


def parse_bronze_to_silver(
    bronze_path: str | Path,
    silver_path: str | Path,
    batch_size: int = 250_000,
) -> dict[str, Any]:
    """Parse an Arrow-readable bronze parquet while preserving every source column."""
    source = Path(bronze_path).resolve()
    destination = Path(silver_path).resolve()
    if source == destination:
        raise ValueError("Bronze and silver parquet paths must be different.")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")
    if not source.is_file():
        raise FileNotFoundError(f"Bronze parquet file does not exist: {source}")

    parquet = pq.ParquetFile(source)
    if "timestamp" not in parquet.schema.names:
        raise ValueError("Bronze parquet is missing required timestamp column.")
    schema = parquet.schema_arrow
    timestamp_type = schema.field("timestamp").type
    if not pa.types.is_timestamp(timestamp_type):
        raise ValueError(
            "Bronze timestamp must be parseable as an Arrow timestamp; "
            f"found {timestamp_type}."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(f".{destination.name}.tmp")
    writer: pq.ParquetWriter | None = None
    row_count = 0
    try:
        writer = pq.ParquetWriter(temporary_path, schema, compression="zstd")
        for batch in parquet.iter_batches(batch_size=batch_size):
            table = pa.Table.from_batches([batch])
            if table.schema != schema:
                table = table.cast(schema, safe=True)
            writer.write_table(table)
            row_count += table.num_rows
        writer.close()
        writer = None
        if row_count == 0:
            raise ValueError("Bronze parquet contains no rows.")
        os.replace(temporary_path, destination)
    except Exception:
        if writer is not None:
            writer.close()
        temporary_path.unlink(missing_ok=True)
        raise

    silver = pq.ParquetFile(destination)
    return {
        "bronze_path": str(source),
        "path": str(destination),
        "rows": row_count,
        "columns": silver.schema.names,
        "row_groups": silver.metadata.num_row_groups,
    }


def build_gold_features(
    silver_path: str | Path,
    gold_path: str | Path,
    config: Any | None = None,
) -> dict[str, Any]:
    """Engineer causal model features for the configured customer training sample."""
    from dataclasses import replace

    from gridvision_pipeline import (
        POINT_FEATURES,
        PipelineConfig,
        add_causal_features,
        load_customer_sample,
        split_customers,
    )

    source = Path(silver_path).resolve()
    destination = Path(gold_path).resolve()
    if source == destination:
        raise ValueError("Silver and gold parquet paths must be different.")
    if not source.is_file():
        raise FileNotFoundError(f"Silver parquet file does not exist: {source}")
    pipeline_config = config or PipelineConfig(parquet_path=str(source))
    pipeline_config = replace(pipeline_config, parquet_path=str(source))
    customer_splits, _ = split_customers(source, pipeline_config)
    sampled = load_customer_sample(source, customer_splits)
    features = add_causal_features(sampled)
    gold_columns = GOLD_BASE_COLUMNS + POINT_FEATURES
    missing_features = set(gold_columns) - set(features.columns)
    if missing_features:
        raise ValueError(
            f"Feature engineering omitted expected gold columns: "
            f"{sorted(missing_features)}"
        )
    gold = features.loc[:, gold_columns]

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(f".{destination.name}.tmp")
    try:
        gold.to_parquet(temporary_path, index=False, compression="zstd")
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    prepared = pq.ParquetFile(destination)
    return {
        "silver_path": str(source),
        "path": str(destination),
        "rows": int(prepared.metadata.num_rows),
        "columns": prepared.schema.names,
        "row_groups": prepared.metadata.num_row_groups,
        "sampled_customer_counts": {
            split: len(customer_ids)
            for split, customer_ids in customer_splits.items()
        },
        "feature_columns": ["baseline", *POINT_FEATURES],
    }


def prepare_model_input(
    source_path: str | Path,
    output_path: str | Path,
    batch_size: int = 250_000,
) -> dict[str, Any]:
    """Project and validate source parquet columns without loading the file in memory."""
    source = Path(source_path).resolve()
    destination = Path(output_path).resolve()
    if source == destination:
        raise ValueError("Source and prepared parquet paths must be different.")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")
    if not source.is_file():
        raise FileNotFoundError(f"Source parquet file does not exist: {source}")

    parquet = pq.ParquetFile(source)
    missing_columns = set(INPUT_COLUMNS) - set(parquet.schema.names)
    if missing_columns:
        raise ValueError(
            f"Parquet input is missing model columns: {sorted(missing_columns)}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(f".{destination.name}.tmp")
    writer: pq.ParquetWriter | None = None
    row_count = 0
    try:
        writer = pq.ParquetWriter(temporary_path, MODEL_INPUT_SCHEMA, compression="zstd")
        for batch in parquet.iter_batches(columns=INPUT_COLUMNS, batch_size=batch_size):
            projected = pa.Table.from_batches([batch.select(INPUT_COLUMNS)])
            for name in INPUT_COLUMNS:
                if projected.column(name).null_count:
                    raise ValueError(
                        f"Required model column {name!r} contains null values."
                    )
            for name in NUMERIC_MODEL_COLUMNS:
                finite = pc.is_finite(projected.column(name))
                if not bool(pc.all(finite).as_py()):
                    raise ValueError(
                        f"Required numeric model column {name!r} contains "
                        "non-finite values."
                    )
            try:
                projected = projected.cast(MODEL_INPUT_SCHEMA, safe=True)
            except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as error:
                raise ValueError(
                    "Source model columns do not match the expected numeric and "
                    f"timestamp types: {error}"
                ) from error
            writer.write_table(projected)
            row_count += projected.num_rows
        writer.close()
        writer = None
        if row_count == 0:
            raise ValueError("Source parquet contains no model input rows.")
        os.replace(temporary_path, destination)
    except Exception:
        if writer is not None:
            writer.close()
        temporary_path.unlink(missing_ok=True)
        raise
    prepared = pq.ParquetFile(destination)
    return {
        "source_path": str(source),
        "path": str(destination),
        "rows": row_count,
        "columns": prepared.schema.names,
        "row_groups": prepared.metadata.num_row_groups,
    }
