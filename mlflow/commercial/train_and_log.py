"""Train the commercial LightGBM model and track it in its own MLflow experiment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from training.commercial_forecast.modeling import train_commercial_model  # noqa: E402


def main() -> int:
    result = train_commercial_model()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["promotion_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
