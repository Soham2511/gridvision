"""Build the residential customer's Bronze, Silver, and Gold data layers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.data_engineering.pipeline import prepare_customer_data


def main() -> None:
    """Parse CLI options, build the customer layers, and print a summary."""
    parser = argparse.ArgumentParser(
        description="Prepare customer Parquet data layers from the raw snapshot."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="GridVision project root (default: detected from this script).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2048,
        help="Source timestamps processed per batch (default: 2048).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace customer Bronze/Silver/Gold outputs if they exist.",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive.")
    report = prepare_customer_data(
        args.project_root.resolve(),
        batch_size=args.batch_size,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "households": report["household_count"],
                "silver_interval_rows": report["interval_reading_count"],
                "gold_customer_days": report["gold"]["row_count"],
                "latest_customer_rows": report["gold"][
                    "latest_prediction_entity_count"
                ],
                "outputs": report["outputs"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
