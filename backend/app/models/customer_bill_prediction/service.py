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

    def _load_metadata(self) -> dict[str, Any]:
        if self._metadata is None:
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
        if self._frame is None:
            if not self.dataset_path.is_file():
                raise CustomerBillPredictionError(
                    f"Customer gold dataset is missing: {self.dataset_path}"
                )
            try:
                frame = pd.read_parquet(self.dataset_path)
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

    def get_model_catalog(self) -> list[dict[str, Any]]:
        catalog = []
        for model_id, definition in MODEL_REGISTRY.items():
            if model_id == "customer-bill-prediction":
                catalog.append(self.get_summary())
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
