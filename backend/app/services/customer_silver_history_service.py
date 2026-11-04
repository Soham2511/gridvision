"""Aggregate authorized reporting windows from the customer Silver dataset."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb


class CustomerSilverHistoryError(RuntimeError):
    """The configured customer Silver source could not be read."""


class CustomerSilverHistoryService:
    REQUIRED_COLUMNS = ("OBJECTID", "timestamp", "normalized_building_energy_kwh")

    def __init__(self, dataset_path: str | Path, metadata_path: str | Path | None = None) -> None:
        self.dataset_path = Path(dataset_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None

    @staticmethod
    def _sql_path(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    def _query(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        if not self.dataset_path.is_file():
            raise CustomerSilverHistoryError("Customer Silver data is unavailable.")
        connection = duckdb.connect()
        try:
            return connection.execute(query.format(path=self._sql_path(self.dataset_path)), params).fetchall()
        except (duckdb.Error, OSError) as exc:
            raise CustomerSilverHistoryError("Customer Silver data is unavailable.") from exc
        finally:
            connection.close()

    def get_cohort_history(
        self, start_date: date, end_date: date, entity_id: int | None = None
    ) -> dict[str, Any]:
        if end_date < start_date or (end_date - start_date).days > 30:
            raise ValueError("Silver history window must be ordered and no longer than 31 days.")
        if entity_id is not None and (isinstance(entity_id, bool) or entity_id <= 0):
            raise ValueError("Silver entity ID must be a positive integer.")

        cols_rows = self._query("DESCRIBE SELECT * FROM read_parquet({path}) LIMIT 0")
        cols = {row[0] for row in cols_rows}
        missing = sorted(set(self.REQUIRED_COLUMNS).difference(cols))
        if missing:
            raise CustomerSilverHistoryError("Customer Silver data is missing required history fields.")

        cov_where = ' WHERE "OBJECTID" = ? AND timestamp IS NOT NULL AND "normalized_building_energy_kwh" IS NOT NULL AND "normalized_building_energy_kwh" >= 0' if entity_id is not None else ' WHERE timestamp IS NOT NULL AND "normalized_building_energy_kwh" IS NOT NULL AND "normalized_building_energy_kwh" >= 0'
        cov_params = (entity_id,) if entity_id is not None else ()
        cov_res = self._query(
            f'''SELECT MIN(CAST(timestamp AS DATE)), MAX(CAST(timestamp AS DATE))
                FROM read_parquet({{path}}){cov_where}''',
            cov_params,
        )
        available_start = cov_res[0][0].isoformat() if cov_res and cov_res[0][0] is not None else None
        available_end = cov_res[0][1].isoformat() if cov_res and cov_res[0][1] is not None else None

        where_entity = ' WHERE "OBJECTID" = ? AND' if entity_id is not None else ' WHERE'
        end_exclusive = end_date + timedelta(days=1)
        params = (entity_id, start_date, end_exclusive) if entity_id is not None else (start_date, end_exclusive)
        rows = self._query(
            f'''SELECT strftime(CAST(timestamp AS DATE), '%Y-%m-%d') AS day,
                       SUM("normalized_building_energy_kwh") AS total_kwh,
                       COUNT(DISTINCT "OBJECTID") AS household_count,
                       COUNT(*) AS observation_count
                FROM read_parquet({{path}})
                {where_entity} CAST(timestamp AS TIMESTAMP) >= ? AND CAST(timestamp AS TIMESTAMP) < ?
                  AND "normalized_building_energy_kwh" IS NOT NULL
                  AND "normalized_building_energy_kwh" >= 0
                GROUP BY day ORDER BY day''',
            params,
        )

        records = [
            {
                "date": row[0],
                "totalConsumptionKwh": round(float(row[1]), 3),
                "householdCount": int(row[2]),
            }
            for row in rows
        ]
        totals = [record["totalConsumptionKwh"] for record in records]
        obs_count = sum(int(row[3]) for row in rows)
        hh_count = max((int(row[2]) for row in rows), default=0) if entity_id is None else (1 if records else 0)

        if entity_id is not None:
            hourly_rows = self._query(
                f'''SELECT strftime(CAST(timestamp AS TIMESTAMP), '%Y-%m-%d %H:%M:%S') AS ts,
                           "normalized_building_energy_kwh" AS kwh
                    FROM read_parquet({{path}})
                    {where_entity} CAST(timestamp AS TIMESTAMP) >= ? AND CAST(timestamp AS TIMESTAMP) < ?
                      AND "normalized_building_energy_kwh" IS NOT NULL
                      AND "normalized_building_energy_kwh" >= 0
                    ORDER BY timestamp''',
                params,
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
                    WHERE CAST(timestamp AS TIMESTAMP) >= ? AND CAST(timestamp AS TIMESTAMP) < ?
                      AND "normalized_building_energy_kwh" IS NOT NULL
                      AND "normalized_building_energy_kwh" >= 0
                    GROUP BY timestamp ORDER BY timestamp''',
                params,
            )
            hourly_records = [
                {"timestamp": row[0], "consumptionKwh": round(float(row[1]), 4)}
                for row in hourly_rows
            ]

        metadata: dict[str, Any] = {}
        if self.metadata_path and self.metadata_path.is_file():
            try:
                loaded = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    metadata = loaded
            except (OSError, json.JSONDecodeError):
                metadata = {}
        return {
            "persona": "household",
            **({"entityId": entity_id} if entity_id is not None else {}),
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "scope": "household_entity" if entity_id is not None else "household_cohort",
            "unit": "kWh",
            "householdCount": hh_count,
            "daysReturned": len(records),
            "observationCount": obs_count,
            "sourceCoverage": {"start": available_start, "end": available_end},
            "totalConsumptionKwh": round(sum(totals), 3),
            "averageDailyConsumptionKwh": round(sum(totals) / len(totals), 3) if totals else None,
            "dailyConsumption": records,
            "hourlyReadings": hourly_records,
            "dataset": {
                "name": metadata.get("dataset_name", "customer_silver"),
                "version": metadata.get("dataset_version", "untracked"),
                "qualityPassed": metadata.get("quality_passed"),
            },
        }

    def get_latest_available_month(self, entity_id: int | None = None) -> dict[str, Any]:
        """Summarize the latest Silver month for one entity or the full cohort."""
        if entity_id is not None:
            if isinstance(entity_id, bool) or entity_id <= 0:
                raise ValueError("Silver entity ID must be a positive integer.")
        where = ' WHERE "OBJECTID" = ? AND timestamp IS NOT NULL' if entity_id is not None else ' WHERE timestamp IS NOT NULL'
        params = (entity_id,) if entity_id is not None else ()
        result = self._query(
            f'''SELECT MAX(CAST(timestamp AS DATE))
                FROM read_parquet({{path}}){where}''',
            params,
        )
        latest_date = result[0][0] if result else None
        if latest_date is None:
            if entity_id is not None:
                raise CustomerSilverHistoryError(
                    "Customer Silver contains no observations for the selected entity."
                )
            raise CustomerSilverHistoryError("Customer Silver contains no valid observation timestamps.")
        if isinstance(latest_date, str):
            latest_date = date.fromisoformat(latest_date)
        start_date = latest_date.replace(day=1)
        return self.get_cohort_history(start_date, latest_date, entity_id=entity_id)

    def get_source_metadata(self) -> dict[str, Any]:
        dataset: dict[str, Any] = {}
        if self.metadata_path and self.metadata_path.is_file():
            try:
                value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    dataset = value
            except (OSError, json.JSONDecodeError):
                dataset = {}
        return {
            "sourceId": "customer_silver",
            "dataset": dataset.get("dataset_name", "customer_silver"),
            "datasetVersion": dataset.get("dataset_version", "untracked"),
            "provenance": "Silver hourly household energy observations aggregated by day.",
            "units": "kWh",
            "data_class": "historical",
            "is_live_telemetry": False,
        }
