"""Run GridVision anomaly data preparation, feature generation, and tracked training."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = (
    PROJECT_ROOT
    / "backend"
    / "app"
    / "models"
    / "anomaly_prediction"
    / "runtime"
)


def main() -> None:
    if str(RUNTIME_PATH) not in sys.path:
        sys.path.insert(0, str(RUNTIME_PATH))
    from gridvision_mlflow import main as train_and_track

    train_and_track()


if __name__ == "__main__":
    main()
