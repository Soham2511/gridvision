"""Training and tracking settings for the commercial building model."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("GRIDVISION_DATA_DIR", PROJECT_ROOT / "data")).resolve()
LOG_ROOT = Path(os.getenv("GRIDVISION_LOG_DIR", PROJECT_ROOT / "logs")).resolve()


@dataclass(frozen=True)
class CommercialTrainingSettings:
    gold_path: Path = DATA_ROOT / "gold" / "commercial_gold.parquet"
    dataset_manifest_path: Path = (
        DATA_ROOT / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json"
    )
    model_path: Path = PROJECT_ROOT / "models" / "commercial" / "building_forecast.joblib"
    experiment_name: str = "gridvision-commercial-building-forecasting"
    model_name: str = "gridvision-commercial-building-forecast"
    model_alias: str = "champion"
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    max_training_rows: int = 500_000
    max_validation_rows: int = 100_000
    max_test_rows: int = 100_000
    n_estimators: int = 500
    learning_rate: float = 0.05
    num_leaves: int = 31
    max_depth: int = -1
    min_child_samples: int = 30
    reg_lambda: float = 1.0
    n_jobs: int = 1
    random_state: int = 42
    max_validation_wape: float = 1.0
    require_baseline_improvement: bool = True
    seed: int = 42

    @classmethod
    def from_environment(cls) -> "CommercialTrainingSettings":
        """Create settings from commercial-specific environment variables."""
        defaults = cls()
        return cls(
            gold_path=Path(os.getenv("COMMERCIAL_GOLD_DATASET", str(defaults.gold_path))),
            dataset_manifest_path=Path(
                os.getenv("COMMERCIAL_GOLD_MANIFEST", str(defaults.dataset_manifest_path))
            ),
            model_path=Path(os.getenv("COMMERCIAL_MODEL_PATH", str(defaults.model_path))),
            experiment_name=os.getenv(
                "COMMERCIAL_MLFLOW_EXPERIMENT", defaults.experiment_name
            ),
            model_name=os.getenv("COMMERCIAL_MLFLOW_MODEL_NAME", defaults.model_name),
            model_alias=os.getenv("COMMERCIAL_MLFLOW_MODEL_ALIAS", defaults.model_alias),
            train_fraction=float(os.getenv("COMMERCIAL_TRAIN_FRACTION", "0.70")),
            validation_fraction=float(
                os.getenv("COMMERCIAL_VALIDATION_FRACTION", "0.15")
            ),
            max_training_rows=int(os.getenv("COMMERCIAL_MAX_TRAINING_ROWS", "500000")),
            max_validation_rows=int(os.getenv("COMMERCIAL_MAX_VALIDATION_ROWS", "100000")),
            max_test_rows=int(os.getenv("COMMERCIAL_MAX_TEST_ROWS", "100000")),
            n_estimators=int(os.getenv("COMMERCIAL_LGBM_N_ESTIMATORS", "500")),
            learning_rate=float(os.getenv("COMMERCIAL_LGBM_LEARNING_RATE", "0.05")),
            num_leaves=int(os.getenv("COMMERCIAL_LGBM_NUM_LEAVES", "31")),
            max_depth=int(os.getenv("COMMERCIAL_LGBM_MAX_DEPTH", "-1")),
            min_child_samples=int(os.getenv("COMMERCIAL_LGBM_MIN_CHILD_SAMPLES", "30")),
            reg_lambda=float(os.getenv("COMMERCIAL_LGBM_REG_LAMBDA", "1.0")),
            n_jobs=int(os.getenv("COMMERCIAL_LGBM_THREADS", "1")),
            random_state=int(os.getenv("COMMERCIAL_RANDOM_STATE", "42")),
            max_validation_wape=float(
                os.getenv("COMMERCIAL_MAX_VALIDATION_WAPE", "1.0")
            ),
            require_baseline_improvement=os.getenv(
                "COMMERCIAL_REQUIRE_BASELINE_IMPROVEMENT", "1"
            ).strip().lower() in {"1", "true", "yes"},
            seed=int(os.getenv("COMMERCIAL_SAMPLING_SEED", "42")),
        )

