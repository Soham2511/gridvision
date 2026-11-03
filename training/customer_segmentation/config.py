"""Configuration for the independent building segmentation pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SegmentationSettings:
    source_path: Path
    output_dir: Path
    building_sample_fraction: float = 0.1
    window_end: date | None = None
    window_months: int = 12
    minimum_coverage: float = 0.9
    duckdb_memory_limit: str = "1GB"
    duckdb_threads: int = 1
    duckdb_temp_dir: Path = Path("/tmp/gridvision-segmentation-duckdb")
    minimum_category_size: int = 50
    minimum_cluster_size: int = 5
    minimum_cluster_fraction: float = 0.005
    correlation_threshold: float = 0.95
    random_seed: int = 42
    min_k: int = 2
    max_k: int = 10

    @classmethod
    def from_environment(cls) -> "SegmentationSettings":
        end = os.getenv("SEGMENTATION_WINDOW_END", "").strip()
        data_root = Path(
            os.getenv("GRIDVISION_DATA_DIR", PROJECT_ROOT / "data")
        ).expanduser()
        source_filename = os.getenv(
            "GRIDVISION_SOURCE_FILENAME", "training_sample_50000.parquet"
        )
        return cls(
            source_path=Path(
                os.getenv(
                    "SEGMENTATION_SOURCE_PATH",
                    data_root / "bronze" / source_filename,
                )
            ).expanduser(),
            output_dir=Path(
                os.getenv(
                    "SEGMENTATION_OUTPUT_DIR",
                    PROJECT_ROOT / "data" / "segmentation",
                )
            ).expanduser(),
            building_sample_fraction=float(
                os.getenv("SEGMENTATION_BUILDING_SAMPLE_FRACTION", "0.1")
            ),
            window_end=date.fromisoformat(end) if end else None,
            window_months=int(os.getenv("SEGMENTATION_WINDOW_MONTHS", "12")),
            minimum_coverage=float(os.getenv("SEGMENTATION_MIN_COVERAGE", "0.9")),
            duckdb_memory_limit=os.getenv("SEGMENTATION_DUCKDB_MEMORY_LIMIT", "1GB"),
            duckdb_threads=max(1, int(os.getenv("SEGMENTATION_DUCKDB_THREADS", "1"))),
            duckdb_temp_dir=Path(
                os.getenv(
                    "SEGMENTATION_DUCKDB_TEMP_DIR",
                    "/tmp/gridvision-segmentation-duckdb",
                )
            ).expanduser(),
            minimum_category_size=int(
                os.getenv("SEGMENTATION_MINIMUM_CATEGORY_SIZE", "50")
            ),
            minimum_cluster_size=int(os.getenv("SEGMENTATION_MINIMUM_CLUSTER_SIZE", "5")),
            minimum_cluster_fraction=float(
                os.getenv("SEGMENTATION_MINIMUM_CLUSTER_FRACTION", "0.005")
            ),
            correlation_threshold=float(
                os.getenv("SEGMENTATION_CORRELATION_THRESHOLD", "0.95")
            ),
            random_seed=int(os.getenv("SEGMENTATION_RANDOM_SEED", "42")),
            min_k=int(os.getenv("SEGMENTATION_MIN_K", "2")),
            max_k=int(os.getenv("SEGMENTATION_MAX_K", "10")),
        )

    def validate(self) -> None:
        if not 0 < self.building_sample_fraction <= 1:
            raise ValueError("building_sample_fraction must be in (0, 1]")
        if self.window_months <= 0:
            raise ValueError("window_months must be positive")
        if not 0 < self.minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be in (0, 1]")
        if self.minimum_category_size < 2:
            raise ValueError("minimum_category_size must be at least 2")
        if self.minimum_cluster_size < 2:
            raise ValueError("minimum_cluster_size must be at least 2")
        if not 0 <= self.minimum_cluster_fraction < 1:
            raise ValueError("minimum_cluster_fraction must be in [0, 1)")
        if not 0 < self.correlation_threshold <= 1:
            raise ValueError("correlation_threshold must be in (0, 1]")
        if self.min_k < 2 or self.max_k < self.min_k:
            raise ValueError("cluster range must satisfy 2 <= min_k <= max_k")
