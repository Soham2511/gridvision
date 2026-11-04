from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .schemas import QueryRequest

from ..paths import PROJECT_ROOT, SIMULATIONS_DIR

WORKSPACE_ROOT = PROJECT_ROOT
DEFAULT_SIMULATIONS_DIR = SIMULATIONS_DIR
GRID_COUNT = 53
FORECAST_HOURS = 24
ENERGY_TOLERANCE_KWH = 1e-5
FILENAME_PATTERN = re.compile(r"redistribution_plan_(\d{4}-\d{2}-\d{2})\.json$")
CSV_COLUMNS = [
    "timestamp",
    "from_grid",
    "to_grid",
    "energy_sent_kwh",
    "energy_received_kwh",
    "energy_lost_kwh",
    "loss_pct",
    "source_remaining_surplus_kwh",
    "destination_remaining_deficit_kwh",
]


class SimulationDataError(ValueError):
    """A missing or invalid simulation source or inconsistent simulation data."""


@dataclass(frozen=True)
class RetrievedRecords:
    forecast_date: str
    intent: str
    requested_grid_ids: tuple[int, ...]
    hourly_records: list[dict[str, Any]]
    transfers: list[dict[str, Any]]
    network: dict[str, Any]
    simulation_metadata: dict[str, Any]

    @property
    def start_timestamp(self) -> str:
        return self.hourly_records[0]["timestamp"]

    @property
    def end_timestamp(self) -> str:
        return self.hourly_records[-1]["timestamp"]


def list_available_simulations(
    simulations_dir: str | Path = DEFAULT_SIMULATIONS_DIR,
) -> list[dict[str, str]]:
    """Return bounded date and interval metadata without loading all plan records."""
    directory = Path(simulations_dir).expanduser().resolve()
    if not directory.is_dir():
        return []
    available = []
    for path in sorted(directory.glob("redistribution_plan_*.json")):
        match = FILENAME_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        forecast_date = date.fromisoformat(match.group(1))
        try:
            with path.open(encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise SimulationDataError(
                f"Unable to read simulation metadata from {path}."
            ) from exc
        if not isinstance(payload, dict):
            raise SimulationDataError(f"Simulation JSON root must be an object: {path}")
        metadata = payload.get("simulation_metadata")
        if not isinstance(metadata, dict):
            raise SimulationDataError(f"Simulation metadata is invalid: {path}")
        first = metadata.get("forecast_date")
        if first != forecast_date.isoformat():
            continue
        first_timestamp = metadata.get("first_forecast_timestamp")
        last_timestamp = metadata.get("last_forecast_timestamp")
        if not first_timestamp or not last_timestamp:
            hour_records = payload.get("hourly_results", [])
            if hour_records:
                first_timestamp = hour_records[0].get("timestamp")
                last_timestamp = hour_records[-1].get("timestamp")
        available.append(
            {
                "forecast_date": first,
                "start_timestamp": first_timestamp or "",
                "end_timestamp": last_timestamp or "",
            }
        )
    return available


def _validate_network(network: Any) -> dict[str, Any]:
    if not isinstance(network, dict):
        raise SimulationDataError(
            "The simulation JSON has no network metadata; visualization is unavailable."
        )
    grids = network.get("grids")
    connections = network.get("connections")
    if not isinstance(grids, list) or len(grids) != GRID_COUNT:
        raise SimulationDataError(
            "The simulation network is missing its 53 grid metadata records."
        )
    if not isinstance(connections, list):
        raise SimulationDataError(
            "The simulation network is missing connection records."
        )
    grid_ids = []
    for grid in grids:
        if not isinstance(grid, dict) or not {
            "grid_id",
            "centroid_latitude",
            "centroid_longitude",
        }.issubset(grid):
            raise SimulationDataError("Grid metadata is incomplete.")
        grid_id = int(grid["grid_id"])
        latitude, longitude = float(grid["centroid_latitude"]), float(
            grid["centroid_longitude"]
        )
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise SimulationDataError("Grid centroid coordinates must be finite.")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise SimulationDataError("Grid centroid coordinates are out of range.")
        grid_ids.append(grid_id)
    if len(set(grid_ids)) != GRID_COUNT:
        raise SimulationDataError("Grid metadata contains duplicate grid IDs.")
    edge_keys = set()
    for edge in connections:
        if not isinstance(edge, dict) or not {
            "grid_a_id",
            "grid_b_id",
            "distance_km",
            "capacity_kwh_per_hour",
            "loss_pct",
        }.issubset(edge):
            raise SimulationDataError("Network connection metadata is incomplete.")
        left, right = int(edge["grid_a_id"]), int(edge["grid_b_id"])
        key = tuple(sorted((left, right)))
        if left == right or left not in grid_ids or right not in grid_ids:
            raise SimulationDataError("Network connection references invalid grids.")
        if key in edge_keys:
            raise SimulationDataError("Network contains duplicate undirected edges.")
        edge_keys.add(key)
        distance = float(edge["distance_km"])
        capacity = float(edge["capacity_kwh_per_hour"])
        loss = float(edge["loss_pct"])
        if not all(math.isfinite(value) for value in (distance, capacity, loss)):
            raise SimulationDataError("Network edge values must be finite.")
        if distance < 0 or capacity <= 0 or not 0 <= loss < 1:
            raise SimulationDataError("Network edge values are outside valid ranges.")
    return network


def load_simulation_json(
    forecast_date: str,
    simulations_dir: str | Path = DEFAULT_SIMULATIONS_DIR,
) -> dict[str, Any]:
    """Load one date-specific JSON plan and validate its deterministic structure."""
    try:
        parsed_date = date.fromisoformat(forecast_date)
    except ValueError as exc:
        raise SimulationDataError("forecast_date must use YYYY-MM-DD format.") from exc
    if parsed_date.isoformat() != forecast_date:
        raise SimulationDataError("forecast_date must use YYYY-MM-DD format.")
    path = Path(simulations_dir).expanduser().resolve() / (
        f"redistribution_plan_{parsed_date.isoformat()}.json"
    )
    if not path.is_file():
        dates = [entry["forecast_date"] for entry in list_available_simulations(simulations_dir)]
        suffix = f" Available forecast dates: {', '.join(dates)}." if dates else ""
        raise FileNotFoundError(
            f"No redistribution plan exists for {parsed_date.isoformat()}.{suffix}"
        )
    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise SimulationDataError(f"Unable to read valid simulation JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SimulationDataError("Simulation JSON root must be an object.")
    metadata = payload.get("simulation_metadata")
    hours = payload.get("hourly_results")
    transfers = payload.get("transfers")
    if not isinstance(metadata, dict) or metadata.get("forecast_date") != forecast_date:
        raise SimulationDataError("Simulation metadata date does not match its filename.")
    if metadata.get("grid_count") != GRID_COUNT or metadata.get(
        "forecast_interval_count"
    ) != FORECAST_HOURS:
        raise SimulationDataError("Simulation metadata does not describe 53 grids and 24 hours.")
    if not isinstance(hours, list) or len(hours) != FORECAST_HOURS:
        raise SimulationDataError("Simulation JSON must contain exactly 24 hourly records.")
    if not isinstance(transfers, list):
        raise SimulationDataError("Simulation JSON transfers must be a list.")
    network = _validate_network(payload.get("network"))
    known_grid_ids = {int(grid["grid_id"]) for grid in network["grids"]}
    timestamps = []
    for hour in hours:
        if not isinstance(hour, dict) or not isinstance(hour.get("timestamp"), str):
            raise SimulationDataError("Hourly record has no ISO timestamp.")
        try:
            timestamp = datetime.fromisoformat(hour["timestamp"])
        except ValueError as exc:
            raise SimulationDataError("Hourly record timestamp is invalid.") from exc
        if timestamp.tzinfo is not None:
            raise SimulationDataError("Hourly timestamps must be timezone-naive.")
        grids = hour.get("grids")
        if not isinstance(grids, list) or len(grids) != GRID_COUNT:
            raise SimulationDataError("Every hour must contain all 53 grids.")
        if {int(grid.get("grid_id", -1)) for grid in grids} != known_grid_ids:
            raise SimulationDataError("Hourly grid IDs do not match network metadata.")
        timestamps.append(timestamp)
        for grid in grids:
            required = {
                "grid_id",
                "predicted_demand_kwh",
                "synthetic_supply_kwh",
                "initial_surplus_kwh",
                "initial_deficit_kwh",
                "energy_sent_kwh",
                "energy_received_kwh",
                "transmission_losses_kwh",
                "remaining_surplus_kwh",
                "unmet_demand_kwh",
            }
            if not required.issubset(grid):
                raise SimulationDataError("Hourly grid balance record is incomplete.")
            amounts = [float(grid[key]) for key in required if key != "grid_id"]
            if not all(math.isfinite(value) and value >= -ENERGY_TOLERANCE_KWH for value in amounts):
                raise SimulationDataError("Hourly grid values must be finite and non-negative.")
            left = (
                float(grid["synthetic_supply_kwh"])
                + float(grid["energy_received_kwh"])
            )
            right = (
                float(grid["predicted_demand_kwh"])
                - float(grid["unmet_demand_kwh"])
                + float(grid["energy_sent_kwh"])
                + float(grid["remaining_surplus_kwh"])
            )
            if not math.isclose(left, right, abs_tol=ENERGY_TOLERANCE_KWH):
                raise SimulationDataError(
                    f"Energy balance check failed for grid {grid['grid_id']} "
                    f"at {hour['timestamp']}."
                )
    if timestamps != sorted(timestamps) or any(
        current - previous != timedelta(hours=1)
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        raise SimulationDataError("Simulation timestamps must be unique hourly intervals.")
    if timestamps[0].date().isoformat() != forecast_date:
        raise SimulationDataError("Hourly timestamps do not match the forecast date.")
    network_edges = {
        tuple(sorted((int(edge["grid_a_id"]), int(edge["grid_b_id"])))): edge
        for edge in network["connections"]
    }
    transfers_by_hour_grid: dict[tuple[str, int], dict[str, float]] = {}
    sent_by_hour_edge: dict[tuple[str, tuple[int, int]], float] = {}
    for transfer in transfers:
        required = {
            "timestamp",
            "source_grid_id",
            "destination_grid_id",
            "energy_sent_kwh",
            "energy_received_kwh",
            "energy_lost_kwh",
            "loss_pct",
        }
        if not isinstance(transfer, dict) or not required.issubset(transfer):
            raise SimulationDataError("Transfer record is incomplete.")
        source, destination = int(transfer["source_grid_id"]), int(
            transfer["destination_grid_id"]
        )
        edge = network_edges.get(tuple(sorted((source, destination))))
        if edge is None:
            raise SimulationDataError("Transfer uses a connection absent from the network.")
        sent = float(transfer["energy_sent_kwh"])
        received = float(transfer["energy_received_kwh"])
        lost = float(transfer["energy_lost_kwh"])
        if not all(math.isfinite(value) and value >= 0 for value in (sent, received, lost)):
            raise SimulationDataError("Transfer energy values must be finite and non-negative.")
        if not math.isclose(sent, received + lost, abs_tol=ENERGY_TOLERANCE_KWH):
            raise SimulationDataError("Transfer energy conservation check failed.")
        if not math.isclose(float(transfer["loss_pct"]), float(edge["loss_pct"]), abs_tol=1e-9):
            raise SimulationDataError("Transfer loss does not match network parameters.")
        expected_lost = sent * float(edge["loss_pct"])
        if not math.isclose(lost, expected_lost, abs_tol=ENERGY_TOLERANCE_KWH):
            raise SimulationDataError("Transfer energy loss does not match its loss rate.")
        if transfer["timestamp"] not in {timestamp.isoformat() for timestamp in timestamps}:
            raise SimulationDataError("Transfer timestamp does not match a forecast hour.")
        grid_keys = (
            (transfer["timestamp"], source),
            (transfer["timestamp"], destination),
        )
        source_values = transfers_by_hour_grid.setdefault(
            grid_keys[0],
            {"energy_sent_kwh": 0.0, "energy_received_kwh": 0.0, "loss_kwh": 0.0},
        )
        source_values["energy_sent_kwh"] += sent
        source_values["loss_kwh"] += lost
        destination_values = transfers_by_hour_grid.setdefault(
            grid_keys[1],
            {"energy_sent_kwh": 0.0, "energy_received_kwh": 0.0, "loss_kwh": 0.0},
        )
        destination_values["energy_received_kwh"] += received
        edge_key = tuple(sorted((source, destination)))
        edge_hour_key = (transfer["timestamp"], edge_key)
        sent_by_hour_edge[edge_hour_key] = sent_by_hour_edge.get(edge_hour_key, 0.0) + sent

    for (timestamp, edge_key), sent in sent_by_hour_edge.items():
        if sent > float(network_edges[edge_key]["capacity_kwh_per_hour"]) + ENERGY_TOLERANCE_KWH:
            raise SimulationDataError(
                f"Combined transfers exceed edge capacity at {timestamp}."
            )
    for hour in hours:
        timestamp = hour["timestamp"]
        for grid in hour["grids"]:
            grid_id = int(grid["grid_id"])
            transfer_values = transfers_by_hour_grid.get(
                (timestamp, grid_id),
                {"energy_sent_kwh": 0.0, "energy_received_kwh": 0.0, "loss_kwh": 0.0},
            )
            for transfer_key, grid_key in (
                ("energy_sent_kwh", "energy_sent_kwh"),
                ("energy_received_kwh", "energy_received_kwh"),
                ("loss_kwh", "transmission_losses_kwh"),
            ):
                if not math.isclose(
                    transfer_values[transfer_key],
                    float(grid[grid_key]),
                    abs_tol=ENERGY_TOLERANCE_KWH,
                ):
                    raise SimulationDataError(
                        f"Grid transfer totals do not reconcile for grid {grid_id} "
                        f"at {timestamp}."
                    )
    payload["network"] = network
    return payload


def _resolve_request_window(
    request: QueryRequest,
    payload: dict[str, Any],
    *,
    last_request: QueryRequest | None = None,
) -> list[dict[str, Any]]:
    hours = payload["hourly_results"]
    timestamps = [datetime.fromisoformat(hour["timestamp"]) for hour in hours]
    if request.intent in {"summary"} and request.start_timestamp is None:
        return hours

    start: datetime | None = (
        datetime.fromisoformat(request.start_timestamp)
        if request.start_timestamp
        else None
    )
    duration = request.duration_hours
    if request.intent == "compare_hours":
        duration = duration or 2
    if duration is None:
        duration = 1

    if start is None and last_request is not None and last_request.start_timestamp:
        previous_start = datetime.fromisoformat(last_request.start_timestamp)
        previous_duration = last_request.duration_hours or 1
        previous_end = previous_start + timedelta(hours=previous_duration - 1)
        later = [timestamp for timestamp in timestamps if timestamp > previous_end]
        if later:
            start = later[0]
    if start is None:
        if len(timestamps) == 1:
            start = timestamps[0]
        elif request.intent in {"summary"}:
            return hours
        else:
            start = timestamps[0]

    if start not in timestamps:
        raise SimulationDataError(
            f"Timestamp {start.isoformat()} is not available in this forecast."
        )
    start_index = timestamps.index(start)
    selected = hours[start_index : start_index + duration]
    if len(selected) != duration:
        raise SimulationDataError(
            f"Only {len(selected)} hourly intervals remain after {start.isoformat()}."
        )
    return selected


def retrieve_relevant_records(
    request: QueryRequest,
    *,
    simulations_dir: str | Path = DEFAULT_SIMULATIONS_DIR,
    last_request: QueryRequest | None = None,
) -> RetrievedRecords:
    """Select time, grids, and transfers deterministically from the JSON plan."""
    if request.forecast_date is None:
        available = list_available_simulations(simulations_dir)
        if len(available) != 1:
            dates = ", ".join(item["forecast_date"] for item in available)
            raise SimulationDataError(
                "A forecast date is required because the available simulation "
                f"date is ambiguous. Available dates: {dates or 'none'}."
            )
        forecast_date = available[0]["forecast_date"]
    else:
        forecast_date = request.forecast_date

    payload = load_simulation_json(forecast_date, simulations_dir)
    known_grid_ids = {int(grid["grid_id"]) for grid in payload["network"]["grids"]}
    invalid_grids = set(request.grid_ids) - known_grid_ids
    if invalid_grids:
        raise SimulationDataError(
            f"Unknown grid IDs: {sorted(invalid_grids)}. Use only grid IDs in this plan."
        )
    hours = _resolve_request_window(request, payload, last_request=last_request)
    selected_timestamps = {hour["timestamp"] for hour in hours}

    selected_grids = set(request.grid_ids)
    transfers = [
        transfer
        for transfer in payload["transfers"]
        if transfer["timestamp"] in selected_timestamps
        and (
            not selected_grids
            or int(transfer["source_grid_id"]) in selected_grids
            or int(transfer["destination_grid_id"]) in selected_grids
        )
    ]
    relevant_ids = {
        int(grid["grid_id"])
        for hour in hours
        for grid in hour["grids"]
        if not selected_grids or int(grid["grid_id"]) in selected_grids
    } | {
        int(grid_id)
        for transfer in transfers
        for grid_id in (transfer["source_grid_id"], transfer["destination_grid_id"])
    }
    if selected_grids:
        for edge in payload["network"]["connections"]:
            left, right = int(edge["grid_a_id"]), int(edge["grid_b_id"])
            if left in selected_grids:
                relevant_ids.add(right)
            if right in selected_grids:
                relevant_ids.add(left)
    grid_lookup = {
        int(grid["grid_id"]): grid for grid in payload["network"]["grids"]
    }
    edges = []
    for edge in payload["network"]["connections"]:
        left, right = int(edge["grid_a_id"]), int(edge["grid_b_id"])
        if selected_grids:
            if left in selected_grids or right in selected_grids:
                edges.append(edge)
        elif left in relevant_ids and right in relevant_ids:
            edges.append(edge)
    network_grid_ids = set(relevant_ids)
    for edge in edges:
        network_grid_ids.update(
            (int(edge["grid_a_id"]), int(edge["grid_b_id"]))
        )
    network = {
        "grid_count": len(network_grid_ids),
        "connection_count": len(edges),
        "grids": [
            grid_lookup[grid_id] for grid_id in sorted(network_grid_ids)
        ],
        "connections": edges,
        "configuration": payload["network"].get("configuration", {}),
    }
    transfer_ids_by_hour: dict[str, set[int]] = {}
    for transfer in transfers:
        transfer_ids_by_hour.setdefault(transfer["timestamp"], set()).update(
            (int(transfer["source_grid_id"]), int(transfer["destination_grid_id"]))
        )
    selected_hours = []
    for hour in hours:
        relevant_hour_ids = selected_grids | transfer_ids_by_hour.get(
            hour["timestamp"], set()
        )
        if selected_grids:
            for edge in edges:
                left, right = int(edge["grid_a_id"]), int(edge["grid_b_id"])
                if left in selected_grids:
                    relevant_hour_ids.add(right)
                if right in selected_grids:
                    relevant_hour_ids.add(left)
        selected_hours.append(
            {
                "timestamp": hour["timestamp"],
                "grids": [
                    grid
                    for grid in hour["grids"]
                    if not selected_grids
                    or int(grid["grid_id"]) in relevant_hour_ids
                ],
            }
        )
    records = RetrievedRecords(
        forecast_date=forecast_date,
        intent=request.intent,
        requested_grid_ids=tuple(request.grid_ids),
        hourly_records=selected_hours,
        transfers=transfers,
        network=network,
        simulation_metadata={
            "forecast_date": payload["simulation_metadata"]["forecast_date"],
            "forecast_origin_timestamp": payload["simulation_metadata"].get(
                "forecast_origin_timestamp"
            ),
            "run_timestamp": payload["simulation_metadata"].get("run_timestamp"),
            "assumptions": payload["simulation_metadata"].get("assumptions", {}),
        },
    )
    calculate_summary(records)
    return records


def calculate_summary(records: RetrievedRecords) -> dict[str, Any]:
    """Compute auditable totals and balances using only selected Python records."""
    grid_totals: dict[int, dict[str, float]] = {}
    requested_grids = set(records.requested_grid_ids)
    for hour in records.hourly_records:
        for grid in hour["grids"]:
            grid_id = int(grid["grid_id"])
            if requested_grids and grid_id not in requested_grids:
                continue
            totals = grid_totals.setdefault(
                grid_id,
                {
                    "predicted_demand_kwh": 0.0,
                    "synthetic_supply_kwh": 0.0,
                    "initial_surplus_kwh": 0.0,
                    "initial_deficit_kwh": 0.0,
                    "energy_sent_kwh": 0.0,
                    "energy_received_kwh": 0.0,
                    "transmission_losses_kwh": 0.0,
                    "remaining_surplus_kwh": 0.0,
                    "unmet_demand_kwh": 0.0,
                },
            )
            for key in totals:
                totals[key] += float(grid[key])

    transfer_totals: dict[tuple[int, int], dict[str, float]] = {}
    for transfer in records.transfers:
        key = (
            int(transfer["source_grid_id"]),
            int(transfer["destination_grid_id"]),
        )
        totals = transfer_totals.setdefault(
            key,
            {
                "energy_sent_kwh": 0.0,
                "energy_received_kwh": 0.0,
                "energy_lost_kwh": 0.0,
            },
        )
        for field in totals:
            totals[field] += float(transfer[field])

    sent = sum(float(item["energy_sent_kwh"]) for item in records.transfers)
    received = sum(float(item["energy_received_kwh"]) for item in records.transfers)
    losses = sum(float(item["energy_lost_kwh"]) for item in records.transfers)
    if not math.isclose(sent, received + losses, abs_tol=ENERGY_TOLERANCE_KWH):
        raise SimulationDataError("Selected period transfer conservation check failed.")

    grids = [
        {"grid_id": grid_id, **values}
        for grid_id, values in sorted(grid_totals.items())
    ]
    surplus_grids = [
        grid["grid_id"]
        for grid in grids
        if grid["initial_surplus_kwh"] > ENERGY_TOLERANCE_KWH
    ]
    deficit_grids = [
        grid["grid_id"]
        for grid in grids
        if grid["initial_deficit_kwh"] > ENERGY_TOLERANCE_KWH
    ]
    unmet_grids = [
        grid["grid_id"]
        for grid in grids
        if grid["unmet_demand_kwh"] > ENERGY_TOLERANCE_KWH
    ]
    hourly_totals = []
    for hour in records.hourly_records:
        selected_hour_grids = [
            grid
            for grid in hour["grids"]
            if not requested_grids or int(grid["grid_id"]) in requested_grids
        ]
        hour_transfers = [
            transfer
            for transfer in records.transfers
            if transfer["timestamp"] == hour["timestamp"]
        ]
        hourly_totals.append(
            {
                "timestamp": hour["timestamp"],
                "grid_count": len(selected_hour_grids),
                "predicted_demand_kwh": sum(
                    float(grid["predicted_demand_kwh"])
                    for grid in selected_hour_grids
                ),
                "synthetic_supply_kwh": sum(
                    float(grid["synthetic_supply_kwh"])
                    for grid in selected_hour_grids
                ),
                "initial_surplus_kwh": sum(
                    float(grid["initial_surplus_kwh"])
                    for grid in selected_hour_grids
                ),
                "initial_deficit_kwh": sum(
                    float(grid["initial_deficit_kwh"])
                    for grid in selected_hour_grids
                ),
                "energy_sent_kwh": sum(
                    float(transfer["energy_sent_kwh"])
                    for transfer in hour_transfers
                ),
                "energy_received_kwh": sum(
                    float(transfer["energy_received_kwh"])
                    for transfer in hour_transfers
                ),
                "transmission_losses_kwh": sum(
                    float(transfer["energy_lost_kwh"])
                    for transfer in hour_transfers
                ),
                "remaining_surplus_kwh": sum(
                    float(grid["remaining_surplus_kwh"])
                    for grid in selected_hour_grids
                ),
                "unmet_demand_kwh": sum(
                    float(grid["unmet_demand_kwh"])
                    for grid in selected_hour_grids
                ),
            }
        )
    return {
        "forecast_date": records.forecast_date,
        "start_timestamp": records.start_timestamp,
        "end_timestamp": records.end_timestamp,
        "interval_count": len(records.hourly_records),
        "grid_count": len(grids),
        "predicted_demand_total_kwh": sum(
            grid["predicted_demand_kwh"] for grid in grids
        ),
        "synthetic_supply_total_kwh": sum(
            grid["synthetic_supply_kwh"] for grid in grids
        ),
        "initial_surplus_total_kwh": sum(
            grid["initial_surplus_kwh"] for grid in grids
        ),
        "initial_deficit_total_kwh": sum(
            grid["initial_deficit_kwh"] for grid in grids
        ),
        "energy_sent_total_kwh": sent,
        "energy_received_total_kwh": received,
        "transmission_losses_total_kwh": losses,
        "remaining_surplus_total_kwh": sum(
            grid["remaining_surplus_kwh"] for grid in grids
        ),
        "unmet_demand_total_kwh": sum(grid["unmet_demand_kwh"] for grid in grids),
        "surplus_grid_ids": surplus_grids,
        "deficit_grid_ids": deficit_grids,
        "unmet_demand_grid_ids": unmet_grids,
        "grid_totals": grids,
        "hourly_totals": hourly_totals,
        "transfers_by_grid_pair": [
            {
                "from_grid": source,
                "to_grid": destination,
                **values,
            }
            for (source, destination), values in sorted(transfer_totals.items())
        ],
    }


def calculate_demand_solution(
    records: RetrievedRecords,
    target_grid_ids: list[int] | tuple[int, ...],
) -> dict[str, Any]:
    """Suggest minimum-loss feasible direct transfers for remaining deficits.

    Suggestions use only the selected hour's remaining surplus and existing
    network edges. They do not model economics, controllability, or real grid
    operation and are not an optimization across multiple forecast hours.
    """
    if not target_grid_ids:
        raise ValueError("Demand-solution requests require at least one target grid.")
    grid_lookup = {
        int(grid["grid_id"]): grid for grid in records.network.get("grids", [])
    }
    known_ids = {int(grid["grid_id"]) for grid in grid_lookup.values()}
    unknown_ids = set(target_grid_ids) - known_ids
    if unknown_ids:
        raise SimulationDataError(
            f"Network metadata is missing target grids: {sorted(unknown_ids)}."
        )
    edge_lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for edge in records.network.get("connections", []):
        key = tuple(sorted((int(edge["grid_a_id"]), int(edge["grid_b_id"]))))
        edge_lookup[key] = edge

    grid_records_by_hour = {
        (
            hour["timestamp"],
            int(grid["grid_id"]),
        ): grid
        for hour in records.hourly_records
        for grid in hour["grids"]
    }
    used_capacity: dict[tuple[str, tuple[int, int]], float] = {}
    for transfer in records.transfers:
        edge_key = tuple(
            sorted((int(transfer["source_grid_id"]), int(transfer["destination_grid_id"])))
        )
        capacity_key = (transfer["timestamp"], edge_key)
        used_capacity[capacity_key] = used_capacity.get(capacity_key, 0.0) + float(
            transfer["energy_sent_kwh"]
        )
    remaining_by_source: dict[tuple[str, int], float] = {}
    recommendations: list[dict[str, Any]] = []
    unserved: list[dict[str, Any]] = []

    for hour in records.hourly_records:
        timestamp = hour["timestamp"]
        for target_id in target_grid_ids:
            target = grid_records_by_hour.get((timestamp, target_id))
            if target is None:
                raise SimulationDataError(
                    f"Grid {target_id} balance is missing at {timestamp}."
                )
            unmet = float(target["unmet_demand_kwh"])
            if unmet <= ENERGY_TOLERANCE_KWH:
                continue
            candidates = []
            for edge_key, edge in edge_lookup.items():
                if target_id not in edge_key:
                    continue
                source_id = edge_key[0] if edge_key[1] == target_id else edge_key[1]
                donor = grid_records_by_hour.get((timestamp, source_id))
                if donor is None:
                    continue
                source_key = (timestamp, source_id)
                available_surplus = remaining_by_source.setdefault(
                    source_key,
                    float(donor["remaining_surplus_kwh"]),
                )
                capacity_key = (timestamp, edge_key)
                remaining_capacity = max(
                    0.0,
                    float(edge["capacity_kwh_per_hour"])
                    - used_capacity.get(capacity_key, 0.0),
                )
                if available_surplus <= ENERGY_TOLERANCE_KWH:
                    continue
                if remaining_capacity <= ENERGY_TOLERANCE_KWH:
                    continue
                candidates.append(
                    (
                        float(edge["loss_pct"]),
                        float(edge["distance_km"]),
                        source_id,
                        edge_key,
                        available_surplus,
                        remaining_capacity,
                    )
                )
            candidates.sort(key=lambda item: (item[0], item[1], item[2]))

            remaining_demand = unmet
            for candidate in candidates:
                loss_pct = candidate[0]
                source_id = candidate[2]
                edge_key = candidate[3]
                available_surplus = candidate[4]
                remaining_capacity = candidate[5]
                if remaining_demand <= ENERGY_TOLERANCE_KWH:
                    break
                if not 0 <= loss_pct < 1:
                    raise SimulationDataError("Network has an invalid loss parameter.")
                energy_sent = min(
                    available_surplus,
                    remaining_capacity,
                    remaining_demand / (1 - loss_pct),
                )
                if energy_sent <= ENERGY_TOLERANCE_KWH:
                    continue
                energy_lost = energy_sent * loss_pct
                energy_received = energy_sent - energy_lost
                recommendations.append(
                    {
                        "timestamp": timestamp,
                        "source_grid_id": source_id,
                        "destination_grid_id": target_id,
                        "recommended_energy_sent_kwh": energy_sent,
                        "recommended_energy_received_kwh": energy_received,
                        "estimated_energy_lost_kwh": energy_lost,
                        "loss_pct": loss_pct,
                    }
                )
                source_key = (timestamp, source_id)
                remaining_by_source[source_key] -= energy_sent
                capacity_key = (timestamp, edge_key)
                used_capacity[capacity_key] = (
                    used_capacity.get(capacity_key, 0.0) + energy_sent
                )
                remaining_demand = max(0.0, remaining_demand - energy_received)
            if remaining_demand > ENERGY_TOLERANCE_KWH:
                unserved.append(
                    {
                        "timestamp": timestamp,
                        "grid_id": target_id,
                        "unmet_demand_kwh": remaining_demand,
                    }
                )
    return {
        "demand_solution_recommendations": recommendations,
        "demand_solution_unserved": unserved,
    }
