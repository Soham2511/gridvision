from __future__ import annotations

import csv
import math
import os
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ..paths import (
    ASSISTANT_OUTPUT_DIR,
    FORECAST_DATA_PATH,
    HISTORICAL_DATA_PATH,
    MODEL_PATH,
    PROJECT_ROOT,
    SIMULATIONS_DIR,
)

WORKSPACE_ROOT = PROJECT_ROOT
DEFAULT_HISTORICAL_DATA_PATH = HISTORICAL_DATA_PATH
DEFAULT_FORECAST_DATA_PATH = FORECAST_DATA_PATH
DEFAULT_MODEL_PATH = MODEL_PATH
DEFAULT_SIMULATIONS_DIR = SIMULATIONS_DIR
DEFAULT_ANALYSIS_OUTPUT_DIR = ASSISTANT_OUTPUT_DIR
HISTORICAL_DEMAND_COLUMN = "total_normalized_building_energy_kwh"
GRID_ID_COLUMN = "id.grid.coarse"
GRID_COUNT = 53
FORECAST_HOURS = 24
SUPPORTED_YEAR = 2018


class EnergyAnalysisError(ValueError):
    """Missing, unsupported, or inconsistent historical or predicted data."""


def _validate_date_range(start_date: str, end_date: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise EnergyAnalysisError("Dates must use YYYY-MM-DD format.") from exc
    if start.isoformat() != start_date or end.isoformat() != end_date:
        raise EnergyAnalysisError("Dates must use YYYY-MM-DD format.")
    if start.year != SUPPORTED_YEAR or end.year != SUPPORTED_YEAR:
        raise EnergyAnalysisError("Only energy data from 2018 is supported.")
    if end < start:
        raise EnergyAnalysisError("The analysis end date must not precede its start date.")
    return start, end


def _hour_window(
    start_date: date,
    end_date: date,
    start_timestamp: str | None,
    duration_hours: int | None,
) -> tuple[datetime, datetime]:
    if start_timestamp is None:
        return (
            datetime.combine(start_date, time.min),
            datetime.combine(end_date + timedelta(days=1), time.min),
        )
    try:
        start = datetime.fromisoformat(start_timestamp)
    except ValueError as exc:
        raise EnergyAnalysisError("Hourly analysis timestamps must use ISO 8601.") from exc
    if start.tzinfo is not None or start.minute or start.second or start.microsecond:
        raise EnergyAnalysisError(
            "Hourly analysis timestamps must be timezone-naive and hour-aligned."
        )
    if not start_date <= start.date() <= end_date:
        raise EnergyAnalysisError(
            "The selected hour must fall within the requested 2018 date range."
        )
    hours = duration_hours or 1
    if not 1 <= hours <= FORECAST_HOURS:
        raise EnergyAnalysisError("Hourly analysis duration must be from 1 to 24 hours.")
    end = start + timedelta(hours=hours)
    if end > datetime.combine(end_date + timedelta(days=1), time.min):
        raise EnergyAnalysisError(
            "The selected hourly window extends beyond the requested 2018 date range."
        )
    return start, end


@lru_cache(maxsize=4)
def available_grid_ids(
    historical_data_path: str = str(DEFAULT_HISTORICAL_DATA_PATH),
) -> tuple[int, ...]:
    path = Path(historical_data_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Historical energy data not found: {path}")
    try:
        with duckdb.connect() as connection:
            values = connection.execute(
                f'SELECT DISTINCT "{GRID_ID_COLUMN}" '
                "FROM read_parquet(?) WHERE timestamp IS NOT NULL ORDER BY 1",
                [str(path)],
            ).fetchall()
    except duckdb.Error as exc:
        raise EnergyAnalysisError("Unable to inspect the historical energy dataset.") from exc
    grid_ids = tuple(int(row[0]) for row in values)
    if len(grid_ids) != GRID_COUNT:
        raise EnergyAnalysisError(
            f"Historical data must contain exactly {GRID_COUNT} grids; found {len(grid_ids)}."
        )
    return grid_ids


def historical_demand_summary(
    start_date: str,
    end_date: str,
    grid_ids: list[int] | None = None,
    *,
    start_timestamp: str | None = None,
    duration_hours: int | None = None,
    historical_data_path: str | Path = DEFAULT_HISTORICAL_DATA_PATH,
) -> dict[str, Any]:
    """Aggregate actual 2018 demand data in Python/DuckDB, grouped by grid."""
    start, end = _validate_date_range(start_date, end_date)
    path = Path(historical_data_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Historical energy data not found: {path}")
    valid_grids = set(available_grid_ids(str(path)))
    window_start, window_end = _hour_window(
        start,
        end,
        start_timestamp,
        duration_hours,
    )
    selected_grids = sorted(set(grid_ids or []))
    unknown_grids = set(selected_grids) - valid_grids
    if unknown_grids:
        raise EnergyAnalysisError(f"Unknown grid IDs: {sorted(unknown_grids)}.")

    grid_filter = ""
    parameters: list[Any] = [
        str(path),
        window_start,
        window_end,
    ]
    if selected_grids:
        grid_filter = f' AND "{GRID_ID_COLUMN}" IN ({", ".join("?" for _ in selected_grids)})'
        parameters.extend(selected_grids)
    query = (
        f'SELECT "{GRID_ID_COLUMN}" AS grid_id, '
        f'count(DISTINCT timestamp) AS interval_count, '
        f'sum("{HISTORICAL_DEMAND_COLUMN}") AS total_demand_kwh, '
        f'avg("{HISTORICAL_DEMAND_COLUMN}") AS average_hourly_demand_kwh, '
        f'min("{HISTORICAL_DEMAND_COLUMN}") AS minimum_hourly_demand_kwh, '
        f'max("{HISTORICAL_DEMAND_COLUMN}") AS maximum_hourly_demand_kwh, '
        f'arg_max(timestamp, "{HISTORICAL_DEMAND_COLUMN}") AS peak_timestamp '
        "FROM read_parquet(?) "
        f'WHERE timestamp >= ? AND timestamp < ?{grid_filter} '
        f'AND "{HISTORICAL_DEMAND_COLUMN}" IS NOT NULL '
        f'GROUP BY "{GRID_ID_COLUMN}" ORDER BY grid_id'
    )
    try:
        with duckdb.connect() as connection:
            grid_rows = connection.execute(query, parameters).fetchdf()
    except duckdb.Error as exc:
        raise EnergyAnalysisError("Unable to analyze the historical energy dataset.") from exc
    if grid_rows.empty:
        raise EnergyAnalysisError(
            f"No historical energy records are available from {start} through {end}."
        )
    if selected_grids:
        missing_grids = set(selected_grids) - set(
            int(value) for value in grid_rows["grid_id"].tolist()
        )
        if missing_grids:
            raise EnergyAnalysisError(
                f"No historical records are available for grids {sorted(missing_grids)} "
                f"from {start} through {end}."
            )
    demand_columns = [
        "total_demand_kwh",
        "average_hourly_demand_kwh",
        "minimum_hourly_demand_kwh",
        "maximum_hourly_demand_kwh",
    ]
    demand_values = grid_rows[demand_columns].to_numpy().ravel()
    if not all(
        math.isfinite(float(value)) and float(value) >= 0
        for value in demand_values
    ):
        raise EnergyAnalysisError(
            "Historical demand contains non-finite or negative energy values."
        )

    hourly_query = (
        f'SELECT timestamp, sum("{HISTORICAL_DEMAND_COLUMN}") AS total_demand_kwh '
        "FROM read_parquet(?) "
        "WHERE timestamp >= ? AND timestamp < ?"
        f"{grid_filter} AND \"{HISTORICAL_DEMAND_COLUMN}\" IS NOT NULL "
        "GROUP BY timestamp ORDER BY timestamp"
    )
    try:
        with duckdb.connect() as connection:
            hourly = connection.execute(hourly_query, parameters).fetchdf()
    except duckdb.Error as exc:
        raise EnergyAnalysisError("Unable to aggregate historical hourly demand.") from exc

    returned_timestamps = pd.to_datetime(hourly["timestamp"])
    if (returned_timestamps < window_start).any() or (returned_timestamps >= window_end).any():
        raise EnergyAnalysisError(
            "Historical query returned records outside the requested time window."
        )
    expected_timestamps = pd.date_range(
        window_start,
        window_end - timedelta(hours=1),
        freq="h",
    )
    coverage_query = (
        f'SELECT "{GRID_ID_COLUMN}" AS grid_id, timestamp '
        "FROM read_parquet(?) WHERE timestamp >= ? AND timestamp < ?"
        f"{grid_filter} AND \"{HISTORICAL_DEMAND_COLUMN}\" IS NOT NULL"
    )
    try:
        with duckdb.connect() as connection:
            coverage_rows = connection.execute(
                coverage_query,
                parameters,
            ).fetchdf()
    except duckdb.Error as exc:
        raise EnergyAnalysisError(
            "Unable to validate historical timestamp coverage."
        ) from exc
    observed_by_grid = {
        int(grid_id): set(pd.to_datetime(rows).tolist())
        for grid_id, rows in coverage_rows.groupby("grid_id")["timestamp"]
    }

    per_grid = [
        {
            "grid_id": int(row.grid_id),
            "interval_count": int(row.interval_count),
            "total_demand_kwh": float(row.total_demand_kwh),
            "average_hourly_demand_kwh": float(row.average_hourly_demand_kwh),
            "minimum_hourly_demand_kwh": float(row.minimum_hourly_demand_kwh),
            "maximum_hourly_demand_kwh": float(row.maximum_hourly_demand_kwh),
            "peak_timestamp": pd.Timestamp(row.peak_timestamp).isoformat(),
        }
        for row in grid_rows.itertuples(index=False)
    ]
    for grid in per_grid:
        observed = observed_by_grid.get(grid["grid_id"], set())
        missing_timestamps = [
            timestamp.isoformat()
            for timestamp in expected_timestamps
            if timestamp.to_pydatetime() not in observed
        ]
        grid["expected_interval_count"] = len(expected_timestamps)
        grid["missing_interval_count"] = len(missing_timestamps)
        grid["missing_timestamps"] = missing_timestamps
        grid["coverage_complete"] = not missing_timestamps
    expected_grid_ids = set(selected_grids) if selected_grids else valid_grids
    missing_grid_ids = sorted(expected_grid_ids - set(observed_by_grid))
    timestamps_present = set(returned_timestamps.tolist())
    missing_network_timestamps = [
        timestamp.isoformat()
        for timestamp in expected_timestamps
        if timestamp.to_pydatetime() not in timestamps_present
    ]
    return {
        "source": "historical_measurements",
        "is_synthetic": False,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "grid_count": len(per_grid),
        "interval_count": int(hourly["timestamp"].nunique()),
        "expected_interval_count": len(expected_timestamps),
        "missing_network_timestamps": missing_network_timestamps,
        "missing_grid_ids": missing_grid_ids,
        "coverage_complete": (
            not missing_network_timestamps
            and not missing_grid_ids
            and all(grid["coverage_complete"] for grid in per_grid)
        ),
        "total_demand_kwh": float(grid_rows["total_demand_kwh"].sum()),
        "average_network_demand_kwh": float(hourly["total_demand_kwh"].mean()),
        "peak_network_demand_kwh": float(hourly["total_demand_kwh"].max()),
        "peak_network_timestamp": pd.Timestamp(
            hourly.loc[hourly["total_demand_kwh"].idxmax(), "timestamp"]
        ).isoformat(),
        "grid_totals": per_grid,
        "grid_ids": sorted(int(value) for value in grid_rows["grid_id"].tolist()),
        "covered_start_timestamp": pd.Timestamp(hourly["timestamp"].min()).isoformat(),
        "covered_end_timestamp": pd.Timestamp(hourly["timestamp"].max()).isoformat(),
    }


def _validate_prediction_frame(frame: pd.DataFrame, target_date: date) -> pd.DataFrame:
    required = {GRID_ID_COLUMN, "target_timestamp", "predicted_demand_kwh"}
    missing = required - set(frame.columns)
    if missing:
        raise EnergyAnalysisError(
            f"Saved forecast data is missing columns: {sorted(missing)}."
        )
    result = frame.copy()
    result[GRID_ID_COLUMN] = result[GRID_ID_COLUMN].astype(int)
    result["target_timestamp"] = pd.to_datetime(result["target_timestamp"])
    result["predicted_demand_kwh"] = pd.to_numeric(
        result["predicted_demand_kwh"], errors="raise"
    )
    if (
        result[GRID_ID_COLUMN].nunique() != GRID_COUNT
        or len(result) != GRID_COUNT * FORECAST_HOURS
    ):
        raise EnergyAnalysisError(
            f"A forecast must contain exactly {GRID_COUNT} grids and "
            f"{FORECAST_HOURS} hourly intervals."
        )
    if result.duplicated([GRID_ID_COLUMN, "target_timestamp"]).any():
        raise EnergyAnalysisError("Forecast contains duplicate grid/hour records.")
    expected_timestamps = {
        datetime.combine(target_date, time.min) + timedelta(hours=hour)
        for hour in range(FORECAST_HOURS)
    }
    if set(result["target_timestamp"].tolist()) != expected_timestamps:
        raise EnergyAnalysisError("Forecast does not cover the requested 2018 day.")
    if not result["predicted_demand_kwh"].map(math.isfinite).all():
        raise EnergyAnalysisError("Forecast contains non-finite demand values.")
    if (result["predicted_demand_kwh"] < 0).any():
        raise EnergyAnalysisError("Forecast contains negative demand values.")
    for _, grid_rows in result.groupby(GRID_ID_COLUMN):
        if len(grid_rows) != FORECAST_HOURS:
            raise EnergyAnalysisError("Every forecast grid must have all 24 hours.")
    return result.sort_values(["target_timestamp", GRID_ID_COLUMN]).reset_index(drop=True)


def _prediction_cache_path(
    target_date: date,
    output_dir: str | Path = DEFAULT_ANALYSIS_OUTPUT_DIR,
) -> Path:
    return (
        Path(output_dir).expanduser().resolve()
        / "predictions"
        / f"predicted_demand_{target_date.isoformat()}.parquet"
    )


@lru_cache(maxsize=1)
def _load_hybrid_model(model_path: str) -> Any:
    from .. import redistribution

    return redistribution.load_hybrid_model(model_path)


def _forecast_frame_for_date(
    parsed_date: date,
    *,
    simulations_dir: str | Path,
    forecast_data_path: str | Path,
    model_path: str | Path,
    output_dir: str | Path,
) -> pd.DataFrame:
    plan_path = Path(simulations_dir).expanduser().resolve() / (
        f"redistribution_plan_{parsed_date.isoformat()}.json"
    )
    if plan_path.is_file():
        from .data import load_simulation_json

        payload = load_simulation_json(parsed_date.isoformat(), simulations_dir)
        rows = [
            {
                GRID_ID_COLUMN: grid["grid_id"],
                "target_timestamp": hour["timestamp"],
                "predicted_demand_kwh": grid["predicted_demand_kwh"],
            }
            for hour in payload["hourly_results"]
            for grid in hour["grids"]
        ]
        frame = pd.DataFrame(rows)
    else:
        cache_path = _prediction_cache_path(parsed_date, output_dir)
        if cache_path.is_file():
            try:
                frame = pd.read_parquet(cache_path)
            except (OSError, ValueError) as exc:
                raise EnergyAnalysisError(
                    f"Unable to read saved forecast cache: {cache_path}"
                ) from exc
            metadata_columns = {
                GRID_ID_COLUMN,
                "target_timestamp",
                "forecast_horizon_hours",
                "centroid_latitude",
                "centroid_longitude",
                "selected_model",
            }
            if not metadata_columns.issubset(frame.columns):
                origin = datetime.combine(parsed_date - timedelta(days=1), time(hour=23))
                feature_path = Path(forecast_data_path).expanduser().resolve()
                try:
                    with duckdb.connect() as connection:
                        columns = {
                            row[0]
                            for row in connection.execute(
                                "DESCRIBE SELECT * FROM read_parquet(?)",
                                [str(feature_path)],
                            ).fetchall()
                        }
                        required_metadata = {
                            GRID_ID_COLUMN,
                            "forecast_origin_timestamp",
                            "target_timestamp",
                            "forecast_horizon_hours",
                            "centroid_latitude",
                            "centroid_longitude",
                        }
                        missing_metadata = required_metadata - columns
                        if missing_metadata:
                            raise EnergyAnalysisError(
                                "Saved forecast features are missing metadata: "
                                f"{sorted(missing_metadata)}."
                            )
                        metadata = connection.execute(
                            "SELECT "
                            f'"{GRID_ID_COLUMN}", "forecast_origin_timestamp", '
                            '"target_timestamp", "forecast_horizon_hours", '
                            '"centroid_latitude", "centroid_longitude" '
                            "FROM read_parquet(?) "
                            'WHERE "forecast_origin_timestamp" = ? '
                            f'ORDER BY "target_timestamp", "{GRID_ID_COLUMN}"',
                            [str(feature_path), origin],
                        ).fetchdf()
                    model = _load_hybrid_model(
                        str(Path(model_path).expanduser().resolve())
                    )
                except (duckdb.Error, FileNotFoundError, ValueError) as exc:
                    if isinstance(exc, EnergyAnalysisError):
                        raise
                    raise EnergyAnalysisError(
                        "Unable to restore saved forecast metadata for redistribution."
                    ) from exc
                if (
                    len(metadata) != GRID_COUNT * FORECAST_HOURS
                    or set(metadata[GRID_ID_COLUMN].astype(int)) != set(model.routing)
                ):
                    raise EnergyAnalysisError(
                        "Saved forecast metadata does not contain all 53 routed grids "
                        "and 24 hours."
                    )
                metadata[GRID_ID_COLUMN] = metadata[GRID_ID_COLUMN].astype(int)
                metadata["target_timestamp"] = pd.to_datetime(
                    metadata["target_timestamp"]
                )
                if metadata.duplicated([GRID_ID_COLUMN, "target_timestamp"]).any():
                    raise EnergyAnalysisError(
                        "Saved forecast metadata contains duplicate grid/hour rows."
                    )
                frame = _validate_prediction_frame(frame, parsed_date)
                frame = frame.drop(
                    columns=sorted(
                        metadata_columns - {GRID_ID_COLUMN, "target_timestamp"}
                    ),
                    errors="ignore",
                )
                frame = frame.merge(
                    metadata.drop(columns="forecast_origin_timestamp"),
                    on=[GRID_ID_COLUMN, "target_timestamp"],
                    how="left",
                    validate="one_to_one",
                )
                frame["selected_model"] = frame[GRID_ID_COLUMN].map(model.routing)
        else:
            origin = datetime.combine(parsed_date - timedelta(days=1), time(hour=23))
            try:
                model = _load_hybrid_model(
                    str(Path(model_path).expanduser().resolve())
                )
                from .. import redistribution

                frame = redistribution.generate_forecast(
                    model,
                    forecast_data_path=forecast_data_path,
                    origin=origin,
                )
            except (FileNotFoundError, ValueError) as exc:
                raise EnergyAnalysisError(
                    f"No supported model forecast is available for {parsed_date}: {exc}"
                ) from exc
            frame = _validate_prediction_frame(frame, parsed_date)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = cache_path.with_name(cache_path.name + ".tmp")
            try:
                frame.to_parquet(temporary_path, index=False)
                os.replace(temporary_path, cache_path)
            finally:
                temporary_path.unlink(missing_ok=True)
    return _validate_prediction_frame(frame, parsed_date)


def forecast_demand_for_date(
    target_date: str,
    grid_ids: list[int] | None = None,
    *,
    start_timestamp: str | None = None,
    duration_hours: int | None = None,
    simulations_dir: str | Path = DEFAULT_SIMULATIONS_DIR,
    forecast_data_path: str | Path = DEFAULT_FORECAST_DATA_PATH,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    output_dir: str | Path = DEFAULT_ANALYSIS_OUTPUT_DIR,
) -> dict[str, Any]:
    """Load an existing day plan or forecast one 2018 day with the saved model."""
    parsed_date, _ = _validate_date_range(target_date, target_date)
    frame = _forecast_frame_for_date(
        parsed_date,
        simulations_dir=simulations_dir,
        forecast_data_path=forecast_data_path,
        model_path=model_path,
        output_dir=output_dir,
    )
    selected_grids = sorted(set(grid_ids or []))
    valid_grids = set(int(value) for value in frame[GRID_ID_COLUMN].tolist())
    unknown_grids = set(selected_grids) - valid_grids
    if unknown_grids:
        raise EnergyAnalysisError(f"Unknown grid IDs: {sorted(unknown_grids)}.")
    if selected_grids:
        frame = frame[frame[GRID_ID_COLUMN].isin(selected_grids)]
    if start_timestamp is not None:
        window_start, window_end = _hour_window(
            parsed_date,
            parsed_date,
            start_timestamp,
            duration_hours,
        )
        frame = frame[
            (frame["target_timestamp"] >= window_start)
            & (frame["target_timestamp"] < window_end)
        ]
    if frame.empty:
        raise EnergyAnalysisError("No model predictions are available for the selected hour.")
    totals = (
        frame.groupby(GRID_ID_COLUMN)["predicted_demand_kwh"]
        .agg(["count", "sum", "mean", "min", "max"])
        .reset_index()
    )
    hourly = frame.groupby("target_timestamp")["predicted_demand_kwh"].sum()
    return {
        "source": "model_prediction",
        "is_synthetic": False,
        "forecast_date": parsed_date.isoformat(),
        "grid_count": int(totals[GRID_ID_COLUMN].nunique()),
        "interval_count": int(frame["target_timestamp"].nunique()),
        "total_predicted_demand_kwh": float(frame["predicted_demand_kwh"].sum()),
        "average_network_demand_kwh": float(hourly.mean()),
        "peak_network_demand_kwh": float(hourly.max()),
        "peak_network_timestamp": pd.Timestamp(hourly.idxmax()).isoformat(),
        "grid_totals": [
            {
                "grid_id": int(row[GRID_ID_COLUMN]),
                "interval_count": int(row["count"]),
                "total_predicted_demand_kwh": float(row["sum"]),
                "average_hourly_predicted_demand_kwh": float(row["mean"]),
                "minimum_hourly_predicted_demand_kwh": float(row["min"]),
                "maximum_hourly_predicted_demand_kwh": float(row["max"]),
            }
            for _, row in totals.iterrows()
        ],
        "grid_ids": sorted(int(value) for value in totals[GRID_ID_COLUMN].tolist()),
        "covered_start_timestamp": pd.Timestamp(frame["target_timestamp"].min()).isoformat(),
        "covered_end_timestamp": pd.Timestamp(frame["target_timestamp"].max()).isoformat(),
    }


def compare_historical_and_predicted_demand(
    target_date: str,
    grid_ids: list[int] | None = None,
    *,
    start_timestamp: str | None = None,
    duration_hours: int | None = None,
    simulations_dir: str | Path = DEFAULT_SIMULATIONS_DIR,
    forecast_data_path: str | Path = DEFAULT_FORECAST_DATA_PATH,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    output_dir: str | Path = DEFAULT_ANALYSIS_OUTPUT_DIR,
) -> dict[str, Any]:
    """Compare model predictions with the matching historical observed hours."""
    parsed_date, _ = _validate_date_range(target_date, target_date)
    path = DEFAULT_HISTORICAL_DATA_PATH.resolve()
    valid_grids = set(available_grid_ids(str(path)))
    selected_grids = sorted(set(grid_ids or []))
    window_start, window_end = _hour_window(
        parsed_date,
        parsed_date,
        start_timestamp,
        duration_hours,
    )
    unknown_grids = set(selected_grids) - valid_grids
    if unknown_grids:
        raise EnergyAnalysisError(f"Unknown grid IDs: {sorted(unknown_grids)}.")
    grid_filter = ""
    parameters: list[Any] = [
        str(path),
        window_start,
        window_end,
    ]
    if selected_grids:
        grid_filter = f' AND "{GRID_ID_COLUMN}" IN ({", ".join("?" for _ in selected_grids)})'
        parameters.extend(selected_grids)
    try:
        with duckdb.connect() as connection:
            actual_frame = connection.execute(
                f'SELECT "{GRID_ID_COLUMN}" AS grid_id, timestamp, '
                f'"{HISTORICAL_DEMAND_COLUMN}" AS historical_demand_kwh '
                "FROM read_parquet(?) "
                "WHERE timestamp >= ? AND timestamp < ?"
                f'{grid_filter} AND "{HISTORICAL_DEMAND_COLUMN}" IS NOT NULL',
                parameters,
            ).fetchdf()
    except duckdb.Error as exc:
        raise EnergyAnalysisError("Unable to load historical comparison data.") from exc
    if actual_frame.empty:
        raise EnergyAnalysisError(
            f"No historical energy records are available for {parsed_date}."
        )
    predicted_frame = _forecast_frame_for_date(
        parsed_date,
        simulations_dir=simulations_dir,
        forecast_data_path=forecast_data_path,
        model_path=model_path,
        output_dir=output_dir,
    )
    if selected_grids:
        predicted_frame = predicted_frame[
            predicted_frame[GRID_ID_COLUMN].isin(selected_grids)
        ]
    if start_timestamp is not None:
        predicted_frame = predicted_frame[
            (predicted_frame["target_timestamp"] >= window_start)
            & (predicted_frame["target_timestamp"] < window_end)
        ]
    actual_frame = actual_frame.rename(columns={"grid_id": GRID_ID_COLUMN})
    actual_frame["timestamp"] = pd.to_datetime(actual_frame["timestamp"])
    matched = actual_frame.merge(
        predicted_frame,
        left_on=[GRID_ID_COLUMN, "timestamp"],
        right_on=[GRID_ID_COLUMN, "target_timestamp"],
        how="inner",
        validate="one_to_one",
    )
    if matched.empty:
        raise EnergyAnalysisError(
            "Historical records do not overlap the selected model forecast hours."
        )
    expected_grids = set(selected_grids) if selected_grids else valid_grids
    missing_grids = expected_grids - set(
        int(value) for value in matched[GRID_ID_COLUMN].unique()
    )
    if missing_grids:
        raise EnergyAnalysisError(
            "Historical records do not overlap the selected forecast for grids "
            f"{sorted(missing_grids)}."
        )
    matched["prediction_error_kwh"] = (
        matched["predicted_demand_kwh"] - matched["historical_demand_kwh"]
    )
    matched["absolute_error_kwh"] = matched["prediction_error_kwh"].abs()
    matched["squared_error_kwh2"] = matched["prediction_error_kwh"] ** 2
    matched["percentage_error"] = (
        matched["absolute_error_kwh"] / matched["historical_demand_kwh"].abs()
    ).where(matched["historical_demand_kwh"] != 0)
    grouped = (
        matched.groupby(GRID_ID_COLUMN)
        .agg(
            interval_count=("timestamp", "nunique"),
            historical_demand_kwh=("historical_demand_kwh", "sum"),
            predicted_demand_kwh=("predicted_demand_kwh", "sum"),
            prediction_error_kwh=("prediction_error_kwh", "sum"),
            mae_kwh=("absolute_error_kwh", "mean"),
            mean_squared_error_kwh2=("squared_error_kwh2", "mean"),
            absolute_error_sum_kwh=("absolute_error_kwh", "sum"),
            actual_absolute_sum_kwh=(
                "historical_demand_kwh",
                lambda values: values.abs().sum(),
            ),
            mape_sum=("percentage_error", lambda values: values.dropna().sum()),
            mape_valid_count=("percentage_error", "count"),
        )
        .reset_index()
    )
    grid_comparisons = []
    for row in grouped.to_dict(orient="records"):
        actual_value = float(row["historical_demand_kwh"])
        predicted_value = float(row["predicted_demand_kwh"])
        difference = float(row["prediction_error_kwh"])
        actual_denominator = float(row["actual_absolute_sum_kwh"])
        wape = (
            float(row["absolute_error_sum_kwh"]) / actual_denominator * 100
            if actual_denominator > 0
            else None
        )
        mape_valid_count = int(row["mape_valid_count"])
        grid_comparisons.append(
            {
                "grid_id": int(row[GRID_ID_COLUMN]),
                "interval_count": int(row["interval_count"]),
                "historical_demand_kwh": actual_value,
                "predicted_demand_kwh": predicted_value,
                "prediction_error_kwh": difference,
                "mae_kwh": float(row["mae_kwh"]),
                "rmse_kwh": math.sqrt(float(row["mean_squared_error_kwh2"])),
                "mape_pct": (
                    float(row["mape_sum"]) / mape_valid_count * 100
                    if mape_valid_count
                    else None
                ),
                "mape_valid_interval_count": mape_valid_count,
                "wape_pct": wape,
            }
        )
    expected_interval_count = int(
        (window_end - window_start).total_seconds() // 3600
    )
    matched_by_timestamp = matched.groupby("timestamp", as_index=False).agg(
        historical_demand_kwh=("historical_demand_kwh", "sum"),
        predicted_demand_kwh=("predicted_demand_kwh", "sum"),
    )
    network_error = (
        matched_by_timestamp["predicted_demand_kwh"]
        - matched_by_timestamp["historical_demand_kwh"]
    )
    network_absolute_error = network_error.abs()
    network_actual_absolute = matched_by_timestamp["historical_demand_kwh"].abs()
    network_mape_mask = network_actual_absolute > 0
    network_mape = (
        float(
            (
                network_absolute_error[network_mape_mask]
                / network_actual_absolute[network_mape_mask]
            ).mean()
            * 100
        )
        if network_mape_mask.any()
        else None
    )
    network_actual_total = float(network_actual_absolute.sum())
    network_wape = (
        float(network_absolute_error.sum()) / network_actual_total * 100
        if network_actual_total > 0
        else None
    )
    expected_timestamps = pd.date_range(
        window_start,
        window_end - timedelta(hours=1),
        freq="h",
    )
    matched_timestamps = set(pd.to_datetime(matched["timestamp"]).tolist())
    missing_comparison_timestamps = [
        timestamp.isoformat()
        for timestamp in expected_timestamps
        if timestamp.to_pydatetime() not in matched_timestamps
    ]
    accuracy_is_complete = (
        not missing_comparison_timestamps
        and not missing_grids
        and all(
            grid["interval_count"] == expected_interval_count
            for grid in grid_comparisons
        )
    )
    incomplete_grid_ids = sorted(
        grid["grid_id"]
        for grid in grid_comparisons
        if grid["interval_count"] != expected_interval_count
    )
    expected_grid_ids = set(selected_grids) if selected_grids else valid_grids
    expected_pair_count = len(expected_grid_ids) * expected_interval_count
    missing_pair_count = max(0, expected_pair_count - len(matched))
    return {
        "source": "historical_and_model_prediction_comparison",
        "is_synthetic": False,
        "forecast_date": target_date,
        "interval_count": int(matched["timestamp"].nunique()),
        "expected_interval_count": expected_interval_count,
        "missing_timestamps": missing_comparison_timestamps,
        "missing_grid_ids": sorted(missing_grids),
        "incomplete_grid_ids": incomplete_grid_ids,
        "expected_grid_timestamp_pairs": expected_pair_count,
        "matched_grid_timestamp_pairs": int(len(matched)),
        "missing_grid_timestamp_pair_count": missing_pair_count,
        "coverage_complete": accuracy_is_complete,
        "grid_count": len(grid_comparisons),
        "historical_total_demand_kwh": float(matched["historical_demand_kwh"].sum()),
        "predicted_total_demand_kwh": float(matched["predicted_demand_kwh"].sum()),
        "grid_totals": grid_comparisons,
        "grid_ids": [row["grid_id"] for row in grid_comparisons],
        "network_accuracy": {
            "matched_hour_count": int(matched_by_timestamp.shape[0]),
            "mae_kwh": float(network_absolute_error.mean()),
            "rmse_kwh": float(math.sqrt(float((network_error**2).mean()))),
            "mape_pct": network_mape,
            "mape_valid_hour_count": int(network_mape_mask.sum()),
            "wape_pct": network_wape,
            "coverage_complete": accuracy_is_complete,
            "metrics_use_only_matched_grid_timestamp_pairs": True,
        },
        "metric_definitions": {
            "mae": "mean(abs(predicted_demand_kwh - historical_demand_kwh))",
            "rmse": "sqrt(mean((predicted_demand_kwh - historical_demand_kwh)^2))",
            "mape": "mean(abs(error / actual)) * 100; zero actuals are excluded",
            "wape": "sum(abs(error)) / sum(abs(actual)) * 100",
        },
    }


def format_analysis_report(
    result: dict[str, Any],
    *,
    detailed: bool = False,
) -> str:
    """Render factual analysis values from Python-produced result dictionaries."""
    lines: list[str] = []
    scope = "network" if result["grid_count"] == GRID_COUNT else "selected grid(s)"
    if result["source"] == "historical_measurements":
        lines.extend(
            [
                f"Historical energy data: {result['start_date']} through {result['end_date']}.",
                f"Observed energy demand: {result['total_demand_kwh']:.2f} kWh across "
                f"{result['grid_count']} grid(s) and {result['interval_count']} hourly intervals.",
                f"Observed timestamps: {result['covered_start_timestamp']} through "
                f"{result['covered_end_timestamp']}.",
                f"Hourly coverage: {result['interval_count']} of "
                f"{result['expected_interval_count']} expected network intervals; "
                f"complete={result['coverage_complete']}.",
                f"Average {scope} demand: {result['average_network_demand_kwh']:.2f} kWh per hour.",
                f"Peak {scope} demand: {result['peak_network_demand_kwh']:.2f} kWh at "
                f"{result['peak_network_timestamp']}.",
            ]
        )
        for grid in (
            result["grid_totals"] if detailed or result["grid_count"] == 1 else []
        ):
            lines.append(
                f"Grid {grid['grid_id']}: {grid['total_demand_kwh']:.2f} kWh total; "
                f"{grid['average_hourly_demand_kwh']:.2f} kWh average per recorded hour; "
                f"peak {grid['maximum_hourly_demand_kwh']:.2f} kWh at {grid['peak_timestamp']}."
            )
        if result["missing_grid_ids"]:
            lines.append(f"Grids with no records in this range: {result['missing_grid_ids']}.")
        if result["missing_network_timestamps"]:
            lines.append(
                f"Missing network timestamps: {result['missing_network_timestamps']}."
            )
        lines.append("Values are historical dataset records, not future forecasts.")
    elif result["source"] == "model_prediction":
        lines.extend(
            [
                f"Model forecast date: {result['forecast_date']}.",
                f"Predicted demand: {result['total_predicted_demand_kwh']:.2f} kWh across "
                f"{result['grid_count']} grid(s) and {result['interval_count']} hourly intervals.",
                f"Forecast timestamps: {result['covered_start_timestamp']} through "
                f"{result['covered_end_timestamp']}.",
                f"Forecast intervals available: {result['interval_count']} of "
                f"{FORECAST_HOURS} expected.",
                f"Average {scope} demand: {result['average_network_demand_kwh']:.2f} kWh per hour.",
                f"Peak {scope} demand: {result['peak_network_demand_kwh']:.2f} kWh at "
                f"{result['peak_network_timestamp']}.",
            ]
        )
        for grid in (
            result["grid_totals"] if detailed or result["grid_count"] == 1 else []
        ):
            lines.append(
                f"Grid {grid['grid_id']}: {grid['total_predicted_demand_kwh']:.2f} kWh "
                f"predicted; {grid['average_hourly_predicted_demand_kwh']:.2f} kWh "
                "average per hour."
            )
        lines.append(
            "These are model predictions; supply, network, and transmission losses "
            "are not part of this demand-only analysis."
        )
    else:
        lines.extend(
            [
                f"Historical versus predicted demand for {result['forecast_date']}.",
                f"Matched observed and predicted intervals: {result['interval_count']} of "
                f"{result['expected_interval_count']} expected; "
                f"coverage complete={result['coverage_complete']}.",
                f"Historical demand: {result['historical_total_demand_kwh']:.2f} kWh; "
                f"predicted demand: {result['predicted_total_demand_kwh']:.2f} kWh.",
                "Network-level accuracy (calculated over matched hours only): "
                f"WAPE {result['network_accuracy']['wape_pct']:.2f}%"
                if result["network_accuracy"]["wape_pct"] is not None
                else "Network-level WAPE unavailable because matched actual demand sums to zero.",
            ]
        )
        network_accuracy = result["network_accuracy"]
        lines.extend(
            [
                f"Network MAE: {network_accuracy['mae_kwh']:.2f} kWh; "
                f"RMSE: {network_accuracy['rmse_kwh']:.2f} kWh; "
                + (
                    f"MAPE: {network_accuracy['mape_pct']:.2f}%."
                    if network_accuracy["mape_pct"] is not None
                    else "MAPE unavailable because all matched actual values are zero."
                ),
                "Metric definitions: "
                "MAE = mean absolute error; RMSE = square root of mean squared error; "
                "MAPE = mean absolute percentage error excluding zero actuals; "
                "WAPE = sum of absolute errors / sum of absolute actuals × 100.",
            ]
        )
        if result["missing_grid_ids"] or result["incomplete_grid_ids"]:
            lines.append(
                f"Incomplete grid coverage: missing grids {result['missing_grid_ids']}; "
                f"grids missing one or more requested hours {result['incomplete_grid_ids']}."
            )
        if result["missing_timestamps"]:
            lines.append(f"Unmatched timestamps: {result['missing_timestamps']}.")
        if len(result["grid_totals"]) > 1:
            lines.extend(
                [
                    "| Grid | Matched hours | MAE (kWh) | RMSE (kWh) | MAPE (%) | WAPE (%) |",
                    "|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for grid in result["grid_totals"]:
                mape = (
                    f"{grid['mape_pct']:.2f}"
                    if grid["mape_pct"] is not None
                    else "n/a (zero actual)"
                )
                wape = (
                    f"{grid['wape_pct']:.2f}"
                    if grid["wape_pct"] is not None
                    else "n/a (zero actual)"
                )
                lines.append(
                    f"| {grid['grid_id']} | {grid['interval_count']} | "
                    f"{grid['mae_kwh']:.2f} | {grid['rmse_kwh']:.2f} | "
                    f"{mape} | {wape} |"
                )
        elif result["grid_totals"]:
            grid = result["grid_totals"][0]
            lines.append(
                f"Grid {grid['grid_id']} accuracy across {grid['interval_count']} "
                f"matched hours: MAE {grid['mae_kwh']:.2f} kWh; "
                f"RMSE {grid['rmse_kwh']:.2f} kWh; "
                + (
                    f"MAPE {grid['mape_pct']:.2f}%; "
                    if grid["mape_pct"] is not None
                    else "MAPE unavailable for zero actual demand; "
                )
                + (
                    f"WAPE {grid['wape_pct']:.2f}%."
                    if grid["wape_pct"] is not None
                    else "WAPE unavailable for zero actual demand."
                )
            )
        if detailed:
            for grid in result["grid_totals"]:
                lines.append(
                    f"Grid {grid['grid_id']} totals: actual "
                    f"{grid['historical_demand_kwh']:.2f} kWh; predicted "
                    f"{grid['predicted_demand_kwh']:.2f} kWh."
                )
        lines.append(
            "The historical values are recorded data; predicted values are model "
            "outputs, not measured future demand."
        )
    return "\n".join(lines)


def save_analysis_csv(
    result: dict[str, Any],
    *,
    output_dir: str | Path = DEFAULT_ANALYSIS_OUTPUT_DIR,
) -> Path:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    date_label = result.get("forecast_date") or (
        result.get("start_date", "2018") + "_to_" + result.get("end_date", "2018")
    )
    path = directory / f"energy_analysis_{date_label}.csv"
    rows = result["grid_totals"]
    fieldnames = sorted({key for row in rows for key in row})
    temporary_path = path.with_suffix(".csv.tmp")
    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def save_analysis_image(
    result: dict[str, Any],
    *,
    output_dir: str | Path = DEFAULT_ANALYSIS_OUTPUT_DIR,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    date_label = result.get("forecast_date") or (
        result.get("start_date", "2018") + "_to_" + result.get("end_date", "2018")
    )
    path = directory / f"energy_analysis_{date_label}.png"
    rows = result["grid_totals"]
    grid_ids = [str(row["grid_id"]) for row in rows]
    figure, axis = plt.subplots(figsize=(max(8, len(rows) * 0.18), 5))
    try:
        if result["source"] == "historical_and_model_prediction_comparison":
            actual = [row["historical_demand_kwh"] for row in rows]
            predicted = [row["predicted_demand_kwh"] for row in rows]
            positions = list(range(len(rows)))
            width = 0.4
            axis.bar(
                [position - width / 2 for position in positions],
                actual,
                width,
                label="Historical observed demand",
            )
            axis.bar(
                [position + width / 2 for position in positions],
                predicted,
                width,
                label="Model-predicted demand",
            )
            axis.legend()
        else:
            value_key = (
                "total_demand_kwh"
                if result["source"] == "historical_measurements"
                else "total_predicted_demand_kwh"
            )
            axis.bar(grid_ids, [row[value_key] for row in rows])
        axis.set_title(
            "Historical energy demand"
            if result["source"] == "historical_measurements"
            else "Model-predicted energy demand"
            if result["source"] == "model_prediction"
            else "Historical and model-predicted energy demand"
        )
        axis.set_xlabel("Grid ID")
        axis.set_ylabel("Energy demand (kWh)")
        axis.tick_params(axis="x", rotation=90)
        figure.tight_layout()
        temporary_path = path.with_suffix(".png.tmp")
        try:
            figure.savefig(temporary_path, format="png")
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
    finally:
        plt.close(figure)
    return path
