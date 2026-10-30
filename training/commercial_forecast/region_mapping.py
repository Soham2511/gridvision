"""Join commercial building forecasts to government total-grid forecasts."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from training.government_load.sql import identifier, sql_string

GRID_KEY = "id.grid.coarse"
BUILDING_KEY = "OBJECTID"
JOIN_COLUMNS = (GRID_KEY, "target_timestamp", "forecast_horizon_hours")
REQUIRED_COMMERCIAL = {BUILDING_KEY, *JOIN_COLUMNS}
REQUIRED_GOVERNMENT = {GRID_KEY, "target_timestamp", "forecast_horizon_hours", "prediction"}


def validate_grid_key_types(commercial_path: str | Path, government_path: str | Path) -> dict[str, str]:
    """Require the shared coarse-grid key to have the same integer type in both files."""
    commercial_schema = pq.read_schema(Path(commercial_path))
    government_schema = pq.read_schema(Path(government_path))
    try:
        commercial_type = commercial_schema.field(GRID_KEY).type
        government_type = government_schema.field(GRID_KEY).type
    except KeyError as exc:
        raise ValueError(f"Both datasets must include {GRID_KEY!r}") from exc
    if not pa.types.is_integer(commercial_type) or not pa.types.is_integer(government_type):
        raise TypeError(
            f"{GRID_KEY} must be an integer in both datasets; found "
            f"commercial={commercial_type}, government={government_type}"
        )
    if commercial_type != government_type:
        raise TypeError(
            f"{GRID_KEY} types differ: commercial={commercial_type}, "
            f"government={government_type}"
        )
    return {"commercial": str(commercial_type), "government": str(government_type)}


def join_building_forecasts(
    commercial_forecasts_path: str | Path,
    government_predictions_path: str | Path,
    output_path: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    """Left join regional total-grid forecasts and report building/grid coverage.

    Rows without a government grid stay in the output with a null regional
    prediction and ``missing_government_grid`` status. A known grid with no
    prediction for the requested timestamp/horizon is marked
    ``government_forecast_unavailable``.
    """
    commercial = Path(commercial_forecasts_path).expanduser().resolve()
    government = Path(government_predictions_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    report = Path(report_path).expanduser().resolve()
    for label, path in (("commercial forecasts", commercial), ("government predictions", government)):
        if not path.is_file():
            raise FileNotFoundError(f"{label} parquet not found: {path}")
    if output in {commercial, government}:
        raise ValueError("Joined forecast output must not overwrite either input")
    types = validate_grid_key_types(commercial, government)

    connection = duckdb.connect()
    staged = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.stage.parquet")
    try:
        commercial_sql, government_sql = sql_string(commercial), sql_string(government)
        schemas = {
            "commercial": {row[0] for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({commercial_sql})"
            ).fetchall()},
            "government": {row[0] for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({government_sql})"
            ).fetchall()},
        }
        for label, required in (("commercial", REQUIRED_COMMERCIAL), ("government", REQUIRED_GOVERNMENT)):
            missing = sorted(required - schemas[label])
            if missing:
                raise ValueError(f"{label.title()} forecasts missing required columns: {missing}")

        duplicate_commercial_mapping = connection.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT {identifier(BUILDING_KEY)}
              FROM read_parquet({commercial_sql})
              GROUP BY {identifier(BUILDING_KEY)}
              HAVING COUNT(DISTINCT {identifier(GRID_KEY)}) > 1
            )
            """
        ).fetchone()[0]
        if duplicate_commercial_mapping:
            raise ValueError(
                f"{duplicate_commercial_mapping} commercial buildings map to multiple coarse grids"
            )
        duplicate_gov_rows = connection.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT {identifier(GRID_KEY)}, target_timestamp, forecast_horizon_hours
              FROM read_parquet({government_sql}) GROUP BY ALL HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        if duplicate_gov_rows:
            raise ValueError("Government predictions contain duplicate grid/time/horizon keys")

        counts = connection.execute(
            f"""
            WITH building_map AS (
              SELECT {identifier(BUILDING_KEY)}, ANY_VALUE({identifier(GRID_KEY)}) AS grid_id
              FROM read_parquet({commercial_sql}) GROUP BY {identifier(BUILDING_KEY)}
            ), government_grids AS (
              SELECT DISTINCT {identifier(GRID_KEY)} AS grid_id
              FROM read_parquet({government_sql})
            )
            SELECT
              (SELECT COUNT(*) FROM building_map),
              (SELECT COUNT(*) FROM building_map b JOIN government_grids g USING (grid_id)),
              (SELECT COUNT(*) FROM building_map b LEFT JOIN government_grids g USING (grid_id) WHERE g.grid_id IS NULL),
              (SELECT COUNT(DISTINCT {identifier(GRID_KEY)}) FROM read_parquet({commercial_sql})),
              (SELECT COUNT(*) FROM (SELECT DISTINCT {identifier(GRID_KEY)} FROM read_parquet({commercial_sql})) c JOIN government_grids g ON c.{identifier(GRID_KEY)} = g.grid_id),
              (SELECT COUNT(*) FROM (SELECT DISTINCT {identifier(GRID_KEY)} FROM read_parquet({commercial_sql})) c LEFT JOIN government_grids g ON c.{identifier(GRID_KEY)} = g.grid_id WHERE g.grid_id IS NULL)
            """
        ).fetchone()
        building_count, mapped_buildings, unmatched_buildings, commercial_grids, matched_grids, unmatched_grids = map(int, counts)

        output.parent.mkdir(parents=True, exist_ok=True)
        connection.execute(
            f"""
            COPY (
              SELECT c.*,
                     g.prediction AS total_grid_demand_prediction,
                     CASE
                       WHEN gg.grid_id IS NULL THEN 'missing_government_grid'
                       WHEN g.prediction IS NULL THEN 'government_forecast_unavailable'
                       ELSE 'matched'
                     END AS region_forecast_status,
                     'total_grid_demand' AS region_forecast_scope
              FROM read_parquet({commercial_sql}) c
              LEFT JOIN (SELECT DISTINCT {identifier(GRID_KEY)} AS grid_id
                         FROM read_parquet({government_sql})) gg
                ON c.{identifier(GRID_KEY)} = gg.grid_id
              LEFT JOIN read_parquet({government_sql}) g
                ON c.{identifier(GRID_KEY)} = g.{identifier(GRID_KEY)}
               AND c.target_timestamp = g.target_timestamp
               AND c.forecast_horizon_hours = g.forecast_horizon_hours
            ) TO {sql_string(staged)} (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        row_counts = connection.execute(
            f"""
            SELECT COUNT(*),
              COUNT(*) FILTER (WHERE region_forecast_status = 'matched'),
              COUNT(*) FILTER (WHERE region_forecast_status = 'missing_government_grid'),
              COUNT(*) FILTER (WHERE region_forecast_status = 'government_forecast_unavailable')
            FROM read_parquet({sql_string(staged)})
            """
        ).fetchone()
        os.replace(staged, output)
        payload: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "commercial_dataset": str(commercial),
            "government_predictions": str(government),
            "joined_output": str(output),
            "join_key": GRID_KEY,
            "join_columns": list(JOIN_COLUMNS),
            "grid_key_types": types,
            "grid_definition": (
                "The shared source field id.grid.coarse; government ETL aggregates all "
                "building types by this key and timestamp. Regional values are total grid demand."
            ),
            "building_coverage": {
                "commercial_buildings": building_count,
                "matched_buildings": mapped_buildings,
                "unmatched_buildings": unmatched_buildings,
            },
            "grid_coverage": {
                "commercial_grids": commercial_grids,
                "matched_grids": matched_grids,
                "unmatched_grids": unmatched_grids,
            },
            "forecast_rows": {
                "total": int(row_counts[0]),
                "matched": int(row_counts[1]),
                "missing_grid": int(row_counts[2]),
                "forecast_unavailable": int(row_counts[3]),
            },
            "missing_grid_behavior": "Preserve building row; set regional prediction null and status missing_government_grid.",
            "quality_passed": int(row_counts[0]) == int(row_counts[1]) + int(row_counts[2]) + int(row_counts[3]),
        }
    finally:
        connection.close()
        staged.unlink(missing_ok=True)

    report.parent.mkdir(parents=True, exist_ok=True)
    temporary_report = report.with_suffix(report.suffix + ".stage")
    temporary_report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary_report, report)
    return payload
