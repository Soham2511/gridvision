"""Idempotent sample-to-silver/gold transforms for the customer energy DAG."""

from __future__ import annotations

import gc
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import duckdb
import pyarrow.compute as pc
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("GRIDVISION_DATA_DIR", PROJECT_ROOT / "data")).resolve()
LOG_ROOT = Path(
    os.getenv("GRIDVISION_LOG_DIR", PROJECT_ROOT / "logs")
).resolve()
SOURCE_PATH = Path(
    os.getenv(
        "GRIDVISION_SOURCE_PATH",
        DATA_ROOT / "sample" / "training_sample_50000.parquet",
    )
).resolve()
BRONZE_PATH = DATA_ROOT / "bronze" / SOURCE_PATH.name
SILVER_PATH = DATA_ROOT / "silver" / "customer_silver.parquet"
GOLD_PATH = DATA_ROOT / "gold" / "customer_gold.parquet"
MIN_MONTH_COVERAGE = float(os.getenv("CUSTOMER_MIN_MONTH_COVERAGE", "0.95"))
TARIFF_INR_PER_KWH = float(os.getenv("CUSTOMER_TARIFF_INR_PER_KWH", "10.0"))
DUCKDB_MEMORY_LIMIT = os.getenv("CUSTOMER_DUCKDB_MEMORY_LIMIT", "4GB")
DUCKDB_THREADS = max(1, int(os.getenv("CUSTOMER_DUCKDB_THREADS", "2")))
FILTER_BATCH_SIZE = 65536
GOLD_PARTITION_COUNT = max(1, int(os.getenv("CUSTOMER_GOLD_PARTITIONS", "64")))
DUCKDB_TEMP_DIR = Path(
    os.getenv(
        "CUSTOMER_DUCKDB_TEMP_DIR",
        Path.home() / ".cache" / "gridvision" / "duckdb_temp",
    )
).expanduser().resolve()
DATASET_VERSIONS_DIR = DATA_ROOT / "metadata" / "dataset_versions"
QUALITY_REPORTS_DIR = LOG_ROOT / "data" / "quality_reports"
MLFLOW_DATA_QUALITY_EXPERIMENT = os.getenv(
    "MLFLOW_DATA_QUALITY_EXPERIMENT", "GridVision Data Quality"
)


def _connect() -> duckdb.DuckDBPyConnection:
    """Create a bounded DuckDB connection with a configurable spill directory."""
    DUCKDB_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute(f"SET threads = {DUCKDB_THREADS}")
    connection.execute("SET preserve_insertion_order = false")
    connection.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    escaped_spill_dir = DUCKDB_TEMP_DIR.as_posix().replace("'", "''")
    connection.execute(f"SET temp_directory = '{escaped_spill_dir}'")
    return connection


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stage_path = path.with_suffix(f"{path.suffix}.stage")
    stage_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    stage_path.replace(path)


def _latest_dataset_manifest(dataset_name: str) -> dict[str, Any] | None:
    path = DATASET_VERSIONS_DIR / dataset_name / "latest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_columns(parquet_path: Path) -> list[dict[str, str]]:
    schema = pq.read_schema(parquet_path)
    return [{"name": field.name, "type": str(field.type)} for field in schema]


def _record_dataset(
    *,
    dataset_name: str,
    stage: str,
    dataset_path: Path,
    row_count: int,
    quality_checks: dict[str, dict[str, Any]],
    parameters: dict[str, Any] | None = None,
    parent_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist dataset quality and lineage records and log them to MLflow if configured."""
    created_at = datetime.now(timezone.utc).isoformat()
    version = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    report = {
        "dataset_name": dataset_name,
        "dataset_version": version,
        "stage": stage,
        "created_at": created_at,
        "dataset_path": str(dataset_path),
        "row_count": row_count,
        "size_bytes": dataset_path.stat().st_size,
        "columns": _schema_columns(dataset_path),
        "quality_checks": quality_checks,
        "quality_passed": all(
            check["passed"] for check in quality_checks.values()
        ),
        "parameters": parameters or {},
        "parent_dataset_versions": parent_versions or {},
    }
    report_path = QUALITY_REPORTS_DIR / f"{stage}_{version}.json"
    version_dir = DATASET_VERSIONS_DIR / dataset_name
    manifest_path = version_dir / f"{version}.json"
    versioned_dataset_path = version_dir / f"{version}{dataset_path.suffix}"
    version_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.link(dataset_path, versioned_dataset_path)
    except OSError as exc:
        raise RuntimeError(
            "Could not create a dataset-version snapshot using a hard link. "
            f"Source: {dataset_path}; destination: {versioned_dataset_path}. "
            "Keep the dataset and metadata directories on the same filesystem."
        ) from exc
    report["quality_report"] = str(report_path)
    report["manifest_path"] = str(manifest_path)
    report["versioned_dataset_path"] = str(versioned_dataset_path)

    _json_write(report_path, report)
    _json_write(manifest_path, report)

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if tracking_uri:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        # Do not use MLflow's default experiment: its artifact URI may predate
        # the HTTP tracking server and point at a host-local Windows path.
        mlflow.set_experiment(MLFLOW_DATA_QUALITY_EXPERIMENT)
        with mlflow.start_run(run_name=f"data-quality-{stage}") as run:
            mlflow.set_tags(
                {
                    "run_type": "data_quality",
                    "dataset_name": dataset_name,
                    "dataset_version": version,
                    "pipeline_stage": stage,
                    "quality_passed": str(report["quality_passed"]).lower(),
                    **{
                        f"parent_{name}_version": parent_version
                        for name, parent_version in (parent_versions or {}).items()
                    },
                }
            )
            mlflow.log_params(
                {
                    "dataset_path": str(dataset_path),
                    "row_count": row_count,
                    **{
                        f"parameter_{key}": value
                        for key, value in (parameters or {}).items()
                        if isinstance(value, (str, int, float, bool))
                    },
                }
            )
            mlflow.log_metric("row_count", row_count)
            mlflow.log_metric(
                "quality_checks_passed",
                sum(check["passed"] for check in quality_checks.values()),
            )
            mlflow.log_metric("quality_checks_total", len(quality_checks))
            report["mlflow_run_id"] = run.info.run_id
            _json_write(report_path, report)
            _json_write(manifest_path, report)
            mlflow.log_artifact(str(report_path), artifact_path="data_quality")
            mlflow.log_artifact(str(manifest_path), artifact_path="dataset_lineage")
    else:
        _json_write(report_path, report)
        _json_write(manifest_path, report)

    latest_path = version_dir / "latest.json"
    _json_write(latest_path, report)
    if not report["quality_passed"]:
        failed = [
            name
            for name, check in quality_checks.items()
            if not check["passed"]
        ]
        raise ValueError(
            f"{stage} quality checks failed for {dataset_path}: {failed}. "
            f"See report {report_path}."
        )
    return {
        "dataset_version": version,
        "quality_report": str(report_path),
        "manifest": str(manifest_path),
        "quality_passed": report["quality_passed"],
        "mlflow_run_id": report.get("mlflow_run_id"),
    }


def _files_match(source: Path, destination: Path) -> bool:
    """Compare file contents exactly without loading either file into memory."""
    if source.stat().st_size != destination.stat().st_size:
        return False
    if os.path.samefile(source, destination):
        return True
    with source.open("rb") as source_file, destination.open("rb") as destination_file:
        while True:
            source_chunk = source_file.read(1024 * 1024)
            destination_chunk = destination_file.read(1024 * 1024)
            if source_chunk != destination_chunk:
                return False
            if not source_chunk:
                return True


def _sql_path(path: Path) -> str:
    """Return a path as a safely escaped DuckDB SQL string literal."""
    return "'" + str(path).replace("'", "''") + "'"


def create_bronze(
    source_path: str | Path = SOURCE_PATH,
    bronze_path: str | Path = BRONZE_PATH,
) -> dict[str, Any]:
    """Register the source byte-for-byte as bronze without a second full copy when possible."""
    source = Path(source_path).resolve()
    bronze = Path(bronze_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source Parquet file does not exist: {source}")
    pq.read_metadata(source)
    bronze.parent.mkdir(parents=True, exist_ok=True)
    copy_mode = "same_file"
    if bronze == source:
        output = bronze
    elif bronze.exists() and _files_match(source, bronze):
        output = bronze
        copy_mode = "reused"
    else:
        stage_path = bronze.with_name(f"{bronze.name}.stage")
        if stage_path.exists():
            stage_path.unlink()
        try:
            os.link(source, stage_path)
            copy_mode = "hardlink"
        except OSError:
            shutil.copy2(source, stage_path)
            copy_mode = "copy"
        stage_path.replace(bronze)
        output = bronze

    metadata = pq.read_metadata(output)
    source_matches = bronze == source or _files_match(source, output)
    quality = _record_dataset(
        dataset_name="customer_bronze",
        stage="bronze",
        dataset_path=output,
        row_count=metadata.num_rows,
        quality_checks={
            "parquet_readable": {"passed": metadata.num_rows > 0, "observed": metadata.num_rows},
            "has_columns": {
                "passed": len(metadata.schema) > 0,
                "observed": len(metadata.schema),
            },
            "source_size_matches": {
                "passed": output.stat().st_size == source.stat().st_size,
                "observed": output.stat().st_size,
                "expected": source.stat().st_size,
            },
            "source_content_matches": {
                "passed": source_matches,
                "observed": source_matches,
            },
        },
        parameters={"source_path": str(source), "copy_mode": copy_mode},
    )
    return {"path": str(output), "rows": metadata.num_rows, **quality}


def create_customer_silver(
    source_path: str | Path = BRONZE_PATH,
    silver_path: str | Path = SILVER_PATH,
) -> dict[str, Any]:
    """Filter Bronze to residential rows without changing or grouping the records."""
    source = Path(source_path).resolve()
    silver = Path(silver_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Bronze dataset does not exist: {source}")
    silver.parent.mkdir(parents=True, exist_ok=True)
    stage_path = silver.with_name(f"{silver.stem}.stage{silver.suffix}")
    stage_path.unlink(missing_ok=True)
    parquet_file = pq.ParquetFile(source)
    use_type_index = parquet_file.schema_arrow.get_field_index("GeneralUseType")
    if use_type_index < 0:
        raise ValueError(f"Bronze dataset is missing GeneralUseType: {source}")

    row_count = 0
    try:
        with pq.ParquetWriter(
            stage_path,
            schema=parquet_file.schema_arrow,
            compression="zstd",
        ) as writer:
            for batch in parquet_file.iter_batches(batch_size=FILTER_BATCH_SIZE):
                use_types = batch.column(use_type_index)
                is_residential = pc.fill_null(
                    pc.equal(
                        pc.utf8_trim(use_types, characters=" \t\n\r"),
                        "Residential",
                    ),
                    False,
                )
                residential_batch = pc.filter(batch, is_residential)
                if residential_batch.num_rows:
                    writer.write_batch(residential_batch)
                    row_count += residential_batch.num_rows
        if row_count == 0:
            raise RuntimeError("Silver filter produced no residential rows.")
        stage_path.replace(silver)
    finally:
        stage_path.unlink(missing_ok=True)

    quality = _record_dataset(
        dataset_name="customer_silver",
        stage="silver",
        dataset_path=silver,
        row_count=row_count,
        quality_checks={
            "non_empty": {"passed": row_count > 0, "observed": row_count},
            "residential_only": {
                "passed": True,
                "filter": "GeneralUseType = Residential",
            },
        },
        parameters={"filter": "GeneralUseType = Residential"},
        parent_versions={
            "customer_bronze": (
                _latest_dataset_manifest("customer_bronze") or {}
            ).get("dataset_version", "untracked"),
        },
    )
    return {
        "path": str(silver),
        "rows": row_count,
        **quality,
    }


def build_customer_bill_gold(
    silver_path: str | Path = SILVER_PATH,
    output_path: str | Path = GOLD_PATH,
) -> dict[str, Any]:
    """Build leakage-safe residential monthly labels and cutoff features."""
    silver = Path(silver_path).resolve()
    output = Path(output_path).resolve()
    if not silver.is_file():
        raise FileNotFoundError(f"Silver dataset does not exist: {silver}")
    query = f"""
        WITH observations AS (
            SELECT
                TRY_CAST("OBJECTID" AS BIGINT) AS entity_id,
                TRY_CAST("timestamp" AS TIMESTAMP) AS observed_at,
                TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) AS energy_kwh
            FROM read_parquet(__SILVER_INPUT__)
            WHERE TRIM("GeneralUseType") = 'Residential'
              AND TRY_CAST("OBJECTID" AS BIGINT) IS NOT NULL
              AND TRY_CAST("timestamp" AS TIMESTAMP) IS NOT NULL
              AND TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) >= 0
              AND isfinite(TRY_CAST("normalized_building_energy_kwh" AS DOUBLE))
        ), entity_metadata AS (
            SELECT
                TRY_CAST("OBJECTID" AS BIGINT) AS entity_id,
                ANY_VALUE("idf.kw") AS idf_kw,
                ANY_VALUE(TRY_CAST("id.grid.coarse" AS BIGINT)) AS id_grid_coarse,
                ANY_VALUE(TRY_CAST("building.area.m2" AS DOUBLE)) AS building_area_m2,
                ANY_VALUE(TRY_CAST("FootprintArea.m2" AS DOUBLE)) AS footprint_area_m2,
                ANY_VALUE("SpecificUseType") AS specific_use_type,
                ANY_VALUE(TRY_CAST("EffectiveYearBuilt" AS DOUBLE)) AS effective_year_built,
                ANY_VALUE("building.type") AS building_type,
                ANY_VALUE("vintage") AS vintage,
                ANY_VALUE("usetype") AS usetype,
                ANY_VALUE(TRY_CAST("id.grid.finer" AS DOUBLE)) AS id_grid_finer,
                ANY_VALUE("id.tract") AS id_tract,
                ANY_VALUE(TRY_CAST("latitude" AS DOUBLE)) AS latitude,
                ANY_VALUE(TRY_CAST("longitude" AS DOUBLE)) AS longitude
            FROM read_parquet(__SILVER_INPUT__)
            WHERE TRIM("GeneralUseType") = 'Residential'
              AND TRY_CAST("OBJECTID" AS BIGINT) IS NOT NULL
            GROUP BY entity_id
        ), hourly AS (
            SELECT
                entity_id,
                observed_at,
                AVG(energy_kwh) AS energy_kwh
            FROM observations
            GROUP BY entity_id, observed_at
        ), monthly AS (
            SELECT
                entity_id,
                DATE_TRUNC('month', observed_at)::DATE AS month_start,
                SUM(energy_kwh) AS monthly_kwh,
                COUNT(*) AS observed_hours,
                24 * DAY(LAST_DAY(ANY_VALUE(observed_at))) AS expected_hours,
                SUM(energy_kwh) FILTER (WHERE observed_at < DATE_TRUNC('month', observed_at) + INTERVAL 7 DAY) AS energy_days_1_7_kwh,
                COUNT(*) FILTER (WHERE observed_at < DATE_TRUNC('month', observed_at) + INTERVAL 7 DAY) AS hours_days_1_7,
                SUM(energy_kwh) FILTER (WHERE observed_at >= DATE_TRUNC('month', observed_at) + INTERVAL 7 DAY AND observed_at < DATE_TRUNC('month', observed_at) + INTERVAL 14 DAY) AS energy_days_8_14_kwh,
                COUNT(*) FILTER (WHERE observed_at >= DATE_TRUNC('month', observed_at) + INTERVAL 7 DAY AND observed_at < DATE_TRUNC('month', observed_at) + INTERVAL 14 DAY) AS hours_days_8_14,
                SUM(energy_kwh) FILTER (WHERE observed_at >= DATE_TRUNC('month', observed_at) + INTERVAL 14 DAY AND observed_at < DATE_TRUNC('month', observed_at) + INTERVAL 21 DAY) AS energy_days_15_21_kwh,
                COUNT(*) FILTER (WHERE observed_at >= DATE_TRUNC('month', observed_at) + INTERVAL 14 DAY AND observed_at < DATE_TRUNC('month', observed_at) + INTERVAL 21 DAY) AS hours_days_15_21
            FROM hourly
            GROUP BY entity_id, DATE_TRUNC('month', observed_at)::DATE
        ), complete AS (
            SELECT *, observed_hours * 1.0 / expected_hours AS coverage_ratio
            FROM monthly
            WHERE observed_hours * 1.0 / expected_hours >= {MIN_MONTH_COVERAGE}
        ), lagged AS (
            SELECT *,
                LAG(monthly_kwh) OVER (PARTITION BY entity_id ORDER BY month_start) AS previous_month_kwh,
                LAG(month_start) OVER (PARTITION BY entity_id ORDER BY month_start) AS previous_month_start
            FROM complete
        ), base AS (
            SELECT *,
                CASE WHEN previous_month_start = month_start - INTERVAL 1 MONTH
                     THEN previous_month_kwh END AS prior_month_kwh,
                DAY(LAST_DAY(month_start)) AS days_in_month,
                MONTH(month_start) AS month_of_year,
                SIN(2 * PI() * MONTH(month_start) / 12.0) AS month_sin,
                COS(2 * PI() * MONTH(month_start) / 12.0) AS month_cos
            FROM lagged
        ), cutoffs AS (
            SELECT *, 7 AS cutoff_day, energy_days_1_7_kwh AS cumulative_energy_kwh,
                energy_days_1_7_kwh AS recent_7d_energy_kwh, hours_days_1_7 AS observed_hours_to_cutoff,
                hours_days_1_7 AS recent_7d_hours
            FROM base
            UNION ALL
            SELECT *, 14, energy_days_1_7_kwh + energy_days_8_14_kwh,
                energy_days_8_14_kwh, hours_days_1_7 + hours_days_8_14, hours_days_8_14
            FROM base
            UNION ALL
            SELECT *, 21, energy_days_1_7_kwh + energy_days_8_14_kwh + energy_days_15_21_kwh,
                energy_days_15_21_kwh, hours_days_1_7 + hours_days_8_14 + hours_days_15_21, hours_days_15_21
            FROM base
        )
        SELECT
            c.entity_id,
            c.month_start,
            m.idf_kw,
            m.id_grid_coarse,
            m.building_area_m2,
            m.footprint_area_m2,
            m.specific_use_type,
            m.effective_year_built,
            m.building_type,
            m.vintage,
            m.usetype,
            m.id_grid_finer,
            m.id_tract,
            m.latitude,
            m.longitude,
            c.coverage_ratio,
            c.observed_hours,
            c.expected_hours,
            c.cutoff_day,
            c.days_in_month,
            c.month_of_year,
            c.month_sin,
            c.month_cos,
            c.prior_month_kwh,
            c.prior_month_kwh / NULLIF(m.building_area_m2, 0) AS prior_month_kwh_per_m2,
            c.observed_hours_to_cutoff,
            c.cumulative_energy_kwh,
            c.recent_7d_energy_kwh,
            c.recent_7d_energy_kwh / NULLIF(c.recent_7d_hours, 0) AS recent_7d_mean_hourly_kwh,
            c.cumulative_energy_kwh / NULLIF(c.observed_hours_to_cutoff, 0) AS mean_hourly_energy_to_cutoff,
            c.cumulative_energy_kwh / NULLIF(m.building_area_m2, 0) AS cumulative_energy_per_m2,
            c.cumulative_energy_kwh / c.cutoff_day * c.days_in_month AS naive_projected_month_kwh,
            c.monthly_kwh AS target_month_kwh,
            c.monthly_kwh * {TARIFF_INR_PER_KWH} AS target_bill_inr
        FROM cutoffs c
        JOIN entity_metadata m USING (entity_id)
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.stem}.stage-",
        dir=output.parent,
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        input_partitions_path = temporary_root / "input"
        gold_parts_path = temporary_root / "gold_parts"
        gold_parts_path.mkdir()
        stage_path = temporary_root / output.name
        partition_query = f"""
            SELECT *,
                COALESCE(
                    hash(TRY_CAST("OBJECTID" AS BIGINT)) % {GOLD_PARTITION_COUNT},
                    {GOLD_PARTITION_COUNT}
                ) AS "_gold_partition"
            FROM read_parquet({_sql_path(silver)})
            WHERE TRIM("GeneralUseType") = 'Residential'
              AND TRY_CAST("OBJECTID" AS BIGINT) IS NOT NULL
              AND TRY_CAST("timestamp" AS TIMESTAMP) IS NOT NULL
              AND TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) >= 0
              AND isfinite(TRY_CAST("normalized_building_energy_kwh" AS DOUBLE))
        """
        partition_conn = _connect()
        try:
            partition_conn.execute(
                f"COPY ({partition_query}) TO {_sql_path(input_partitions_path)} "
                "(FORMAT PARQUET, PARTITION_BY (_gold_partition), "
                "COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
            )
        finally:
            partition_conn.close()

        gold_parts: list[Path] = []
        for partition in range(GOLD_PARTITION_COUNT + 1):
            input_partition = (
                input_partitions_path
                / f"_gold_partition={partition}"
                / "*.parquet"
            )
            if not list(input_partition.parent.glob("*.parquet")):
                continue
            gold_part = gold_parts_path / f"part-{partition:02d}.parquet"
            partitioned_query = query.replace(
                "__SILVER_INPUT__",
                _sql_path(input_partition),
            )
            logger.info("Processing gold partition %s/%s", partition, GOLD_PARTITION_COUNT)
            part_conn = _connect()
            try:
                part_conn.execute(
                    f"COPY ({partitioned_query}) TO {_sql_path(gold_part)} "
                    "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
                )
            finally:
                part_conn.close()
                del part_conn
                gc.collect()
            gold_parts.append(gold_part)

        if not gold_parts:
            raise RuntimeError("Gold transform created no rows.")
        gold_parts_sql = ", ".join(_sql_path(path) for path in gold_parts)
        merge_conn = _connect()
        try:
            merge_conn.execute(
                f"COPY (SELECT * FROM read_parquet([{gold_parts_sql}])) "
                f"TO {_sql_path(stage_path)} "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
            )
        finally:
            merge_conn.close()

        if pq.read_metadata(stage_path).num_rows == 0:
            raise RuntimeError(f"Transform produced an empty dataset: {output}")
        stage_path.replace(output)

    output_sql = _sql_path(output)
    summary_conn = _connect()
    try:
        summary = summary_conn.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                COUNT(DISTINCT entity_id) AS entity_count,
                COUNT(*) FILTER (WHERE entity_id IS NULL) AS null_entity_rows,
                COUNT(*) FILTER (WHERE month_start IS NULL) AS null_month_rows,
                COUNT(*) FILTER (WHERE target_month_kwh IS NULL) AS null_target_rows,
                COUNT(*) FILTER (WHERE NOT isfinite(target_month_kwh)) AS non_finite_target_rows,
                COUNT(*) FILTER (WHERE target_month_kwh < 0) AS negative_target_rows,
                MIN(target_month_kwh) AS min_target_kwh,
                MAX(target_month_kwh) AS max_target_kwh,
                MIN(coverage_ratio) AS min_coverage_ratio
            FROM read_parquet({output_sql})
            """
        ).fetchone()
        duplicate_keys = summary_conn.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT entity_id, month_start, cutoff_day
                FROM read_parquet({output_sql})
                GROUP BY entity_id, month_start, cutoff_day
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    finally:
        summary_conn.close()

    quality = _record_dataset(
        dataset_name="customer_gold",
        stage="gold",
        dataset_path=output,
        row_count=int(summary[0]),
        quality_checks={
            "non_empty": {"passed": summary[0] > 0, "observed": int(summary[0])},
            "required_keys_present": {
                "passed": summary[2] == 0 and summary[3] == 0,
                "null_entity_rows": int(summary[2]),
                "null_month_rows": int(summary[3]),
            },
            "valid_target": {
                "passed": (
                    summary[4] == 0
                    and summary[5] == 0
                    and summary[6] == 0
                ),
                "null_target_rows": int(summary[4]),
                "non_finite_target_rows": int(summary[5]),
                "negative_target_rows": int(summary[6]),
                "minimum_target_kwh": summary[7],
                "maximum_target_kwh": summary[8],
            },
            "valid_month_coverage": {
                "passed": (
                    summary[9] is not None
                    and summary[9] >= MIN_MONTH_COVERAGE
                ),
                "minimum_observed_coverage": summary[9],
                "required_coverage": MIN_MONTH_COVERAGE,
            },
            "unique_entity_month_cutoff": {
                "passed": duplicate_keys == 0,
                "duplicate_keys": int(duplicate_keys),
            },
        },
        parameters={
            "minimum_month_coverage": MIN_MONTH_COVERAGE,
            "tariff_inr_per_kwh": TARIFF_INR_PER_KWH,
        },
        parent_versions={
            "customer_silver": (
                _latest_dataset_manifest("customer_silver") or {}
            ).get("dataset_version", "untracked"),
        },
    )
    return {
        "path": str(output),
        "rows": pq.read_metadata(output).num_rows,
        "unique_buildings": int(summary[1]),
        **quality,
    }
