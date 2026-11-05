"""Serve the trained commercial and government forecast artifacts."""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd

from app.providers.mlflow_adapter import MLflowModelAdapter
from app.providers.model_provider import BaseModelProvider, PredictionOutput
from app.api.error_handlers import (
    InvalidInputError,
    ModelUnavailableError,
    ResourceNotFoundError,
)
from training.commercial_forecast.features import FEATURE_COLUMNS, prepare_features

# Backward-compatibility shim for models pickled with scikit-learn 1.6.x deserialized on scikit-learn 1.7+
try:
    import sklearn.compose._column_transformer as _ct

    if not hasattr(_ct, "_RemainderColsList"):
        class _RemainderColsList(list):
            pass

        _ct._RemainderColsList = _RemainderColsList
except Exception:
    pass


class TrainedForecastProvider(BaseModelProvider):
    """Serve historical forecast replays and delegate customer bills to MLflow."""

    def __init__(
        self,
        customer_provider: MLflowModelAdapter,
        commercial_data: Path,
        commercial_model: Path,
        government_data: Path,
        government_model: Path,
        tracking_uri: str = "",
        commercial_model_name: str = "gridvision-commercial-building-forecast",
        government_model_name: str = "gridvision-government-load-forecast",
        model_alias: str = "champion",
        commercial_model_alias: str | None = None,
        government_model_alias: str | None = None,
        commercial_metadata: Path | None = None,
    ) -> None:
        self.customer_provider = customer_provider
        self.commercial_data = Path(commercial_data)
        self.commercial_metadata = (
            Path(commercial_metadata) if commercial_metadata is not None else None
        )
        self.commercial_model_path = Path(commercial_model)
        self.government_data = Path(government_data)
        self.government_model_path = Path(government_model)
        self.tracking_uri = tracking_uri
        self.commercial_model_name = commercial_model_name
        self.government_model_name = government_model_name
        self.model_alias = model_alias
        self.commercial_model_alias = commercial_model_alias or model_alias
        self.government_model_alias = government_model_alias or model_alias
        self._mlflow_models: dict[str, tuple[Any, str]] = {}
        self._commercial_bundle: dict[str, Any] | None = None
        self._government_bundle: dict[str, Any] | None = None
        self._commercial_entities: list[dict[str, Any]] | None = None
        self._regional_entities: list[dict[str, Any]] | None = None
        self._commercial_forecasts: dict[
            tuple[str, int, tuple[int, ...]], pd.DataFrame
        ] = {}
        self._regional_forecasts: dict[
            tuple[int, tuple[int, ...]], pd.DataFrame
        ] = {}
        self._government_actuals: pd.DataFrame | None = None
        self._government_contexts: pd.DataFrame | None = None
        self._government_forecasts: pd.DataFrame | None = None

    @staticmethod
    def _sql_path(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    def _query(self, path: Path, query: str) -> pd.DataFrame:
        if not path.is_file():
            raise FileNotFoundError(f"Forecast data file is missing: {path}")
        connection = duckdb.connect()
        try:
            return connection.execute(query.format(path=self._sql_path(path))).fetchdf()
        finally:
            connection.close()

    def get_commercial_source_metadata(self) -> dict[str, Any]:
        """Read the registered version for the existing Commercial Gold table."""
        if self.commercial_metadata is None or not self.commercial_metadata.is_file():
            raise FileNotFoundError("Commercial Gold dataset metadata is unavailable.")
        try:
            metadata = json.loads(self.commercial_metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Commercial Gold dataset metadata is invalid.") from exc
        if metadata.get("dataset_name") != "commercial_gold":
            raise ValueError("Commercial Gold metadata identifies a different dataset.")
        return {
            "sourceId": "commercial_gold",
            "dataset": "commercial_gold",
            "datasetVersion": metadata.get("dataset_version", "untracked"),
            "units": "kWh",
            "isLiveTelemetry": False,
        }

    def get_government_source_metadata(self) -> dict[str, Any]:
        """Describe the configured 2018 prepared grid history source."""
        actuals, _ = self._get_government_observations()
        return {
            "sourceId": "government_2018",
            "dataset": self.government_data.stem,
            # This prepared table has no source-version manifest in the repo.
            "datasetVersion": "untracked",
            "period": {
                "start": pd.Timestamp(actuals["target_timestamp"].min()).isoformat(),
                "end": pd.Timestamp(actuals["target_timestamp"].max()).isoformat(),
            },
            "sourceUnits": "kWh",
            "isLiveTelemetry": False,
        }

    def get_commercial_buildings(self) -> list[dict[str, Any]]:
        if self._commercial_entities is None:
            rows = self._query(
                self.commercial_data,
                """SELECT OBJECTID, any_value(\"id.grid.coarse\") AS grid_id,
                          any_value(GeneralUseType) AS use_type,
                          any_value(SpecificUseType) AS specific_use_type,
                          any_value(\"building.type\") AS building_type,
                          any_value(\"building.area.m2\") AS area,
                          any_value(\"FootprintArea.m2\") AS footprint_area,
                          any_value(EffectiveYearBuilt) AS year_built,
                          any_value(\"idf.kw\") AS idf_kw,
                          any_value(latitude) AS latitude,
                          any_value(longitude) AS longitude,
                          max(target_timestamp) AS last_timestamp
                   FROM read_parquet({path}) GROUP BY OBJECTID
                   ORDER BY OBJECTID LIMIT 100""",
            )
            self._commercial_entities = [
                {
                    "buildingId": str(int(row.OBJECTID)),
                    "siteId": f"Grid {int(row.grid_id)}",
                    "id.grid.coarse": int(row.grid_id),
                    "coarseGridId": int(row.grid_id),
                    "primarySpaceUsage": str(row.use_type or "Commercial"),
                    "specificSpaceUsage": row.specific_use_type,
                    "buildingType": row.building_type,
                    "sqm": float(row.area or 0),
                    "footprintAreaM2": (
                        float(row.footprint_area)
                        if pd.notna(row.footprint_area)
                        else None
                    ),
                    "yearBuilt": int(row.year_built or 0),
                    "idfKw": row.idf_kw,
                    "latitude": (
                        float(row.latitude) if pd.notna(row.latitude) else None
                    ),
                    "longitude": (
                        float(row.longitude) if pd.notna(row.longitude) else None
                    ),
                    # Gold provides historical target rows, not a current meter
                    # reading or a prediction generated at catalog time.
                    "recentDemandKwh": None,
                    "predictedDemandKwh": None,
                    "lastTimestamp": row.last_timestamp.isoformat(),
                }
                for row in rows.itertuples(index=False)
            ]
        return self._commercial_entities

    def get_commercial_building(self, building_id: str) -> dict[str, Any] | None:
        """Return metadata for a single commercial building from Gold or Silver datasets."""
        clean_id = str(building_id).strip()
        try:
            numeric_id = int(clean_id)
        except (ValueError, TypeError):
            return None

        # 1. Match from cached commercial entities
        for item in self.get_commercial_buildings():
            if item["buildingId"] == str(numeric_id):
                return item

        # 2. Query commercial_data (commercial_gold) directly for numeric_id
        try:
            rows = self._query(
                self.commercial_data,
                f"""SELECT OBJECTID, any_value("id.grid.coarse") AS grid_id,
                          any_value(GeneralUseType) AS use_type,
                          any_value(SpecificUseType) AS specific_use_type,
                          any_value("building.type") AS building_type,
                          any_value("building.area.m2") AS area,
                          any_value("FootprintArea.m2") AS footprint_area,
                          any_value(EffectiveYearBuilt) AS year_built,
                          any_value("idf.kw") AS idf_kw,
                          any_value(latitude) AS latitude,
                          any_value(longitude) AS longitude,
                          max(target_timestamp) AS last_timestamp
                   FROM read_parquet({{path}})
                   WHERE OBJECTID = {numeric_id}
                   GROUP BY OBJECTID""",
            )
            if not rows.empty:
                row = rows.iloc[0]
                return {
                    "buildingId": str(int(row.OBJECTID)),
                    "siteId": f"Grid {int(row.grid_id)}",
                    "id.grid.coarse": int(row.grid_id),
                    "coarseGridId": int(row.grid_id),
                    "primarySpaceUsage": str(row.use_type or "Commercial"),
                    "specificSpaceUsage": row.specific_use_type,
                    "buildingType": row.building_type,
                    "sqm": float(row.area or 0),
                    "footprintAreaM2": (
                        float(row.footprint_area)
                        if pd.notna(row.footprint_area)
                        else None
                    ),
                    "yearBuilt": int(row.year_built or 0),
                    "idfKw": row.idf_kw,
                    "latitude": (
                        float(row.latitude) if pd.notna(row.latitude) else None
                    ),
                    "longitude": (
                        float(row.longitude) if pd.notna(row.longitude) else None
                    ),
                    "recentDemandKwh": None,
                    "predictedDemandKwh": None,
                    "lastTimestamp": (
                        pd.Timestamp(row.last_timestamp).isoformat()
                        if pd.notna(row.last_timestamp)
                        else None
                    ),
                }
        except Exception:
            pass

        # 3. Fallback: query commercial_silver or sample dataset if available
        candidates = [
            Path("data/silver/commercial_silver.parquet"),
            Path("/data/silver/commercial_silver.parquet"),
            Path("data/sample/training_sample_50000.parquet"),
        ]
        for candidate_path in candidates:
            if candidate_path.is_file():
                try:
                    rows = self._query(
                        candidate_path,
                        f"""SELECT OBJECTID, any_value("id.grid.coarse") AS grid_id,
                                  any_value(GeneralUseType) AS use_type,
                                  any_value(SpecificUseType) AS specific_use_type,
                                  any_value("building.type") AS building_type,
                                  any_value("building.area.m2") AS area,
                                  any_value("FootprintArea.m2") AS footprint_area,
                                  any_value(EffectiveYearBuilt) AS year_built,
                                  any_value("idf.kw") AS idf_kw,
                                  any_value(latitude) AS latitude,
                                  any_value(longitude) AS longitude,
                                  max(timestamp) AS last_timestamp
                           FROM read_parquet({{path}})
                           WHERE OBJECTID = {numeric_id}
                           GROUP BY OBJECTID""",
                    )
                    if not rows.empty:
                        row = rows.iloc[0]
                        return {
                            "buildingId": str(int(row.OBJECTID)),
                            "siteId": f"Grid {int(row.grid_id)}",
                            "id.grid.coarse": int(row.grid_id),
                            "coarseGridId": int(row.grid_id),
                            "primarySpaceUsage": str(row.use_type or "Commercial"),
                            "specificSpaceUsage": row.specific_use_type,
                            "buildingType": row.building_type,
                            "sqm": float(row.area or 0),
                            "footprintAreaM2": (
                                float(row.footprint_area)
                                if pd.notna(row.footprint_area)
                                else None
                            ),
                            "yearBuilt": int(row.year_built or 0),
                            "idfKw": row.idf_kw,
                            "latitude": (
                                float(row.latitude) if pd.notna(row.latitude) else None
                            ),
                            "longitude": (
                                float(row.longitude) if pd.notna(row.longitude) else None
                            ),
                            "recentDemandKwh": None,
                            "predictedDemandKwh": None,
                            "lastTimestamp": (
                                pd.Timestamp(row.last_timestamp).isoformat()
                                if pd.notna(row.last_timestamp)
                                else None
                            ),
                        }
                except Exception:
                    continue

        return None

    @staticmethod
    def _commercial_range_days(time_range: str) -> int:
        ranges = {"1D": 1, "7D": 7, "1M": 30, "3M": 90, "1Y": 365}
        try:
            return ranges[time_range.upper()]
        except (AttributeError, KeyError) as exc:
            raise InvalidInputError(f"Unsupported commercial time range: {time_range}") from exc

    def get_commercial_historical_insights(
        self, time_range: str = "30D", entity_id: str | None = None
    ) -> dict[str, Any]:
        """Return historical daily rollups from commercial Gold observations."""
        selected_range = time_range.upper()
        range_days = {"30D": 30, "90D": 90, "1Y": 365}
        if selected_range not in {*range_days, "ALL"}:
            raise InvalidInputError(
                f"Unsupported commercial historical time range: {time_range}"
            )
        numeric_id = None
        commercial_alias_map = {
            "Panther_office_1": 466,
            "Bull_assembly_3": 50073,
            "Eagle_education_2": 126397,
            "Fox_retail_1": 136456,
            "Panther_parking_1": 151840,
        }
        if entity_id is not None:
            clean_eid = str(entity_id).strip()
            if clean_eid in commercial_alias_map:
                numeric_id = commercial_alias_map[clean_eid]
            elif clean_eid.lower() in ("all", "all buildings", "commercial", "none", ""):
                numeric_id = None
            else:
                try:
                    numeric_id = int(clean_eid)
                except (TypeError, ValueError) as exc:
                    raise InvalidInputError(
                        f"Invalid commercial building ID: {entity_id}"
                    ) from exc

        if numeric_id is None:
            period_filter = ""
            if selected_range != "ALL":
                latest = self._query(
                    self.commercial_data,
                    """SELECT max(target_timestamp) AS latest
                       FROM read_parquet({path})
                       WHERE forecast_horizon_hours = 1""",
                ).iloc[0]["latest"]
                if pd.isna(latest):
                    raise ResourceNotFoundError("No Commercial Gold history is available.")
                first_day = (
                    pd.Timestamp(latest).normalize()
                    - pd.Timedelta(days=range_days[selected_range] - 1)
                )
                period_filter = (
                    f"AND target_timestamp >= TIMESTAMP '{first_day:%Y-%m-%d %H:%M:%S}'"
                )
            daily = self._query(
                self.commercial_data,
                f"""WITH hourly AS (
                       SELECT target_timestamp, sum(target_energy) AS energy
                       FROM read_parquet({{path}})
                       WHERE forecast_horizon_hours = 1
                         AND target_energy IS NOT NULL {period_filter}
                       GROUP BY target_timestamp
                   )
                   SELECT CAST(target_timestamp AS DATE) AS day,
                          avg(energy) AS avgDemand,
                          sum(energy) AS totalConsumption,
                          max(energy) AS peakDemand,
                          arg_max(target_timestamp, energy) AS peakTimestamp
                   FROM hourly
                   GROUP BY CAST(target_timestamp AS DATE)
                   ORDER BY day""",
            )
            entity_count_query = self._query(
                self.commercial_data,
                f"""SELECT count(DISTINCT OBJECTID) AS entity_count
                    FROM read_parquet({{path}})
                    WHERE forecast_horizon_hours = 1
                      AND target_energy IS NOT NULL {period_filter}""",
            )
            entity_count = int(entity_count_query.iloc[0]["entity_count"])
        else:
            rows = self._query(
                self.commercial_data,
                f"""SELECT target_timestamp, target_energy
                    FROM read_parquet({{path}})
                    WHERE OBJECTID = {numeric_id}
                      AND forecast_horizon_hours = 1
                    ORDER BY target_timestamp""",
            )
            if rows.empty:
                raise ResourceNotFoundError(
                    f"No Commercial Gold history is available for building {numeric_id}."
                )
            rows["target_timestamp"] = pd.to_datetime(rows["target_timestamp"])
            rows["target_energy"] = pd.to_numeric(rows["target_energy"], errors="coerce")
            rows = rows.dropna(subset=["target_timestamp", "target_energy"])
            rows = rows.loc[np.isfinite(rows["target_energy"])]
            rows = rows.drop_duplicates("target_timestamp", keep="last")
            if rows.empty:
                raise ResourceNotFoundError(
                    f"No valid Commercial Gold history is available for building {numeric_id}."
                )
            latest_timestamp = pd.Timestamp(rows["target_timestamp"].max())
            if selected_range != "ALL":
                first_day = latest_timestamp.normalize() - pd.Timedelta(
                    days=range_days[selected_range] - 1
                )
                rows = rows.loc[rows["target_timestamp"] >= first_day]
            if rows.empty:
                raise ResourceNotFoundError(
                    f"No observations fall in the selected {time_range} range for building {numeric_id}."
                )
            rows["day"] = rows["target_timestamp"].dt.normalize()
            daily = (
                rows.groupby("day", as_index=False)
                .agg(
                    avgDemand=("target_energy", "mean"),
                    totalConsumption=("target_energy", "sum"),
                )
                .sort_values("day")
            )
            daily_peaks = rows.loc[
                rows.groupby("day")["target_energy"].idxmax(),
                ["day", "target_energy", "target_timestamp"],
            ].rename(
                columns={
                    "target_energy": "peakDemand",
                    "target_timestamp": "peakTimestamp",
                }
            )
            daily = daily.merge(daily_peaks, on="day", validate="one_to_one")
            entity_count = None
        if daily.empty:
            raise ResourceNotFoundError("No Commercial Gold observations are available for the selected period.")
        history_curve = [
            {
                "date": pd.Timestamp(row.day).strftime("%d %b"),
                "fullDate": pd.Timestamp(row.day).strftime("%d %b %Y"),
                "peakDemand": round(float(row.peakDemand), 3),
                "avgDemand": round(float(row.avgDemand), 3),
                "totalConsumption": round(float(row.totalConsumption), 3),
                "peakTime": pd.Timestamp(row.peakTimestamp).strftime("%I:%M %p"),
            }
            for row in daily.itertuples(index=False)
        ]
        daily_totals = daily["totalConsumption"]
        average_daily = float(daily_totals.mean())
        peak_row = daily.loc[daily["peakDemand"].idxmax()]
        return {
            "persona": "commercial",
            "entityId": str(numeric_id) if numeric_id is not None else None,
            **({"scope": "commercial_cohort", "entityCount": entity_count} if numeric_id is None else {}),
            "timeRange": selected_range,
            "daysReturned": len(history_curve),
            "startDate": pd.Timestamp(daily["day"].min()).strftime("%d %b %Y"),
            "endDate": pd.Timestamp(daily["day"].max()).strftime("%d %b %Y"),
            "avgDailyConsumption": round(average_daily, 3),
            "avgMonthlyConsumption": round(average_daily * 30, 3),
            "peakConsumption": round(float(peak_row["peakDemand"]), 3),
            "peakTimestamp": pd.Timestamp(peak_row["peakTimestamp"]).strftime(
                "%d %b %Y, %I:%M %p"
            ),
            "unit": "kWh",
            "historyCurve": history_curve,
        }

    def get_government_historical_insights(
        self, time_range: str = "30D", entity_id: str | None = None
    ) -> dict[str, Any]:
        """Return historical daily rollups for a selected grid or all grids."""
        selected_range = time_range.upper()
        range_days = {"30D": 30, "90D": 90, "1Y": 365}
        if selected_range not in {*range_days, "ALL"}:
            raise InvalidInputError(
                f"Unsupported Government historical time range: {time_range}"
            )
        actuals, _ = self._get_government_observations()
        selected_grid = None
        if entity_id is not None:
            clean_entity = str(entity_id).strip()
            # Normalize aggregate / system-wide aliases
            if clean_entity.lower() in (
                "bear & aggregate",
                "bear and aggregate",
                "aggregate",
                "all",
                "system-wide",
                "system",
                "all grids",
                "grid aggregate",
                "none",
                "",
            ):
                selected_grid = None
            elif clean_entity in {"Bear": 50, "Bull": 64, "Eagle": 65, "Fox": 51, "Panther": 63, "Peacock": 77}:
                selected_grid = {"Bear": 50, "Bull": 64, "Eagle": 65, "Fox": 51, "Panther": 63, "Peacock": 77}[clean_entity]
            else:
                try:
                    selected_grid = int(clean_entity)
                except (TypeError, ValueError) as exc:
                    raise InvalidInputError(
                        f"Invalid Government grid ID: {entity_id}"
                    ) from exc
            if selected_grid is not None:
                actuals = actuals.loc[actuals["grid_id"] == selected_grid]
                if actuals.empty:
                    raise ResourceNotFoundError(
                        f"Government grid {selected_grid} has no historical observations."
                    )
        latest_timestamp = pd.Timestamp(actuals["target_timestamp"].max())
        first_timestamp = (
            latest_timestamp.normalize()
            - pd.Timedelta(days=range_days[selected_range] - 1)
            if selected_range != "ALL"
            else pd.Timestamp(actuals["target_timestamp"].min()).normalize()
        )
        filtered = actuals.loc[
            actuals["target_timestamp"] >= first_timestamp
        ].copy()
        if filtered.empty:
            raise ResourceNotFoundError(
                f"No Government observations fall in the selected {time_range} range."
            )

        system_hourly = (
            filtered.groupby("target_timestamp", as_index=False)["target_energy"]
            .sum()
            .sort_values("target_timestamp")
        )
        system_hourly["day"] = system_hourly["target_timestamp"].dt.normalize()
        daily = (
            system_hourly.groupby("day", as_index=False)
            .agg(
                avgDemand=("target_energy", "mean"),
                totalConsumption=("target_energy", "sum"),
            )
            .sort_values("day")
        )
        daily_peaks = system_hourly.loc[
            system_hourly.groupby("day")["target_energy"].idxmax(),
            ["day", "target_energy", "target_timestamp"],
        ].rename(
            columns={
                "target_energy": "peakDemand",
                "target_timestamp": "peakTimestamp",
            }
        )
        daily = daily.merge(daily_peaks, on="day", validate="one_to_one")
        history_curve = [
            {
                "date": pd.Timestamp(row.day).strftime("%d %b"),
                "fullDate": pd.Timestamp(row.day).strftime("%d %b %Y"),
                "peakDemand": round(float(row.peakDemand) / 1000, 3),
                "avgDemand": round(float(row.avgDemand) / 1000, 3),
                "totalConsumption": round(float(row.totalConsumption) / 1000, 3),
                "peakTime": pd.Timestamp(row.peakTimestamp).strftime("%I:%M %p"),
            }
            for row in daily.itertuples(index=False)
        ]
        peak_row = daily.loc[daily["peakDemand"].idxmax()]
        average_daily_demand = float(daily["avgDemand"].mean()) / 1000
        return {
            "persona": "government",
            "entityId": str(selected_grid) if selected_grid is not None else "system-wide",
            "scope": "grid" if selected_grid is not None else "system-wide",
            "timeRange": selected_range,
            "daysReturned": len(history_curve),
            "startDate": pd.Timestamp(daily["day"].min()).strftime("%d %b %Y"),
            "endDate": pd.Timestamp(daily["day"].max()).strftime("%d %b %Y"),
            "avgDailyConsumption": round(average_daily_demand, 3),
            "avgMonthlyConsumption": round(average_daily_demand, 3),
            "peakConsumption": round(float(peak_row["peakDemand"]) / 1000, 3),
            "peakTimestamp": pd.Timestamp(peak_row["peakTimestamp"]).strftime(
                "%d %b %Y, %I:%M %p"
            ),
            "unit": "MW",
            "historyCurve": history_curve,
        }

    @staticmethod
    def _commercial_forecast_days(
        time_range: str, latest_actual: pd.Timestamp
    ) -> int:
        offsets = {
            "1D": pd.DateOffset(days=1),
            "7D": pd.DateOffset(days=3),
            "1M": pd.DateOffset(months=1),
            "3M": pd.DateOffset(months=3),
            "1Y": pd.DateOffset(years=1),
        }
        try:
            end_timestamp = latest_actual + offsets[time_range.upper()]
        except (AttributeError, KeyError) as exc:
            raise InvalidInputError(
                f"Unsupported commercial time range: {time_range}"
            ) from exc
        return int(
            np.ceil(
                (end_timestamp - latest_actual) / pd.Timedelta(days=1)
            )
        )

    @classmethod
    def _commercial_forecast_segments(
        cls, time_range: str, latest_actual: pd.Timestamp
    ) -> list[int]:
        selected_range = time_range.upper()
        forecast_days = cls._commercial_forecast_days(selected_range, latest_actual)
        if selected_range in {"1D", "7D", "1M"}:
            return [1] * forecast_days
        if selected_range == "3M":
            return [
                min(7, forecast_days - start_day)
                for start_day in range(0, forecast_days, 7)
            ]

        forecast_start = latest_actual.normalize() + pd.Timedelta(days=1)
        segments = []
        elapsed_days = 0
        month_index = 0
        while elapsed_days < forecast_days:
            month_start = forecast_start + pd.DateOffset(months=month_index)
            next_month = forecast_start + pd.DateOffset(months=month_index + 1)
            month_days = min(
                (next_month - month_start).days,
                forecast_days - elapsed_days,
            )
            segments.append(month_days)
            elapsed_days += month_days
            month_index += 1
        return segments

    @staticmethod
    def _commercial_forecast_description(time_range: str) -> str:
        descriptions = {
            "1D": "next 24 hours",
            "7D": "next 3 days",
            "1M": "next month · daily",
            "3M": "next 3 months · weekly",
            "1Y": "next year · monthly",
        }
        try:
            return descriptions[time_range.upper()]
        except (AttributeError, KeyError) as exc:
            raise InvalidInputError(
                f"Unsupported commercial time range: {time_range}"
            ) from exc

    @staticmethod
    def _commercial_curve_bucket(
        timestamp: pd.Timestamp, time_range: str
    ) -> pd.Timestamp:
        selected_range = time_range.upper()
        if selected_range == "1D":
            return timestamp
        if selected_range in {"7D", "1M"}:
            return timestamp.normalize()
        if selected_range == "3M":
            return timestamp.to_period("W-SUN").start_time.normalize()
        return timestamp.to_period("M").start_time.normalize()

    @staticmethod
    def _commercial_forecast_curve_bucket(
        timestamp: pd.Timestamp,
        time_range: str,
        latest_actual: pd.Timestamp,
    ) -> pd.Timestamp:
        selected_range = time_range.upper()
        if selected_range == "3M":
            forecast_start = latest_actual.normalize() + pd.Timedelta(days=1)
            week_index = (timestamp.normalize() - forecast_start).days // 7
            return forecast_start + pd.Timedelta(days=week_index * 7)
        if selected_range == "1Y":
            forecast_start = latest_actual.normalize() + pd.Timedelta(days=1)
            month_index = (
                (timestamp.year - forecast_start.year) * 12
                + timestamp.month
                - forecast_start.month
            )
            bucket_start = forecast_start + pd.DateOffset(months=month_index)
            if timestamp < bucket_start:
                bucket_start = forecast_start + pd.DateOffset(
                    months=month_index - 1
                )
            return bucket_start
        return TrainedForecastProvider._commercial_curve_bucket(
            timestamp, selected_range
        )

    @staticmethod
    def _commercial_time_label(timestamp: pd.Timestamp, hourly: bool) -> str:
        return timestamp.strftime("%d %b %Y %H:%M" if hourly else "%d %b %Y")

    def get_commercial_dashboard(
        self, building_id: str, time_range: str = "1D"
    ) -> dict[str, Any]:
        """Build the building dashboard from Gold observations and registered forecasts."""
        if building_id == "regional":
            return self.get_regional_commercial_dashboard(time_range)

        commercial_alias_map = {
            "Panther_office_1": 466,
            "Bull_assembly_3": 50073,
            "Eagle_education_2": 126397,
            "Fox_retail_1": 136456,
            "Panther_parking_1": 151840,
        }
        clean_bid = str(building_id).strip()
        if clean_bid in commercial_alias_map:
            numeric_id = commercial_alias_map[clean_bid]
        else:
            try:
                numeric_id = int(clean_bid)
            except (TypeError, ValueError) as exc:
                raise InvalidInputError(f"Invalid commercial building ID: {building_id}") from exc

        building = next(
            (item for item in self.get_commercial_buildings() if item["buildingId"] == str(numeric_id)),
            None,
        )
        if building is None:
            raise ResourceNotFoundError(
                f"Commercial building ID '{building_id}' is not in the current Gold model sample."
            )

        days = self._commercial_range_days(time_range)
        actuals = self._query(
            self.commercial_data,
            f"""SELECT target_timestamp, target_energy
                FROM read_parquet({{path}})
                WHERE OBJECTID = {numeric_id}
                  AND forecast_horizon_hours = 1
                ORDER BY target_timestamp""",
        )
        context = self._query(
            self.commercial_data,
            f"""SELECT * FROM read_parquet({{path}})
                WHERE OBJECTID = {numeric_id}
                  AND forecast_horizon_hours = 1
                ORDER BY target_timestamp DESC LIMIT 1""",
        )
        if actuals.empty or context.empty:
            raise ResourceNotFoundError(
                f"No historical Commercial observations are available for building {numeric_id}."
            )
        actuals["target_timestamp"] = pd.to_datetime(actuals["target_timestamp"])
        actuals["target_energy"] = pd.to_numeric(
            actuals["target_energy"], errors="coerce"
        )
        actuals = actuals.dropna(subset=["target_timestamp", "target_energy"])
        actuals = actuals.loc[np.isfinite(actuals["target_energy"])]
        actuals = actuals.drop_duplicates("target_timestamp", keep="last")
        if actuals.empty:
            raise ResourceNotFoundError(
                f"No valid Commercial observations are available for building {numeric_id}."
            )
        latest_actual = pd.Timestamp(actuals["target_timestamp"].max())
        forecast_segments = self._commercial_forecast_segments(
            time_range, latest_actual
        )
        forecast_days = sum(forecast_segments)
        try:
            cache_key = (
                str(numeric_id),
                self.commercial_data.stat().st_mtime_ns,
                tuple(forecast_segments),
            )
            forecast_rows = self._commercial_forecasts.get(cache_key)
            if forecast_rows is None:
                model, _ = self._load_mlflow_model("commercial")
                forecast_rows = self._recursive_commercial_forecast(
                    model,
                    context.iloc[0],
                    actuals,
                    latest_actual,
                    forecast_segments,
                )
                self._commercial_forecasts[cache_key] = forecast_rows
        except Exception as exc:
            raise ModelUnavailableError(
                f"Unable to load the Commercial forecast for building {numeric_id}: {exc}"
            ) from exc

        forecast_rows = forecast_rows.copy()
        forecast_rows["target_timestamp"] = pd.to_datetime(forecast_rows["target_timestamp"])
        start = latest_actual - pd.Timedelta(days=days)
        previous_start = start - pd.Timedelta(days=days)
        period_actuals = actuals.loc[actuals["target_timestamp"] > start]
        previous_actuals = actuals.loc[
            (actuals["target_timestamp"] > previous_start)
            & (actuals["target_timestamp"] <= start)
        ]
        if period_actuals.empty:
            raise ResourceNotFoundError(
                f"No observations fall in the selected {time_range} range for building {numeric_id}."
            )

        average = float(period_actuals["target_energy"].mean())
        previous_average = (
            float(previous_actuals["target_energy"].mean())
            if not previous_actuals.empty
            else average
        )
        delta_pct = (
            ((average - previous_average) / previous_average) * 100.0
            if previous_average > 0
            else 0.0
        )
        peak_row = period_actuals.loc[period_actuals["target_energy"].idxmax()]
        predicted_peak_row = forecast_rows.loc[forecast_rows["prediction"].idxmax()]
        hourly = time_range.upper() == "1D"

        curve_buckets: dict[pd.Timestamp, dict[str, Any]] = {}
        for row in period_actuals.itertuples(index=False):
            timestamp = pd.Timestamp(row.target_timestamp)
            bucket = self._commercial_curve_bucket(timestamp, time_range)
            data = curve_buckets.setdefault(
                bucket, {"actual_values": [], "predicted_values": []}
            )
            data["actual_values"].append(float(row.target_energy))

        for row in forecast_rows.itertuples(index=False):
            timestamp = pd.Timestamp(row.target_timestamp)
            bucket = self._commercial_forecast_curve_bucket(
                timestamp, time_range, latest_actual
            )
            data = curve_buckets.setdefault(
                bucket, {"actual_values": [], "predicted_values": []}
            )
            data["predicted_values"].append(float(row.prediction))

        curve = []
        for timestamp, values in sorted(curve_buckets.items()):
            actual_value = (
                float(np.mean(values["actual_values"]))
                if values["actual_values"]
                else None
            )
            predicted_value = (
                float(np.mean(values["predicted_values"]))
                if values["predicted_values"]
                else None
            )
            curve.append({
                "time": self._commercial_time_label(timestamp, hourly),
                "actualDemand": round(actual_value, 3) if actual_value is not None else None,
                "predictedDemand": round(predicted_value, 3) if predicted_value is not None else None,
                "fullDate": timestamp.strftime("%d %b %Y %H:%M" if hourly else "%d %b %Y"),
            })

        actual_callout = None
        predicted_callout = None
        demarcation_time = None
        if hourly:
            actual_timestamp = pd.Timestamp(period_actuals["target_timestamp"].max())
            predicted_peak_timestamp = pd.Timestamp(predicted_peak_row["target_timestamp"])
            actual_callout = {
                "time": self._commercial_time_label(actual_timestamp, True),
                "value": round(float(period_actuals.loc[period_actuals["target_timestamp"] == actual_timestamp, "target_energy"].iloc[-1]), 3),
                "timestamp": actual_timestamp.strftime("%d %b %Y, %I:%M %p"),
                "label": "Actual Demand",
            }
            predicted_callout = {
                "time": self._commercial_time_label(predicted_peak_timestamp, True),
                "value": round(float(predicted_peak_row["prediction"]), 3),
                "timestamp": predicted_peak_timestamp.strftime("%d %b %Y, %I:%M %p"),
                "label": "Predicted Peak · Next 24 Hours",
            }
            demarcation_time = actual_callout["time"]

        return {
            "tab": "building",
            "buildingId": str(numeric_id),
            "regionId": str(building.get("id.grid.coarse", "")),
            "timeRange": time_range.upper(),
            "avgDemand": round(average, 3),
            "avgDemandDeltaPct": round(delta_pct, 2),
            "prevPeriodAvgDemand": round(previous_average, 3),
            "peakDemand": round(float(peak_row["target_energy"]), 3),
            "peakTimestamp": pd.Timestamp(peak_row["target_timestamp"]).strftime("%d %b %Y, %I:%M %p"),
            "predictedPeak": round(float(predicted_peak_row["prediction"]), 3),
            "predictedPeakTimestamp": pd.Timestamp(predicted_peak_row["target_timestamp"]).strftime("%d %b %Y, %I:%M %p"),
            "predictedTotal": round(float(forecast_rows["prediction"].sum()), 3),
            "predictedTotalHorizon": (
                f"{self._commercial_forecast_description(time_range)} "
                f"ending {(latest_actual + pd.Timedelta(days=forecast_days)):%d %b %Y}"
            ),
            "unit": "kW",
            "totalUnit": "kWh",
            "actualCallout": actual_callout,
            "predictedCallout": predicted_callout,
            "demarcationTime": demarcation_time,
            "dataPeriod": (
                f"Gold history: {period_actuals['target_timestamp'].min():%d %b %Y} "
                f"– {latest_actual:%d %b %Y}; "
                f"{self._commercial_forecast_description(time_range)} forecast through "
                f"{(latest_actual + pd.Timedelta(days=forecast_days)):%d %b %Y}."
            ),
            "curve": curve,
        }

    def get_regional_commercial_dashboard(
        self, time_range: str = "1D"
    ) -> dict[str, Any]:
        """Build the regional dashboard from aggregated commercial Gold data."""
        days = self._commercial_range_days(time_range)
        actuals = self._query(
            self.commercial_data,
            """SELECT OBJECTID, target_timestamp, target_energy
               FROM read_parquet({path})
               WHERE forecast_horizon_hours = 1
               ORDER BY OBJECTID, target_timestamp""",
        )
        contexts = self._query(
            self.commercial_data,
            """SELECT * FROM read_parquet({path})
               WHERE forecast_horizon_hours = 1
               QUALIFY row_number() OVER (
                   PARTITION BY OBJECTID ORDER BY target_timestamp DESC
               ) = 1
               ORDER BY OBJECTID""",
        )
        if actuals.empty or contexts.empty:
            raise ResourceNotFoundError(
                "No historical Commercial observations are available for the regional dashboard."
            )

        actuals["target_timestamp"] = pd.to_datetime(actuals["target_timestamp"])
        actuals["target_energy"] = pd.to_numeric(
            actuals["target_energy"], errors="coerce"
        )
        actuals = actuals.dropna(subset=["target_timestamp", "target_energy"])
        actuals = actuals.loc[np.isfinite(actuals["target_energy"])]
        actuals = actuals.drop_duplicates(
            ["OBJECTID", "target_timestamp"], keep="last"
        )
        all_actuals = actuals.copy()
        contexts["target_timestamp"] = pd.to_datetime(contexts["target_timestamp"])
        latest_actual = pd.Timestamp(actuals["target_timestamp"].max())
        forecast_segments = self._commercial_forecast_segments(
            time_range, latest_actual
        )
        forecast_days = sum(forecast_segments)
        current_entities = set(
            actuals.loc[
                actuals["target_timestamp"] == latest_actual, "OBJECTID"
            ].tolist()
        )
        contexts = contexts.loc[contexts["OBJECTID"].isin(current_entities)]
        actuals = actuals.loc[actuals["OBJECTID"].isin(current_entities)]
        if contexts.empty or actuals.empty:
            raise ResourceNotFoundError(
                "No current Commercial entities are available for the regional forecast."
            )

        cache_key = (
            self.commercial_data.stat().st_mtime_ns,
            tuple(forecast_segments),
        )
        forecast_rows = self._regional_forecasts.get(cache_key)
        if forecast_rows is None:
            try:
                model, _ = self._load_mlflow_model("commercial")
                forecast_rows = self._recursive_commercial_regional_forecast(
                    model, contexts, actuals, latest_actual, forecast_segments
                )
                self._regional_forecasts[cache_key] = forecast_rows
            except Exception as exc:
                raise ModelUnavailableError(
                    f"Unable to load the regional Commercial forecast: {exc}"
                ) from exc

        forecast_rows = forecast_rows.copy()
        forecast_rows["target_timestamp"] = pd.to_datetime(
            forecast_rows["target_timestamp"]
        )
        actual_curve = (
            all_actuals.groupby("target_timestamp", as_index=False)["target_energy"]
            .sum()
            .sort_values("target_timestamp")
        )
        start = latest_actual - pd.Timedelta(days=days)
        previous_start = start - pd.Timedelta(days=days)
        period_actuals = actual_curve.loc[actual_curve["target_timestamp"] > start]
        previous_actuals = actual_curve.loc[
            (actual_curve["target_timestamp"] > previous_start)
            & (actual_curve["target_timestamp"] <= start)
        ]
        if period_actuals.empty:
            raise ResourceNotFoundError(
                f"No observations fall in the selected {time_range} range for the regional dashboard."
            )

        average = float(period_actuals["target_energy"].mean())
        previous_average = (
            float(previous_actuals["target_energy"].mean())
            if not previous_actuals.empty
            else average
        )
        delta_pct = (
            ((average - previous_average) / previous_average) * 100.0
            if previous_average > 0
            else 0.0
        )
        peak_row = period_actuals.loc[period_actuals["target_energy"].idxmax()]
        predicted_peak_row = forecast_rows.loc[forecast_rows["prediction"].idxmax()]
        hourly = time_range.upper() == "1D"

        curve_buckets: dict[pd.Timestamp, dict[str, list[float]]] = {}
        for row in period_actuals.itertuples(index=False):
            timestamp = pd.Timestamp(row.target_timestamp)
            bucket = self._commercial_curve_bucket(timestamp, time_range)
            curve_buckets.setdefault(
                bucket, {"actual_values": [], "predicted_values": []}
            )["actual_values"].append(float(row.target_energy))

        for row in forecast_rows.itertuples(index=False):
            timestamp = pd.Timestamp(row.target_timestamp)
            bucket = self._commercial_forecast_curve_bucket(
                timestamp, time_range, latest_actual
            )
            curve_buckets.setdefault(
                bucket, {"actual_values": [], "predicted_values": []}
            )["predicted_values"].append(float(row.prediction))

        curve = []
        for timestamp, values in sorted(curve_buckets.items()):
            actual_value = (
                float(np.mean(values["actual_values"]))
                if values["actual_values"]
                else None
            )
            predicted_value = (
                float(np.mean(values["predicted_values"]))
                if values["predicted_values"]
                else None
            )
            curve.append(
                {
                    "time": self._commercial_time_label(timestamp, hourly),
                    "actualDemand": (
                        round(actual_value, 3) if actual_value is not None else None
                    ),
                    "predictedDemand": (
                        round(predicted_value, 3)
                        if predicted_value is not None
                        else None
                    ),
                    "fullDate": timestamp.strftime(
                        "%d %b %Y %H:%M" if hourly else "%d %b %Y"
                    ),
                }
            )

        return {
            "tab": "regional",
            "buildingId": "regional",
            "regionId": "all",
            "timeRange": time_range.upper(),
            "avgDemand": round(average, 3),
            "avgDemandDeltaPct": round(delta_pct, 2),
            "prevPeriodAvgDemand": round(previous_average, 3),
            "peakDemand": round(float(peak_row["target_energy"]), 3),
            "peakTimestamp": pd.Timestamp(peak_row["target_timestamp"]).strftime(
                "%d %b %Y, %I:%M %p"
            ),
            "predictedPeak": round(float(predicted_peak_row["prediction"]), 3),
            "predictedPeakTimestamp": pd.Timestamp(
                predicted_peak_row["target_timestamp"]
            ).strftime("%d %b %Y, %I:%M %p"),
            "predictedTotal": round(float(forecast_rows["prediction"].sum()), 3),
            "predictedTotalHorizon": (
                f"{self._commercial_forecast_description(time_range)} "
                f"ending {(latest_actual + pd.Timedelta(days=forecast_days)):%d %b %Y}"
            ),
            "unit": "kW",
            "totalUnit": "kWh",
            "dataPeriod": (
                f"Gold history: {period_actuals['target_timestamp'].min():%d %b %Y} "
                f"– {latest_actual:%d %b %Y}; "
                f"{self._commercial_forecast_description(time_range)} regional forecast through "
                f"{(latest_actual + pd.Timedelta(days=forecast_days)):%d %b %Y}."
            ),
            "curve": curve,
        }

    @staticmethod
    def _recursive_commercial_regional_forecast(
        model: Any,
        contexts: pd.DataFrame,
        actuals: pd.DataFrame,
        latest_actual: pd.Timestamp,
        forecast_segments: list[int],
    ) -> pd.DataFrame:
        """Forecast one daily profile per interval and carry it across its days."""
        static_columns = FEATURE_COLUMNS[:10]
        actuals_by_entity = {
            entity_id: group.sort_values("target_timestamp")
            for entity_id, group in actuals.groupby("OBJECTID", sort=True)
        }
        states = []
        for _, context in contexts.sort_values("OBJECTID").iterrows():
            entity_id = context["OBJECTID"]
            history = deque(
                (
                    pd.Timestamp(row.target_timestamp),
                    float(row.target_energy),
                )
                for row in actuals_by_entity[entity_id].itertuples(index=False)
            )
            states.append(
                {
                    "history": history,
                    "static_features": {
                        column: context[column] for column in static_columns
                    },
                }
            )

        forecast_rows: list[dict[str, Any]] = []
        day_index = 0
        for segment_days in forecast_segments:
            origin = latest_actual + pd.Timedelta(days=day_index)
            feature_rows = []
            for state in states:
                history = state["history"]
                oldest_needed = origin - pd.Timedelta(hours=720)
                while history and history[0][0] < oldest_needed:
                    history.popleft()
                history_by_timestamp = dict(history)
                rolling_values = {
                    window: [
                        value
                        for timestamp, value in history
                        if timestamp >= origin - pd.Timedelta(hours=window)
                    ]
                    for window in (24, 168, 720)
                }
                dynamic_features: dict[str, float] = {
                    "energy_at_origin": history_by_timestamp.get(origin, np.nan),
                    "energy_lag_1": history_by_timestamp.get(
                        origin - pd.Timedelta(hours=1), np.nan
                    ),
                    "energy_lag_24": history_by_timestamp.get(
                        origin - pd.Timedelta(hours=24), np.nan
                    ),
                    "energy_lag_168": history_by_timestamp.get(
                        origin - pd.Timedelta(hours=168), np.nan
                    ),
                    "energy_lag_336": history_by_timestamp.get(
                        origin - pd.Timedelta(hours=336), np.nan
                    ),
                    "energy_lag_720": history_by_timestamp.get(
                        origin - pd.Timedelta(hours=720), np.nan
                    ),
                }
                for window, values in rolling_values.items():
                    period = "24h" if window == 24 else "7d" if window == 168 else "30d"
                    dynamic_features[f"energy_rolling_mean_{period}"] = (
                        float(np.mean(values)) if values else np.nan
                    )
                    dynamic_features[f"energy_rolling_std_{period}"] = (
                        float(np.std(values, ddof=1)) if len(values) > 1 else np.nan
                    )
                    dynamic_features[f"energy_observation_count_{period}"] = len(
                        values
                    )

                for horizon in range(1, 25):
                    target_timestamp = origin + pd.Timedelta(hours=horizon)
                    day_of_year = target_timestamp.dayofyear
                    day_of_week = (target_timestamp.weekday() + 1) % 7
                    feature_rows.append(
                        {
                            **state["static_features"],
                            **dynamic_features,
                            "forecast_horizon_hours": horizon,
                            "target_hour": target_timestamp.hour,
                            "target_day_of_week": day_of_week,
                            "target_month": target_timestamp.month,
                            "target_is_weekend": int(day_of_week in (0, 6)),
                            "target_day_of_month": target_timestamp.day,
                            "target_day_of_year": day_of_year,
                            "target_hour_sin": np.sin(
                                2 * np.pi * target_timestamp.hour / 24
                            ),
                            "target_hour_cos": np.cos(
                                2 * np.pi * target_timestamp.hour / 24
                            ),
                            "target_day_of_year_sin": np.sin(
                                2 * np.pi * (day_of_year - 1) / 365.25
                            ),
                            "target_day_of_year_cos": np.cos(
                                2 * np.pi * (day_of_year - 1) / 365.25
                            ),
                        }
                    )

            predictions = np.asarray(
                model.predict(
                    prepare_features(
                        pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)
                    )
                ),
                dtype=float,
            ).reshape(-1)
            if len(predictions) != len(states) * 24 or not np.isfinite(
                predictions
            ).all():
                raise ValueError("The Commercial model returned invalid regional forecast values.")
            predictions = np.maximum(predictions, 0.0).reshape(len(states), 24)
            for segment_day in range(segment_days):
                for state, entity_predictions in zip(
                    states, predictions, strict=True
                ):
                    history = state["history"]
                    for horizon, prediction in enumerate(
                        entity_predictions, start=1
                    ):
                        target_timestamp = origin + pd.Timedelta(
                            days=segment_day, hours=horizon
                        )
                        history.append((target_timestamp, float(prediction)))
                for horizon in range(24):
                    forecast_rows.append(
                        {
                            "forecast_day": day_index + segment_day,
                            "target_timestamp": origin
                            + pd.Timedelta(
                                days=segment_day, hours=horizon + 1
                            ),
                            "prediction": float(predictions[:, horizon].sum()),
                        }
                    )
            day_index += segment_days
        return pd.DataFrame(forecast_rows)

    @staticmethod
    def _recursive_commercial_forecast(
        model: Any,
        context: pd.Series,
        actuals: pd.DataFrame,
        latest_actual: pd.Timestamp,
        forecast_segments: list[int],
    ) -> pd.DataFrame:
        """Forecast one daily profile per interval and carry it across its days."""
        history: deque[tuple[pd.Timestamp, float]] = deque(
            (pd.Timestamp(row.target_timestamp), float(row.target_energy))
            for row in actuals.itertuples(index=False)
        )
        static_columns = FEATURE_COLUMNS[:10]
        static_features = {column: context[column] for column in static_columns}
        forecast_rows: list[dict[str, Any]] = []

        day_index = 0
        for segment_days in forecast_segments:
            origin = latest_actual + pd.Timedelta(days=day_index)
            oldest_needed = origin - pd.Timedelta(hours=720)
            while history and history[0][0] < oldest_needed:
                history.popleft()
            history_by_timestamp = dict(history)
            rolling_values: dict[int, list[float]] = {
                window: [
                    value
                    for timestamp, value in history
                    if timestamp >= origin - pd.Timedelta(hours=window)
                ]
                for window in (24, 168, 720)
            }

            dynamic_features: dict[str, float] = {
                "energy_at_origin": history_by_timestamp.get(origin, np.nan),
                "energy_lag_1": history_by_timestamp.get(
                    origin - pd.Timedelta(hours=1), np.nan
                ),
                "energy_lag_24": history_by_timestamp.get(
                    origin - pd.Timedelta(hours=24), np.nan
                ),
                "energy_lag_168": history_by_timestamp.get(
                    origin - pd.Timedelta(hours=168), np.nan
                ),
                "energy_lag_336": history_by_timestamp.get(
                    origin - pd.Timedelta(hours=336), np.nan
                ),
                "energy_lag_720": history_by_timestamp.get(
                    origin - pd.Timedelta(hours=720), np.nan
                ),
            }
            for window, values in rolling_values.items():
                if window == 24:
                    dynamic_features["energy_rolling_mean_24h"] = (
                        float(np.mean(values)) if values else np.nan
                    )
                    dynamic_features["energy_rolling_std_24h"] = (
                        float(np.std(values, ddof=1)) if len(values) > 1 else np.nan
                    )
                    dynamic_features["energy_observation_count_24h"] = len(values)
                else:
                    period = "7d" if window == 168 else "30d"
                    dynamic_features[f"energy_rolling_mean_{period}"] = (
                        float(np.mean(values)) if values else np.nan
                    )
                    dynamic_features[f"energy_rolling_std_{period}"] = (
                        float(np.std(values, ddof=1)) if len(values) > 1 else np.nan
                    )
                    dynamic_features[f"energy_observation_count_{period}"] = len(values)

            feature_rows = []
            for horizon in range(1, 25):
                target_timestamp = origin + pd.Timedelta(hours=horizon)
                day_of_year = target_timestamp.dayofyear
                day_of_week = (target_timestamp.weekday() + 1) % 7
                row = {
                    **static_features,
                    **dynamic_features,
                    "forecast_horizon_hours": horizon,
                    "target_hour": target_timestamp.hour,
                    "target_day_of_week": day_of_week,
                    "target_month": target_timestamp.month,
                    "target_is_weekend": int(day_of_week in (0, 6)),
                    "target_day_of_month": target_timestamp.day,
                    "target_day_of_year": day_of_year,
                    "target_hour_sin": np.sin(2 * np.pi * target_timestamp.hour / 24),
                    "target_hour_cos": np.cos(2 * np.pi * target_timestamp.hour / 24),
                    "target_day_of_year_sin": np.sin(
                        2 * np.pi * (day_of_year - 1) / 365.25
                    ),
                    "target_day_of_year_cos": np.cos(
                        2 * np.pi * (day_of_year - 1) / 365.25
                    ),
                }
                feature_rows.append(row)

            predictions = np.asarray(
                model.predict(
                    prepare_features(
                        pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)
                    )
                ),
                dtype=float,
            ).reshape(-1)
            if len(predictions) != 24 or not np.isfinite(predictions).all():
                raise ValueError("The Commercial model returned invalid forecast values.")
            predictions = np.maximum(predictions, 0.0)
            for segment_day in range(segment_days):
                for horizon, prediction in enumerate(predictions, start=1):
                    target_timestamp = origin + pd.Timedelta(
                        days=segment_day, hours=horizon
                    )
                    forecast_rows.append(
                        {
                            "forecast_day": day_index + segment_day,
                            "target_timestamp": target_timestamp,
                            "prediction": float(prediction),
                        }
                    )
                    history.append((target_timestamp, float(prediction)))
            day_index += segment_days
        return pd.DataFrame(forecast_rows)

    def get_regional_sites(self) -> list[dict[str, Any]]:
        if self._regional_entities is None:
            rows = self._query(
                self.government_data,
                """WITH totals AS (
                       SELECT \"id.grid.coarse\" AS grid_id,
                              sum(target_energy) AS total_kwh,
                              avg(target_energy) AS average_kwh,
                              max(target_energy) AS peak_kwh,
                              max(building_count) AS building_count,
                              max(target_timestamp) AS last_timestamp
                       FROM read_parquet({path}) GROUP BY \"id.grid.coarse\"
                   )
                   SELECT *, 100.0 * total_kwh / sum(total_kwh) OVER () AS share_pct
                   FROM totals ORDER BY grid_id LIMIT 100""",
            )
            self._regional_entities = [
                {
                    "siteId": str(int(row.grid_id)),
                    "buildingCount": int(row.building_count or 0),
                    "totalDemandKwh": float(row.total_kwh or 0),
                    "predictedDemandKwh": None,
                    "peakHourKwh": float(row.peak_kwh or 0),
                    "shareOfTotalPct": round(float(row.share_pct or 0), 3),
                    "season": "Historical 2018",
                    "name": f"Grid {int(row.grid_id)}",
                    "region": "Historical grid dataset",
                    "averageDemandMw": float(row.average_kwh or 0) / 1000,
                    "peakDemandMw": float(row.peak_kwh or 0) / 1000,
                    "lastTimestamp": row.last_timestamp.isoformat(),
                }
                for row in rows.itertuples(index=False)
            ]
        return self._regional_entities

    def _latest_origin(
        self, path: Path, id_column: str, entity_id: str, horizon_count: int
    ) -> pd.Timestamp:
        rows = self._query(
            path,
            f"""SELECT forecast_origin_timestamp,
                       count(DISTINCT CASE
                           WHEN forecast_horizon_hours BETWEEN 1 AND {int(horizon_count)}
                           THEN forecast_horizon_hours
                       END) AS steps
                FROM read_parquet({{path}})
                WHERE {id_column} = {int(entity_id)}
                  AND target_timestamp >= TIMESTAMP '2018-12-01'
                GROUP BY forecast_origin_timestamp
                HAVING steps > 0
                ORDER BY steps DESC, forecast_origin_timestamp DESC LIMIT 1""",
        )
        if rows.empty:
            raise ResourceNotFoundError(
                f"No commercial forecast data is available for entity {entity_id}."
            )
        return pd.Timestamp(rows.iloc[0]["forecast_origin_timestamp"])

    def _horizon_rows(
        self, path: Path, id_column: str, entity_id: str, horizon_count: int
    ) -> pd.DataFrame:
        origin = self._latest_origin(path, id_column, entity_id, horizon_count)
        return self._query(
            path,
            f"""SELECT * FROM read_parquet({{path}})
                WHERE {id_column} = {int(entity_id)}
                  AND forecast_origin_timestamp = TIMESTAMP '{origin:%Y-%m-%d %H:%M:%S}'
                  AND forecast_horizon_hours BETWEEN 1 AND {int(horizon_count)}
                ORDER BY forecast_horizon_hours LIMIT {int(horizon_count)}""",
        )

    def _load_commercial_bundle(self) -> dict[str, Any]:
        if self._commercial_bundle is None:
            if not self.commercial_model_path.is_file():
                raise FileNotFoundError(f"Commercial model is missing: {self.commercial_model_path}")
            self._commercial_bundle = joblib.load(self.commercial_model_path)
        return self._commercial_bundle

    def _load_government_bundle(self) -> dict[str, Any]:
        if self._government_bundle is None:
            if not self.government_model_path.is_file():
                raise ModelUnavailableError(
                    f"Government model is missing: {self.government_model_path}"
                )
            try:
                self._government_bundle = joblib.load(self.government_model_path)
            except Exception as exc:
                raise ModelUnavailableError(
                    f"Unable to load the local Government forecast model: {exc}"
                ) from exc
        return self._government_bundle

    @staticmethod
    def _government_range_days(time_range: str) -> int:
        ranges = {"1D": 1, "7D": 7, "1M": 30, "3M": 90, "1Y": 365}
        try:
            return ranges[time_range.upper()]
        except (AttributeError, KeyError) as exc:
            raise InvalidInputError(
                f"Unsupported Government time range: {time_range}"
            ) from exc

    def _get_government_observations(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        if self._government_actuals is None or self._government_contexts is None:
            actuals = self._query(
                self.government_data,
                """SELECT "id.grid.coarse" AS grid_id, target_timestamp, target_energy
                   FROM read_parquet({path})
                   WHERE forecast_horizon_hours = 1
                   ORDER BY "id.grid.coarse", target_timestamp""",
            )
            contexts = self._query(
                self.government_data,
                """SELECT *
                   FROM read_parquet({path})
                   WHERE forecast_horizon_hours = 1
                   QUALIFY row_number() OVER (
                       PARTITION BY "id.grid.coarse"
                       ORDER BY target_timestamp DESC
                   ) = 1""",
            )
            if actuals.empty or contexts.empty:
                raise ResourceNotFoundError(
                    "No historical Government grid observations are available."
                )
            actuals["grid_id"] = pd.to_numeric(actuals["grid_id"], errors="coerce")
            actuals["target_timestamp"] = pd.to_datetime(
                actuals["target_timestamp"]
            )
            actuals["target_energy"] = pd.to_numeric(
                actuals["target_energy"], errors="coerce"
            )
            actuals = actuals.dropna(
                subset=["grid_id", "target_timestamp", "target_energy"]
            )
            actuals = actuals.loc[np.isfinite(actuals["target_energy"])]
            actuals = actuals.drop_duplicates(
                ["grid_id", "target_timestamp"], keep="last"
            )
            contexts["id.grid.coarse"] = pd.to_numeric(
                contexts["id.grid.coarse"], errors="coerce"
            )
            contexts["target_timestamp"] = pd.to_datetime(
                contexts["target_timestamp"]
            )
            contexts = contexts.dropna(
                subset=["id.grid.coarse", "target_timestamp"]
            )
            if actuals.empty or contexts.empty:
                raise ResourceNotFoundError(
                    "No valid historical Government grid observations are available."
                )
            self._government_actuals = actuals.sort_values(
                ["grid_id", "target_timestamp"]
            ).reset_index(drop=True)
            self._government_contexts = contexts.reset_index(drop=True)
        return self._government_actuals, self._government_contexts

    def _predict_government_24h(self) -> pd.DataFrame:
        if self._government_forecasts is not None:
            return self._government_forecasts

        actuals, contexts = self._get_government_observations()
        bundle = self._load_government_bundle()
        features = bundle.get("features")
        routing_frame = bundle.get("routing")
        if (
            not isinstance(features, list)
            or not all(isinstance(feature, str) for feature in features)
            or not isinstance(routing_frame, pd.DataFrame)
            or not {"grid_id", "selected_model"}.issubset(routing_frame.columns)
        ):
            raise ModelUnavailableError(
                "The local Government model artifact has an invalid feature or routing contract."
            )
        routing = dict(
            zip(
                routing_frame["grid_id"],
                routing_frame["selected_model"],
                strict=True,
            )
        )
        model_by_name = {
            "original": bundle.get("original_model"),
            "log": bundle.get("log_model"),
        }
        if not all(model_by_name.values()):
            raise ModelUnavailableError(
                "The local Government model artifact is missing a forecast model."
            )

        dynamic_feature_names = {
            "forecast_horizon_hours",
            "energy_at_origin",
            "energy_lag_1h",
            "energy_lag_24h",
            "energy_lag_168h",
            "energy_lag_336h",
            "energy_lag_720h",
            "energy_mean_24h",
            "energy_std_24h",
            "energy_count_24h",
            "energy_mean_7d",
            "energy_std_7d",
            "energy_count_7d",
            "energy_mean_30d",
            "energy_std_30d",
            "energy_count_30d",
            "target_hour",
            "target_year",
            "target_day_of_week",
            "target_month",
            "target_is_weekend",
            "target_day_of_month",
            "target_day_of_year",
        }
        dynamic_feature_names.update(
            {
                "target_hour_sin",
                "target_hour_cos",
                "target_day_of_year_sin",
                "target_day_of_year_cos",
            }
        )
        predictions: list[dict[str, Any]] = []
        for _, context in contexts.iterrows():
            grid_id = int(context["id.grid.coarse"])
            selected_model = routing.get(grid_id)
            if selected_model not in model_by_name:
                raise ModelUnavailableError(
                    f"The Government model has no valid route for grid {grid_id}."
                )
            grid_history = actuals.loc[actuals["grid_id"] == grid_id]
            if grid_history.empty:
                continue
            history = grid_history.set_index("target_timestamp")["target_energy"]
            origin = pd.Timestamp(history.index.max())
            history_values = history.loc[
                history.index >= origin - pd.Timedelta(days=30)
            ]
            static_features = {
                name: context[name]
                for name in features
                if name not in dynamic_feature_names
                and name in context.index
            }
            dynamic_features: dict[str, float] = {
                "energy_at_origin": float(history.loc[origin]),
            }
            for lag, feature_name in (
                (1, "energy_lag_1h"),
                (24, "energy_lag_24h"),
                (168, "energy_lag_168h"),
                (336, "energy_lag_336h"),
                (720, "energy_lag_720h"),
            ):
                timestamp = origin - pd.Timedelta(hours=lag)
                dynamic_features[feature_name] = (
                    float(history.loc[timestamp])
                    if timestamp in history.index
                    else np.nan
                )
            for hours, suffix in ((24, "24h"), (168, "7d"), (720, "30d")):
                values = history_values.loc[
                    history_values.index >= origin - pd.Timedelta(hours=hours)
                ].to_numpy(dtype=float)
                dynamic_features[f"energy_mean_{suffix}"] = (
                    float(np.mean(values)) if len(values) else np.nan
                )
                dynamic_features[f"energy_std_{suffix}"] = (
                    float(np.std(values, ddof=1)) if len(values) > 1 else np.nan
                )
                dynamic_features[f"energy_count_{suffix}"] = len(values)

            feature_rows = []
            for horizon in range(1, 25):
                target_timestamp = origin + pd.Timedelta(hours=horizon)
                day_of_year = target_timestamp.dayofyear
                day_of_week = (target_timestamp.weekday() + 1) % 7
                feature_rows.append(
                    {
                        **static_features,
                        **dynamic_features,
                        "forecast_horizon_hours": horizon,
                        "target_hour": target_timestamp.hour,
                        "target_year": target_timestamp.year,
                        "target_day_of_week": day_of_week,
                        "target_month": target_timestamp.month,
                        "target_is_weekend": int(day_of_week in (0, 6)),
                        "target_day_of_month": target_timestamp.day,
                        "target_day_of_year": day_of_year,
                        "target_hour_sin": np.sin(
                            2 * np.pi * target_timestamp.hour / 24
                        ),
                        "target_hour_cos": np.cos(
                            2 * np.pi * target_timestamp.hour / 24
                        ),
                        "target_day_of_year_sin": np.sin(
                            2 * np.pi * (day_of_year - 1) / 365.25
                        ),
                        "target_day_of_year_cos": np.cos(
                            2 * np.pi * (day_of_year - 1) / 365.25
                        ),
                    }
                )
            matrix = (
                pd.DataFrame(feature_rows, columns=features)
                .astype(np.float32)
                .replace([np.inf, -np.inf], np.nan)
            )
            raw_predictions = np.asarray(
                model_by_name[selected_model].predict(matrix), dtype=float
            ).reshape(-1)
            if len(raw_predictions) != 24 or not np.isfinite(raw_predictions).all():
                raise ModelUnavailableError(
                    f"The Government model returned invalid predictions for grid {grid_id}."
                )
            if selected_model == "log":
                raw_predictions = np.expm1(np.maximum(raw_predictions, 0))
            for horizon, prediction in enumerate(raw_predictions, start=1):
                predictions.append(
                    {
                        "grid_id": grid_id,
                        "target_timestamp": origin
                        + pd.Timedelta(hours=horizon),
                        "prediction": float(max(0.0, prediction)),
                    }
                )

        if not predictions:
            raise ResourceNotFoundError(
                "No Government grid forecasts could be produced from the available history."
            )
        self._government_forecasts = pd.DataFrame(predictions)
        return self._government_forecasts

    @staticmethod
    def _government_bucket_frequency(time_range: str) -> str:
        return {
            "1D": "h",
            "7D": "D",
            "1M": "D",
            "3M": "W-MON",
            "1Y": "MS",
        }[time_range]

    @staticmethod
    def _government_delta(
        current: pd.DataFrame, previous: pd.DataFrame
    ) -> tuple[float | None, float | None]:
        current_average = (
            float(current["target_energy"].mean()) if not current.empty else 0.0
        )
        if previous.empty:
            return None, None
        previous_average = float(previous["target_energy"].mean())
        delta = (
            (current_average - previous_average) / previous_average * 100
            if previous_average
            else None
        )
        return delta, previous_average / 1000

    def get_government_regions(
        self, time_range: str = "1D"
    ) -> list[dict[str, Any]]:
        range_days = self._government_range_days(time_range)
        actuals, contexts = self._get_government_observations()
        forecasts = self._predict_government_24h()
        latest = pd.Timestamp(actuals["target_timestamp"].max())
        period_start = latest.normalize() - pd.Timedelta(days=range_days - 1)
        previous_start = period_start - pd.Timedelta(days=range_days)
        previous_end = period_start - pd.Timedelta(hours=1)
        palette = ("#2563EB", "#10B981", "#7C3AED", "#D97706", "#0891B2")
        items = []
        for index, (_, context) in enumerate(
            contexts.sort_values("id.grid.coarse").iterrows()
        ):
            grid_id = int(context["id.grid.coarse"])
            history = actuals.loc[actuals["grid_id"] == grid_id]
            selected = history.loc[
                (history["target_timestamp"] >= period_start)
                & (history["target_timestamp"] <= latest)
            ]
            previous = history.loc[
                (history["target_timestamp"] >= previous_start)
                & (history["target_timestamp"] <= previous_end)
            ]
            forecast = forecasts.loc[forecasts["grid_id"] == grid_id]
            delta, _ = self._government_delta(selected, previous)
            daily_sparkline = (
                selected.assign(day=selected["target_timestamp"].dt.normalize())
                .groupby("day")["target_energy"]
                .mean()
                .tail(4)
                .div(1000)
                .round(3)
                .tolist()
            )
            items.append(
                {
                    "id": str(grid_id),
                    "name": f"Grid {grid_id}",
                    "currentDemand": round(float(selected["target_energy"].mean()) / 1000, 3),
                    "predictedDemand": round(float(forecast["prediction"].mean()) / 1000, 3),
                    "deltaPct": round(delta, 1) if delta is not None else None,
                    "isIncreaseNegative": True,
                    "pinColor": palette[index % len(palette)],
                    "sparkline": daily_sparkline,
                    "unit": "MW",
                }
            )
        return items

    def get_government_dashboard(
        self,
        view_type: str = "overall",
        region_id: str | None = None,
        time_range: str = "1D",
    ) -> dict[str, Any]:
        selected_range = time_range.upper()
        range_days = self._government_range_days(selected_range)
        if view_type not in {"overall", "region"}:
            raise InvalidInputError(f"Unsupported Government view type: {view_type}")
        if view_type == "region":
            clean_region = str(region_id).strip() if region_id is not None else ""
            if clean_region.lower() in ("bear & aggregate", "bear and aggregate", "aggregate", "all", "system-wide", "system", "none", ""):
                selected_grid = None
                view_type = "overall"
            elif clean_region in {"Bear": 50, "Bull": 64, "Eagle": 65, "Fox": 51, "Panther": 63, "Peacock": 77}:
                selected_grid = {"Bear": 50, "Bull": 64, "Eagle": 65, "Fox": 51, "Panther": 63, "Peacock": 77}[clean_region]
            else:
                try:
                    selected_grid = int(clean_region) if clean_region else None
                except (TypeError, ValueError) as exc:
                    raise InvalidInputError(f"Invalid Government grid ID: {region_id}") from exc
                if selected_grid is None:
                    raise InvalidInputError("A Government grid ID is required for regional view.")
        else:
            selected_grid = None

        actuals, _ = self._get_government_observations()
        forecasts = self._predict_government_24h()
        latest = pd.Timestamp(actuals["target_timestamp"].max())
        period_start = latest.normalize() - pd.Timedelta(days=range_days - 1)
        selected_actuals = actuals.loc[
            (actuals["target_timestamp"] >= period_start)
            & (actuals["target_timestamp"] <= latest)
        ]
        selected_forecasts = forecasts.loc[
            forecasts["target_timestamp"] > latest
        ]
        if selected_grid is not None:
            selected_actuals = selected_actuals.loc[
                selected_actuals["grid_id"] == selected_grid
            ]
            selected_forecasts = selected_forecasts.loc[
                selected_forecasts["grid_id"] == selected_grid
            ]
            if selected_actuals.empty:
                raise ResourceNotFoundError(
                    f"Government grid {selected_grid} has no historical observations."
                )
            region_name = f"Grid {selected_grid}"
        else:
            region_name = "System-Wide"
            selected_actuals = (
                selected_actuals.groupby("target_timestamp", as_index=False)[
                    "target_energy"
                ]
                .sum()
            )
            selected_forecasts = (
                selected_forecasts.groupby("target_timestamp", as_index=False)[
                    "prediction"
                ]
                .sum()
            )

        previous_start = period_start - pd.Timedelta(days=range_days)
        previous_end = period_start - pd.Timedelta(hours=1)
        previous = actuals.loc[
            (actuals["target_timestamp"] >= previous_start)
            & (actuals["target_timestamp"] <= previous_end)
        ]
        if selected_grid is not None:
            previous = previous.loc[previous["grid_id"] == selected_grid]
        else:
            previous = previous.groupby("target_timestamp", as_index=False)[
                "target_energy"
            ].sum()
        delta, previous_average = self._government_delta(
            selected_actuals, previous
        )
        peak_row = selected_actuals.loc[
            selected_actuals["target_energy"].idxmax()
        ]
        predicted_peak_row = selected_forecasts.loc[
            selected_forecasts["prediction"].idxmax()
        ]
        frequency = self._government_bucket_frequency(selected_range)
        actual_buckets = (
            selected_actuals.set_index("target_timestamp")["target_energy"]
            .resample(frequency)
            .mean()
            .dropna()
        )
        predicted_buckets = (
            selected_forecasts.set_index("target_timestamp")["prediction"]
            .resample(frequency)
            .mean()
            .dropna()
        )
        if selected_range == "1D":
            first_bucket = period_start.floor("h")
            last_bucket = latest.floor("h")
        elif selected_range == "3M":
            first_bucket = period_start.to_period("W-MON").end_time.normalize()
            last_bucket = latest.to_period("W-MON").end_time.normalize()
        elif selected_range == "1Y":
            first_bucket = period_start.to_period("M").start_time
            last_bucket = latest.to_period("M").start_time
        else:
            first_bucket = period_start.normalize()
            last_bucket = latest.normalize()
        expected_buckets = pd.date_range(
            start=first_bucket, end=last_bucket, freq=frequency
        )
        actual_buckets = actual_buckets.reindex(expected_buckets)
        bucket_times = sorted(set(actual_buckets.index) | set(predicted_buckets.index))
        curve = []
        for timestamp in bucket_times:
            if selected_range == "1D":
                label = timestamp.strftime("%d %b %H:%M")
            elif selected_range == "1Y":
                label = timestamp.strftime("%b %Y")
            else:
                label = timestamp.strftime("%d %b")
            actual_value = actual_buckets.get(timestamp)
            predicted_value = predicted_buckets.get(timestamp)
            curve.append(
                {
                    "time": label,
                    "actualDemand": (
                        round(float(actual_value) / 1000, 3)
                        if pd.notna(actual_value)
                        else None
                    ),
                    "predictedDemand": (
                        round(float(predicted_value) / 1000, 3)
                        if pd.notna(predicted_value)
                        else None
                    ),
                    "fullDate": timestamp.strftime("%d %b %Y, %H:%M"),
                }
            )

        actual_peak = float(peak_row["target_energy"]) / 1000
        predicted_peak = float(predicted_peak_row["prediction"]) / 1000
        predicted_total = float(selected_forecasts["prediction"].sum()) / 1000
        max_demand = max(actual_peak, predicted_peak, 0.001)
        tick_step = max_demand / 6
        ticks = [round(tick_step * index, 2) for index in range(7)]
        if selected_range == "1D":
            demarcation_time = latest.strftime("%d %b %H:%M")
        elif selected_range == "1Y":
            demarcation_time = latest.strftime("%b %Y")
        else:
            demarcation_time = latest.strftime("%d %b")

        def chart_point(timestamp: pd.Timestamp, value: float, label: str) -> dict[str, Any]:
            if selected_range == "1D":
                time_label = timestamp.strftime("%d %b %H:%M")
            elif selected_range == "1Y":
                time_label = timestamp.strftime("%b %Y")
            else:
                time_label = timestamp.strftime("%d %b")
            return {
                "time": time_label,
                "value": round(value, 3),
                "timestamp": timestamp.strftime("%d %b %Y, %I:%M %p"),
                "label": label,
            }

        return {
            "viewType": view_type,
            "regionId": str(selected_grid) if selected_grid is not None else None,
            "regionName": region_name,
            "timeRange": selected_range,
            "avgDemand": round(float(selected_actuals["target_energy"].mean()) / 1000, 3),
            "avgDemandDeltaPct": round(delta, 1) if delta is not None else None,
            "prevPeriodAvgDemand": round(previous_average, 3) if previous_average is not None else None,
            "peakDemand": round(actual_peak, 3),
            "peakTimestamp": pd.Timestamp(peak_row["target_timestamp"]).strftime(
                "%d %b %Y, %I:%M %p"
            ),
            "predictedPeak": round(predicted_peak, 3),
            "predictedPeakTimestamp": pd.Timestamp(
                predicted_peak_row["target_timestamp"]
            ).strftime("%d %b %Y, %I:%M %p"),
            "predictedTotal": round(predicted_total, 3),
            "predictedTotalHorizon": (
                f"Next 24 hours · ending "
                f"{pd.Timestamp(selected_forecasts['target_timestamp'].max()):%d %b %Y}"
            ),
            "unit": "MW",
            "totalUnit": "MWh",
            "actualCallout": chart_point(
                pd.Timestamp(peak_row["target_timestamp"]),
                actual_peak,
                "Historical Peak",
            ),
            "predictedCallout": chart_point(
                pd.Timestamp(predicted_peak_row["target_timestamp"]),
                predicted_peak,
                "Predicted Peak · Next 24 Hours",
            ),
            "demarcationTime": demarcation_time,
            "dataPeriod": (
                f"Historical replay through {latest:%d %b %Y %H:%M}; "
                "forecast limited to the next 24 hours."
            ),
            "yDomain": [0, round(tick_step * 6, 2)],
            "yTicks": ticks,
            "curve": curve,
        }

    def _load_mlflow_model(self, sector: str) -> tuple[Any, str]:
        if sector in self._mlflow_models:
            return self._mlflow_models[sector]
        if not self.tracking_uri:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for forecast model serving.")
        name = self.commercial_model_name if sector == "commercial" else self.government_model_name
        alias = self._model_alias(sector)
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            mlflow.set_tracking_uri(self.tracking_uri)
            version = MlflowClient(
                tracking_uri=self.tracking_uri
            ).get_model_version_by_alias(name, alias)
            model = mlflow.pyfunc.load_model(f"models:/{name}@{alias}")
            loaded = (model, str(version.version))
            self._mlflow_models[sector] = loaded
            return loaded
        except Exception as exc:
            raise RuntimeError(
                f"Unable to load registered {sector} model {name}@{alias}: {exc}"
            ) from exc

    def predict_horizon(
        self, sector: str, entity_id: str, horizon_count: int = 24
    ) -> list[dict[str, Any]]:
        sector = sector.lower()
        if sector == "government":
            clean_entity = str(entity_id).strip() if entity_id else ""
            if clean_entity.lower() in ("bear & aggregate", "bear and aggregate", "aggregate", "all", "system-wide", "system", "none", ""):
                grid_id = None
            elif clean_entity in {"Bear": 50, "Bull": 64, "Eagle": 65, "Fox": 51, "Panther": 63, "Peacock": 77}:
                grid_id = {"Bear": 50, "Bull": 64, "Eagle": 65, "Fox": 51, "Panther": 63, "Peacock": 77}[clean_entity]
            else:
                try:
                    grid_id = int(clean_entity)
                except (TypeError, ValueError) as exc:
                    raise InvalidInputError(
                        f"Invalid Government grid ID: {entity_id}"
                    ) from exc
            if not 1 <= horizon_count <= 24:
                raise InvalidInputError(
                    "Government forecast horizons must be between 1 and 24 hours."
                )
            forecasts = self._predict_government_24h()
            if grid_id is not None:
                grid_forecasts = forecasts.loc[
                    forecasts["grid_id"] == grid_id
                ].sort_values("target_timestamp")
            else:
                grid_forecasts = (
                    forecasts.groupby("target_timestamp", as_index=False)["prediction"]
                    .sum()
                    .sort_values("target_timestamp")
                )
            if grid_forecasts.empty:
                raise ResourceNotFoundError(
                    f"No Government forecast is available for grid {grid_id}."
                )
            output = []
            for horizon, row in enumerate(
                grid_forecasts.itertuples(index=False), start=1
            ):
                if horizon > horizon_count:
                    break
                timestamp = pd.Timestamp(row.target_timestamp)
                output.append({
                    "timestamp": timestamp.isoformat()
                    + ("Z" if timestamp.tzinfo is None else ""),
                    "horizon_hours": horizon,
                    "prediction": float(row.prediction),
                    "forecastDemand": float(row.prediction),
                    "actualDemand": None,
                    "formattedTime": timestamp.strftime("%d %b %Y %H:%M"),
                    "unit": "kWh",
                    "actual": None,
                })
            return output
        if sector == "commercial":
            rows = self._horizon_rows(self.commercial_data, "OBJECTID", entity_id, horizon_count)
            model, _ = self._load_mlflow_model(sector)
            predictions = model.predict(rows.loc[:, FEATURE_COLUMNS])
        else:
            return self.customer_provider.predict_horizon(sector, entity_id, horizon_count)

        output = []
        for row, prediction in zip(rows.itertuples(index=False), predictions, strict=True):
            timestamp = pd.Timestamp(row.target_timestamp).isoformat()
            output.append({
                "timestamp": timestamp + ("Z" if "+" not in timestamp else ""),
                "horizon_hours": int(row.forecast_horizon_hours),
                "prediction": float(max(0, prediction)),
                "forecastDemand": float(max(0, prediction)),
                "actualDemand": float(row.target_energy),
                "formattedTime": pd.Timestamp(row.target_timestamp).strftime("%d %b %Y %H:%M"),
                "unit": "kWh",
                "actual": float(row.target_energy),
            })
        return output

    def predict(
        self,
        model_name: str,
        entity_id: str,
        features: dict[str, Any],
        actual_kwh_so_far: float | None = None,
        context: str = "future_forecast",
    ) -> PredictionOutput:
        return self.customer_provider.predict(
            model_name, entity_id, features, actual_kwh_so_far, context
        )

    def get_horizon_model_status(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        for sector, data_path, model_name in (
            ("commercial", self.commercial_data, self.commercial_model_name),
            ("government", self.government_data, self.government_model_name),
        ):
            model_alias = self._model_alias(sector)
            version, registry_error = self._registered_model_version(sector)
            data_available = data_path.is_file()
            local_model_available = (
                self.government_model_path.is_file()
                if sector == "government"
                else True
            )
            reasons = []
            if not data_available:
                reasons.append(f"Forecast dataset is missing: {data_path}")
            if version is None:
                reasons.append(registry_error or (
                    f"Registered model alias is unavailable: {model_name}@{model_alias}"
                ))
            elif sector == "commercial":
                try:
                    self._load_mlflow_model(sector)
                except RuntimeError as exc:
                    reasons.append(str(exc))
            if not local_model_available:
                reasons.append(
                    f"Government model artifact is missing: {self.government_model_path}"
                )
            status[sector] = {
                "status": (
                    "ready"
                    if data_available
                    and version is not None
                    and local_model_available
                    and not reasons
                    else "unavailable"
                ),
                "is_demo": False,
                "model_name": model_name,
                "model_alias": model_alias,
                "model_version": version,
                "provider": (
                    "mlflow_registered_alias+local_bundle"
                    if sector == "government"
                    else "mlflow_registered_alias"
                ),
                "data_available": data_available,
                "error": "; ".join(reasons) if reasons else None,
                **self._registered_metadata(sector),
            }
        return status

    def _registered_version(self, sector: str) -> str | None:
        version, _ = self._registered_model_version(sector)
        return version

    def _model_alias(self, sector: str) -> str:
        return (
            self.commercial_model_alias
            if sector == "commercial"
            else self.government_model_alias
        )

    def _registered_model_version(
        self, sector: str
    ) -> tuple[str | None, str | None]:
        """Resolve the configured alias without loading a serving artifact."""
        model_name = (
            self.commercial_model_name
            if sector == "commercial"
            else self.government_model_name
        )
        model_alias = self._model_alias(sector)
        if not self.tracking_uri:
            return None, "MLFLOW_TRACKING_URI is not configured."
        try:
            from mlflow.tracking import MlflowClient

            client = MlflowClient(tracking_uri=self.tracking_uri)
            version = client.get_model_version_by_alias(model_name, model_alias)
            return str(version.version), None
        except Exception as exc:
            return (
                None,
                f"Unable to resolve MLflow alias {model_name}@{model_alias} "
                f"at {self.tracking_uri}: {exc}",
            )

    def _registered_metadata(self, sector: str) -> dict[str, Any]:
        try:
            from mlflow.tracking import MlflowClient

            model_name = self.commercial_model_name if sector == "commercial" else self.government_model_name
            client = MlflowClient(tracking_uri=self.tracking_uri)
            version = client.get_model_version_by_alias(
                model_name, self._model_alias(sector)
            )
            metrics = client.get_run(version.run_id).data.metrics
            if sector == "commercial":
                candidates = [
                    key for key in metrics
                    if key.startswith("test_")
                    and key.endswith(("_mae", "_rmse", "_wape"))
                    and "persistence_baseline" not in key
                ]
                selected = candidates[0].rsplit("_", 1)[0] if candidates else ""
                metric_values = {
                    "mae_kwh": metrics.get(f"{selected}_mae"),
                    "rmse_kwh": metrics.get(f"{selected}_rmse"),
                    "wape": metrics.get(f"{selected}_wape"),
                } if selected else {}
                features = list(FEATURE_COLUMNS)
            else:
                metric_values = {
                    "mae_kwh": metrics.get("validation_hybrid_mae"),
                    "rmse_kwh": metrics.get("validation_hybrid_rmse"),
                    "wape": metrics.get("validation_hybrid_wape"),
                }
                features = self._load_government_bundle().get("features", [])
            return {
                "test_metrics": {key: value for key, value in metric_values.items() if value is not None},
                "features": features,
            }
        except Exception:
            return {"test_metrics": {}, "features": []}

    def _model_is_registered(self, sector: str) -> bool:
        return self._registered_version(sector) is not None

    def get_model_status(self) -> dict[str, Any]:
        models = self.get_horizon_model_status()
        ready = any(item["status"] == "ready" for item in models.values())
        return {
            "provider": "trained_forecast_provider",
            "status": "ready" if ready else "unavailable",
            "is_demo": False,
            "customer_bill": self.customer_provider.get_model_status(),
            "models": models,
        }

    def get_forecast_model_info(self, sector: str) -> dict[str, Any]:
        if sector == "residential":
            return self.customer_provider.get_forecast_model_info(sector)
        names = {
            "commercial": self.commercial_model_name,
            "government": self.government_model_name,
        }
        data_path = {
            "commercial": self.commercial_data,
            "government": self.government_data,
        }[sector]
        version = self._registered_version(sector)
        model_alias = self._model_alias(sector)
        local_model_available = (
            self.government_model_path.is_file()
            if sector == "government"
            else True
        )
        data_available = data_path.is_file()
        ready = version is not None and local_model_available and data_available
        return {
            "model_name": names[sector],
            "model_version": version or "not_deployed",
            "model_alias": model_alias,
            "provider": (
                "mlflow_registered_alias+local_bundle"
                if sector == "government"
                else "mlflow_registered_alias"
            ),
            "is_demo": not ready,
            "evaluation_status": "historical_holdout_replay",
            "data_available": data_available,
            "error": (
                "Government forecast data, local model bundle, or registered alias is unavailable."
                if not ready and sector == "government"
                else None
            ),
            **self._registered_metadata(sector),
        }
