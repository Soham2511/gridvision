"""DuckDB-backed validation, profiling, and building feature generation."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from .config import SegmentationSettings

logger = logging.getLogger("gridvision.segmentation.pipeline")

REQUIRED_COLUMNS = {
    "OBJECTID",
    "id.grid.coarse",
    "id.grid.finer",
    "id.tract",
    "latitude",
    "longitude",
    "GeneralUseType",
    "SpecificUseType",
    "usetype",
    "building.type",
    "timestamp",
    "normalized_building_energy_kwh",
}
PROFILE_CATEGORIES = ("GeneralUseType", "SpecificUseType", "usetype", "building.type")
IDENTIFIER_COLUMNS = {
    "OBJECTID",
    "id.grid.coarse",
    "id.grid.finer",
    "id.tract",
    "latitude",
    "longitude",
    *PROFILE_CATEGORIES,
}


def _connect(settings: SegmentationSettings) -> duckdb.DuckDBPyConnection:
    settings.duckdb_temp_dir.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute(f"SET threads = {int(settings.duckdb_threads)}")
    connection.execute("SET preserve_insertion_order = false")
    escaped_memory = settings.duckdb_memory_limit.replace("'", "''")
    escaped_temp = settings.duckdb_temp_dir.resolve().as_posix().replace("'", "''")
    connection.execute(f"SET memory_limit = '{escaped_memory}'")
    connection.execute(f"SET temp_directory = '{escaped_temp}'")
    return connection


def _parquet_sql(path: Path) -> str:
    # SQL string literals are escaped because DuckDB's read_parquet path is part of SQL.
    escaped = path.expanduser().resolve().as_posix().replace("'", "''")
    return f"read_parquet('{escaped}')"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix + ".stage")
    stage.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
    stage.replace(path)


def _prepare_segmentation_source(
    settings: SegmentationSettings,
) -> tuple[Path, dict[str, Any]]:
    """Create or reuse a deterministic building sample before expensive stages."""
    settings.validate()
    source = settings.source_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Segmentation source Parquet not found: {source}")
    source_stat = source.stat()
    sample_fraction = settings.building_sample_fraction
    manifest: dict[str, Any] = {
        "source_path": str(source),
        "source_bytes": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
        "building_sample_fraction": sample_fraction,
    }
    if sample_fraction >= 1:
        manifest["processed_source_path"] = str(source)
        return source, manifest

    sample_path = settings.output_dir / "source_sample.parquet"
    manifest_path = settings.output_dir / "reports" / "source_sample.json"
    if sample_path.is_file() and manifest_path.is_file():
        try:
            cached = json.loads(manifest_path.read_text(encoding="utf-8"))
            if all(cached.get(key) == value for key, value in manifest.items()):
                manifest["processed_source_path"] = str(sample_path.resolve())
                manifest["sampled_buildings"] = cached.get("sampled_buildings")
                manifest["sampled_rows"] = cached.get("sampled_rows")
                return sample_path.resolve(), manifest
        except (OSError, json.JSONDecodeError):
            pass

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    stage = sample_path.with_name(f".{sample_path.name}.stage")
    stage.unlink(missing_ok=True)
    threshold = max(1, int(sample_fraction * 1_000_000))
    logger.info(
        "Creating deterministic segmentation sample at %.1f%% of buildings "
        "from %s; first preparation scans the source once",
        sample_fraction * 100,
        source,
    )
    con = _connect(settings)
    try:
        schema = con.execute(
            f"DESCRIBE SELECT * FROM {_parquet_sql(source)}"
        ).fetchall()
        missing = sorted(REQUIRED_COLUMNS - {row[0] for row in schema})
        if missing:
            raise ValueError(f"Segmentation source missing required columns: {missing}")
        con.execute(
            f"""
            COPY (
              SELECT *
              FROM {_parquet_sql(source)}
              WHERE OBJECTID IS NULL
                 OR hash(OBJECTID) % 1000000 < {threshold}
                 OR GeneralUseType IN ('Institutional', 'Recreational')
            ) TO '{stage.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        sample_info = con.execute(
            f"""SELECT COUNT(*), COUNT(DISTINCT OBJECTID)
                FROM {_parquet_sql(stage)}"""
        ).fetchone()
        if not sample_info or sample_info[0] == 0:
            raise ValueError(
                "Deterministic segmentation sampling produced no rows; "
                "increase SEGMENTATION_BUILDING_SAMPLE_FRACTION."
            )
        stage.replace(sample_path)
    except Exception:
        stage.unlink(missing_ok=True)
        raise
    finally:
        con.close()

    manifest.update(
        {
            "processed_source_path": str(sample_path.resolve()),
            "sampled_buildings": int(sample_info[1]),
            "sampled_rows": int(sample_info[0]),
        }
    )
    _atomic_json(manifest_path, manifest)
    logger.info(
        "Created segmentation source sample: %s buildings, %s rows at %s",
        manifest["sampled_buildings"],
        manifest["sampled_rows"],
        sample_path,
    )
    return sample_path.resolve(), manifest


def validate_source(settings: SegmentationSettings) -> dict[str, Any]:
    settings.validate()
    original_source = settings.source_path.expanduser().resolve()
    source, sample_manifest = _prepare_segmentation_source(settings)
    con = _connect(settings)
    try:
        schema = con.execute(f"DESCRIBE SELECT * FROM {_parquet_sql(source)}").fetchall()
        columns = {row[0] for row in schema}
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Segmentation source missing required columns: {missing}")

        missing_expressions = ",\n".join(
            f'COUNT(*) FILTER (WHERE "{name.replace(chr(34), chr(34) * 2)}" IS NULL) AS "missing__{index}"'
            for index, row in enumerate(schema)
            for name in (row[0],)
        )
        logger.info(
            "Profiling segmentation input (%s bytes): validating sampled rows, "
            "energy values, coordinates, categories, and coverage",
            source.stat().st_size,
        )
        checks = con.execute(
            f"""
            SELECT
              COUNT(*) AS rows,
              COUNT(*) FILTER (WHERE OBJECTID IS NULL) AS missing_building_id,
              COUNT(*) FILTER (WHERE TRY_CAST(timestamp AS TIMESTAMP) IS NULL) AS invalid_timestamp,
              COUNT(*) FILTER (
                WHERE TRY_CAST(normalized_building_energy_kwh AS DOUBLE) IS NULL
                   OR NOT isfinite(TRY_CAST(normalized_building_energy_kwh AS DOUBLE))
                   OR TRY_CAST(normalized_building_energy_kwh AS DOUBLE) < 0
              ) AS invalid_energy,
              MIN(TRY_CAST(timestamp AS TIMESTAMP)) AS timestamp_min,
              MAX(TRY_CAST(timestamp AS TIMESTAMP)) AS timestamp_max,
              COUNT(DISTINCT OBJECTID) AS distinct_buildings,
              COUNT(*) FILTER (WHERE "id.grid.coarse" IS NULL) AS missing_coarse_grid,
              COUNT(*) FILTER (WHERE latitude IS NULL OR longitude IS NULL) AS missing_coordinates,
              COUNT(DISTINCT "id.grid.coarse") AS coarse_grid_count,
              COUNT(DISTINCT "id.grid.finer") AS finer_grid_count,
              COUNT(DISTINCT "id.tract") AS tract_count,
              MIN(latitude) AS latitude_min,
              MAX(latitude) AS latitude_max,
              MIN(longitude) AS longitude_min,
              MAX(longitude) AS longitude_max,
              COUNT(*) FILTER (WHERE NOT isfinite(latitude) OR latitude < -90 OR latitude > 90) AS invalid_latitude_rows,
              COUNT(*) FILTER (WHERE NOT isfinite(longitude) OR longitude < -180 OR longitude > 180) AS invalid_longitude_rows,
              MIN(normalized_building_energy_kwh) AS energy_min,
              MAX(normalized_building_energy_kwh) AS energy_max,
              AVG(normalized_building_energy_kwh) AS energy_mean,
              APPROX_QUANTILE(normalized_building_energy_kwh, 0.5) AS energy_median_approx,
              APPROX_QUANTILE(normalized_building_energy_kwh, 0.95) AS energy_p95_approx,
              COUNT(*) FILTER (WHERE normalized_building_energy_kwh = 0) AS zero_energy_rows,
              COUNT(DISTINCT timestamp) AS distinct_timestamps,
              {missing_expressions}
            FROM {_parquet_sql(source)}
            """
        ).fetchone()
        indexes = {row[0]: index for index, row in enumerate(con.description)}
        missingness = {
            row[0]: int(checks[indexes[f"missing__{position}"]])
            for position, row in enumerate(schema)
        }
        report = {
            "source_path": str(original_source),
            "source_bytes": sample_manifest["source_bytes"],
            "source_mtime_ns": sample_manifest["source_mtime_ns"],
            "processed_source_path": str(source),
            "building_sample_fraction": sample_manifest[
                "building_sample_fraction"
            ],
            "sampled_buildings": sample_manifest.get("sampled_buildings"),
            "sampled_rows": sample_manifest.get("sampled_rows"),
            "columns": [{"name": row[0], "type": row[1]} for row in schema],
            "row_count": checks[0],
            "missing_building_id_rows": checks[1],
            "invalid_timestamp_rows": checks[2],
            "invalid_energy_rows": checks[3],
            "timestamp_min": checks[4],
            "timestamp_max": checks[5],
            "distinct_buildings": checks[6],
            "missing_coarse_grid_rows": checks[7],
            "missing_coordinate_rows": checks[8],
            "distinct_coarse_grids": checks[9],
            "distinct_finer_grids": checks[10],
            "distinct_tracts": checks[11],
            "coordinate_bounds": {
                "latitude_min": checks[12],
                "latitude_max": checks[13],
                "longitude_min": checks[14],
                "longitude_max": checks[15],
                "invalid_latitude_rows": checks[16],
                "invalid_longitude_rows": checks[17],
            },
            "energy_summary": {
                "minimum": checks[18],
                "maximum": checks[19],
                "mean": checks[20],
                "median_approx": checks[21],
                "p95_approx": checks[22],
                "zero_reading_rows": checks[23],
            },
            "distinct_timestamps": checks[24],
            "missingness_null_rows_by_column": missingness,
            "category_values": {},
            "duplicate_building_timestamp_rows": None,
            "energy_semantics": "unverified; source values are validated, not reinterpreted",
        }
        for category in PROFILE_CATEGORIES:
            logger.info("Counting source buildings by %s", category)
            report["category_values"][category] = [
                {"value": row[0], "rows": row[1], "buildings": row[2]}
                for row in con.execute(
                    f"""
                    SELECT CAST("{category}" AS VARCHAR), COUNT(*), COUNT(DISTINCT OBJECTID)
                    FROM {_parquet_sql(source)}
                    GROUP BY 1 ORDER BY 2 DESC
                    """
                ).fetchall()
            ]
        logger.info("Checking duplicate building/timestamp records")
        duplicate_count = con.execute(
            f"""
            SELECT COALESCE(SUM(n - 1), 0)
            FROM (
              SELECT COUNT(*) AS n
              FROM {_parquet_sql(source)}
              GROUP BY OBJECTID, timestamp
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        report["duplicate_building_timestamp_rows"] = duplicate_count
        logger.info("Calculating observation coverage by building")
        coverage = con.execute(
            f"""
            WITH by_building AS (
              SELECT OBJECTID, COUNT(*) AS observed_rows,
                     MIN(timestamp) AS first_timestamp,
                     MAX(timestamp) AS last_timestamp,
                     COUNT(DISTINCT "id.grid.coarse") AS coarse_grid_values,
                     COUNT(DISTINCT "id.grid.finer") AS finer_grid_values,
                     COUNT(DISTINCT "id.tract") AS tract_values,
                     COUNT(DISTINCT GeneralUseType) AS general_use_values,
                     COUNT(DISTINCT SpecificUseType) AS specific_use_values,
                     COUNT(DISTINCT usetype) AS usetype_values,
                     COUNT(DISTINCT "building.type") AS building_type_values
              FROM {_parquet_sql(source)}
              GROUP BY OBJECTID
            )
            SELECT COUNT(*) AS building_groups,
                   MIN(observed_rows) AS min_rows,
                   APPROX_QUANTILE(observed_rows, 0.5) AS median_rows,
                   MAX(observed_rows) AS max_rows,
                   MIN(first_timestamp) AS first_observation,
                   MAX(last_timestamp) AS last_observation,
                   COUNT(*) FILTER (WHERE coarse_grid_values > 1) AS inconsistent_coarse_grid_buildings,
                   COUNT(*) FILTER (WHERE finer_grid_values > 1) AS inconsistent_finer_grid_buildings,
                   COUNT(*) FILTER (WHERE tract_values > 1) AS inconsistent_tract_buildings,
                   COUNT(*) FILTER (WHERE general_use_values > 1 OR specific_use_values > 1
                                     OR usetype_values > 1 OR building_type_values > 1) AS inconsistent_category_buildings
            FROM by_building
            """
        ).fetchone()
        report["building_coverage_and_mapping"] = {
            "building_groups_including_null_id": coverage[0],
            "minimum_rows_per_building": coverage[1],
            "median_rows_per_building_approx": coverage[2],
            "maximum_rows_per_building": coverage[3],
            "first_observation": coverage[4],
            "last_observation": coverage[5],
            "buildings_with_multiple_coarse_grids": coverage[6],
            "buildings_with_multiple_finer_grids": coverage[7],
            "buildings_with_multiple_tracts": coverage[8],
            "buildings_with_inconsistent_categories": coverage[9],
        }
        report["profiled_at_utc"] = con.execute("SELECT current_timestamp").fetchone()[0]
        _atomic_json(settings.reports_dir / "source_profile.json", report)
        logger.info("Completed segmentation source profile: %s", report)
        return report
    finally:
        con.close()


def generate_building_features(settings: SegmentationSettings) -> dict[str, Any]:
    """Build one eligible building row using SQL; raw hourly readings stay in DuckDB."""
    profile = load_or_validate_source_profile(settings)
    if profile["duplicate_building_timestamp_rows"]:
        raise ValueError(
            "Source has duplicate (OBJECTID, timestamp) rows; resolve source duplicate "
            "semantics before feature generation. See the configured source profile report."
        )
    if profile["invalid_timestamp_rows"] or profile["missing_building_id_rows"]:
        raise ValueError("Source has invalid timestamps or building IDs")
    if profile["timestamp_min"] is None or profile["timestamp_max"] is None:
        raise ValueError("Source has no valid timestamps")
    timestamp_max = profile["timestamp_max"]
    if isinstance(timestamp_max, str):
        timestamp_max = datetime.fromisoformat(timestamp_max)

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.feature_path.parent.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    source = Path(profile["processed_source_path"]).expanduser().resolve()
    con = _connect(settings)
    try:
        window_end = settings.window_end or timestamp_max.date()
        # Half-open interval ends at midnight after window_end; this avoids partial-day truncation.
        end_exclusive = con.execute(
            "SELECT CAST(? AS DATE) + INTERVAL 1 DAY", [window_end]
        ).fetchone()[0]
        start = con.execute(
            "SELECT CAST(? AS DATE) - (? * INTERVAL 1 MONTH)",
            [end_exclusive, settings.window_months],
        ).fetchone()[0]
        expected_hours = con.execute(
            "SELECT date_diff('hour', CAST(? AS TIMESTAMP), CAST(? AS TIMESTAMP))",
            [start, end_exclusive],
        ).fetchone()[0]
        output = settings.feature_path
        stage = output.with_suffix(".parquet.stage")
        read = _parquet_sql(source)
        sql = f"""
        COPY (
          WITH window_rows AS (
            SELECT
              CAST(OBJECTID AS BIGINT) AS OBJECTID,
              CAST("id.grid.coarse" AS BIGINT) AS "id.grid.coarse",
              TRY_CAST("id.grid.finer" AS DOUBLE) AS "id.grid.finer",
              CAST("id.tract" AS VARCHAR) AS "id.tract",
              TRY_CAST(latitude AS DOUBLE) AS latitude,
              TRY_CAST(longitude AS DOUBLE) AS longitude,
              CAST("GeneralUseType" AS VARCHAR) AS "GeneralUseType",
              CAST("SpecificUseType" AS VARCHAR) AS "SpecificUseType",
              CAST(usetype AS VARCHAR) AS usetype,
              CAST("building.type" AS VARCHAR) AS "building.type",
              CAST(timestamp AS TIMESTAMP) AS timestamp,
              TRY_CAST(normalized_building_energy_kwh AS DOUBLE) AS energy
            FROM {read}
            WHERE CAST(timestamp AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
              AND CAST(timestamp AS TIMESTAMP) < CAST(? AS TIMESTAMP)
              AND OBJECTID IS NOT NULL
              AND isfinite(TRY_CAST(normalized_building_energy_kwh AS DOUBLE))
              AND TRY_CAST(normalized_building_energy_kwh AS DOUBLE) >= 0
          ),
          per_hour AS NOT MATERIALIZED (
            SELECT *, EXTRACT(hour FROM timestamp) AS hour,
                   EXTRACT(dow FROM timestamp) IN (0, 6) AS is_weekend,
                   CAST(timestamp AS DATE) AS observation_date,
                   EXTRACT(month FROM timestamp) AS month_num
            FROM window_rows
          ),
          daily AS (
            SELECT OBJECTID, observation_date,
                   SUM(energy) AS daily_energy,
                   AVG(energy) AS daily_mean,
                   STDDEV_SAMP(energy) AS daily_std
            FROM per_hour GROUP BY OBJECTID, observation_date
          ),
          monthly AS (
            SELECT OBJECTID, month_num, SUM(energy) AS monthly_energy
            FROM per_hour GROUP BY OBJECTID, month_num
          ),
          mean_hourly AS (
            SELECT OBJECTID, hour, AVG(energy) AS mean_energy
            FROM per_hour GROUP BY OBJECTID, hour
          ),
          peak_hour AS (
            SELECT OBJECTID, hour AS peak_consumption_hour
            FROM mean_hourly
            QUALIFY ROW_NUMBER() OVER (
              PARTITION BY OBJECTID ORDER BY mean_energy DESC, hour ASC
            ) = 1
          ),
          base AS (
            SELECT
              OBJECTID,
              COUNT(*) AS observed_hours,
              CAST(COUNT(*) AS DOUBLE) / {int(expected_hours)} AS coverage_ratio,
              AVG(energy) AS mean_energy_kwh,
              APPROX_QUANTILE(energy, 0.5) AS median_energy_kwh,
              STDDEV_SAMP(energy) AS stddev_energy_kwh,
              APPROX_QUANTILE(energy, 0.95) AS p95_energy_kwh,
              MAX(energy) AS peak_energy_kwh,
              AVG(energy) AS average_energy_kwh,
              SUM(energy) FILTER (WHERE hour BETWEEN 0 AND 5) / NULLIF(SUM(energy), 0) AS night_energy_share,
              SUM(energy) FILTER (WHERE hour BETWEEN 6 AND 11) / NULLIF(SUM(energy), 0) AS morning_energy_share,
              SUM(energy) FILTER (WHERE hour BETWEEN 12 AND 17) / NULLIF(SUM(energy), 0) AS afternoon_energy_share,
              SUM(energy) FILTER (WHERE hour BETWEEN 18 AND 23) / NULLIF(SUM(energy), 0) AS evening_energy_share,
              AVG(energy) FILTER (WHERE NOT is_weekend) AS weekday_mean_hourly_energy_kwh,
              AVG(energy) FILTER (WHERE is_weekend) AS weekend_mean_hourly_energy_kwh,
              COUNT(*) FILTER (WHERE is_weekend) AS weekend_observations,
              COUNT(*) FILTER (WHERE NOT is_weekend) AS weekday_observations,
              ANY_VALUE("id.grid.coarse") AS "id.grid.coarse",
              ANY_VALUE("id.grid.finer") AS "id.grid.finer",
              ANY_VALUE("id.tract") AS "id.tract",
              AVG(latitude) AS latitude,
              AVG(longitude) AS longitude,
              ANY_VALUE("GeneralUseType") AS "GeneralUseType",
              ANY_VALUE("SpecificUseType") AS "SpecificUseType",
              ANY_VALUE(usetype) AS usetype,
              ANY_VALUE("building.type") AS "building.type"
            FROM per_hour GROUP BY OBJECTID
          ),
          daily_features AS (
            SELECT OBJECTID,
              AVG(daily_std) AS mean_daily_stddev_kwh,
              STDDEV_SAMP(daily_energy) AS daily_energy_stddev_kwh,
              AVG(daily_energy) AS mean_daily_energy_kwh
            FROM daily GROUP BY OBJECTID
          ),
          monthly_features AS (
            SELECT OBJECTID,
              STDDEV_SAMP(monthly_energy) / NULLIF(AVG(monthly_energy), 0) AS monthly_energy_cv,
              MAX(monthly_energy) / NULLIF(AVG(monthly_energy), 0) AS monthly_peak_to_average
            FROM monthly GROUP BY OBJECTID
          ),
          enriched AS (
            SELECT b.*,
              p.peak_consumption_hour,
              b.stddev_energy_kwh / NULLIF(b.mean_energy_kwh, 0) AS coefficient_of_variation,
              b.peak_energy_kwh / NULLIF(b.average_energy_kwh, 0) AS peak_to_average_ratio,
              b.weekend_mean_hourly_energy_kwh / NULLIF(b.weekday_mean_hourly_energy_kwh, 0) AS weekend_to_weekday_ratio,
              SIN(2 * PI() * p.peak_consumption_hour / 24.0) AS peak_hour_sin,
              COS(2 * PI() * p.peak_consumption_hour / 24.0) AS peak_hour_cos,
              d.mean_daily_stddev_kwh,
              d.daily_energy_stddev_kwh,
              d.mean_daily_energy_kwh,
              m.monthly_energy_cv,
              m.monthly_peak_to_average
            FROM base b
            JOIN peak_hour p USING (OBJECTID)
            LEFT JOIN daily_features d USING (OBJECTID)
            LEFT JOIN monthly_features m USING (OBJECTID)
          )
          SELECT * FROM enriched
          WHERE coverage_ratio >= {float(settings.minimum_coverage)}
            AND "id.grid.coarse" IS NOT NULL
        ) TO '{stage.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        logger.info(
              "Aggregating hourly readings into building features for %s through %s; "
              "this is a full-source DuckDB query",
              start,
              end_exclusive,
        )
        con.execute(sql, [start, end_exclusive])
        stage.replace(output)
        result = con.execute(
            f"""SELECT COUNT(*), COUNT(DISTINCT OBJECTID), MIN(coverage_ratio),
                       AVG(coverage_ratio), MAX(coverage_ratio)
                FROM {_parquet_sql(output)}"""
        ).fetchone()
        if result[0] == 0:
            raise ValueError(
                "No buildings meet the configured observation coverage "
                "threshold for this window."
            )
        if result[0] != result[1]:
            raise ValueError(
                "Feature generation did not produce exactly one row per OBJECTID."
            )
        excluded = con.execute(
            f"""SELECT COUNT(DISTINCT OBJECTID)
                FROM (
                  SELECT OBJECTID, COUNT(*) AS n
                  FROM {read}
                  WHERE CAST(timestamp AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                    AND CAST(timestamp AS TIMESTAMP) < CAST(? AS TIMESTAMP)
                    AND OBJECTID IS NOT NULL
                    AND isfinite(TRY_CAST(normalized_building_energy_kwh AS DOUBLE))
                    AND TRY_CAST(normalized_building_energy_kwh AS DOUBLE) >= 0
                  GROUP BY OBJECTID
                  HAVING COUNT(*) < CEIL({int(expected_hours)} * {float(settings.minimum_coverage)})
                )""",
            [start, end_exclusive],
        ).fetchone()[0]
        feature_fields = [
            "mean_energy_kwh",
            "median_energy_kwh",
            "stddev_energy_kwh",
            "p95_energy_kwh",
            "peak_energy_kwh",
            "night_energy_share",
            "morning_energy_share",
            "afternoon_energy_share",
            "evening_energy_share",
            "weekday_mean_hourly_energy_kwh",
            "weekend_mean_hourly_energy_kwh",
            "coefficient_of_variation",
            "peak_to_average_ratio",
            "weekend_to_weekday_ratio",
            "peak_hour_sin",
            "peak_hour_cos",
            "mean_daily_stddev_kwh",
            "daily_energy_stddev_kwh",
            "monthly_energy_cv",
            "monthly_peak_to_average",
        ]
        missing_features = {
            field: int(value)
            for field, value in zip(
                feature_fields,
                con.execute(
                    "SELECT "
                    + ", ".join(
                        f'COUNT(*) FILTER (WHERE "{field}" IS NULL)'
                        for field in feature_fields
                    )
                    + f" FROM {_parquet_sql(output)}"
                ).fetchone(),
            )
        }
        category_counts = [
            {"GeneralUseType": row[0], "building_count": row[1]}
            for row in con.execute(
                f"""SELECT "GeneralUseType", COUNT(DISTINCT OBJECTID)
                    FROM {_parquet_sql(output)} GROUP BY 1 ORDER BY 1"""
            ).fetchall()
        ]
        finer_grid_missing = con.execute(
            f"SELECT COUNT(*) FROM {_parquet_sql(output)} WHERE "
            '"id.grid.finer" IS NULL'
        ).fetchone()[0]
        report = {
            "source_path": profile["source_path"],
            "processed_source_path": str(source),
            "observation_start": str(start),
            "observation_end_exclusive": str(end_exclusive),
            "window_months": settings.window_months,
            "expected_hourly_observations": expected_hours,
            "minimum_coverage": settings.minimum_coverage,
            "quantile_method": "DuckDB APPROX_QUANTILE T-Digest estimates for median and p95",
            "scope": "all GeneralUseType values in the configured Bronze source, including Residential",
            "buildings_by_general_use_type_in_source": [
                {"GeneralUseType": item["value"], "building_count": int(item["buildings"])}
                for item in profile["category_values"]["GeneralUseType"]
            ],
            "feature_path": str(output),
            "feature_rows": result[0],
            "eligible_buildings": result[1],
            "excluded_low_coverage_buildings": excluded,
            "minimum_observed_coverage": result[2],
            "mean_observed_coverage": result[3],
            "maximum_observed_coverage": result[4],
            "feature_columns": [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {_parquet_sql(output)}").fetchall()],
            "behaviour_feature_columns": feature_fields,
            "null_feature_values_by_column": missing_features,
            "buildings_by_general_use_type": category_counts,
            "missing_finer_grid_buildings": finer_grid_missing,
            "metadata_columns_excluded_from_clustering": sorted(IDENTIFIER_COLUMNS),
        }
        _atomic_json(settings.reports_dir / "feature_generation.json", report)
        logger.info("Generated segmentation building features: %s", report)
        return report
    finally:
        con.close()


def load_or_validate_source_profile(settings: SegmentationSettings) -> dict[str, Any]:
    """Reuse a profile only when it describes the current immutable source file."""
    profile_path = settings.reports_dir / "source_profile.json"
    _, sample_manifest = _prepare_segmentation_source(settings)
    profile: dict[str, Any] | None = None
    if profile_path.is_file():
        try:
            cached = json.loads(profile_path.read_text(encoding="utf-8"))
            if all(
                cached.get(key) == value
                for key, value in sample_manifest.items()
            ):
                profile = cached
        except (OSError, json.JSONDecodeError):
            profile = None
    if profile is None:
        profile = validate_source(settings)
    return profile
