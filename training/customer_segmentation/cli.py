"""Command line interface for Customer Segmentation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from .config import SegmentationSettings
from .pipeline import run_pipeline


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--window-end", type=date.fromisoformat)
    parser.add_argument("--window-months", type=int)
    parser.add_argument("--minimum-coverage", type=float)
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()
    settings = SegmentationSettings.from_environment()
    updates = {
        key: value
        for key, value in {
            "source_path": args.source,
            "output_dir": args.output_dir,
            "window_end": args.window_end,
            "window_months": args.window_months,
            "minimum_coverage": args.minimum_coverage,
        }.items()
        if value is not None
    }
    settings = replace(settings, **updates)
    if args.profile_only:
        from .data_pipeline import validate_source

        logging.getLogger("gridvision.segmentation").info(
            "Starting source-profile-only run; this does not create segmentation charts."
        )
        result = validate_source(settings)
    else:
        result = run_pipeline(settings, register_mlflow=not args.no_mlflow)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
