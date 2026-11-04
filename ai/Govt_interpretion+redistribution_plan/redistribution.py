from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd
from scipy.optimize import linprog

from .paths import (
    FORECAST_DATA_PATH,
    MODEL_PATH,
    NETWORK_PATH,
    PROJECT_ROOT,
    SIMULATIONS_DIR,
)

GRID_COUNT = 53
FORECAST_HOURS = 24
NEAREST_NEIGHBORS = 3
EARTH_RADIUS_KM = 6371.0088
DEFAULT_VARIATION_LIMIT = 0.10
DEFAULT_BASE_LOSS_PCT = 0.01
DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM = 0.0005
DEFAULT_MAXIMUM_LOSS_PCT = 0.08
DEFAULT_CAPACITY_KWH_PER_HOUR = 10_000.0
ENERGY_TOLERANCE_KWH = 1e-6
EXPECTED_FEATURE_COUNT = 36

WORKSPACE_ROOT = PROJECT_ROOT
DEFAULT_MODEL_PATH = MODEL_PATH
DEFAULT_FORECAST_DATA_PATH = FORECAST_DATA_PATH
DEFAULT_NETWORK_PATH = NETWORK_PATH
DEFAULT_OUTPUT_DIR = SIMULATIONS_DIR


@dataclass(frozen=True)
class HybridModel:
    original_model: Any
    log_model: Any
    features: list[str]
    routing: dict[Any, str]
    config: dict[str, Any]
    model_path: Path


def _python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(_python_scalar(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    value = _python_scalar(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Simulation output contains a non-finite numeric value")
    return value


def _load_joblib_artifact(path: Path) -> Any:
    """Load artifacts that contain StringDtype pickles from newer pandas.

    pandas versions before 2.2 do not accept ``na_value`` in StringDtype's
    constructor, although joblib artifacts produced by newer pandas pass it
    while unpickling.  The saved routing strings are converted to ordinary
    Python strings below, so for this short deserialization window the legacy
    constructor can safely ignore that newer constructor argument.
    """
    from pandas.core.arrays.string_ import StringDtype

    original_init = StringDtype.__init__
    try:
        parameters = inspect.signature(original_init).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "na_value" in parameters:
        return joblib.load(path)

    def compatible_init(
        self: Any, storage: str | None = None, na_value: Any = pd.NA
    ) -> None:
        del na_value
        original_init(self, storage=storage)

    StringDtype.__init__ = compatible_init
    try:
        return joblib.load(path)
    finally:
        StringDtype.__init__ = original_init


def _parse_origin(origin: str | date | datetime) -> tuple[datetime, bool]:
    date_only = False
    if isinstance(origin, datetime):
        timestamp = origin
    elif isinstance(origin, date):
        timestamp = datetime.combine(origin, time(hour=23))
        date_only = True
    elif isinstance(origin, str):
        value = origin.strip()
        if not value:
            raise ValueError("Forecast origin must not be empty")
        try:
            if len(value) == 10:
                timestamp = datetime.combine(date.fromisoformat(value), time(hour=23))
                date_only = True
            else:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                "Forecast origin must be an ISO 8601 date or datetime"
            ) from exc
    else:
        raise TypeError("Forecast origin must be a string, date, or datetime")

    if timestamp.tzinfo is not None and timestamp.utcoffset() is not None:
        raise ValueError(
            "Timezone-aware origins are not supported; model timestamps are naive"
        )
    if timestamp.minute or timestamp.second or timestamp.microsecond:
        raise ValueError("Forecast origin must align to an exact hour")
    return timestamp, date_only


def load_hybrid_model(model_path: str | Path = DEFAULT_MODEL_PATH) -> HybridModel:
    """Load and validate the saved hybrid model without changing its artifact."""
    path = Path(model_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Hybrid model artifact not found: {path}")
    artifact = _load_joblib_artifact(path)
    if not isinstance(artifact, dict):
        raise ValueError("Hybrid model artifact must be a dictionary")
    required_keys = {"original_model", "log_model", "features", "routing"}
    missing_keys = required_keys - artifact.keys()
    if missing_keys:
        raise ValueError(
            f"Hybrid model artifact is missing keys: {sorted(missing_keys)}"
        )

    features = artifact["features"]
    if (
        not isinstance(features, list)
        or len(features) != EXPECTED_FEATURE_COUNT
        or not all(isinstance(feature, str) for feature in features)
        or len(set(features)) != len(features)
    ):
        raise ValueError(
            f"Hybrid model must contain {EXPECTED_FEATURE_COUNT} unique ordered features"
        )

    routing_frame = artifact["routing"]
    if not isinstance(routing_frame, pd.DataFrame) or not {
        "grid_id",
        "selected_model",
    }.issubset(routing_frame.columns):
        raise ValueError("Hybrid model artifact has an invalid routing table")
    if len(routing_frame) != GRID_COUNT:
        raise ValueError(f"Hybrid model routing must contain exactly {GRID_COUNT} grids")
    # Avoid pandas ArrowStringArray operations here: older pandas can
    # deserialize a newer large_string array but cannot safely take/slice it.
    # The routing table is small, and only its scalar values are needed.
    grid_ids = routing_frame["grid_id"].tolist()
    selected_models = routing_frame["selected_model"].astype(object).tolist()
    if any(pd.isna(grid_id) for grid_id in grid_ids) or any(
        pd.isna(route) for route in selected_models
    ):
        raise ValueError("Hybrid model routing table contains null values")
    if len(set(grid_ids)) != len(grid_ids):
        raise ValueError("Hybrid model routing table contains duplicate grid IDs")
    invalid_routes = set(selected_models) - {"original", "log"}
    if invalid_routes:
        raise ValueError(f"Unknown model routes: {sorted(invalid_routes)}")

    for model_key in ("original_model", "log_model"):
        estimator = artifact[model_key]
        model_features = getattr(estimator, "feature_name_", None)
        if model_features and list(model_features) != features:
            raise ValueError(
                f"{model_key} feature order does not match the saved feature list"
            )

    return HybridModel(
        original_model=artifact["original_model"],
        log_model=artifact["log_model"],
        features=features,
        routing=dict(zip(grid_ids, selected_models, strict=True)),
        config=artifact.get("config", {}),
        model_path=path,
    )


def generate_forecast(
    model: HybridModel,
    forecast_data_path: str | Path = DEFAULT_FORECAST_DATA_PATH,
    origin: str | date | datetime = "2018-09-24",
) -> pd.DataFrame:
    """Predict 24 intervals for every grid using saved feature order and routing."""
    origin_timestamp, _ = _parse_origin(origin)
    data_path = Path(forecast_data_path).expanduser().resolve()
    if not data_path.is_file():
        raise FileNotFoundError(f"Forecast feature parquet not found: {data_path}")

    connection = duckdb.connect()
    try:
        schema_rows = connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(data_path)]
        ).fetchall()
        available = {row[0] for row in schema_rows}
        required = {
            "id.grid.coarse",
            "forecast_origin_timestamp",
            "target_timestamp",
            "forecast_horizon_hours",
            *model.features,
        }
        missing = sorted(required - available)
        if missing:
            raise ValueError(f"Forecast data is missing required columns: {missing}")

        selected = [
            '"id.grid.coarse"',
            '"forecast_origin_timestamp"',
            '"target_timestamp"',
            '"forecast_horizon_hours"',
            *(f'"{feature.replace(chr(34), chr(34) * 2)}"' for feature in model.features),
        ]
        query = (
            f"SELECT {', '.join(selected)} FROM read_parquet(?) "
            'WHERE "forecast_origin_timestamp" = ? '
            'ORDER BY "target_timestamp", "id.grid.coarse"'
        )
        frame = connection.execute(
            query, [str(data_path), origin_timestamp]
        ).fetchdf()
    finally:
        connection.close()

    if frame.empty:
        raise ValueError(
            f"No forecast features found for origin {origin_timestamp.isoformat()}"
        )
    if frame["id.grid.coarse"].nunique() != GRID_COUNT:
        raise ValueError(
            f"Forecast origin must include exactly {GRID_COUNT} grids; found "
            f"{frame['id.grid.coarse'].nunique()}"
        )
    if len(frame) != GRID_COUNT * FORECAST_HOURS:
        raise ValueError(
            f"Expected exactly {GRID_COUNT * FORECAST_HOURS} forecast rows; "
            f"found {len(frame)}"
        )
    if frame.duplicated(["id.grid.coarse", "forecast_horizon_hours"]).any():
        raise ValueError("Forecast data contains duplicate grid/horizon rows")
    horizons = set(frame["forecast_horizon_hours"].astype(int))
    if horizons != set(range(1, FORECAST_HOURS + 1)):
        raise ValueError("Forecast data must contain all horizons 1 through 24")
    if set(frame["id.grid.coarse"]) != set(model.routing):
        raise ValueError("Forecast grid IDs do not match model routing assignments")
    for _, grid_rows in frame.groupby("id.grid.coarse", sort=False):
        if set(grid_rows["forecast_horizon_hours"].astype(int)) != horizons:
            raise ValueError("Every grid must have all 24 forecast horizons")
    expected_timestamps = {
        origin_timestamp + pd.Timedelta(hours=horizon)
        for horizon in range(1, FORECAST_HOURS + 1)
    }
    if set(pd.to_datetime(frame["target_timestamp"])) != expected_timestamps:
        raise ValueError("Forecast target timestamps do not match hourly horizons")

    # Keep the artifact's order; infinities follow the legacy path and become nulls.
    features = frame.loc[:, model.features].astype(np.float32)
    features = features.replace([np.inf, -np.inf], np.nan)
    selected_models = frame["id.grid.coarse"].map(model.routing).to_numpy()
    predictions = np.empty(len(frame), dtype=np.float64)
    for model_name, estimator in (
        ("original", model.original_model),
        ("log", model.log_model),
    ):
        positions = np.flatnonzero(selected_models == model_name)
        if not positions.size:
            continue
        values = np.asarray(estimator.predict(features.iloc[positions]), dtype=np.float64)
        if model_name == "log":
            values = np.expm1(np.maximum(values, 0))
        predictions[positions] = values
    if not np.isfinite(predictions).all():
        raise ValueError("Hybrid model produced non-finite demand predictions")
    if (predictions < 0).any():
        raise ValueError(
            "Hybrid model produced negative demand; refusing to create negative "
            "synthetic supply"
        )

    result = frame.loc[
        :,
        [
            "id.grid.coarse",
            "forecast_origin_timestamp",
            "target_timestamp",
            "forecast_horizon_hours",
            "centroid_latitude",
            "centroid_longitude",
        ],
    ].copy()
    result["selected_model"] = selected_models
    result["predicted_demand_kwh"] = predictions
    return result


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance between two latitude/longitude coordinates."""
    coordinates = (latitude_a, longitude_a, latitude_b, longitude_b)
    if not all(math.isfinite(float(value)) for value in coordinates):
        raise ValueError("Grid centroid coordinates must be finite")
    if not -90 <= latitude_a <= 90 or not -90 <= latitude_b <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not -180 <= longitude_a <= 180 or not -180 <= longitude_b <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees")

    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, haversine)))


def calculate_transmission_loss(
    distance_km: float,
    energy_sent_kwh: float,
    *,
    base_loss_pct: float = DEFAULT_BASE_LOSS_PCT,
    additional_loss_pct_per_km: float = DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM,
    maximum_loss_pct: float = DEFAULT_MAXIMUM_LOSS_PCT,
) -> dict[str, float]:
    """Calculate synthetic sent, lost, and received energy for one transfer."""
    values = (
        distance_km,
        energy_sent_kwh,
        base_loss_pct,
        additional_loss_pct_per_km,
        maximum_loss_pct,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Transmission loss inputs must be finite")
    if distance_km < 0 or energy_sent_kwh < 0:
        raise ValueError("Distance and sent energy must be non-negative")
    if not 0 <= base_loss_pct <= maximum_loss_pct < 1:
        raise ValueError("Loss fractions must satisfy 0 <= base <= maximum < 1")
    if additional_loss_pct_per_km < 0:
        raise ValueError("Distance-based loss rate must be non-negative")

    loss_pct = min(
        maximum_loss_pct,
        base_loss_pct + additional_loss_pct_per_km * distance_km,
    )
    energy_lost = energy_sent_kwh * loss_pct
    energy_received = energy_sent_kwh - energy_lost
    if not math.isclose(
        energy_sent_kwh, energy_received + energy_lost, abs_tol=ENERGY_TOLERANCE_KWH
    ):
        raise ArithmeticError("Transfer energy conservation check failed")
    return {
        "energy_sent_kwh": float(energy_sent_kwh),
        "energy_lost_kwh": float(energy_lost),
        "energy_received_kwh": float(energy_received),
        "loss_pct": float(loss_pct),
    }


def _grid_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"id.grid.coarse", "centroid_latitude", "centroid_longitude"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Grid metadata is missing columns: {sorted(missing)}")
    result = frame.loc[:, sorted(required)].drop_duplicates()
    if result["id.grid.coarse"].duplicated().any():
        raise ValueError("Grid metadata contains conflicting centroids for a grid")
    if len(result) != GRID_COUNT:
        raise ValueError(f"Grid metadata must contain exactly {GRID_COUNT} grids")
    result = result.sort_values("id.grid.coarse").reset_index(drop=True)
    if result[["centroid_latitude", "centroid_longitude"]].isna().any().any():
        raise ValueError("Grid metadata contains missing centroid coordinates")
    return result


def _network_configuration(
    neighbor_count: int,
    capacity_kwh_per_hour: float,
    base_loss_pct: float,
    additional_loss_pct_per_km: float,
    maximum_loss_pct: float,
) -> dict[str, Any]:
    if neighbor_count < 1 or neighbor_count >= GRID_COUNT:
        raise ValueError(f"neighbor_count must be between 1 and {GRID_COUNT - 1}")
    if not math.isfinite(capacity_kwh_per_hour) or capacity_kwh_per_hour <= 0:
        raise ValueError("Synthetic edge capacity must be finite and positive")
    calculate_transmission_loss(
        0,
        0,
        base_loss_pct=base_loss_pct,
        additional_loss_pct_per_km=additional_loss_pct_per_km,
        maximum_loss_pct=maximum_loss_pct,
    )
    return {
        "neighbor_count": neighbor_count,
        "capacity_kwh_per_hour": float(capacity_kwh_per_hour),
        "earth_radius_km": EARTH_RADIUS_KM,
        "loss_parameters": {
            "base_loss_pct": float(base_loss_pct),
            "additional_loss_pct_per_km": float(additional_loss_pct_per_km),
            "maximum_loss_pct": float(maximum_loss_pct),
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(_json_safe(payload), file, indent=2, allow_nan=False)
            file.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_grid_network(
    grid_metadata: pd.DataFrame,
    *,
    network_path: str | Path | None = DEFAULT_NETWORK_PATH,
    neighbor_count: int = NEAREST_NEIGHBORS,
    capacity_kwh_per_hour: float = DEFAULT_CAPACITY_KWH_PER_HOUR,
    base_loss_pct: float = DEFAULT_BASE_LOSS_PCT,
    additional_loss_pct_per_km: float = DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM,
    maximum_loss_pct: float = DEFAULT_MAXIMUM_LOSS_PCT,
) -> dict[str, Any]:
    """Build and persist an undirected, unique, nearest-neighbor network."""
    grids = _grid_metadata(grid_metadata)
    configuration = _network_configuration(
        neighbor_count,
        capacity_kwh_per_hour,
        base_loss_pct,
        additional_loss_pct_per_km,
        maximum_loss_pct,
    )
    grid_records = [
        {
            "grid_id": _python_scalar(row["id.grid.coarse"]),
            "centroid_latitude": float(row["centroid_latitude"]),
            "centroid_longitude": float(row["centroid_longitude"]),
        }
        for _, row in grids.iterrows()
    ]

    path = Path(network_path).expanduser().resolve() if network_path else None
    if path is not None and path.is_file():
        with path.open(encoding="utf-8") as file:
            existing = json.load(file)
        if existing.get("grids") != _json_safe(grid_records):
            if path != DEFAULT_NETWORK_PATH.resolve():
                raise ValueError(
                    f"Persisted network {path} does not match current grid metadata; "
                    "choose a new network path to build a different network"
                )
            # Keep the prior synthetic network intact. Store a deterministic
            # network keyed to the new grid metadata, so updated model inputs
            # can run without silently replacing a user's existing network.
            fingerprint_input = json.dumps(
                {"grids": _json_safe(grid_records), "configuration": configuration},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            fingerprint = hashlib.sha256(fingerprint_input).hexdigest()[:12]
            path = path.with_name(f"{path.stem}_{fingerprint}{path.suffix}")
            if path.is_file():
                with path.open(encoding="utf-8") as file:
                    existing = json.load(file)
                if (
                    existing.get("grids") != _json_safe(grid_records)
                    or existing.get("configuration") != configuration
                    or not isinstance(existing.get("connections"), list)
                ):
                    raise ValueError(f"Persisted network is invalid: {path}")
                return existing
            # Continue below to build and persist the versioned network.
            existing = None
        if existing is not None and existing.get("configuration") != configuration:
            raise ValueError(
                f"Persisted network {path} uses different network parameters; "
                "choose a new network path to change them"
            )
        if existing is not None and not isinstance(existing.get("connections"), list):
            raise ValueError(f"Persisted network is invalid: {path}")
        if existing is not None:
            return existing

    ids = [record["grid_id"] for record in grid_records]
    coordinates = {
        record["grid_id"]: (
            record["centroid_latitude"],
            record["centroid_longitude"],
        )
        for record in grid_records
    }
    edge_keys: set[tuple[Any, Any]] = set()
    for grid_id in ids:
        latitude, longitude = coordinates[grid_id]
        neighbors = []
        for other_id in ids:
            if other_id == grid_id:
                continue
            other_latitude, other_longitude = coordinates[other_id]
            distance = haversine_distance_km(
                latitude, longitude, other_latitude, other_longitude
            )
            neighbors.append((distance, other_id))
        neighbors.sort(key=lambda pair: (pair[0], pair[1]))
        edge_keys.update(tuple(sorted((grid_id, other_id))) for _, other_id in neighbors[:neighbor_count])

    loss_parameters = configuration["loss_parameters"]
    connections = []
    for left, right in sorted(edge_keys):
        distance = haversine_distance_km(
            *coordinates[left], *coordinates[right]
        )
        loss_pct = min(
            loss_parameters["maximum_loss_pct"],
            loss_parameters["base_loss_pct"]
            + loss_parameters["additional_loss_pct_per_km"] * distance,
        )
        connections.append(
            {
                "grid_a_id": _python_scalar(left),
                "grid_b_id": _python_scalar(right),
                "distance_km": distance,
                "capacity_kwh_per_hour": configuration["capacity_kwh_per_hour"],
                "loss_pct": loss_pct,
            }
        )

    network = {
        "grid_count": GRID_COUNT,
        "connection_count": len(connections),
        "grids": grid_records,
        "configuration": configuration,
        "connections": connections,
    }
    if path is not None:
        _atomic_write_json(path, network)
    return network


def generate_synthetic_supply(
    forecast: pd.DataFrame,
    *,
    random_seed: int = 42,
    variation_limit: float = DEFAULT_VARIATION_LIMIT,
) -> pd.DataFrame:
    """Add independently sampled synthetic supply while retaining model demand."""
    if not math.isfinite(variation_limit) or not 0 <= variation_limit <= 0.10:
        raise ValueError("variation_limit must be between 0 and 0.10")
    required = {
        "id.grid.coarse",
        "target_timestamp",
        "predicted_demand_kwh",
    }
    missing = required - set(forecast.columns)
    if missing:
        raise ValueError(f"Forecast is missing required columns: {sorted(missing)}")
    if (forecast["predicted_demand_kwh"] < 0).any():
        raise ValueError("Predicted demand must be non-negative")
    if not np.isfinite(forecast["predicted_demand_kwh"].to_numpy(dtype=float)).all():
        raise ValueError("Predicted demand must be finite")

    result = forecast.copy()
    stable_order = result.sort_values(
        ["target_timestamp", "id.grid.coarse"], kind="stable"
    ).index
    rng = np.random.default_rng(random_seed)
    variations = pd.Series(
        rng.uniform(-variation_limit, variation_limit, size=len(result)),
        index=stable_order,
    ).reindex(result.index)
    result["supply_variation"] = variations.to_numpy(dtype=np.float64)
    result["synthetic_supply_kwh"] = (
        result["predicted_demand_kwh"] * (1 + result["supply_variation"])
    )
    if (result["synthetic_supply_kwh"] < 0).any():
        raise ArithmeticError("Synthetic supply cannot be negative")
    return result


def calculate_grid_balance(
    forecast: pd.DataFrame,
    synthetic_supply: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate initial per-grid surplus and deficit for each forecast hour."""
    keys = ["id.grid.coarse", "target_timestamp"]
    if forecast.duplicated(keys).any() or synthetic_supply.duplicated(keys).any():
        raise ValueError("Forecast and supply must have unique grid/hour rows")
    if set(map(tuple, forecast[keys].to_numpy())) != set(
        map(tuple, synthetic_supply[keys].to_numpy())
    ):
        raise ValueError("Forecast and synthetic supply grid/hour rows do not match")
    supply_columns = [*keys, "synthetic_supply_kwh"]
    if "supply_variation" in synthetic_supply.columns:
        supply_columns.append("supply_variation")
    supply = synthetic_supply.loc[:, supply_columns]
    balance = forecast.merge(supply, on=keys, how="inner", validate="one_to_one")
    net = balance["synthetic_supply_kwh"] - balance["predicted_demand_kwh"]
    balance["initial_surplus_kwh"] = net.clip(lower=0)
    balance["initial_deficit_kwh"] = (-net).clip(lower=0)
    return balance


def optimize_redistribution(
    hourly_balance: pd.DataFrame,
    network: dict[str, Any],
) -> list[dict[str, Any]]:
    """Minimize unmet demand first, then losses, using direct-neighbor LP flows."""
    if hourly_balance["target_timestamp"].nunique() > 1:
        raise ValueError("Redistribution optimization accepts one forecast hour")
    balances = hourly_balance.set_index("id.grid.coarse")
    surplus = balances["initial_surplus_kwh"].astype(float).to_dict()
    deficit = balances["initial_deficit_kwh"].astype(float).to_dict()
    if any(value < 0 or not math.isfinite(value) for value in (*surplus.values(), *deficit.values())):
        raise ValueError("Grid surpluses and deficits must be finite and non-negative")

    arcs: list[dict[str, Any]] = []
    for edge in network["connections"]:
        left, right = edge["grid_a_id"], edge["grid_b_id"]
        if left not in balances.index or right not in balances.index:
            raise ValueError("Network connection references a grid absent this hour")
        for source, destination in ((left, right), (right, left)):
            if surplus[source] > ENERGY_TOLERANCE_KWH and deficit[destination] > ENERGY_TOLERANCE_KWH:
                arcs.append(
                    {
                        "source": source,
                        "destination": destination,
                        "edge": edge,
                        "loss_pct": float(edge["loss_pct"]),
                    }
                )
    deficit_grids = [
        grid_id
        for grid_id, value in deficit.items()
        if value > ENERGY_TOLERANCE_KWH
    ]
    if not arcs or not deficit_grids:
        return []

    arc_count = len(arcs)
    variable_count = arc_count + len(deficit_grids)
    unmet_offset = arc_count
    source_grids = list(surplus)
    edge_keys = {
        tuple(sorted((edge["grid_a_id"], edge["grid_b_id"])))
        for edge in network["connections"]
    }

    inequality_rows: list[np.ndarray] = []
    inequality_bounds: list[float] = []
    for source in source_grids:
        row = np.zeros(variable_count)
        for index, arc in enumerate(arcs):
            if arc["source"] == source:
                row[index] = 1
        if np.any(row):
            inequality_rows.append(row)
            inequality_bounds.append(surplus[source])
    for edge_key in sorted(edge_keys):
        row = np.zeros(variable_count)
        for index, arc in enumerate(arcs):
            if tuple(sorted((arc["source"], arc["destination"]))) == edge_key:
                row[index] = 1
        if np.any(row):
            edge = next(
                edge
                for edge in network["connections"]
                if tuple(sorted((edge["grid_a_id"], edge["grid_b_id"]))) == edge_key
            )
            inequality_rows.append(row)
            inequality_bounds.append(float(edge["capacity_kwh_per_hour"]))

    equality_rows: list[np.ndarray] = []
    equality_bounds: list[float] = []
    for unmet_index, destination in enumerate(deficit_grids):
        row = np.zeros(variable_count)
        for index, arc in enumerate(arcs):
            if arc["destination"] == destination:
                row[index] = 1 - arc["loss_pct"]
        row[unmet_offset + unmet_index] = 1
        equality_rows.append(row)
        equality_bounds.append(deficit[destination])

    bounds = [(0, None)] * variable_count
    constraints = {
        "A_ub": np.vstack(inequality_rows) if inequality_rows else None,
        "b_ub": np.asarray(inequality_bounds) if inequality_bounds else None,
        "A_eq": np.vstack(equality_rows),
        "b_eq": np.asarray(equality_bounds),
        "bounds": bounds,
        "method": "highs",
    }
    first_objective = np.zeros(variable_count)
    first_objective[unmet_offset:] = 1
    minimum_unmet = linprog(first_objective, **constraints)
    if not minimum_unmet.success:
        raise RuntimeError(f"Redistribution optimization failed: {minimum_unmet.message}")

    loss_objective = np.zeros(variable_count)
    loss_objective[:arc_count] = [arc["loss_pct"] for arc in arcs]
    unmet_constraint = np.zeros(variable_count)
    unmet_constraint[unmet_offset:] = 1
    second_A_ub = (
        np.vstack([constraints["A_ub"], unmet_constraint])
        if constraints["A_ub"] is not None
        else unmet_constraint.reshape(1, -1)
    )
    second_b_ub = np.append(
        constraints["b_ub"]
        if constraints["b_ub"] is not None
        else np.asarray([], dtype=float),
        float(minimum_unmet.fun) + ENERGY_TOLERANCE_KWH,
    )
    minimum_loss = linprog(
        loss_objective,
        **{
            **constraints,
            "A_ub": second_A_ub,
            "b_ub": second_b_ub,
        },
    )
    if not minimum_loss.success:
        raise RuntimeError(f"Loss optimization failed: {minimum_loss.message}")

    timestamp = pd.Timestamp(hourly_balance["target_timestamp"].iloc[0]).isoformat()
    transfers = []
    for index, arc in enumerate(arcs):
        sent = float(minimum_loss.x[index])
        if sent <= ENERGY_TOLERANCE_KWH:
            continue
        edge = arc["edge"]
        if tuple(sorted((arc["source"], arc["destination"]))) not in edge_keys:
            raise ArithmeticError("Optimizer produced a transfer on a nonexistent edge")
        if sent > float(edge["capacity_kwh_per_hour"]) + ENERGY_TOLERANCE_KWH:
            raise ArithmeticError("Optimizer exceeded an edge transfer capacity")
        amounts = calculate_transmission_loss(
            float(edge["distance_km"]),
            sent,
            base_loss_pct=float(network["configuration"]["loss_parameters"]["base_loss_pct"]),
            additional_loss_pct_per_km=float(
                network["configuration"]["loss_parameters"][
                    "additional_loss_pct_per_km"
                ]
            ),
            maximum_loss_pct=float(
                network["configuration"]["loss_parameters"]["maximum_loss_pct"]
            ),
        )
        if not math.isclose(
            amounts["loss_pct"], arc["loss_pct"], abs_tol=ENERGY_TOLERANCE_KWH
        ):
            raise ValueError("Connection loss does not match the network configuration")
        transfers.append(
            {
                "timestamp": timestamp,
                "source_grid_id": _python_scalar(arc["source"]),
                "destination_grid_id": _python_scalar(arc["destination"]),
                **amounts,
            }
        )

    for source in source_grids:
        sent_total = sum(
            transfer["energy_sent_kwh"]
            for transfer in transfers
            if transfer["source_grid_id"] == source
        )
        if sent_total > surplus[source] + ENERGY_TOLERANCE_KWH:
            raise ArithmeticError("A grid supplied more than its initial surplus")
    sent_total = sum(row["energy_sent_kwh"] for row in transfers)
    received_total = sum(row["energy_received_kwh"] for row in transfers)
    lost_total = sum(row["energy_lost_kwh"] for row in transfers)
    if not math.isclose(
        sent_total, received_total + lost_total, abs_tol=ENERGY_TOLERANCE_KWH
    ):
        raise ArithmeticError("Hourly transfer energy conservation check failed")
    return transfers


def create_hourly_results(
    balance: pd.DataFrame,
    network: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Optimize each hour and build grid/hour summaries plus transfer records."""
    hourly_results: list[dict[str, Any]] = []
    all_transfers: list[dict[str, Any]] = []
    for timestamp, hour_balance in balance.groupby("target_timestamp", sort=True):
        transfers = optimize_redistribution(hour_balance, network)
        all_transfers.extend(transfers)
        sent_by_grid: dict[Any, float] = {}
        received_by_grid: dict[Any, float] = {}
        losses_by_grid: dict[Any, float] = {}
        for transfer in transfers:
            source = transfer["source_grid_id"]
            destination = transfer["destination_grid_id"]
            sent_by_grid[source] = (
                sent_by_grid.get(source, 0.0) + transfer["energy_sent_kwh"]
            )
            received_by_grid[destination] = (
                received_by_grid.get(destination, 0.0)
                + transfer["energy_received_kwh"]
            )
            losses_by_grid[source] = (
                losses_by_grid.get(source, 0.0) + transfer["energy_lost_kwh"]
            )

        grids = []
        for _, row in hour_balance.sort_values("id.grid.coarse").iterrows():
            grid_id = _python_scalar(row["id.grid.coarse"])
            sent = sent_by_grid.get(grid_id, 0.0)
            received = received_by_grid.get(grid_id, 0.0)
            initial_surplus = float(row["initial_surplus_kwh"])
            initial_deficit = float(row["initial_deficit_kwh"])
            remaining_surplus = max(0.0, initial_surplus - sent)
            unmet_demand = max(0.0, initial_deficit - received)
            if sent > initial_surplus + ENERGY_TOLERANCE_KWH:
                raise ArithmeticError(f"Grid {grid_id} exceeded available surplus")
            grids.append(
                {
                    "grid_id": grid_id,
                    "predicted_demand_kwh": float(row["predicted_demand_kwh"]),
                    "synthetic_supply_kwh": float(row["synthetic_supply_kwh"]),
                    "supply_variation": float(row["supply_variation"]),
                    "initial_surplus_kwh": initial_surplus,
                    "initial_deficit_kwh": initial_deficit,
                    "energy_sent_kwh": sent,
                    "energy_received_kwh": received,
                    "transmission_losses_kwh": losses_by_grid.get(grid_id, 0.0),
                    "remaining_surplus_kwh": remaining_surplus,
                    "unmet_demand_kwh": unmet_demand,
                }
            )
        hourly_results.append(
            {
                "timestamp": pd.Timestamp(timestamp).isoformat(),
                "grids": grids,
            }
        )
    if len(hourly_results) != FORECAST_HOURS:
        raise ValueError(
            f"Expected exactly {FORECAST_HOURS} hourly result records; "
            f"found {len(hourly_results)}"
        )
    for record in hourly_results:
        if len(record["grids"]) != GRID_COUNT:
            raise ValueError(
                f"Each hour must contain exactly {GRID_COUNT} grid results"
            )
    return hourly_results, all_transfers


def save_simulation_output(
    simulation_output: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Write one complete JSON output atomically, rejecting non-finite values."""
    path = Path(output_path).expanduser().resolve()
    _atomic_write_json(path, simulation_output)
    return path


def run_simulation(
    origin: str | date | datetime,
    *,
    forecast_frame: pd.DataFrame | None = None,
    hybrid_model: HybridModel | None = None,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    forecast_data_path: str | Path = DEFAULT_FORECAST_DATA_PATH,
    network_path: str | Path | None = DEFAULT_NETWORK_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    random_seed: int = 42,
    variation_limit: float = DEFAULT_VARIATION_LIMIT,
    neighbor_count: int = NEAREST_NEIGHBORS,
    capacity_kwh_per_hour: float = DEFAULT_CAPACITY_KWH_PER_HOUR,
    base_loss_pct: float = DEFAULT_BASE_LOSS_PCT,
    additional_loss_pct_per_km: float = DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM,
    maximum_loss_pct: float = DEFAULT_MAXIMUM_LOSS_PCT,
) -> Path:
    """Run forecast, synthetic supply, fixed network, and hourly optimization."""
    origin_timestamp, date_only = _parse_origin(origin)
    model = hybrid_model or load_hybrid_model(model_path)
    forecast = (
        generate_forecast(model, forecast_data_path, origin_timestamp)
        if forecast_frame is None
        else forecast_frame.copy()
    )
    required_forecast_columns = {
        "id.grid.coarse",
        "forecast_horizon_hours",
        "target_timestamp",
        "centroid_latitude",
        "centroid_longitude",
        "selected_model",
        "predicted_demand_kwh",
    }
    missing_forecast_columns = required_forecast_columns - set(forecast.columns)
    if missing_forecast_columns:
        raise ValueError(
            "Forecast frame is missing required columns: "
            f"{sorted(missing_forecast_columns)}"
        )
    if len(forecast) != GRID_COUNT * FORECAST_HOURS:
        raise ValueError(
            f"Forecast frame must contain exactly {GRID_COUNT * FORECAST_HOURS} rows"
        )
    if forecast.duplicated(["id.grid.coarse", "forecast_horizon_hours"]).any():
        raise ValueError("Forecast frame contains duplicate grid/horizon rows")
    forecast_grid_ids = set(forecast["id.grid.coarse"].tolist())
    if forecast_grid_ids != set(model.routing):
        raise ValueError("Forecast frame grid IDs do not match model routing")
    if set(forecast["forecast_horizon_hours"].astype(int)) != set(
        range(1, FORECAST_HOURS + 1)
    ):
        raise ValueError("Forecast frame must include all forecast horizons 1 through 24")
    if set(pd.to_datetime(forecast["target_timestamp"])) != {
        origin_timestamp + pd.Timedelta(hours=horizon)
        for horizon in range(1, FORECAST_HOURS + 1)
    }:
        raise ValueError("Forecast frame timestamps do not match the requested origin")
    for _, grid_forecast in forecast.groupby("id.grid.coarse"):
        if set(grid_forecast["forecast_horizon_hours"].astype(int)) != set(
            range(1, FORECAST_HOURS + 1)
        ):
            raise ValueError("Every forecast grid must contain horizons 1 through 24")
    expected_routes = forecast["id.grid.coarse"].map(model.routing)
    if expected_routes.isna().any() or not (
        expected_routes.to_numpy() == forecast["selected_model"].to_numpy()
    ).all():
        raise ValueError("Forecast frame routing does not match the saved model")
    numeric_columns = [
        "centroid_latitude",
        "centroid_longitude",
        "predicted_demand_kwh",
    ]
    numeric_values = forecast[numeric_columns].to_numpy(dtype=np.float64)
    if not np.isfinite(numeric_values).all() or (
        forecast["predicted_demand_kwh"] < 0
    ).any():
        raise ValueError("Forecast frame contains invalid demand or grid coordinates")
    if not forecast["centroid_latitude"].between(-90, 90).all() or not forecast[
        "centroid_longitude"
    ].between(-180, 180).all():
        raise ValueError("Forecast frame contains out-of-range grid coordinates")
    supply = generate_synthetic_supply(
        forecast, random_seed=random_seed, variation_limit=variation_limit
    )
    balance = calculate_grid_balance(forecast, supply)
    metadata = forecast.drop_duplicates("id.grid.coarse")
    network = build_grid_network(
        metadata,
        network_path=network_path,
        neighbor_count=neighbor_count,
        capacity_kwh_per_hour=capacity_kwh_per_hour,
        base_loss_pct=base_loss_pct,
        additional_loss_pct_per_km=additional_loss_pct_per_km,
        maximum_loss_pct=maximum_loss_pct,
    )
    hourly_results, transfers = create_hourly_results(balance, network)

    target_start = pd.Timestamp(forecast["target_timestamp"].min())
    simulation_output = {
        "simulation_metadata": {
            "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "forecast_origin_timestamp": origin_timestamp.isoformat(),
            "origin_was_date_only": date_only,
            "forecast_date": target_start.date().isoformat(),
            "forecast_interval_count": FORECAST_HOURS,
            "grid_count": GRID_COUNT,
            "model_name": model.config.get(
                "model_name", "Hybrid grid energy forecaster"
            ),
            "model_artifact": model.model_path.name,
            "random_seed": random_seed,
            "assumptions": {
                "data_classification": "synthetic scenario; not measured supply",
                "units": "kWh per hourly interval",
                "supply_generation": (
                    "predicted_demand_kwh * (1 + independent_uniform_variation)"
                ),
                "variation_min": -variation_limit,
                "variation_max": variation_limit,
                "network_and_losses_are_synthetic": True,
                "network_parameters": network["configuration"],
                "redistribution_scope": "direct neighboring grids only; no multi-hop",
                "optimization_priority": (
                    "minimize total unmet demand, then minimize transmission losses"
                ),
            },
        },
        "network": network,
        "hourly_results": hourly_results,
        "transfers": transfers,
    }
    output_path = Path(output_dir).expanduser().resolve() / (
        f"redistribution_plan_{target_start.date().isoformat()}.json"
    )
    return save_simulation_output(simulation_output, output_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Forecast and optimize a synthetic grid energy redistribution plan."
    )
    parser.add_argument(
        "--origin",
        required=True,
        help=(
            "ISO 8601 origin date or hour. A date-only value forecasts the following "
            "calendar day; a datetime forecasts the next 24 hourly intervals."
        ),
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--forecast-data", type=Path, default=DEFAULT_FORECAST_DATA_PATH)
    parser.add_argument("--network", type=Path, default=DEFAULT_NETWORK_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--variation-limit", type=float, default=DEFAULT_VARIATION_LIMIT)
    parser.add_argument("--neighbors", type=int, default=NEAREST_NEIGHBORS)
    parser.add_argument(
        "--capacity-kwh-per-hour",
        type=float,
        default=DEFAULT_CAPACITY_KWH_PER_HOUR,
    )
    parser.add_argument("--base-loss-pct", type=float, default=DEFAULT_BASE_LOSS_PCT)
    parser.add_argument(
        "--additional-loss-pct-per-km",
        type=float,
        default=DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM,
    )
    parser.add_argument(
        "--maximum-loss-pct",
        type=float,
        default=DEFAULT_MAXIMUM_LOSS_PCT,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_path = run_simulation(
        args.origin,
        model_path=args.model,
        forecast_data_path=args.forecast_data,
        network_path=args.network,
        output_dir=args.output_dir,
        random_seed=args.seed,
        variation_limit=args.variation_limit,
        neighbor_count=args.neighbors,
        capacity_kwh_per_hour=args.capacity_kwh_per_hour,
        base_loss_pct=args.base_loss_pct,
        additional_loss_pct_per_km=args.additional_loss_pct_per_km,
        maximum_loss_pct=args.maximum_loss_pct,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
