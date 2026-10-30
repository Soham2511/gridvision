"""Commercial-to-government grid mapping and join coverage tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from training.commercial_forecast.region_mapping import (
    join_building_forecasts,
    validate_grid_key_types,
)


def _fixtures(tmp_path: Path) -> tuple[Path, Path]:
    commercial = tmp_path / "commercial_predictions.parquet"
    government = tmp_path / "government_predictions.parquet"
    pd.DataFrame(
        {
            "OBJECTID": pd.Series([101, 202, 101], dtype="int64"),
            "id.grid.coarse": pd.Series([7, 9, 7], dtype="int64"),
            "target_timestamp": pd.to_datetime(
                ["2020-01-01 01:00", "2020-01-01 01:00", "2020-01-01 02:00"]
            ),
            "forecast_horizon_hours": pd.Series([1, 1, 2], dtype="int64"),
            "prediction": [12.0, 8.0, 13.0],
        }
    ).to_parquet(commercial, index=False)
    pd.DataFrame(
        {
            "id.grid.coarse": pd.Series([7], dtype="int64"),
            "target_timestamp": pd.to_datetime(["2020-01-01 01:00"]),
            "forecast_horizon_hours": pd.Series([1], dtype="int64"),
            "prediction": [250.0],
        }
    ).to_parquet(government, index=False)
    return commercial, government


def test_shared_grid_key_type_and_definition_are_explicit(tmp_path: Path) -> None:
    commercial, government = _fixtures(tmp_path)
    assert validate_grid_key_types(commercial, government) == {
        "commercial": "int64", "government": "int64"
    }


def test_join_reports_coverage_and_preserves_missing_grid_rows(tmp_path: Path) -> None:
    commercial, government = _fixtures(tmp_path)
    output, report_path = tmp_path / "joined.parquet", tmp_path / "coverage.json"
    report = join_building_forecasts(commercial, government, output, report_path)
    joined = pd.read_parquet(output).sort_values(["OBJECTID", "target_timestamp"])

    assert len(joined) == 3
    matched = joined[(joined["OBJECTID"] == 101) & (joined["forecast_horizon_hours"] == 1)].iloc[0]
    assert matched["total_grid_demand_prediction"] == 250.0
    assert matched["region_forecast_status"] == "matched"
    assert matched["region_forecast_scope"] == "total_grid_demand"
    missing_grid = joined[joined["OBJECTID"] == 202].iloc[0]
    assert pd.isna(missing_grid["total_grid_demand_prediction"])
    assert missing_grid["region_forecast_status"] == "missing_government_grid"
    unavailable = joined[(joined["OBJECTID"] == 101) & (joined["forecast_horizon_hours"] == 2)].iloc[0]
    assert unavailable["region_forecast_status"] == "government_forecast_unavailable"
    assert report["building_coverage"] == {
        "commercial_buildings": 2, "matched_buildings": 1, "unmatched_buildings": 1
    }
    assert report["grid_coverage"] == {
        "commercial_grids": 2, "matched_grids": 1, "unmatched_grids": 1
    }
    assert report["forecast_rows"] == {
        "total": 3, "matched": 1, "missing_grid": 1, "forecast_unavailable": 1
    }
    assert "all" in report["grid_definition"]
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_different_grid_key_types_are_rejected(tmp_path: Path) -> None:
    commercial, government = _fixtures(tmp_path)
    frame = pd.read_parquet(government)
    frame["id.grid.coarse"] = frame["id.grid.coarse"].astype("string")
    frame.to_parquet(government, index=False)
    with pytest.raises(TypeError, match="must be an integer"):
        validate_grid_key_types(commercial, government)
