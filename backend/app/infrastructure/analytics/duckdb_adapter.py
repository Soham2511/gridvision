"""DuckDB analytical query adapter for GridVision Parquet datasets.

Provides thread-safe connection management, parameterized query execution,
and safe aggregation over historical energy Parquet files without full-table memory loading.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

logger = logging.getLogger("gridvision.infrastructure.analytics.duckdb")


class DuckDBAnalyticalAdapter:
    """Encapsulates DuckDB SQL query execution over Parquet datasets."""

    def __init__(self, database_path: str = ":memory:") -> None:
        self.database_path = database_path

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a fresh, isolated connection per operation for thread safety."""
        return duckdb.connect(database=self.database_path)

    def query_intervals_for_entity(
        self,
        parquet_path: Path | str,
        entity_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50000,
    ) -> list[dict[str, Any]]:
        """Extract isolated interval readings for one entity with optional date filtering.

        Uses parameterized queries to prevent SQL injection.
        """
        path_str = str(parquet_path).replace("\\", "/")
        params: list[Any] = [entity_id]
        where_clauses = ['"OBJECTID" = ?', '"normalized_building_energy_kwh" >= 0']

        if start_date:
            where_clauses.append('"timestamp" >= ?')
            params.append(start_date)

        if end_date:
            # Inclusive end-of-day filter
            where_clauses.append('"timestamp" <= ?')
            # If date only (e.g. 2018-05-31), include up to 23:59:59
            end_bound = f"{end_date} 23:59:59" if len(end_date) == 10 else end_date
            params.append(end_bound)

        where_sql = " AND ".join(where_clauses)
        params.append(limit)

        sql = f"""
            SELECT 
                "timestamp",
                "normalized_building_energy_kwh" AS kwh
            FROM '{path_str}'
            WHERE {where_sql}
            ORDER BY "timestamp" ASC
            LIMIT ?
        """

        conn = self._get_connection()
        try:
            df = conn.execute(sql, params).df()
            if df.empty:
                return []

            results = []
            for row in df.itertuples():
                ts = row.timestamp
                if hasattr(ts, "to_pydatetime"):
                    ts = ts.to_pydatetime()
                elif isinstance(ts, str):
                    ts = pd.to_datetime(ts).to_pydatetime()

                results.append({
                    "timestamp": ts,
                    "kwh": float(row.kwh),
                    "is_predicted": False,
                })
            return results
        except Exception as exc:
            logger.error("DuckDB query failed for entity %s: %s", entity_id, exc)
            return []
        finally:
            conn.close()

    def get_date_bounds_for_entity(
        self, parquet_path: Path | str, entity_id: int
    ) -> tuple[str | None, str | None, int]:
        """Retrieve min timestamp, max timestamp, and total row count for an entity."""
        path_str = str(parquet_path).replace("\\", "/")
        sql = f"""
            SELECT 
                MIN("timestamp")::VARCHAR AS min_ts,
                MAX("timestamp")::VARCHAR AS max_ts,
                COUNT(*) AS row_count
            FROM '{path_str}'
            WHERE "OBJECTID" = ? AND "normalized_building_energy_kwh" >= 0
        """
        conn = self._get_connection()
        try:
            res = conn.execute(sql, [entity_id]).fetchone()
            if not res or res[0] is None:
                return None, None, 0
            return str(res[0]), str(res[1]), int(res[2])
        except Exception as exc:
            logger.error("DuckDB date bounds query failed for entity %s: %s", entity_id, exc)
            return None, None, 0
        finally:
            conn.close()
