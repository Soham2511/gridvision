from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PACKAGE_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PACKAGE_ROOT.parents[1]
DATA_ROOT = WORKSPACE_ROOT / "data" / "airflow" / "government"
DEFAULT_FEATURES = WORKSPACE_ROOT / "mlflow" / "government" / "feature_columns_2018.joblib"


class PipelineSettings(BaseModel):
    """Validated paths and resource settings shared by the CLI and Airflow."""

    model_config = ConfigDict(extra="forbid")

    input_path: Path = Field(
        default=(
            WORKSPACE_ROOT
            / "data"
            / "sample"
            / "training_sample_50000.parquet"
        )
    )
    output_path: Path = Field(default=DATA_ROOT / "training_ready_2018.parquet")
    feature_columns_path: Path = Field(default=DEFAULT_FEATURES)
    model_path: Path = Field(default=DATA_ROOT / "hybrid_grid_2018.joblib")
    memory_limit: str = "4GB"
    threads: int = Field(default=4, gt=0)
    horizon_hours: int = Field(default=24, ge=1, le=24)
    batch_size: int = Field(default=100_000, gt=0)
    max_training_rows: int = Field(default=1_000_000, gt=0)
    max_validation_rows: int = Field(default=250_000, gt=0)
    n_estimators: int = Field(default=1200, gt=0)

    @field_validator("memory_limit")
    @classmethod
    def validate_memory_limit(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9]\d*(?:KB|MB|GB|TB)", value.upper()):
            raise ValueError("memory_limit must look like '4GB' or '2048MB'")
        return value.upper()

    @classmethod
    def from_environment(cls) -> PipelineSettings:
        """Build settings from GOVERNMENT_PIPELINE_* environment variables."""
        env_fields: dict[str, tuple[str, Any]] = {
            "input_path": ("GOVERNMENT_PIPELINE_INPUT", Path),
            "output_path": ("GOVERNMENT_PIPELINE_OUTPUT", Path),
            "feature_columns_path": ("GOVERNMENT_PIPELINE_FEATURES", Path),
            "model_path": ("GOVERNMENT_PIPELINE_MODEL", Path),
            "memory_limit": ("GOVERNMENT_PIPELINE_MEMORY_LIMIT", str),
            "threads": ("GOVERNMENT_PIPELINE_THREADS", int),
            "horizon_hours": ("GOVERNMENT_PIPELINE_HORIZON_HOURS", int),
            "batch_size": ("GOVERNMENT_PIPELINE_BATCH_SIZE", int),
            "max_training_rows": ("GOVERNMENT_PIPELINE_MAX_TRAINING_ROWS", int),
            "max_validation_rows": ("GOVERNMENT_PIPELINE_MAX_VALIDATION_ROWS", int),
            "n_estimators": ("GOVERNMENT_PIPELINE_N_ESTIMATORS", int),
        }
        overrides = {
            field: converter(os.environ[variable])
            for field, (variable, converter) in env_fields.items()
            if variable in os.environ
        }
        return cls(**overrides)
