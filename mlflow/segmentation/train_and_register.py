"""Standalone entrypoint for the Customer Segmentation training workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from training.customer_segmentation.config import SegmentationSettings  # noqa: E402
from training.customer_segmentation.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    result = run_pipeline(SegmentationSettings.from_environment(), register_mlflow=True)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
