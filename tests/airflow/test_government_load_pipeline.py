from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

GOVERNMENT_PIPELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "airflow"
    / "2_government_load_prediction"
)
if str(GOVERNMENT_PIPELINE_PATH) not in sys.path:
    sys.path.insert(0, str(GOVERNMENT_PIPELINE_PATH))

from training.government_load.config import PipelineSettings
from grid_forecasting_pipeline.etl import prepare_training_data
from training.government_load.modeling import predict

FEATURES = [
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
]


class ConstantModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.value)


def _write_raw_sample(path: Path) -> None:
    start = datetime(2018, 1, 1)
    rows = []
    buildings = [
        (1, 10, "Residential", 100.0, 60.0, 34.0, -118.0, 2.0),
        (2, 10, "Commercial", 200.0, 120.0, 34.2, -118.2, 3.0),
        (3, 20, "Residential", 50.0, 30.0, 35.0, -117.0, 1.0),
    ]
    for hour in range(30):
        timestamp = start + timedelta(hours=hour)
        for object_id, grid_id, use_type, area, footprint, lat, lon, energy in buildings:
            rows.append(
                {
                    "OBJECTID": object_id,
                    "id.grid.coarse": grid_id,
                    "building.area.m2": area,
                    "FootprintArea.m2": footprint,
                    "GeneralUseType": use_type,
                    "latitude": lat,
                    "longitude": lon,
                    "timestamp": timestamp,
                    "normalized_building_energy_kwh": energy + hour / 10,
                }
            )
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_prepare_builds_training_ready_rows_and_expected_features(tmp_path: Path) -> None:
    source = tmp_path / "raw.parquet"
    features_path = tmp_path / "feature_columns.joblib"
    output = tmp_path / "output" / "training_ready_2018.parquet"
    _write_raw_sample(source)
    joblib.dump(FEATURES, features_path)
    settings = PipelineSettings(
        input_path=source,
        output_path=output,
        feature_columns_path=features_path,
        memory_limit="1GB",
        threads=1,
        horizon_hours=24,
    )

    result = prepare_training_data(settings)

    assert result == output
    ready = pd.read_parquet(output)
    assert len(ready) == 840
    assert set(FEATURES).issubset(ready.columns)
    assert {"target_energy", "target_timestamp", "forecast_origin_timestamp"}.issubset(
        ready.columns
    )
    first = ready.loc[
        (ready["id.grid.coarse"] == 10)
        & (ready["forecast_origin_timestamp"] == datetime(2018, 1, 1))
        & (ready["forecast_horizon_hours"] == 1)
    ].iloc[0]
    assert first["energy_at_origin"] == pytest.approx(5.0)
    assert first["target_energy"] == pytest.approx(5.2)
    assert first["building_count"] == 2
    assert first["Residential_count"] == 1
    assert first["Commercial_count"] == 1
    assert output.with_name("grid_level_energy.parquet").is_file()
    assert output.with_name("grid_history_features.parquet").is_file()
    assert output.with_name("gold_grid_forecasting_2018.parquet").is_file()


def test_settings_validate_resource_values(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        PipelineSettings(
            input_path=tmp_path / "in.parquet",
            output_path=tmp_path / "out.parquet",
            threads=0,
        )


def test_settings_default_to_shared_sample_and_separate_outputs() -> None:
    settings = PipelineSettings()
    project_root = Path(__file__).resolve().parents[2]
    assert settings.input_path == (
        project_root / "data" / "sample" / "training_sample_50000.parquet"
    )
    assert settings.output_path == (
        project_root / "data" / "airflow" / "government" / "training_ready_2018.parquet"
    )
    assert settings.feature_columns_path == (
        project_root / "mlflow" / "government" / "feature_columns_2018.joblib"
    )


def test_settings_use_namespaced_environment_variables(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "government.parquet"
    monkeypatch.setenv("GOVERNMENT_PIPELINE_INPUT", str(source))
    monkeypatch.setenv("GRID_PIPELINE_INPUT", str(tmp_path / "customer.parquet"))

    settings = PipelineSettings.from_environment()

    assert settings.input_path == source


def test_training_fits_saves_and_logs_hybrid_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from training.government_load.modeling import train_hybrid_model

    input_path = tmp_path / "training_ready.parquet"
    feature_columns_path = tmp_path / "features.joblib"
    model_path = tmp_path / "models" / "hybrid.joblib"
    tracking_path = tmp_path / "mlflow"
    monkeypatch.setenv("GRIDVISION_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_path.as_uri())
    features = ["forecast_horizon_hours", "energy_at_origin"]
    joblib.dump(features, feature_columns_path)
    pd.DataFrame(
        {
            "id.grid.coarse": [10, 10, 20, 10, 10, 20],
            "target_timestamp": pd.to_datetime(
                [
                    "2018-09-01",
                    "2018-09-02",
                    "2018-09-03",
                    "2018-10-01",
                    "2018-10-02",
                    "2018-10-03",
                ]
            ),
            "forecast_horizon_hours": [1, 1, 1, 1, 1, 1],
            "energy_at_origin": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
            "target_energy": [2.0, 4.0, 6.0, 3.0, 5.0, 7.0],
        }
    ).to_parquet(input_path, index=False)
    settings = PipelineSettings(
        input_path=input_path,
        output_path=tmp_path / "unused.parquet",
        feature_columns_path=feature_columns_path,
        model_path=model_path,
        threads=1,
        max_training_rows=2,
        max_validation_rows=2,
        n_estimators=2,
    )

    result = train_hybrid_model(settings)

    artifact = joblib.load(model_path)
    assert result["training_rows"] == 2
    assert result["validation_rows"] == 2
    assert result["mlflow_run_id"]
    assert set(result["validation_mae"]) == {"original", "log"}
    assert set(result["validation_metrics"]) == {
        "original",
        "log",
        "hybrid",
        "persistence",
    }
    assert result["validation_metrics"]["hybrid"]["rmse"] >= 0
    assert Path(result["model_card_path"]).is_file()
    assert Path(result["metrics_path"]).is_file()
    assert Path(result["training_log_path"]).is_file()
    artifact_directory = Path(result["artifact_directory"])
    assert (artifact_directory / "validation_predictions.parquet").is_file()
    assert (artifact_directory / "validation_metrics_by_grid.csv").is_file()
    assert (artifact_directory / "validation_metrics_by_horizon.csv").is_file()
    assert (artifact_directory / "feature_importance.csv").is_file()
    assert (artifact_directory / "original_model.txt").is_file()
    assert (artifact_directory / "log_target_model.txt").is_file()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_path.as_uri())
    logged_run = client.get_run(result["mlflow_run_id"])
    assert "validation_hybrid_rmse" in logged_run.data.metrics
    assert "validation_persistence_mae" in logged_run.data.metrics
    assert set(logged_run.data.metrics) == {
        f"validation_{model}_{metric}"
        for model in ("original", "log", "hybrid", "persistence")
        for metric in ("mae", "rmse", "r2")
    } | {
        "validation_hybrid_wape",
        "validation_hybrid_rmsle",
        "validation_hybrid_negative_prediction_rate",
    }
    artifact_names = {
        item.path for item in client.list_artifacts(result["mlflow_run_id"], "training_artifacts")
    }
    assert "training_artifacts/validation_predictions.parquet" in artifact_names
    assert "training_artifacts/feature_importance.csv" in artifact_names
    assert artifact["features"] == features
    assert set(artifact["routing"]["selected_model"]).issubset({"original", "log"})
    assert result["routing_counts"]["original"] + result["routing_counts"].get(
        "log", 0
    ) == 1


def test_training_requires_mlflow_tracking_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from training.government_load.modeling import train_hybrid_model

    input_path = tmp_path / "training_ready.parquet"
    feature_columns_path = tmp_path / "features.joblib"
    joblib.dump(["forecast_horizon_hours", "energy_at_origin"], feature_columns_path)
    pd.DataFrame(
        {
            "id.grid.coarse": [10, 10, 10, 10],
            "target_timestamp": pd.to_datetime(
                ["2018-09-01", "2018-09-02", "2018-10-01", "2018-10-02"]
            ),
            "forecast_horizon_hours": [1, 1, 1, 1],
            "energy_at_origin": [1.0, 2.0, 1.5, 2.5],
            "target_energy": [2.0, 4.0, 3.0, 5.0],
        }
    ).to_parquet(input_path, index=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    settings = PipelineSettings(
        input_path=input_path,
        output_path=tmp_path / "unused.parquet",
        feature_columns_path=feature_columns_path,
        model_path=tmp_path / "models" / "hybrid.joblib",
        threads=1,
        n_estimators=2,
    )

    with pytest.raises(ValueError, match="MLFLOW_TRACKING_URI"):
        train_hybrid_model(settings)


def test_predict_routes_by_grid_and_writes_parquet_batches(tmp_path: Path) -> None:
    input_path = tmp_path / "features.parquet"
    output_path = tmp_path / "predictions.parquet"
    model_path = tmp_path / "hybrid.joblib"
    feature_columns_path = tmp_path / "features.joblib"
    features = ["forecast_horizon_hours", "energy_at_origin"]
    joblib.dump(features, feature_columns_path)
    pd.DataFrame(
        {
            "id.grid.coarse": [1, 2, 3],
            "forecast_origin_timestamp": pd.to_datetime(
                ["2018-01-01", "2018-01-01", "2018-01-01"]
            ),
            "forecast_horizon_hours": [1, 1, 1],
            "energy_at_origin": [10.0, 20.0, 30.0],
            "target_energy": [9.0, 19.0, 29.0],
        }
    ).to_parquet(input_path, index=False)
    joblib.dump(
        {
            "original_model": ConstantModel(7.0),
            "log_model": ConstantModel(float(np.log1p(3.0))),
            "features": features,
            "routing": pd.DataFrame(
                {"grid_id": [1, 2], "selected_model": ["log", "original"]}
            ),
        },
        model_path,
    )
    settings = PipelineSettings(
        input_path=input_path,
        output_path=output_path,
        feature_columns_path=feature_columns_path,
        model_path=model_path,
        batch_size=2,
    )

    result = predict(settings)

    predictions = pd.read_parquet(result)
    assert predictions["selected_model"].tolist() == ["log", "original", "original"]
    assert predictions["prediction"].tolist() == pytest.approx([3.0, 7.0, 7.0])
    assert predictions["target_energy"].tolist() == [9.0, 19.0, 29.0]


def test_predict_requires_all_saved_model_features(tmp_path: Path) -> None:
    input_path = tmp_path / "features.parquet"
    feature_columns_path = tmp_path / "features.joblib"
    model_path = tmp_path / "hybrid.joblib"
    joblib.dump(["missing_feature"], feature_columns_path)
    pd.DataFrame({"id.grid.coarse": [1]}).to_parquet(input_path, index=False)
    joblib.dump(
        {
            "original_model": ConstantModel(1),
            "log_model": ConstantModel(1),
            "features": ["missing_feature"],
            "routing": pd.DataFrame(columns=["grid_id", "selected_model"]),
        },
        model_path,
    )
    settings = PipelineSettings(
        input_path=input_path,
        output_path=tmp_path / "predictions.parquet",
        feature_columns_path=feature_columns_path,
        model_path=model_path,
    )

    with pytest.raises(ValueError, match="missing model features"):
        predict(settings)
