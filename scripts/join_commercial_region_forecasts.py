"""Join commercial building forecasts to government total-grid forecasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.commercial_forecast.region_mapping import join_building_forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commercial", type=Path, required=True, help="Building forecast parquet")
    parser.add_argument("--government", type=Path, required=True, help="Government grid prediction parquet")
    parser.add_argument("--output", type=Path, required=True, help="Joined forecast parquet")
    parser.add_argument("--report", type=Path, required=True, help="Mapping coverage JSON report")
    args = parser.parse_args()
    result = join_building_forecasts(args.commercial, args.government, args.output, args.report)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
