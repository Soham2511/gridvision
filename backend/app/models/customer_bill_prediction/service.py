"""Gold dataset access and inference for the customer bill model."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.models.registry import MODEL_REGISTRY
from app.providers.mlflow_adapter import MLflowIntegrationError, MLflowModelAdapter
from app.providers.model_provider import BaseModelProvider

logger = logging.getLogger("gridvision.models.customer_bill_prediction")


class CustomerBillPredictionError(RuntimeError):
    """The customer bill dataset or model could not serve a request."""


class CustomerBillPredictionService:
    """Serves records and predictions from the customer gold dataset."""

    def __init__(
        self,
        dataset_path: Path,
        metadata_path: Path,
        artifact_path: Path,
        model_provider: BaseModelProvider,
        tariff_inr_per_kwh: float,
    ) -> None:
        self.dataset_path = dataset_path
        self.metadata_path = metadata_path
        self.artifact_path = artifact_path
        self.model_provider = model_provider
        self.tariff_inr_per_kwh = tariff_inr_per_kwh
        self._frame: pd.DataFrame | None = None
        self._artifact: dict[str, Any] | None = None
        self._metadata: dict[str, Any] | None = None
        self._loaded_model_version: str | None = None

    def _sync_with_model_provider(self) -> None:
        if isinstance(self.model_provider, MLflowModelAdapter):
            current_version = getattr(self.model_provider, "_model_version", None)
            if current_version and current_version != self._loaded_model_version:
                self._metadata = None
                self._frame = None
                self._loaded_model_version = current_version

    def _load_metadata(self) -> dict[str, Any]:
        self._sync_with_model_provider()
        if self._metadata is not None:
            return self._metadata

        if self.metadata_path.is_file():
            try:
                self._metadata = json.loads(
                    self.metadata_path.read_text(encoding="utf-8")
                )
                return self._metadata
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not read local metadata: %s", exc)

        # Fallback: dynamically download metadata from active champion MLflow run
        if isinstance(self.model_provider, MLflowModelAdapter):
            run_id = self.model_provider.get_current_run_id()
            if run_id:
                try:
                    import mlflow.artifacts

                    self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
                    local_meta = mlflow.artifacts.download_artifacts(
                        run_id=run_id,
                        artifact_path="model_metadata.json",
                        dst_path=str(self.metadata_path.parent),
                        tracking_uri=self.model_provider.tracking_uri,
                    )
                    self._metadata = json.loads(
                        Path(local_meta).read_text(encoding="utf-8")
                    )
                    return self._metadata
                except Exception as exc:
                    logger.warning("Unable to download metadata from MLflow: %s", exc)

        if not self.metadata_path.is_file():
            raise CustomerBillPredictionError(
                f"Model metadata file is missing: {self.metadata_path}"
            )
        try:
            self._metadata = json.loads(
                self.metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CustomerBillPredictionError(
                f"Unable to read customer bill model metadata: {exc}"
            ) from exc
        return self._metadata

    def _load_frame(self) -> pd.DataFrame:
        self._sync_with_model_provider()
        if self._frame is not None:
            return self._frame

        frame_path = self.dataset_path
        if not frame_path.is_file() and isinstance(self.model_provider, MLflowModelAdapter):
            run_id = self.model_provider.get_current_run_id()
            if run_id:
                try:
                    import mlflow.artifacts

                    dest_dir = self.dataset_path.parent
                    try:
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        test_file = dest_dir / ".write_test"
                        test_file.touch()
                        test_file.unlink()
                    except OSError:
                        dest_dir = Path("/tmp/data/gold")
                        dest_dir.mkdir(parents=True, exist_ok=True)

                    downloaded = mlflow.artifacts.download_artifacts(
                        run_id=run_id,
                        artifact_path="dataset_lineage",
                        dst_path=str(dest_dir),
                        tracking_uri=self.model_provider.tracking_uri,
                    )
                    downloaded_path = Path(downloaded)
                    parquets = list(downloaded_path.glob("*.parquet"))
                    if not parquets:
                        parquets = list(dest_dir.glob("**/*.parquet"))
                    if parquets:
                        frame_path = parquets[0]
                except Exception as exc:
                    logger.warning("Unable to download dataset from MLflow: %s", exc)

        if not frame_path.is_file():
            raise CustomerBillPredictionError(
                f"Customer gold dataset is missing: {self.dataset_path}"
            )
        try:
            frame = pd.read_parquet(frame_path)
        except (OSError, ValueError, ImportError) as exc:
            raise CustomerBillPredictionError(
                f"Unable to read customer gold dataset: {exc}"
            ) from exc
        required_columns = {
            "entity_id",
            "month_start",
            "target_month_kwh",
            "cumulative_energy_kwh",
        }
        missing = sorted(required_columns.difference(frame.columns))
        if missing:
            raise CustomerBillPredictionError(
                f"Customer gold dataset is missing required columns: {missing}"
            )
        self._frame = frame
        return self._frame

    def _load_artifact(self) -> dict[str, Any]:
        if self._artifact is not None:
            return self._artifact
        metadata = self._load_metadata()
        if not self.artifact_path.is_file():
            raise CustomerBillPredictionError(
                f"Customer bill model artifact is missing: {self.artifact_path}"
            )
        expected_digest = metadata.get("pickle_sha256")
        if not expected_digest:
            raise CustomerBillPredictionError(
                "Customer bill model metadata does not contain its artifact checksum."
            )
        digest = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        if digest != expected_digest:
            raise CustomerBillPredictionError(
                "Customer bill model artifact checksum does not match its metadata."
            )

        training_package = self.artifact_path.parents[1] / "training"
        if training_package.is_dir() and str(training_package) not in sys.path:
            sys.path.insert(0, str(training_package))
        try:
            artifact = joblib.load(self.artifact_path)
        except (OSError, ImportError, AttributeError, ValueError) as exc:
            raise CustomerBillPredictionError(
                f"Unable to load customer bill model artifact: {exc}"
            ) from exc
        if not isinstance(artifact, dict) or not {
            "model",
            "features",
            "model_name",
            "model_version",
        }.issubset(artifact):
            raise CustomerBillPredictionError(
                "Customer bill model artifact has an unsupported structure."
            )
        if artifact["features"] != metadata.get("features"):
            raise CustomerBillPredictionError(
                "Customer bill model artifact features do not match its metadata."
            )
        self._artifact = artifact
        return artifact

    @staticmethod
    def _month_string(value: Any) -> str:
        return pd.Timestamp(value).strftime("%Y-%m-%d")

    def get_summary(self) -> dict[str, Any]:
        frame = self._load_frame()
        metadata = self._load_metadata()
        model_error = None
        if isinstance(self.model_provider, MLflowModelAdapter):
            model_configured = self.model_provider.is_configured()
        else:
            try:
                self._load_artifact()
                model_configured = True
            except CustomerBillPredictionError as exc:
                model_configured = False
                model_error = str(exc)
        summary = {
            **MODEL_REGISTRY["customer-bill-prediction"].as_dict(),
            "status": "configured" if model_configured else "unavailable",
            "provider": (
                self.model_provider.PROVIDER_NAME
                if isinstance(self.model_provider, MLflowModelAdapter)
                else "local_artifact"
            ),
            "modelVersion": metadata.get("model_version", "unknown"),
            "selectedModel": metadata.get("selected_model", "unknown"),
            "dataset": {
                "name": metadata.get("dataset", {}).get(
                    "dataset_name", "customer_gold"
                ),
                "rows": int(len(frame)),
                "entities": int(frame["entity_id"].nunique()),
                "regions": int(frame["id_grid_coarse"].nunique())
                if "id_grid_coarse" in frame
                else 0,
                "startMonth": self._month_string(frame["month_start"].min()),
                "endMonth": self._month_string(frame["month_start"].max()),
                "qualityPassed": metadata.get("dataset", {}).get(
                    "quality_passed"
                ),
                "version": metadata.get("dataset", {}).get(
                    "dataset_version", "untracked"
                ),
            },
            "testMetrics": metadata.get("test_metrics", {}),
            "features": metadata.get("features", []),
            "tariffInrPerKwh": self.tariff_inr_per_kwh,
        }
        if model_error:
            summary["error"] = model_error
        return summary

    def get_government_summary(self, definition: Any) -> dict[str, Any]:
        return {
            **definition.as_dict(),
            "status": "configured",
            "provider": (
                self.model_provider.PROVIDER_NAME
                if isinstance(self.model_provider, MLflowModelAdapter)
                else "local_artifact"
            ),
            "modelVersion": "1",
            "selectedModel": "dual_lightgbm_hybrid",
            "dataset": {
                "name": "gold_grid_forecasting_2018",
                "rows": 250000,
                "entities": 53,
                "regions": 53,
                "startMonth": "2018-01-01",
                "endMonth": "2018-12-01",
                "qualityPassed": True,
                "version": "2018-annual-grid",
            },
            "testMetrics": {
                "mae_kwh": 390.29,
                "rmse_kwh": 1160.58,
                "r2": 0.9565,
                "wape": 0.1299,
                "rmsle": 0.2646,
            },
            "features": [
                "forecast_horizon_hours",
                "total_building_area_m2",
                "total_footprint_area_m2",
                "centroid_latitude",
                "centroid_longitude",
                "building_count",
                "Commercial_count",
                "Industrial_count",
                "Institutional_count",
                "Recreational_count",
                "Residential_count",
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
                "target_month",
                "target_day_of_month",
                "target_day_of_week",
                "target_hour",
                "target_day_of_year",
                "target_is_weekend",
                "target_hour_sin",
                "target_hour_cos",
                "target_day_of_year_sin",
                "target_day_of_year_cos",
            ],
            "tariffInrPerKwh": self.tariff_inr_per_kwh,
        }

    def get_model_catalog(self) -> list[dict[str, Any]]:
        catalog = []
        for model_id, definition in MODEL_REGISTRY.items():
            if model_id == "customer-bill-prediction":
                catalog.append(self.get_summary())
                continue
            if model_id == "government-load-forecasting":
                catalog.append(self.get_government_summary(definition))
                continue
            catalog.append({
                **definition.as_dict(),
                "status": "unavailable",
                "provider": "not_registered",
                "modelVersion": "not_deployed",
                "selectedModel": "not_deployed",
            })
        return catalog

    def get_entity_records(
        self, limit: int, offset: int, entity_id: int | None = None
    ) -> dict[str, Any]:
        frame = self._load_frame()
        latest = (
            frame.sort_values(["entity_id", "month_start", "cutoff_day"])
            .drop_duplicates("entity_id", keep="last")
            .sort_values("entity_id")
        )
        total = len(latest)
        if entity_id is not None:
            latest = latest[latest["entity_id"] == entity_id]
            if latest.empty:
                return {"items": [], "total": 0, "limit": limit, "offset": offset}

        items = [
            {
                "entityId": str(int(row.entity_id)),
                "monthStart": self._month_string(row.month_start),
                "cutoffDay": int(row.cutoff_day),
                "buildingType": str(row.building_type),
                "cumulativeEnergyKwh": float(row.cumulative_energy_kwh),
                "actualMonthKwh": float(row.target_month_kwh),
                "coverageRatio": float(row.coverage_ratio),
            }
            for row in latest.iloc[offset : offset + limit].itertuples()
        ]
        return {
            "items": items,
            "total": 1 if entity_id is not None else total,
            "limit": limit,
            "offset": offset,
        }

    def get_entity_months(self, entity_id: int) -> list[dict[str, Any]]:
        frame = self._load_frame()
        rows = frame[frame["entity_id"] == entity_id].sort_values(
            ["month_start", "cutoff_day"]
        )
        if rows.empty:
            return []
        return [
            {
                "entityId": str(int(row.entity_id)),
                "monthStart": self._month_string(row.month_start),
                "cutoffDay": int(row.cutoff_day),
                "buildingType": str(row.building_type),
                "cumulativeEnergyKwh": float(row.cumulative_energy_kwh),
                "actualMonthKwh": float(row.target_month_kwh),
                "coverageRatio": float(row.coverage_ratio),
            }
            for row in rows.itertuples()
        ]

    def get_historical_gold_insights(self, time_range: str) -> dict[str, Any]:
        frame = self._load_frame()
        required_columns = {
            "cutoff_day",
            "naive_projected_month_kwh",
            "target_month_kwh",
            "building_type",
            "coverage_ratio",
        }
        missing = sorted(required_columns.difference(frame.columns))
        if missing:
            raise CustomerBillPredictionError(
                f"Customer gold dataset is missing historical insight columns: {missing}"
            )

        latest = (
            frame.sort_values(["entity_id", "month_start", "cutoff_day"])
            .drop_duplicates(["entity_id", "month_start"], keep="last")
            .copy()
        )
        latest["absolute_projection_error_kwh"] = (
            latest["target_month_kwh"]
            - latest["naive_projected_month_kwh"]
        ).abs()
        available_months = sorted(latest["month_start"].unique())
        month_limit = {"3M": 3, "6M": 6, "1Y": 12}.get(time_range)
        if month_limit is not None:
            selected_months = available_months[-month_limit:]
            latest = latest[latest["month_start"].isin(selected_months)]

        monthly = (
            latest.groupby("month_start", sort=True)
            .agg(
                entity_count=("entity_id", "nunique"),
                average_actual_kwh=("target_month_kwh", "mean"),
                median_actual_kwh=("target_month_kwh", "median"),
                cohort_actual_kwh=("target_month_kwh", "sum"),
                average_projection_kwh=("naive_projected_month_kwh", "mean"),
                average_absolute_error_kwh=(
                    "absolute_projection_error_kwh",
                    "mean",
                ),
                average_coverage_ratio=("coverage_ratio", "mean"),
            )
            .reset_index()
        )
        if monthly.empty:
            raise CustomerBillPredictionError(
                "Customer gold dataset has no monthly records for historical insights."
            )

        metadata = self._load_metadata()
        dataset_metadata = metadata.get("dataset", {})
        model_name = metadata.get("selected_model", "unknown")
        model_version = metadata.get("model_version", "unknown")
        month_records = [
            {
                "monthStart": self._month_string(row.month_start),
                "monthLabel": pd.Timestamp(row.month_start).strftime("%b %Y"),
                "entityCount": int(row.entity_count),
                "averageActualKwh": float(row.average_actual_kwh),
                "medianActualKwh": float(row.median_actual_kwh),
                "cohortActualKwh": float(row.cohort_actual_kwh),
                "averageProjectionKwh": float(row.average_projection_kwh),
                "averageAbsoluteErrorKwh": float(
                    row.average_absolute_error_kwh
                ),
                "averageCoverageRatio": float(row.average_coverage_ratio),
            }
            for row in monthly.itertuples()
        ]
        entity_types = (
            latest.sort_values(["month_start", "cutoff_day"])
            .drop_duplicates("entity_id", keep="last")
            .groupby("building_type")["entity_id"]
            .nunique()
        )

        return {
            "timeRange": time_range,
            "monthsReturned": len(month_records),
            "startMonth": month_records[0]["monthStart"],
            "endMonth": month_records[-1]["monthStart"],
            "averageMonthlyKwhPerEntity": sum(
                record["averageActualKwh"] for record in month_records
            )
            / len(month_records),
            "highestMonthlyAverageKwhPerEntity": max(
                record["averageActualKwh"] for record in month_records
            ),
            "averageProjectionErrorKwh": sum(
                record["averageAbsoluteErrorKwh"] for record in month_records
            )
            / len(month_records),
            "entityCount": int(latest["entity_id"].nunique()),
            "dataset": {
                "name": dataset_metadata.get("dataset_name", "customer_gold"),
                "version": dataset_metadata.get(
                    "dataset_version", "untracked"
                ),
                "sourceRows": int(len(frame)),
                "months": len(available_months),
                "qualityPassed": dataset_metadata.get("quality_passed"),
                "cutoffDay": int(latest["cutoff_day"].max()),
            },
            "model": {
                "name": model_name,
                "version": model_version,
                "testMetrics": metadata.get("test_metrics", {}),
                "features": metadata.get("features", []),
                "provider": (
                    self.model_provider.PROVIDER_NAME
                    if isinstance(self.model_provider, MLflowModelAdapter)
                    else "local_artifact"
                ),
                "description": (
                    "The selected naive month projection scales observed "
                    "consumption to a full month."
                    if model_name == "naive_month_projection"
                    else "Historical model projection from the final available "
                    "cutoff snapshot for each entity-month."
                ),
            },
            "buildingTypeBreakdown": [
                {"buildingType": str(name), "entityCount": int(count)}
                for name, count in entity_types.items()
            ],
            "history": month_records,
        }

    def predict(
        self, entity_id: int, month_start: str, cutoff_day: int
    ) -> dict[str, Any]:
        frame = self._load_frame()
        matches = frame[
            (frame["entity_id"] == entity_id)
            & (frame["month_start"].astype(str) == month_start)
            & (frame["cutoff_day"] == cutoff_day)
        ]
        if matches.empty:
            return {}
        row = matches.iloc[0]
        metadata = self._load_metadata()
        features = metadata.get("features", [])
        if not features or any(feature not in frame.columns for feature in features):
            raise CustomerBillPredictionError(
                "Model input features do not match the customer gold dataset."
            )
        model_features = {
            name: None if pd.isna(row[name]) else row[name].item()
            if hasattr(row[name], "item")
            else row[name]
            for name in features
        }
        actual_kwh = float(row["cumulative_energy_kwh"])
        if isinstance(self.model_provider, MLflowModelAdapter):
            try:
                prediction = self.model_provider.predict(
                    model_name="residential",
                    entity_id=str(entity_id),
                    features=model_features,
                    actual_kwh_so_far=actual_kwh,
                    context="retrospective_gold_replay",
                )
            except MLflowIntegrationError as exc:
                logger.exception("MLflow customer bill prediction failed")
                raise CustomerBillPredictionError(
                    f"MLflow customer bill prediction failed: {exc}"
                ) from exc
            predicted_total = prediction.estimated_month_end_kwh
            provider = prediction.provider
            model_name = prediction.model_name
            model_version = prediction.model_version
        else:
            artifact = self._load_artifact()
            try:
                predicted_total = float(
                    artifact["model"].predict(
                        pd.DataFrame([model_features], columns=features)
                    )[0]
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise CustomerBillPredictionError(
                    f"Customer bill prediction failed: {exc}"
                ) from exc
            provider = "local_artifact"
            model_name = str(artifact["model_name"])
            model_version = str(artifact["model_version"])

        if predicted_total is None:
            raise CustomerBillPredictionError(
                "Customer bill model did not return a month-end estimate."
            )
        actual_total = float(row["target_month_kwh"])
        return {
            "entityId": str(entity_id),
            "monthStart": self._month_string(row["month_start"]),
            "cutoffDay": int(row["cutoff_day"]),
            "actualKwhSoFar": actual_kwh,
            "predictedMonthEndKwh": float(predicted_total),
            "actualMonthEndKwh": actual_total,
            "predictedRemainingKwh": max(0.0, float(predicted_total) - actual_kwh),
            "predictedBillInr": round(float(predicted_total) * self.tariff_inr_per_kwh, 2),
            "actualBillInr": round(actual_total * self.tariff_inr_per_kwh, 2),
            "absoluteErrorKwh": round(abs(float(predicted_total) - actual_total), 2),
            "modelName": model_name,
            "modelVersion": model_version,
            "provider": provider,
            "isDemo": False,
            "evaluationStatus": "retrospective_gold_replay",
        }
