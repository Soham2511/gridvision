"""Bounded historical consumption reads from the commercial Silver dataset."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb


class CommercialSilverHistoryError(RuntimeError):
    """The commercial Silver source could not be read or summarized."""


class CommercialSilverEntityNotFoundError(LookupError):
    """The requested building or cohort has no valid timestamped observations."""


class CommercialSilverHistoryService:
    def __init__(self, dataset_path: str | Path, metadata_path: str | Path | None = None) -> None:
        self.dataset_path = Path(dataset_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None

    @staticmethod
    def _sql_path(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    def _query(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        if not self.dataset_path.is_file():
            raise CommercialSilverHistoryError("Commercial Silver data is unavailable.")
        connection = duckdb.connect()
        try:
            return connection.execute(query.format(path=self._sql_path(self.dataset_path)), params).fetchall()
        except (duckdb.Error, OSError) as exc:
            raise CommercialSilverHistoryError("Commercial Silver data is unavailable.") from exc
        finally:
            connection.close()

    @staticmethod
    def _entity_clause(entity_id: str | None) -> tuple[str, tuple[Any, ...]]:
        if entity_id is None:
            return "", ()
        normalized = str(entity_id).strip()
        if not normalized or len(normalized) > 120:
            raise ValueError("Commercial building ID is invalid.")
        try:
            numeric_id = int(normalized)
        except ValueError as exc:
            raise ValueError("Commercial Silver building ID must be an OBJECTID.") from exc
        if numeric_id <= 0:
            raise ValueError("Commercial Silver building ID must be a positive OBJECTID.")
        return ' WHERE "OBJECTID" = ?', (numeric_id,)

    def get_history(self, start_date: date, end_date: date, entity_id: str | None = None) -> dict[str, Any]:
        if end_date < start_date or (end_date - start_date).days > 30:
            raise ValueError("Commercial Silver history window must be ordered and no longer than 31 days.")
        where, entity_params = self._entity_clause(entity_id)
        rows = self._query(
            f'''SELECT CAST(timestamp AS DATE) AS day,
                       SUM("normalized_building_energy_kwh") AS total_kwh,
                       COUNT(*) AS observation_count,
                       COUNT(DISTINCT "OBJECTID") AS building_count
                FROM read_parquet({{path}})
                {where}{" AND" if where else " WHERE"} timestamp >= ? AND timestamp < ?
                  AND "normalized_building_energy_kwh" IS NOT NULL
                  AND "normalized_building_energy_kwh" >= 0
                GROUP BY day ORDER BY day''',
            (*entity_params, start_date, end_date + timedelta(days=1)),
        )
        daily = [
            {
                "date": row[0].isoformat(),
                "totalConsumptionKwh": round(float(row[1]), 3),
                "observationCount": int(row[2]),
                "buildingCount": int(row[3]),
            }
            for row in rows
        ]
        totals = [record["totalConsumptionKwh"] for record in daily]
        observed = sum(record["observationCount"] for record in daily)

        if entity_id is not None:
            hourly_rows = self._query(
                f'''SELECT strftime(CAST(timestamp AS TIMESTAMP), '%Y-%m-%d %H:%M:%S') AS ts,
                           "normalized_building_energy_kwh" AS kwh
                    FROM read_parquet({{path}})
                    {where} AND timestamp >= ? AND timestamp < ?
                      AND "normalized_building_energy_kwh" IS NOT NULL
                      AND "normalized_building_energy_kwh" >= 0
                    ORDER BY timestamp''',
                (*entity_params, start_date, end_date + timedelta(days=1)),
            )
            hourly_records = [
                {"timestamp": row[0], "consumptionKwh": round(float(row[1]), 4)}
                for row in hourly_rows
            ]
        else:
            hourly_rows = self._query(
                f'''SELECT strftime(CAST(timestamp AS TIMESTAMP), '%Y-%m-%d %H:%M:%S') AS ts,
                           AVG("normalized_building_energy_kwh") AS kwh
                    FROM read_parquet({{path}})
                    WHERE timestamp >= ? AND timestamp < ?
                      AND "normalized_building_energy_kwh" IS NOT NULL
                      AND "normalized_building_energy_kwh" >= 0
                    GROUP BY timestamp ORDER BY timestamp''',
                (start_date, end_date + timedelta(days=1)),
            )
            hourly_records = [
                {"timestamp": row[0], "consumptionKwh": round(float(row[1]), 4)}
                for row in hourly_rows
            ]

        return {
            "persona": "commercial",
            **({"entityId": str(int(entity_id))} if entity_id is not None else {}),
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "scope": "commercial_building" if entity_id is not None else "commercial_cohort",
            "unit": "kWh",
            "buildingCount": max((record["buildingCount"] for record in daily), default=0),
            "daysReturned": len(daily),
            "observationCount": observed,
            "totalConsumptionKwh": round(sum(totals), 3),
            "averageDailyConsumptionKwh": round(sum(totals) / len(totals), 3) if totals else None,
            "dailyConsumption": daily,
            "hourlyReadings": hourly_records,
        }

    def get_latest_available_month(self, entity_id: str | None = None) -> dict[str, Any]:
        where, params = self._entity_clause(entity_id)
        result = self._query(
            f'''SELECT MAX(CAST(timestamp AS DATE))
                FROM read_parquet({{path}}){where}''',
            params,
        )
        latest_day = result[0][0] if result else None
        if latest_day is None:
            qualifier = f" for building {entity_id}" if entity_id else ""
            raise CommercialSilverEntityNotFoundError(f"Commercial Silver has no observations{qualifier}.")
        if isinstance(latest_day, str):
            latest_day = date.fromisoformat(latest_day)
        return self.get_history(latest_day.replace(day=1), latest_day, entity_id)

    def get_source_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if self.metadata_path and self.metadata_path.is_file():
            try:
                loaded = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    metadata = loaded
            except (OSError, json.JSONDecodeError):
                metadata = {}
        return {
            "sourceId": "commercial_silver",
            "dataset": metadata.get("dataset_name", "commercial_silver"),
            "datasetVersion": metadata.get("dataset_version", "untracked"),
            "provenance": "Non-residential commercial Silver energy observations aggregated by day.",
            "units": "kWh",
            "data_class": "historical",
            "is_live_telemetry": False,
        }
