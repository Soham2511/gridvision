"""Training, gating, reproducibility, and MLflow integration tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sys

import mlflow
import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMRegressor
from sklearn.base import BaseEstimator, RegressorMixin

from training.commercial_forecast.config import CommercialTrainingSettings
from training.commercial_forecast.features import FEATURE_COLUMNS, TARGET_COLUMN
from training.commercial_forecast.modeling import (
    CATEGORICAL_FEATURES,
    _features,
    _make_pipeline,
    chronological_boundaries,
    train_commercial_model,
)


class ConstantRegressor(BaseEstimator, RegressorMixin):
    """Deterministic estimator for workflow and registry integration tests."""

    def fit(self, features: pd.DataFrame, target: np.ndarray) -> "ConstantRegressor":
        self.constant_ = float(np.mean(target))
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.full(len(features), self.constant_, dtype=np.float64)


class ZeroRegressor(BaseEstimator, RegressorMixin):
    def fit(self, features: pd.DataFrame, target: np.ndarray) -> "ZeroRegressor":
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(features), dtype=np.float64)


def _gold_fixture(path: Path) -> Path:
    rows = []
    first = datetime(2020, 1, 1)
    for building_id in range(100, 104):
        for step in range(40):
            target_timestamp = first + timedelta(hours=step)
            for horizon in (1, 2):
                origin = target_timestamp - timedelta(hours=horizon)
                row = {feature: 1.0 for feature in FEATURE_COLUMNS}
                row.update(
                    {
                        "GeneralUseType": "Commercial",
                        "SpecificUseType": "Office",
                        "usetype": "office",
                        "building.type": "office",
                        "idf.kw": "small",
                        "forecast_horizon_hours": horizon,
                        "energy_at_origin": 1.0,
                        "target_hour": target_timestamp.hour,
                        "target_day_of_week": target_timestamp.weekday(),
                        "target_month": target_timestamp.month,
                        "target_is_weekend": int(target_timestamp.weekday() >= 5),
                        "target_day_of_month": target_timestamp.day,
                        "target_day_of_year": target_timestamp.timetuple().tm_yday,
                        "target_timestamp": target_timestamp,
                        "forecast_origin_timestamp": origin,
                        "OBJECTID": building_id,
                        "id.grid.coarse": 7,
                        TARGET_COLUMN: 100.0,
                    }
                )
                rows.append(row)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _settings(tmp_path: Path, gold_path: Path) -> CommercialTrainingSettings:
    manifest_path = tmp_path / "data" / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json"
    quality_path = tmp_path / "quality" / "gold_quality.json"
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    quality_path.write_text(json.dumps({"quality_passed": True}), encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "quality_passed": True,
                "dataset_version": "gold-test-v1",
                "dataset_path": str(gold_path.resolve()),
                "quality_report": str(quality_path),
            }
        ),
        encoding="utf-8",
    )
    return replace(
        CommercialTrainingSettings(),
        gold_path=gold_path,
        dataset_manifest_path=manifest_path,
        model_path=tmp_path / "models" / "commercial" / "building.joblib",
        max_training_rows=1_000,
        max_validation_rows=1_000,
        max_test_rows=1_000,
        n_estimators=8,
        min_child_samples=2,
        max_validation_wape=0.1,
        require_baseline_improvement=True,
    )


def test_feature_input_contract_is_fixed_and_ordered() -> None:
    assert len(FEATURE_COLUMNS) == 36
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))
    assert CATEGORICAL_FEATURES == [
        "GeneralUseType",
        "SpecificUseType",
        "usetype",
        "building.type",
        "idf.kw",
    ]
    frame = pd.DataFrame({feature: [1] for feature in FEATURE_COLUMNS})
    frame["GeneralUseType"] = "Commercial"
    frame["SpecificUseType"] = "Office"
    frame["usetype"] = "office"
    frame["building.type"] = "office"
    frame["idf.kw"] = "small"
    prepared = _features(frame)
    assert prepared.columns.tolist() == FEATURE_COLUMNS
    assert prepared["idf.kw"].iloc[0] == "small"
    with pytest.raises(ValueError, match="missing features"):
        _features(frame.drop(columns=[FEATURE_COLUMNS[0]]))


def test_pipeline_uses_deterministic_lightgbm_estimator() -> None:
    settings = replace(CommercialTrainingSettings(), n_estimators=17, random_state=9)
    estimator = _make_pipeline(settings).named_steps["model"]
    assert isinstance(estimator, LGBMRegressor)
    assert estimator.n_estimators == 17
    assert estimator.random_state == 9
    assert estimator.deterministic is True


def test_chronological_boundaries_are_strict_and_ordered() -> None:
    timestamps = pd.Series(pd.date_range("2024-01-01", periods=100, freq="h"))
    train_end, validation_end = chronological_boundaries(timestamps)
    assert timestamps.min() < train_end < validation_end < timestamps.max()
    with pytest.raises(ValueError, match="10 distinct"):
        chronological_boundaries(pd.Series(pd.date_range("2024-01-01", periods=5, freq="h")))


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="The installed Windows LightGBM native library crashes in DatasetSetField; run this smoke test in WSL/Linux.",
)
def test_lightgbm_fit_is_reproducible_on_small_data(tmp_path: Path) -> None:
    gold_path = _gold_fixture(tmp_path / "commercial_gold.parquet")
    gold = pd.read_parquet(gold_path)
    settings = replace(
        CommercialTrainingSettings(), n_estimators=8, min_child_samples=2
    )
    features = _features(gold)
    target = gold[TARGET_COLUMN].to_numpy(dtype=np.float64)
    first = _make_pipeline(settings).fit(features, target).predict(features)
    second = _make_pipeline(settings).fit(features, target).predict(features)
    assert first.shape == target.shape
    assert np.isfinite(first).all()
    np.testing.assert_allclose(first, second, rtol=0, atol=0)


def test_training_logs_and_registers_only_passing_reproducible_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gold_path = _gold_fixture(tmp_path / "commercial_gold.parquet")
    settings = _settings(tmp_path, gold_path)
    log_root = tmp_path / "logs"
    monkeypatch.setattr("training.commercial_forecast.modeling.LOG_ROOT", log_root)
    monkeypatch.setattr(
        "training.commercial_forecast.modeling._make_pipeline",
        lambda _: ConstantRegressor(),
    )
    tracking_uri = (tmp_path / "mlflow").as_uri()

    first = train_commercial_model(settings, tracking_uri=tracking_uri)
    second = train_commercial_model(settings, tracking_uri=tracking_uri)

    assert first["promotion_passed"] is True
    assert first["registered_model"] == settings.model_name
    assert first["registered_version"] == "1"
    champion = first["champion_model"]
    assert champion == second["champion_model"]
    assert set(first["metrics"]["validation"]) == {
        "lightgbm_direct", "lightgbm_log1p", "hist_gradient_boosting", "persistence_baseline"
    }
    assert first["metrics"]["test"][champion]["mae"] == second["metrics"]["test"][champion]["mae"]
    assert first["metrics"]["test"][champion]["rmse"] == second["metrics"]["test"][champion]["rmse"]
    assert first["metrics_by_horizon"]
    assert first["metrics_by_building"]
    assert first["split_ranges"]["train"]["max"] < first["split_ranges"]["validation"]["min"]
    assert first["split_ranges"]["validation"]["max"] < first["split_ranges"]["test"]["min"]
    assert Path(first["model_path"]).is_file()

    client = mlflow.MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name(settings.experiment_name)
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 2
    run = next(run for run in runs if run.info.run_id == first["run_id"])
    assert run.data.params["feature_order"] == json.dumps(FEATURE_COLUMNS)
    assert run.data.params["champion_model"] == champion
    assert run.data.metrics[f"test_{champion}_mae"] == first["metrics"]["test"][champion]["mae"]
    artifacts = client.list_artifacts(first["run_id"])
    assert {artifact.path for artifact in artifacts} >= {
        "dataset_quality",
        "evaluation",
        "commercial_model",
    }

    alias = client.get_model_version_by_alias(settings.model_name, settings.model_alias)
    assert int(alias.version) == 2
    registered_model = mlflow.pyfunc.load_model(
        f"models:/{settings.model_name}@{settings.model_alias}"
    )
    input_schema = registered_model.metadata.get_input_schema()
    assert input_schema is not None
    assert input_schema.input_names() == FEATURE_COLUMNS
    gold = pd.read_parquet(gold_path)
    prediction = registered_model.predict(_features(gold.head(4)))
    assert np.asarray(prediction).shape[0] == 4
    assert np.isfinite(np.asarray(prediction, dtype=float)).all()
    assert (np.asarray(prediction, dtype=float) >= 0).all()
    logged_quality_artifacts = client.list_artifacts(
        first["run_id"], "dataset_quality"
    )
    assert {Path(artifact.path).name for artifact in logged_quality_artifacts} >= {
        "latest.json",
        "gold_quality.json",
    }
    evaluation = json.loads(Path(first["metrics_path"]).read_text(encoding="utf-8"))
    assert evaluation["metrics_by_horizon"]
    assert evaluation["metrics_by_building"]


def test_failed_quality_gate_is_logged_but_not_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gold_path = _gold_fixture(tmp_path / "commercial_gold.parquet")
    settings = replace(
        _settings(tmp_path, gold_path),
        max_validation_wape=0.1,
        require_baseline_improvement=False,
    )
    monkeypatch.setattr(
        "training.commercial_forecast.modeling.LOG_ROOT", tmp_path / "logs"
    )
    monkeypatch.setattr(
        "training.commercial_forecast.modeling._make_candidate",
        lambda _, __: ZeroRegressor(),
    )
    result = train_commercial_model(settings, tracking_uri=(tmp_path / "mlflow").as_uri())
    assert result["promotion_passed"] is False
    assert result["registered_model"] is None
    assert result["status"] == "rejected"
    client = mlflow.MlflowClient(tracking_uri=(tmp_path / "mlflow").as_uri())
    experiment = client.get_experiment_by_name(settings.experiment_name)
    assert experiment is not None
    run = client.get_run(result["run_id"])
    assert run.data.tags["promotion_status"] == "rejected"
    assert any(artifact.path == "evaluation" for artifact in client.list_artifacts(result["run_id"]))
    assert client.search_registered_models(filter_string=f"name = '{settings.model_name}'") == []
