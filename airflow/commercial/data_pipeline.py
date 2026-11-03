"""Commercial non-residential Silver and building-level Gold transforms."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from training.commercial_forecast.features import FEATURE_COLUMNS, TARGET_COLUMN
from training.government_load.sql import identifier, sql_string

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("GRIDVISION_DATA_DIR", PROJECT_ROOT / "data")).resolve()
SOURCE_PATH = Path(
    os.getenv(
        "GRIDVISION_SOURCE_PATH",
        DATA_ROOT / "sample" / "training_sample_50000.parquet",
    )
).resolve()
# The raw source is the Bronze input, matching the existing project convention.
BRONZE_PATH = SOURCE_PATH
SILVER_PATH = Path(
    os.getenv("COMMERCIAL_SILVER_DATASET", DATA_ROOT / "silver" / "commercial_silver.parquet")
).expanduser().resolve()
GOLD_PATH = Path(
    os.getenv("COMMERCIAL_GOLD_DATASET", DATA_ROOT / "gold" / "commercial_gold.parquet")
).expanduser().resolve()
COMMERCIAL_DATA_ROOT = DATA_ROOT / "metadata" / "commercial"
VERSIONS_DIR = COMMERCIAL_DATA_ROOT / "dataset_versions"
QUALITY_REPORTS_DIR = (
    Path(os.getenv("GRIDVISION_LOG_DIR", PROJECT_ROOT / "logs"))
    / "data"
    / "quality_reports"
    / "commercial"
)
MEMORY_LIMIT = os.getenv("COMMERCIAL_DUCKDB_MEMORY_LIMIT", "2GB")
THREADS = max(1, int(os.getenv("COMMERCIAL_DUCKDB_THREADS", "2")))
HORIZON_HOURS = int(os.getenv("COMMERCIAL_FORECAST_HORIZON_HOURS", "24"))
SAMPLE_BUILDINGS = int(os.getenv("COMMERCIAL_SAMPLE_BUILDINGS", "100"))
TEMP_DIR = Path(
    os.getenv(
        "COMMERCIAL_DUCKDB_TEMP_DIR",
        Path.home() / ".cache" / "gridvision" / "commercial_duckdb_temp",
    )
).expanduser().resolve()

RAW_REQUIRED_COLUMNS = {
    "OBJECTID",
    "timestamp",
    "normalized_building_energy_kwh",
    "GeneralUseType",
    "SpecificUseType",
    "usetype",
    "building.type",
    "idf.kw",
    "building.area.m2",
    "FootprintArea.m2",
    "EffectiveYearBuilt",
    "id.grid.coarse",
    "latitude",
    "longitude",
}


def _connect() -> duckdb.DuckDBPyConnection:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute(f"SET threads = {THREADS}")
    connection.execute(f"SET memory_limit = {sql_string(MEMORY_LIMIT)}")
    connection.execute(f"SET temp_directory = {sql_string(TEMP_DIR)}")
    return connection


def _atomic_copy(
    connection: duckdb.DuckDBPyConnection, query: str, output: Path
) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.stage.parquet")
    try:
        connection.execute(
            f"COPY ({query}) TO {sql_string(staged)} "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
        )
        rows = int(pq.read_metadata(staged).num_rows)
        if rows == 0:
            raise ValueError(f"Transform produced an empty dataset: {output}")
        os.replace(staged, output)
        return rows
    finally:
        staged.unlink(missing_ok=True)


def _write_stage_metadata(
    *, stage: str, path: Path, row_count: int, checks: dict[str, dict[str, Any]],
    parameters: dict[str, Any], parent_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    created = datetime.now(timezone.utc)
    version = f"{created:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    payload = {
        "dataset_name": f"commercial_{stage}",
        "dataset_version": version,
        "stage": stage,
        "created_at": created.isoformat(),
        "dataset_path": str(path),
        "row_count": row_count,
        "size_bytes": path.stat().st_size,
        "columns": [
            {"name": field.name, "type": str(field.type)}
            for field in pq.read_schema(path)
        ],
        "quality_checks": checks,
        "quality_passed": all(check["passed"] for check in checks.values()),
        "parameters": parameters,
        "parent_dataset_versions": parent_versions or {},
    }
    report_path = QUALITY_REPORTS_DIR / f"{stage}_{version}.json"
    stage_dir = VERSIONS_DIR / stage
    stage_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = stage_dir / f"{version}.json"
    versioned_path = stage_dir / f"{version}.parquet"
    try:
        os.link(path, versioned_path)
    except OSError:
        # Cross-filesystem deployments may not support hard links.
        import shutil

        shutil.copy2(path, versioned_path)
    payload["quality_report"] = str(report_path)
    payload["manifest_path"] = str(manifest_path)
    payload["versioned_dataset_path"] = str(versioned_path)
    for destination in (report_path, manifest_path, stage_dir / "latest.json"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".stage")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    if not payload["quality_passed"]:
        failed = [name for name, check in checks.items() if not check["passed"]]
        raise ValueError(f"Commercial {stage} quality checks failed: {failed}; see {report_path}")
    return {
        "dataset_version": version,
        "quality_passed": True,
        "quality_report": str(report_path),
        "manifest": str(manifest_path),
        "versioned_dataset_path": str(versioned_path),
    }


def validate_source(source_path: str | Path = SOURCE_PATH) -> dict[str, Any]:
    """Validate source availability, required schema, IDs, and grid assignments."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Commercial source parquet not found: {source}")
    connection = _connect()
    try:
        source_sql = sql_string(source)
        columns = {
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({source_sql})"
            ).fetchall()
        }
        missing = sorted(RAW_REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Commercial source is missing required columns: {missing}")
        invalid_keys = connection.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet({source_sql})
            WHERE "OBJECTID" IS NULL OR timestamp IS NULL
                OR "id.grid.coarse" IS NULL
            """
        ).fetchone()[0]
        conflicting_grids = connection.execute(
            f"""
            SELECT COUNT(*) FROM (
                    SELECT "OBJECTID" FROM read_parquet({source_sql})
                    WHERE "OBJECTID" IS NOT NULL AND "id.grid.coarse" IS NOT NULL
                    GROUP BY "OBJECTID"
                    HAVING COUNT(DISTINCT "id.grid.coarse") > 1
                ) conflicts
            """
        ).fetchone()[0]
        if conflicting_grids:
            raise ValueError(
                f"{conflicting_grids:,} buildings map to multiple coarse grids"
            )
        return {
            "path": str(source),
            "columns": sorted(columns),
            "missing_required_columns": [],
            "rows_with_null_building_timestamp_or_grid": int(invalid_keys),
            "region_key": "id.grid.coarse",
        }
    finally:
        connection.close()


def create_commercial_silver(
    source_path: str | Path = BRONZE_PATH,
    silver_path: str | Path = SILVER_PATH,
    source_validated: bool = False,
) -> dict[str, Any]:
    """Filter the shared Bronze source to non-residential building records."""
    source = Path(source_path).expanduser().resolve()
    output = Path(silver_path).expanduser().resolve()
    if source == output:
        raise ValueError("Commercial Silver cannot overwrite the Bronze source")
    source_info = (
        {"columns": sorted(RAW_REQUIRED_COLUMNS)}
        if source_validated
        else validate_source(source)
    )
    connection = _connect()
    try:
        source_sql = sql_string(source)
        query = f"""
            SELECT * FROM read_parquet({source_sql})
            WHERE "OBJECTID" IS NOT NULL
              AND timestamp IS NOT NULL
              AND "id.grid.coarse" IS NOT NULL
              AND "normalized_building_energy_kwh" IS NOT NULL
              AND TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) >= 0
              AND "GeneralUseType" IS NOT NULL
              AND LOWER(TRIM(CAST("GeneralUseType" AS VARCHAR))) <> 'residential'
        """
        rows = _atomic_copy(connection, query, output)
        residential_count, invalid_use_count = connection.execute(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE LOWER(TRIM(CAST("GeneralUseType" AS VARCHAR))) = 'residential'),
                COUNT(*) FILTER (WHERE "GeneralUseType" IS NULL)
            FROM read_parquet({sql_string(output)})
            """
        ).fetchone()
        checks = {
            "non_empty": {"passed": rows > 0, "observed": rows},
            "residential_excluded": {"passed": residential_count == 0, "observed": int(residential_count)},
            "general_use_type_present": {"passed": invalid_use_count == 0, "observed": int(invalid_use_count)},
            "region_key_retained": {"passed": "id.grid.coarse" in source_info["columns"], "observed": "id.grid.coarse"},
        }
        metadata = _write_stage_metadata(
            stage="silver", path=output, row_count=rows, checks=checks,
            parameters={"filter": "GeneralUseType != Residential", "bronze_path": str(source)},
        )
        return {"path": str(output), "rows": rows, **metadata}
    finally:
        connection.close()


def build_commercial_gold(
    silver_path: str | Path = SILVER_PATH,
    gold_path: str | Path = GOLD_PATH,
    horizon_hours: int = HORIZON_HOURS,
) -> dict[str, Any]:
    """Build leakage-safe building × forecast-origin × horizon feature rows."""
    silver = Path(silver_path).expanduser().resolve()
    output = Path(gold_path).expanduser().resolve()
    if not silver.is_file():
        raise FileNotFoundError(f"Commercial Silver dataset not found: {silver}")
    if not 1 <= horizon_hours <= 24:
        raise ValueError("Commercial forecast horizon must be between 1 and 24 hours")
    if SAMPLE_BUILDINGS < 1:
        raise ValueError("COMMERCIAL_SAMPLE_BUILDINGS must be at least 1")
    if silver == output:
        raise ValueError("Commercial Gold cannot overwrite Silver")
    connection = _connect()
    try:
        silver_sql = sql_string(silver)
        schema = {
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({silver_sql})"
            ).fetchall()
        }
        missing = sorted(RAW_REQUIRED_COLUMNS - schema)
        if missing:
            raise ValueError(f"Commercial Silver is missing columns: {missing}")

        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE commercial_gold_building_sample AS
            SELECT "OBJECTID"
            FROM read_parquet({silver_sql})
            WHERE "OBJECTID" IS NOT NULL
            GROUP BY "OBJECTID"
            ORDER BY hash("OBJECTID"), "OBJECTID"
            LIMIT {SAMPLE_BUILDINGS}
            """
        )
        sampled_buildings = int(
            connection.execute(
                "SELECT COUNT(*) FROM commercial_gold_building_sample"
            ).fetchone()[0]
        )
        if sampled_buildings == 0:
            raise ValueError(f"Commercial Silver has no buildings: {silver}")

        query = f"""
        WITH hourly AS (
            SELECT
                "OBJECTID",
                    "id.grid.coarse",
                CAST(timestamp AS TIMESTAMP) AS timestamp,
                SUM(TRY_CAST("normalized_building_energy_kwh" AS DOUBLE)) AS energy,
                ANY_VALUE("GeneralUseType") AS "GeneralUseType",
                ANY_VALUE("SpecificUseType") AS "SpecificUseType",
                ANY_VALUE(usetype) AS usetype,
                ANY_VALUE("building.type") AS "building.type",
                ANY_VALUE("idf.kw") AS "idf.kw",
                TRY_CAST(ANY_VALUE("building.area.m2") AS DOUBLE) AS "building.area.m2",
                TRY_CAST(ANY_VALUE("FootprintArea.m2") AS DOUBLE) AS "FootprintArea.m2",
                TRY_CAST(ANY_VALUE("EffectiveYearBuilt") AS DOUBLE) AS "EffectiveYearBuilt",
                TRY_CAST(ANY_VALUE(latitude) AS DOUBLE) AS latitude,
                TRY_CAST(ANY_VALUE(longitude) AS DOUBLE) AS longitude
            FROM read_parquet({silver_sql})
            WHERE "OBJECTID" IN (
                  SELECT "OBJECTID" FROM commercial_gold_building_sample
              )
              AND timestamp IS NOT NULL
              AND "id.grid.coarse" IS NOT NULL
              AND TRY_CAST("normalized_building_energy_kwh" AS DOUBLE) >= 0
                GROUP BY "OBJECTID", "id.grid.coarse", CAST(timestamp AS TIMESTAMP)
        ), rolling AS (
            SELECT *,
                AVG(energy) OVER w24 AS energy_rolling_mean_24h,
                STDDEV_SAMP(energy) OVER w24 AS energy_rolling_std_24h,
                COUNT(energy) OVER w24 AS energy_observation_count_24h,
                AVG(energy) OVER w7 AS energy_rolling_mean_7d,
                STDDEV_SAMP(energy) OVER w7 AS energy_rolling_std_7d,
                COUNT(energy) OVER w7 AS energy_observation_count_7d,
                AVG(energy) OVER w30 AS energy_rolling_mean_30d,
                STDDEV_SAMP(energy) OVER w30 AS energy_rolling_std_30d,
                COUNT(energy) OVER w30 AS energy_observation_count_30d
            FROM hourly
            WINDOW
                w24 AS (PARTITION BY "OBJECTID" ORDER BY timestamp RANGE BETWEEN INTERVAL 24 HOURS PRECEDING AND CURRENT ROW),
                w7 AS (PARTITION BY "OBJECTID" ORDER BY timestamp RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND CURRENT ROW),
                w30 AS (PARTITION BY "OBJECTID" ORDER BY timestamp RANGE BETWEEN INTERVAL 30 DAYS PRECEDING AND CURRENT ROW)
        ), history AS (
            SELECT r.*,
                r.energy AS energy_at_origin,
                l1.energy AS energy_lag_1,
                l24.energy AS energy_lag_24,
                l168.energy AS energy_lag_168,
                l336.energy AS energy_lag_336,
                l720.energy AS energy_lag_720
            FROM rolling r
            LEFT JOIN hourly l1 ON l1."OBJECTID" = r."OBJECTID" AND l1.timestamp = r.timestamp - INTERVAL 1 HOUR
            LEFT JOIN hourly l24 ON l24."OBJECTID" = r."OBJECTID" AND l24.timestamp = r.timestamp - INTERVAL 24 HOURS
            LEFT JOIN hourly l168 ON l168."OBJECTID" = r."OBJECTID" AND l168.timestamp = r.timestamp - INTERVAL 168 HOURS
            LEFT JOIN hourly l336 ON l336."OBJECTID" = r."OBJECTID" AND l336.timestamp = r.timestamp - INTERVAL 336 HOURS
            LEFT JOIN hourly l720 ON l720."OBJECTID" = r."OBJECTID" AND l720.timestamp = r.timestamp - INTERVAL 720 HOURS
        ), horizons AS (
            SELECT h.*, n.horizon::INTEGER AS forecast_horizon_hours,
                h.timestamp + n.horizon * INTERVAL '1 hour' AS target_timestamp
            FROM history h CROSS JOIN range(1, {horizon_hours + 1}) n(horizon)
        )
        SELECT
            h."OBJECTID", h."id.grid.coarse",
            h.timestamp AS forecast_origin_timestamp, h.target_timestamp,
            h.forecast_horizon_hours,
            h."GeneralUseType", h."SpecificUseType", h.usetype, h."building.type",
            h."idf.kw", h."building.area.m2", h."FootprintArea.m2",
            h."EffectiveYearBuilt", h.latitude, h.longitude,
            h.energy_at_origin, h.energy_lag_1, h.energy_lag_24, h.energy_lag_168,
            h.energy_lag_336, h.energy_lag_720,
            h.energy_rolling_mean_24h, h.energy_rolling_std_24h, h.energy_observation_count_24h,
            h.energy_rolling_mean_7d, h.energy_rolling_std_7d, h.energy_observation_count_7d,
            h.energy_rolling_mean_30d, h.energy_rolling_std_30d, h.energy_observation_count_30d,
            EXTRACT(HOUR FROM h.target_timestamp)::INTEGER AS target_hour,
            EXTRACT(DOW FROM h.target_timestamp)::INTEGER AS target_day_of_week,
            EXTRACT(MONTH FROM h.target_timestamp)::INTEGER AS target_month,
            CASE WHEN EXTRACT(DOW FROM h.target_timestamp) IN (0, 6) THEN 1 ELSE 0 END AS target_is_weekend,
            EXTRACT(DAY FROM h.target_timestamp)::INTEGER AS target_day_of_month,
            EXTRACT(DOY FROM h.target_timestamp)::INTEGER AS target_day_of_year,
            SIN(2 * PI() * EXTRACT(HOUR FROM h.target_timestamp) / 24.0) AS target_hour_sin,
            COS(2 * PI() * EXTRACT(HOUR FROM h.target_timestamp) / 24.0) AS target_hour_cos,
            SIN(2 * PI() * (EXTRACT(DOY FROM h.target_timestamp) - 1) / 365.25) AS target_day_of_year_sin,
            COS(2 * PI() * (EXTRACT(DOY FROM h.target_timestamp) - 1) / 365.25) AS target_day_of_year_cos,
            target.energy AS {identifier(TARGET_COLUMN)}
        FROM horizons h
        INNER JOIN hourly target
          ON target."OBJECTID" = h."OBJECTID"
         AND target.timestamp = h.target_timestamp
        """
        rows = _atomic_copy(connection, query, output)
        columns = [field.name for field in pq.read_schema(output)]
        expected = set(FEATURE_COLUMNS + [TARGET_COLUMN, *["OBJECTID", "id.grid.coarse", "forecast_origin_timestamp", "target_timestamp"]])
        missing_features = sorted(expected - set(columns))
        duplicate_horizon = columns.count("forecast_horizon_hours") != 1
        row_count, duplicate_keys, invalid_target = connection.execute(
            f"""
            SELECT COUNT(*),
                (SELECT COUNT(*) FROM (SELECT "OBJECTID", forecast_origin_timestamp, forecast_horizon_hours
                    FROM read_parquet({sql_string(output)}) GROUP BY ALL HAVING COUNT(*) > 1) d),
                COUNT(*) FILTER (WHERE target_energy IS NULL OR NOT isfinite(target_energy) OR target_energy < 0)
            FROM read_parquet({sql_string(output)})
            """
        ).fetchone()
        checks = {
            "non_empty": {"passed": rows > 0, "observed": rows},
            "sampled_building_count": {
                "passed": sampled_buildings <= SAMPLE_BUILDINGS,
                "observed": sampled_buildings,
                "limit": SAMPLE_BUILDINGS,
            },
            "feature_contract": {"passed": not missing_features, "missing": missing_features},
            "single_horizon_column": {"passed": not duplicate_horizon, "count": columns.count("forecast_horizon_hours")},
            "unique_building_origin_horizon": {"passed": duplicate_keys == 0, "duplicates": int(duplicate_keys)},
            "valid_target": {"passed": invalid_target == 0, "invalid_rows": int(invalid_target)},
            "target_after_origin": {"passed": connection.execute(
                f"SELECT COUNT(*) = 0 FROM read_parquet({sql_string(output)}) WHERE target_timestamp <= forecast_origin_timestamp"
            ).fetchone()[0], "horizon_hours": horizon_hours},
        }
        metadata = _write_stage_metadata(
            stage="gold", path=output, row_count=int(row_count), checks=checks,
            parameters={
                "horizon_hours": horizon_hours,
                "sample_buildings": SAMPLE_BUILDINGS,
                "sampled_buildings": sampled_buildings,
                "feature_columns": FEATURE_COLUMNS,
                "target_column": TARGET_COLUMN,
            },
            parent_versions={"commercial_silver": _latest_version("silver")},
        )
        return {"path": str(output), "rows": rows, **metadata}
    finally:
        connection.close()


def _latest_version(stage: str) -> str:
    path = VERSIONS_DIR / stage / "latest.json"
    if not path.is_file():
        return "untracked"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("dataset_version", "untracked")
    except (OSError, json.JSONDecodeError):
        return "untracked"

