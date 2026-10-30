"""Run government hybrid-model training with comprehensive MLflow tracking."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = PROJECT_ROOT / "airflow" / "2_government_load_prediction"
for import_path in (PROJECT_ROOT, PIPELINE_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from grid_forecasting_pipeline.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.argv[1:1] = ["train"]
    main()
