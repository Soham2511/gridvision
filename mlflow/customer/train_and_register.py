"""Run the customer bill training and MLflow registration workflow."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for import_path in (PROJECT_ROOT / "training", PROJECT_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from training.train_bill_prediction import main  # noqa: E402


if __name__ == "__main__":
    main()
