"""Serve the trained commercial and government forecast artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd

from app.providers.mlflow_adapter import MLflowModelAdapter
from app.providers.model_provider import BaseModelProvider, PredictionOutput
from training.commercial_forecast.features import FEATURE_COLUMNS


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
    ) -> None:
        self.customer_provider = customer_provider
        self.commercial_data = Path(commercial_data)
        self.commercial_model_path = Path(commercial_model)
        self.government_data = Path(government_data)
        self.government_model_path = Path(government_model)
        self.tracking_uri = tracking_uri
        self.commercial_model_name = commercial_model_name
        self.government_model_name = government_model_name
        self.model_alias = model_alias
        self._mlflow_models: dict[str, tuple[Any, str]] = {}
        self._commercial_bundle: dict[str, Any] | None = None
        self._government_bundle: dict[str, Any] | None = None
        self._commercial_entities: list[dict[str, Any]] | None = None
        self._regional_entities: list[dict[str, Any]] | None = None

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

    def get_commercial_buildings(self) -> list[dict[str, Any]]:
        if self._commercial_entities is None:
            rows = self._query(
                self.commercial_data,
                """SELECT OBJECTID, any_value(\"id.grid.coarse\") AS grid_id,
                          any_value(GeneralUseType) AS use_type,
                          any_value(\"building.area.m2\") AS area,
                          any_value(EffectiveYearBuilt) AS year_built,
                          max(target_timestamp) AS last_timestamp
                   FROM read_parquet({path}) GROUP BY OBJECTID
                   ORDER BY OBJECTID LIMIT 100""",
            )
            self._commercial_entities = [
                {
                    "buildingId": str(int(row.OBJECTID)),
                    "siteId": f"Grid {int(row.grid_id)}",
                    "id.grid.coarse": int(row.grid_id),
                    "primarySpaceUsage": str(row.use_type or "Commercial"),
                    "sqm": float(row.area or 0),
                    "yearBuilt": int(row.year_built or 0),
                    "recentDemandKwh": 0.0,
                    "predictedDemandKwh": 0.0,
                    "lastTimestamp": row.last_timestamp.isoformat(),
                }
                for row in rows.itertuples(index=False)
            ]
        return self._commercial_entities

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
                    "predictedDemandKwh": float(row.total_kwh or 0),
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
                       count(DISTINCT forecast_horizon_hours) AS steps
                FROM read_parquet({{path}})
                WHERE {id_column} = {int(entity_id)}
                  AND target_timestamp >= TIMESTAMP '2018-12-01'
                GROUP BY forecast_origin_timestamp
                HAVING steps >= {int(horizon_count)}
                ORDER BY forecast_origin_timestamp DESC LIMIT 1""",
        )
        if rows.empty:
            raise ValueError(f"No complete held-out horizon for entity {entity_id}.")
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
                raise FileNotFoundError(f"Government model is missing: {self.government_model_path}")
            self._government_bundle = joblib.load(self.government_model_path)
        return self._government_bundle

    def _load_mlflow_model(self, sector: str) -> tuple[Any, str]:
        if sector in self._mlflow_models:
            return self._mlflow_models[sector]
        if not self.tracking_uri:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for forecast model serving.")
        name = self.commercial_model_name if sector == "commercial" else self.government_model_name
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            mlflow.set_tracking_uri(self.tracking_uri)
            version = MlflowClient().get_model_version_by_alias(name, self.model_alias)
            model = mlflow.pyfunc.load_model(f"models:/{name}@{self.model_alias}")
            loaded = (model, str(version.version))
            self._mlflow_models[sector] = loaded
            return loaded
        except Exception as exc:
            raise RuntimeError(f"Unable to load registered {sector} model {name}@{self.model_alias}: {exc}") from exc

    def predict_horizon(
        self, sector: str, entity_id: str, horizon_count: int = 24
    ) -> list[dict[str, Any]]:
        sector = sector.lower()
        if sector == "commercial":
            rows = self._horizon_rows(self.commercial_data, "OBJECTID", entity_id, horizon_count)
            model, _ = self._load_mlflow_model(sector)
            predictions = model.predict(rows.loc[:, FEATURE_COLUMNS])
        elif sector == "government":
            rows = self._horizon_rows(
                self.government_data, '\"id.grid.coarse\"', entity_id, horizon_count
            )
            model, _ = self._load_mlflow_model(sector)
            bundle = self._load_government_bundle()
            features = bundle["features"]
            matrix = rows.loc[:, features].astype(np.float32).replace([np.inf, -np.inf], np.nan)
            matrix["grid_id"] = int(entity_id)
            predictions = model.predict(matrix)
            predictions = np.maximum(np.asarray(predictions, dtype=float), 0)
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
        artifacts = {
            "commercial": self.commercial_data,
            "government": self.government_data,
        }
        return {
            name: {
                "status": "ready" if data.is_file() and self._model_is_registered(name) else "unavailable",
                "is_demo": False,
                "model_name": self.commercial_model_name if name == "commercial" else self.government_model_name,
                "model_alias": self.model_alias,
                "model_version": self._registered_version(name),
                "provider": "mlflow_registered_alias",
                "data_available": data.is_file(),
                **self._registered_metadata(name),
            }
            for name, data in artifacts.items()
        }

    def _registered_version(self, sector: str) -> str | None:
        try:
            return self._load_mlflow_model(sector)[1]
        except Exception:
            return None

    def _registered_metadata(self, sector: str) -> dict[str, Any]:
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            model_name = self.commercial_model_name if sector == "commercial" else self.government_model_name
            mlflow.set_tracking_uri(self.tracking_uri)
            client = MlflowClient()
            version = client.get_model_version_by_alias(model_name, self.model_alias)
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
        return {
            "model_name": names[sector],
            "model_version": version or "unavailable",
            "model_alias": self.model_alias,
            "provider": "mlflow_registered_alias",
            "is_demo": version is None,
            "evaluation_status": "historical_holdout_replay",
            **self._registered_metadata(sector),
        }
