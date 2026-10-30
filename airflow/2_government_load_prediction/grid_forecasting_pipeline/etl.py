from __future__ import annotations

import os
import uuid
from pathlib import Path

import duckdb
import joblib

from training.government_load.config import PipelineSettings
from training.government_load.sql import identifier, sql_string

RAW_REQUIRED_COLUMNS = {
    "OBJECTID",
    "id.grid.coarse",
    "building.area.m2",
    "FootprintArea.m2",
    "GeneralUseType",
    "latitude",
    "longitude",
    "timestamp",
    "normalized_building_energy_kwh",
}
GRID_KEY = '"id.grid.coarse"'


def _temporary_output(path: Path) -> Path:
    return path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp.parquet")


def _copy_query(connection: duckdb.DuckDBPyConnection, query: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_output(output)
    try:
        connection.execute(
            f"COPY ({query}) TO {sql_string(temporary)} "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
        )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _load_features(path: Path) -> list[str]:
    features = joblib.load(path)
    if not isinstance(features, list) or not features:
        raise ValueError(f"Expected a non-empty list of feature names in {path}")
    if not all(isinstance(feature, str) for feature in features):
        raise ValueError(f"Feature names in {path} must all be strings")
    if len(features) != len(set(features)):
        raise ValueError(f"Feature names in {path} contain duplicates")
    return features


def prepare_training_data(settings: PipelineSettings) -> Path:
    """Create grid, history, gold, and training-ready Parquet stages."""
    source = settings.input_path.expanduser().resolve()
    output = settings.output_path.expanduser().resolve()
    features_path = settings.feature_columns_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input parquet file not found: {source}")
    if not features_path.is_file():
        raise FileNotFoundError(f"Feature-column file not found: {features_path}")

    stage_paths = {
        "grid": output.parent / "grid_level_energy.parquet",
        "history": output.parent / "grid_history_features.parquet",
        "gold": output.parent / "gold_grid_forecasting_2018.parquet",
    }
    energy_path = output.parent / ".energy_by_grid_time.parquet"
    if output in {path.resolve() for path in stage_paths.values()}:
        raise ValueError("Training-ready output must not reuse an intermediate filename")
    for stage_path in [output, *stage_paths.values()]:
        if stage_path.resolve() == source:
            raise ValueError(f"Output would overwrite the source dataset: {source}")
    if energy_path.resolve() == source:
        raise ValueError(f"Output would overwrite the source dataset: {source}")

    feature_columns = _load_features(features_path)
    category_features = [
        column
        for column in feature_columns
        if column.endswith("_count")
        and column not in {"building_count", "energy_count_24h", "energy_count_7d", "energy_count_30d"}
    ]
    if not category_features:
        raise ValueError("Feature columns must include the building-use count features")

    connection = duckdb.connect()
    try:
        connection.execute(f"SET memory_limit = {sql_string(settings.memory_limit)}")
        connection.execute(f"SET threads = {settings.threads}")
        temp_directory = output.parent / "duckdb_temp"
        temp_directory.mkdir(parents=True, exist_ok=True)
        connection.execute(
            f"SET temp_directory = {sql_string(temp_directory.resolve())}"
        )

        source_sql = sql_string(source)
        schema = connection.execute(
            f"DESCRIBE SELECT * FROM read_parquet({source_sql})"
        ).fetchall()
        available = {row[0] for row in schema}
        missing = sorted(RAW_REQUIRED_COLUMNS - available)
        if missing:
            raise ValueError(f"Source dataset is missing required columns: {missing}")

        grid_conflicts = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT "OBJECTID"
                FROM read_parquet({source_sql})
                WHERE "OBJECTID" IS NOT NULL
                  AND "id.grid.coarse" IS NOT NULL
                GROUP BY "OBJECTID"
                HAVING COUNT(DISTINCT "id.grid.coarse") > 1
            ) conflicts
            """
        ).fetchone()[0]
        if grid_conflicts:
            raise ValueError(
                f"{grid_conflicts:,} buildings are assigned to multiple coarse grids"
            )

        print("Stage 1/4: aggregating building energy by grid and timestamp")
        _copy_query(
            connection,
            f"""
            SELECT
                "id.grid.coarse",
                timestamp,
                SUM(normalized_building_energy_kwh)
                    AS total_normalized_building_energy_kwh
            FROM read_parquet({source_sql})
            WHERE "OBJECTID" IS NOT NULL
              AND "id.grid.coarse" IS NOT NULL
              AND timestamp IS NOT NULL
            GROUP BY "id.grid.coarse", timestamp
            """,
            energy_path,
        )

        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE unique_buildings AS
            SELECT
                "OBJECTID",
                ANY_VALUE("id.grid.coarse") AS grid_id,
                ANY_VALUE("building.area.m2") AS building_area,
                ANY_VALUE("FootprintArea.m2") AS footprint_area,
                ANY_VALUE("GeneralUseType") AS general_use_type,
                ANY_VALUE(latitude) AS latitude,
                ANY_VALUE(longitude) AS longitude
            FROM read_parquet({source_sql})
            WHERE "OBJECTID" IS NOT NULL
              AND "id.grid.coarse" IS NOT NULL
            GROUP BY "OBJECTID"
            """
        )

        category_expressions = []
        for column in category_features:
            category = column.removesuffix("_count").replace("'", "''")
            category_expressions.append(
                f"COUNT(*) FILTER (WHERE general_use_type = '{category}') "
                f'AS "{column}"'
            )
        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE grid_metadata AS
            SELECT
                grid_id AS "id.grid.coarse",
                COUNT(*) AS building_count,
                SUM(CASE WHEN TRY_CAST(building_area AS DOUBLE) > 0
                    THEN TRY_CAST(building_area AS DOUBLE) ELSE 0 END)
                    AS total_building_area_m2,
                SUM(CASE WHEN TRY_CAST(footprint_area AS DOUBLE) > 0
                    THEN TRY_CAST(footprint_area AS DOUBLE) ELSE 0 END)
                    AS total_footprint_area_m2,
                AVG(CASE
                    WHEN TRY_CAST(latitude AS DOUBLE) BETWEEN -90 AND 90
                     AND TRY_CAST(longitude AS DOUBLE) BETWEEN -180 AND 180
                    THEN TRY_CAST(latitude AS DOUBLE)
                END) AS centroid_latitude,
                AVG(CASE
                    WHEN TRY_CAST(latitude AS DOUBLE) BETWEEN -90 AND 90
                     AND TRY_CAST(longitude AS DOUBLE) BETWEEN -180 AND 180
                    THEN TRY_CAST(longitude AS DOUBLE)
                END) AS centroid_longitude,
                {", ".join(category_expressions)}
            FROM unique_buildings
            GROUP BY grid_id
            """
        )

        print("Stage 2/4: joining grid metadata and creating history features")
        category_sql = ", ".join(
            f"m.{identifier(column)}" for column in category_features
        )
        _copy_query(
            connection,
            f"""
            SELECT
                e."id.grid.coarse",
                e.timestamp,
                e.total_normalized_building_energy_kwh,
                m.total_building_area_m2,
                m.total_footprint_area_m2,
                m.centroid_latitude,
                m.centroid_longitude,
                m.building_count,
                {category_sql}
            FROM read_parquet({sql_string(energy_path)}) e
            INNER JOIN grid_metadata m
              ON e."id.grid.coarse" = m."id.grid.coarse"
            ORDER BY e."id.grid.coarse", e.timestamp
            """,
            stage_paths["grid"],
        )
        grid_with_metadata = stage_paths["grid"]
        grid_with_metadata_sql = sql_string(grid_with_metadata)

        duplicate_keys = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT "id.grid.coarse", timestamp
                FROM read_parquet({grid_with_metadata_sql})
                GROUP BY "id.grid.coarse", timestamp
                HAVING COUNT(*) > 1
            ) duplicate_keys
            """
        ).fetchone()[0]
        if duplicate_keys:
            raise ValueError(
                f"Found {duplicate_keys:,} duplicate grid/timestamp records"
            )

        history_columns = [
            "id.grid.coarse",
            "timestamp",
            "total_normalized_building_energy_kwh",
            "total_building_area_m2",
            "total_footprint_area_m2",
            "centroid_latitude",
            "centroid_longitude",
            "building_count",
            *category_features,
        ]
        base_columns = ", ".join(
            identifier(column) for column in history_columns
        )
        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE base_grid AS
            SELECT {base_columns}
            FROM read_parquet({grid_with_metadata_sql})
            """
        )
        energy_path.unlink(missing_ok=True)
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE grid_rolling_features AS
            SELECT
                *,
                AVG(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 24 HOURS PRECEDING AND CURRENT ROW
                ) AS energy_mean_24h,
                STDDEV_SAMP(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 24 HOURS PRECEDING AND CURRENT ROW
                ) AS energy_std_24h,
                COUNT(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 24 HOURS PRECEDING AND CURRENT ROW
                ) AS energy_count_24h,
                AVG(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND CURRENT ROW
                ) AS energy_mean_7d,
                STDDEV_SAMP(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND CURRENT ROW
                ) AS energy_std_7d,
                COUNT(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND CURRENT ROW
                ) AS energy_count_7d,
                AVG(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 30 DAYS PRECEDING AND CURRENT ROW
                ) AS energy_mean_30d,
                STDDEV_SAMP(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 30 DAYS PRECEDING AND CURRENT ROW
                ) AS energy_std_30d,
                COUNT(total_normalized_building_energy_kwh) OVER (
                    PARTITION BY "id.grid.coarse" ORDER BY timestamp
                    RANGE BETWEEN INTERVAL 30 DAYS PRECEDING AND CURRENT ROW
                ) AS energy_count_30d
            FROM base_grid
            """
        )
        _copy_query(
            connection,
            """
            SELECT
                f.*,
                lag1.total_normalized_building_energy_kwh AS energy_lag_1h,
                lag24.total_normalized_building_energy_kwh AS energy_lag_24h,
                lag168.total_normalized_building_energy_kwh AS energy_lag_168h,
                lag336.total_normalized_building_energy_kwh AS energy_lag_336h,
                lag720.total_normalized_building_energy_kwh AS energy_lag_720h
            FROM grid_rolling_features f
            LEFT JOIN base_grid lag1
              ON lag1."id.grid.coarse" = f."id.grid.coarse"
             AND lag1.timestamp = f.timestamp - INTERVAL 1 HOUR
            LEFT JOIN base_grid lag24
              ON lag24."id.grid.coarse" = f."id.grid.coarse"
             AND lag24.timestamp = f.timestamp - INTERVAL 24 HOURS
            LEFT JOIN base_grid lag168
              ON lag168."id.grid.coarse" = f."id.grid.coarse"
             AND lag168.timestamp = f.timestamp - INTERVAL 168 HOURS
            LEFT JOIN base_grid lag336
              ON lag336."id.grid.coarse" = f."id.grid.coarse"
             AND lag336.timestamp = f.timestamp - INTERVAL 336 HOURS
            LEFT JOIN base_grid lag720
              ON lag720."id.grid.coarse" = f."id.grid.coarse"
             AND lag720.timestamp = f.timestamp - INTERVAL 720 HOURS
            """,
            stage_paths["history"],
        )
        print("Stage 3/4: expanding forecast horizons and labeling gold rows")
        history_sql = sql_string(stage_paths["history"])
        _copy_query(
            connection,
            f"""
            SELECT
                f.timestamp AS forecast_origin_timestamp,
                f.timestamp + h.horizon_hours * INTERVAL '1 hour'
                    AS target_timestamp,
                h.horizon_hours::INTEGER AS forecast_horizon_hours,
                f."id.grid.coarse",
                f.total_building_area_m2,
                f.total_footprint_area_m2,
                f.centroid_latitude,
                f.centroid_longitude,
                f.building_count,
                {", ".join(f'f."{column}"' for column in category_features)},
                f.total_normalized_building_energy_kwh AS energy_at_origin,
                f.energy_lag_1h,
                f.energy_lag_24h,
                f.energy_lag_168h,
                f.energy_lag_336h,
                f.energy_lag_720h,
                f.energy_mean_24h,
                f.energy_std_24h,
                f.energy_count_24h,
                f.energy_mean_7d,
                f.energy_std_7d,
                f.energy_count_7d,
                f.energy_mean_30d,
                f.energy_std_30d,
                f.energy_count_30d,
                EXTRACT(YEAR FROM f.timestamp + h.horizon_hours * INTERVAL '1 hour')
                    ::INTEGER AS target_year,
                EXTRACT(MONTH FROM f.timestamp + h.horizon_hours * INTERVAL '1 hour')
                    ::INTEGER AS target_month,
                EXTRACT(DAY FROM f.timestamp + h.horizon_hours * INTERVAL '1 hour')
                    ::INTEGER AS target_day_of_month,
                EXTRACT(DOW FROM f.timestamp + h.horizon_hours * INTERVAL '1 hour')
                    ::INTEGER AS target_day_of_week,
                EXTRACT(HOUR FROM f.timestamp + h.horizon_hours * INTERVAL '1 hour')
                    ::INTEGER AS target_hour,
                EXTRACT(DOY FROM f.timestamp + h.horizon_hours * INTERVAL '1 hour')
                    ::INTEGER AS target_day_of_year,
                CASE WHEN EXTRACT(DOW FROM
                    f.timestamp + h.horizon_hours * INTERVAL '1 hour'
                ) IN (0, 6) THEN 1 ELSE 0 END AS target_is_weekend,
                SIN(2 * PI() * EXTRACT(HOUR FROM
                    f.timestamp + h.horizon_hours * INTERVAL '1 hour'
                ) / 24.0) AS target_hour_sin,
                COS(2 * PI() * EXTRACT(HOUR FROM
                    f.timestamp + h.horizon_hours * INTERVAL '1 hour'
                ) / 24.0) AS target_hour_cos,
                SIN(2 * PI() * (
                    EXTRACT(DOY FROM
                        f.timestamp + h.horizon_hours * INTERVAL '1 hour'
                    ) - 1
                ) / 365.25) AS target_day_of_year_sin,
                COS(2 * PI() * (
                    EXTRACT(DOY FROM
                        f.timestamp + h.horizon_hours * INTERVAL '1 hour'
                    ) - 1
                ) / 365.25) AS target_day_of_year_cos,
                target.total_normalized_building_energy_kwh AS target_energy,
                target.timestamp IS NOT NULL
                    AND target.total_normalized_building_energy_kwh IS NOT NULL
                    AS target_available
            FROM read_parquet({history_sql}) f
            CROSS JOIN range(1, {settings.horizon_hours + 1}) h(horizon_hours)
            LEFT JOIN read_parquet({history_sql}) target
              ON target."id.grid.coarse" = f."id.grid.coarse"
             AND target.timestamp =
                 f.timestamp + h.horizon_hours * INTERVAL '1 hour'
            """,
            stage_paths["gold"],
        )

        print("Stage 4/4: writing rows with observed target energy")
        gold_sql = sql_string(stage_paths["gold"])
        gold_columns = {
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({gold_sql})"
            ).fetchall()
        }
        missing_features = sorted(set(feature_columns) - gold_columns)
        if missing_features:
            raise ValueError(
                "The prepared data cannot satisfy the saved model features: "
                f"{missing_features}"
            )
        ready_features = list(feature_columns)
        if "target_year" in gold_columns and "target_year" not in ready_features:
            insert_at = (
                ready_features.index("target_month")
                if "target_month" in ready_features
                else len(ready_features)
            )
            ready_features.insert(insert_at, "target_year")
        # Keep the duplicate horizon column from the notebook's ready-table layout.
        selected_features = [
            'forecast_horizon_hours AS "forecast_horizon_hours_1"'
        ]
        selected_features.extend(
            identifier(column)
            for column in ready_features
            if column != "forecast_horizon_hours"
        )
        ready_query = f"""
            SELECT
                "id.grid.coarse",
                forecast_origin_timestamp,
                target_timestamp,
                forecast_horizon_hours,
                {", ".join(selected_features)},
                target_energy
            FROM read_parquet({gold_sql})
            WHERE target_available = TRUE
              AND target_energy IS NOT NULL
        """
        _copy_query(connection, ready_query, output)
        row_count = connection.execute(
            f"SELECT COUNT(*) FROM read_parquet({sql_string(output)})"
        ).fetchone()[0]
        print(f"Wrote {row_count:,} training-ready rows to {output}")
    finally:
        connection.close()
    return output
