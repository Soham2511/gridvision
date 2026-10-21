"""Idempotent sample-to-silver/gold transforms for the customer energy DAG."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
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
SAMPLE_CUSTOMER_BUILDINGS = int(os.getenv("CUSTOMER_SAMPLE_BUILDINGS", "1000"))
RANDOM_SEED = int(os.getenv("CUSTOMER_SAMPLE_SEED", "42"))
MIN_MONTH_COVERAGE = float(os.getenv("CUSTOMER_MIN_MONTH_COVERAGE", "0.95"))
TARIFF_INR_PER_KWH = float(os.getenv("CUSTOMER_TARIFF_INR_PER_KWH", "10.0"))
DUCKDB_MEMORY_LIMIT = os.getenv("CUSTOMER_DUCKDB_MEMORY_LIMIT", "4GB")
DUCKDB_TEMP_DIR = Path(
    os.getenv(
        "CUSTOMER_DUCKDB_TEMP_DIR",
        Path.home() / ".cache" / "gridvision" / "duckdb_temp",
    )
).expanduser().resolve()
DATASET_VERSIONS_DIR = DATA_ROOT / "metadata" / "dataset_versions"
QUALITY_REPORTS_DIR = LOG_ROOT / "data" / "quality_reports"


def _connect() -> duckdb.DuckDBPyConnection:
    """Create a bounded DuckDB connection with a configurable spill directory."""
    DUCKDB_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute("SET threads = 4")
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


def _atomic_parquet_copy(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    output_path: Path,
) -> None:
    """Write a Parquet stage and replace the destination only after validation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stage_path = output_path.with_name(f"{output_path.stem}.stage.parquet")
    if stage_path.exists():
        stage_path.unlink()
    escaped_path = str(stage_path).replace("'", "''")
    connection.execute(
        f"COPY ({query}) TO '{escaped_path}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
    )
    if pq.read_metadata(stage_path).num_rows == 0:
        stage_path.unlink(missing_ok=True)
        raise RuntimeError(f"Transform produced an empty dataset: {output_path}")
    stage_path.replace(output_path)


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
    if bronze == source:
        output = bronze
    elif bronze.exists():
        if bronze.stat().st_size != source.stat().st_size:
            raise RuntimeError(
                f"Existing bronze file differs in size from source: {bronze}"
            )
        output = bronze
    else:
        stage_path = bronze.with_name(f"{bronze.name}.stage")
        if stage_path.exists():
            stage_path.unlink()
        try:
            os.link(source, stage_path)
        except OSError:
            shutil.copy2(source, stage_path)
        stage_path.replace(bronze)
        output = bronze

    metadata = pq.read_metadata(output)
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
        },
        parameters={"source_path": str(source), "copy_mode": "hardlink_or_copy"},
    )
    return {"path": str(output), "rows": metadata.num_rows, **quality}


def _proportional_strata_sample(
    profiles: pd.DataFrame,
    group_columns: list[str],
    sample_size: int,
) -> pd.DataFrame:
    """Select a deterministic proportional sample, including missing-value strata."""
    if sample_size >= len(profiles):
        return profiles.copy()
    stratum_sizes = profiles.groupby(
        group_columns, dropna=False, observed=True
    ).size()
    quotas_float = stratum_sizes / stratum_sizes.sum() * sample_size
    quotas = np.floor(quotas_float).astype(int).clip(upper=stratum_sizes.astype(int))
    remaining = sample_size - int(quotas.sum())
    remainders = (quotas_float - np.floor(quotas_float)).sort_values(ascending=False)
    for stratum in remainders.index:
        if remaining == 0:
            break
        if quotas[stratum] < stratum_sizes[stratum]:
            quotas[stratum] += 1
            remaining -= 1
    if remaining:
        for stratum in stratum_sizes.index:
            available = int(stratum_sizes[stratum] - quotas[stratum])
            take = min(available, remaining)
            quotas[stratum] += take
            remaining -= take
            if remaining == 0:
                break
    selected: list[pd.DataFrame] = []
    for stratum, count in quotas.items():
        if count == 0:
            continue
        mask = pd.Series(True, index=profiles.index)
        for column, value in zip(group_columns, stratum):
            mask &= profiles[column].isna() if pd.isna(value) else profiles[column].eq(value)
        selected.append(profiles.loc[mask].nsmallest(int(count), "_stable_hash"))
    result = pd.concat(selected, ignore_index=True)
    if len(result) != sample_size or result["entity_id"].nunique() != sample_size:
        raise RuntimeError(
            f"Expected {sample_size} unique sampled entities; received {len(result)}."
        )
    return result


def create_customer_silver(
    source_path: str | Path = BRONZE_PATH,
    silver_path: str | Path = SILVER_PATH,
    buildings_per_use: int = SAMPLE_CUSTOMER_BUILDINGS,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Sample residential buildings and preserve their hourly source-shaped rows."""
    source = Path(source_path).resolve()
    silver = Path(silver_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Bronze dataset does not exist: {source}")
    if buildings_per_use < 1:
        raise ValueError("buildings_per_use must be a positive integer.")

    connection = _connect()
    try:
        profiles = connection.execute(
            """
            SELECT
                TRY_CAST(OBJECTID AS BIGINT) AS entity_id,
                ANY_VALUE("building.type") AS building_type,
                ANY_VALUE("SpecificUseType") AS specific_use_type
            FROM read_parquet(?)
            WHERE TRIM(GeneralUseType) = 'Residential'
              AND TRY_CAST(OBJECTID AS BIGINT) IS NOT NULL
            GROUP BY TRY_CAST(OBJECTID AS BIGINT)
            """,
            [str(source)],
        ).fetchdf()
        if profiles.empty:
            raise ValueError("No usable building identifiers exist in the source data.")

        profiles["_stable_hash"] = pd.util.hash_pandas_object(
            profiles["entity_id"].astype(str).radd(f"{seed}:"),
            index=False,
        ).to_numpy(dtype="uint64")
        selected_ids = _proportional_strata_sample(
            profiles,
            ["building_type", "specific_use_type"],
            min(buildings_per_use, len(profiles)),
        )[["entity_id"]].drop_duplicates()

        connection.register("selected_entities_df", selected_ids)
        source_columns_sql = ",\n".join(
            [
                'r."OBJECTID"',
                'ANY_VALUE(r."idf.kw") AS "idf.kw"',
                'ANY_VALUE(r."id.grid.coarse") AS "id.grid.coarse"',
                'ANY_VALUE(r."building.area.m2") AS "building.area.m2"',
                'ANY_VALUE(r."FootprintArea.m2") AS "FootprintArea.m2"',
                'ANY_VALUE(r."GeneralUseType") AS "GeneralUseType"',
                'ANY_VALUE(r."SpecificUseType") AS "SpecificUseType"',
                'ANY_VALUE(r."EffectiveYearBuilt") AS "EffectiveYearBuilt"',
                'ANY_VALUE(r."building.type") AS "building.type"',
                'ANY_VALUE(r."vintage") AS "vintage"',
                'ANY_VALUE(r."usetype") AS "usetype"',
                'ANY_VALUE(r."id.grid.finer") AS "id.grid.finer"',
                'ANY_VALUE(r."id.tract") AS "id.tract"',
                'ANY_VALUE(r."latitude") AS "latitude"',
                'ANY_VALUE(r."longitude") AS "longitude"',
                'CAST(r."timestamp" AS TIMESTAMP) AS "timestamp"',
                'AVG(TRY_CAST(r."normalized_building_energy_kwh" AS DOUBLE)) '
                'AS "normalized_building_energy_kwh"',
            ]
        )
        query = f"""
            SELECT {source_columns_sql}
            FROM read_parquet(?) AS r
            INNER JOIN selected_entities_df AS chosen
                ON TRY_CAST(r."OBJECTID" AS BIGINT) = chosen.entity_id
            WHERE TRIM(r."GeneralUseType") = 'Residential'
              AND TRY_CAST(r."timestamp" AS TIMESTAMP) IS NOT NULL
              AND TRY_CAST(r."normalized_building_energy_kwh" AS DOUBLE) >= 0
            GROUP BY r."OBJECTID", CAST(r."timestamp" AS TIMESTAMP)
            ORDER BY "timestamp", r."OBJECTID"
        """
        stage_path = silver.with_name(f"{silver.stem}.stage.parquet")
        if stage_path.exists():
            stage_path.unlink()
        silver.parent.mkdir(parents=True, exist_ok=True)
        escaped_stage = str(stage_path).replace("'", "''")
        escaped_source = str(source).replace("'", "''")
        query = query.replace("read_parquet(?)", f"read_parquet('{escaped_source}')")
        connection.execute(
            f"COPY ({query}) "
            f"TO '{escaped_stage}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
        )
        row_count = pq.read_metadata(stage_path).num_rows
        if row_count == 0:
            stage_path.unlink(missing_ok=True)
            raise RuntimeError("Silver transform created no rows.")
        stage_path.replace(silver)
        silver_sql = str(silver).replace("'", "''")
        summary = connection.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                COUNT(DISTINCT TRY_CAST("OBJECTID" AS BIGINT)) AS entity_count,
                COUNT(*) FILTER (WHERE TRY_CAST("OBJECTID" AS BIGINT) IS NULL) AS invalid_entity_rows,
                COUNT(*) FILTER (WHERE TRY_CAST("timestamp" AS TIMESTAMP) IS NULL) AS invalid_timestamp_rows,
                COUNT(*) FILTER (WHERE TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) IS NULL) AS invalid_energy_rows,
                COUNT(*) FILTER (WHERE NOT isfinite(TRY_CAST("normalized_building_energy_kwh" AS DOUBLE))) AS non_finite_energy_rows,
                COUNT(*) FILTER (WHERE TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) < 0) AS negative_energy_rows,
                COUNT(*) FILTER (WHERE TRIM("GeneralUseType") != 'Residential') AS non_residential_rows
            FROM read_parquet('{silver_sql}')
            """
        ).fetchone()
        duplicate_keys = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT "OBJECTID", "timestamp"
                FROM read_parquet('{silver_sql}')
                GROUP BY "OBJECTID", "timestamp"
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        entity_count = int(summary[1])
        quality = _record_dataset(
            dataset_name="customer_silver",
            stage="silver",
            dataset_path=silver,
            row_count=int(summary[0]),
            quality_checks={
                "non_empty": {"passed": summary[0] > 0, "observed": int(summary[0])},
                "valid_entity_ids": {
                    "passed": summary[2] == 0,
                    "invalid_rows": int(summary[2]),
                },
                "valid_timestamps": {
                    "passed": summary[3] == 0,
                    "invalid_rows": int(summary[3]),
                },
                "valid_energy": {
                    "passed": summary[4] == 0 and summary[5] == 0 and summary[6] == 0,
                    "null_or_invalid_rows": int(summary[4]),
                    "non_finite_rows": int(summary[5]),
                    "negative_rows": int(summary[6]),
                },
                "residential_only": {
                    "passed": summary[7] == 0,
                    "non_residential_rows": int(summary[7]),
                },
                "unique_entity_timestamp": {
                    "passed": duplicate_keys == 0,
                    "duplicate_keys": int(duplicate_keys),
                },
                "sample_size_matches": {
                    "passed": entity_count == len(selected_ids),
                    "expected_entities": len(selected_ids),
                    "observed_entities": entity_count,
                },
            },
            parameters={"buildings_per_use": buildings_per_use, "seed": seed},
            parent_versions={
                "customer_bronze": (
                    _latest_dataset_manifest("customer_bronze") or {}
                ).get("dataset_version", "untracked"),
            },
        )
        return {
            "path": str(silver),
            "rows": int(summary[0]),
            "unique_buildings": entity_count,
            **quality,
        }
    finally:
        connection.close()


def build_customer_bill_gold(
    silver_path: str | Path = SILVER_PATH,
    output_path: str | Path = GOLD_PATH,
) -> dict[str, Any]:
    """Build leakage-safe residential monthly labels and cutoff features."""
    silver = Path(silver_path).resolve()
    output = Path(output_path).resolve()
    if not silver.is_file():
        raise FileNotFoundError(f"Silver dataset does not exist: {silver}")
    silver_sql = str(silver).replace("'", "''")
    query = f"""
        WITH hourly AS (
            SELECT
                TRY_CAST("OBJECTID" AS BIGINT) AS entity_id,
                CAST("timestamp" AS TIMESTAMP) AS observed_at,
                TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) AS energy_kwh,
                TRY_CAST("building.area.m2" AS DOUBLE) AS building_area_m2,
                TRY_CAST("FootprintArea.m2" AS DOUBLE) AS footprint_area_m2,
                TRY_CAST("EffectiveYearBuilt" AS DOUBLE) AS effective_year_built,
                TRY_CAST("latitude" AS DOUBLE) AS latitude,
                TRY_CAST("longitude" AS DOUBLE) AS longitude,
                "idf.kw" AS idf_kw,
                TRY_CAST("id.grid.coarse" AS BIGINT) AS id_grid_coarse,
                TRY_CAST("id.grid.finer" AS DOUBLE) AS id_grid_finer,
                "id.tract" AS id_tract,
                "SpecificUseType" AS specific_use_type,
                "building.type" AS building_type,
                "vintage" AS vintage,
                "usetype" AS usetype
            FROM read_parquet('{silver_sql}')
            WHERE TRIM("GeneralUseType") = 'Residential'
              AND "timestamp" IS NOT NULL
              AND "normalized_building_energy_kwh" >= 0
        ), monthly AS (
            SELECT
                entity_id,
                DATE_TRUNC('month', observed_at)::DATE AS month_start,
                ANY_VALUE(idf_kw) AS idf_kw,
                ANY_VALUE(id_grid_coarse) AS id_grid_coarse,
                ANY_VALUE(building_area_m2) AS building_area_m2,
                ANY_VALUE(footprint_area_m2) AS footprint_area_m2,
                ANY_VALUE(specific_use_type) AS specific_use_type,
                ANY_VALUE(effective_year_built) AS effective_year_built,
                ANY_VALUE(building_type) AS building_type,
                ANY_VALUE(vintage) AS vintage,
                ANY_VALUE(usetype) AS usetype,
                ANY_VALUE(id_grid_finer) AS id_grid_finer,
                ANY_VALUE(id_tract) AS id_tract,
                ANY_VALUE(latitude) AS latitude,
                ANY_VALUE(longitude) AS longitude,
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
        SELECT entity_id, month_start, idf_kw, id_grid_coarse, building_area_m2, footprint_area_m2,
            specific_use_type, effective_year_built, building_type, vintage, usetype, id_grid_finer,
            id_tract, latitude, longitude, coverage_ratio, observed_hours, expected_hours,
            cutoff_day, days_in_month, month_of_year, month_sin, month_cos, prior_month_kwh,
            prior_month_kwh / NULLIF(building_area_m2, 0) AS prior_month_kwh_per_m2,
            observed_hours_to_cutoff, cumulative_energy_kwh, recent_7d_energy_kwh,
            recent_7d_energy_kwh / NULLIF(recent_7d_hours, 0) AS recent_7d_mean_hourly_kwh,
            cumulative_energy_kwh / NULLIF(observed_hours_to_cutoff, 0) AS mean_hourly_energy_to_cutoff,
            cumulative_energy_kwh / NULLIF(building_area_m2, 0) AS cumulative_energy_per_m2,
            cumulative_energy_kwh / cutoff_day * days_in_month AS naive_projected_month_kwh,
            monthly_kwh AS target_month_kwh, monthly_kwh * {TARIFF_INR_PER_KWH} AS target_bill_inr
        FROM cutoffs
    """
    connection = _connect()
    try:
        _atomic_parquet_copy(connection, query, output)
        output_sql = str(output).replace("'", "''")
        summary = connection.execute(
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
            FROM read_parquet('{output_sql}')
            """
        ).fetchone()
        duplicate_keys = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT entity_id, month_start, cutoff_day
                FROM read_parquet('{output_sql}')
                GROUP BY entity_id, month_start, cutoff_day
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
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
    finally:
        connection.close()
    return {
        "path": str(output),
        "rows": pq.read_metadata(output).num_rows,
        "unique_buildings": int(summary[1]),
        **quality,
    }
