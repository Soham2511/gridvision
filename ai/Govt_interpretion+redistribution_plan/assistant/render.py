from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .data import CSV_COLUMNS, RetrievedRecords
from ..paths import ASSISTANT_OUTPUT_DIR, PROJECT_ROOT

WORKSPACE_ROOT = PROJECT_ROOT
DEFAULT_ARTIFACTS_DIR = ASSISTANT_OUTPUT_DIR
GRID_TOLERANCE_KWH = 1e-8


def _period_slug(records: RetrievedRecords) -> str:
    start = datetime.fromisoformat(records.start_timestamp)
    end = datetime.fromisoformat(records.end_timestamp)
    return f"{records.forecast_date}_{start:%H%M}-{end:%H%M}"


def _output_path(
    records: RetrievedRecords,
    extension: str,
    *,
    output_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> Path:
    grids = "-".join(map(str, records.requested_grid_ids)) or "all-grids"
    return (
        Path(output_dir).expanduser().resolve()
        / f"redistribution_{_period_slug(records)}_{grids}.{extension}"
    )


def generate_csv(
    records: RetrievedRecords,
    output_path: str | Path | None = None,
    *,
    output_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> Path:
    """Write transfer records to the fixed, LLM-independent CSV schema."""
    destination = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else _output_path(records, "csv", output_dir=output_dir)
    )
    remaining_by_timestamp: dict[tuple[str, int], dict[str, float]] = {}
    for hour in records.hourly_records:
        for grid in hour["grids"]:
            remaining_by_timestamp[(hour["timestamp"], int(grid["grid_id"]))] = {
                "remaining_surplus_kwh": float(grid["remaining_surplus_kwh"]),
                "unmet_demand_kwh": float(grid["unmet_demand_kwh"]),
            }

    rows = []
    for transfer in records.transfers:
        timestamp = transfer["timestamp"]
        source_id = int(transfer["source_grid_id"])
        destination_id = int(transfer["destination_grid_id"])
        source_balance = remaining_by_timestamp.get((timestamp, source_id))
        destination_balance = remaining_by_timestamp.get((timestamp, destination_id))
        if source_balance is None or destination_balance is None:
            raise ValueError(
                "Transfer CSV requires grid balance rows for both transfer endpoints."
            )
        rows.append(
            {
                "timestamp": timestamp,
                "from_grid": source_id,
                "to_grid": destination_id,
                "energy_sent_kwh": float(transfer["energy_sent_kwh"]),
                "energy_received_kwh": float(transfer["energy_received_kwh"]),
                "energy_lost_kwh": float(transfer["energy_lost_kwh"]),
                "loss_pct": float(transfer["loss_pct"]),
                "source_remaining_surplus_kwh": source_balance[
                    "remaining_surplus_kwh"
                ],
                "destination_remaining_deficit_kwh": destination_balance[
                    "unmet_demand_kwh"
                ],
            }
        )
    frame = pd.DataFrame(rows, columns=CSV_COLUMNS)
    if not frame.empty:
        frame.sort_values(
            ["timestamp", "from_grid", "to_grid"], inplace=True, kind="stable"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)
    return destination


def _balance_totals(records: RetrievedRecords) -> dict[int, dict[str, float]]:
    totals: dict[int, dict[str, float]] = {}
    for hour in records.hourly_records:
        for grid in hour["grids"]:
            grid_id = int(grid["grid_id"])
            values = totals.setdefault(
                grid_id,
                {
                    "initial_surplus_kwh": 0.0,
                    "initial_deficit_kwh": 0.0,
                    "remaining_surplus_kwh": 0.0,
                    "unmet_demand_kwh": 0.0,
                },
            )
            for name in values:
                values[name] += float(grid[name])
    return totals


def generate_image(
    records: RetrievedRecords,
    network: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
    *,
    recommended_transfers: list[dict[str, Any]] | None = None,
    output_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> Path:
    """Draw selected network nodes, fixed connections, balances, and flows."""
    network_data = network or records.network
    grids = network_data.get("grids")
    connections = network_data.get("connections")
    if not isinstance(grids, list) or not grids:
        raise ValueError("No grid coordinates are available for the network image.")
    if not isinstance(connections, list):
        raise ValueError("Network connection metadata is unavailable.")

    balances = _balance_totals(records)
    transfer_ids = {
        int(grid_id)
        for transfer in records.transfers
        for grid_id in (transfer["source_grid_id"], transfer["destination_grid_id"])
    }
    recommendation_ids = {
        int(grid_id)
        for transfer in recommended_transfers or []
        for grid_id in (transfer["source_grid_id"], transfer["destination_grid_id"])
    }
    active_ids = {
        grid_id
        for grid_id, values in balances.items()
        if values["initial_surplus_kwh"] > GRID_TOLERANCE_KWH
        or values["initial_deficit_kwh"] > GRID_TOLERANCE_KWH
    }
    shown_ids = (
        active_ids
        | transfer_ids
        | recommendation_ids
        | set(records.requested_grid_ids)
    )
    if not shown_ids and not records.requested_grid_ids:
        shown_ids = {int(grid["grid_id"]) for grid in grids}
    if not shown_ids:
        raise ValueError("No relevant grids exist in the selected forecast period.")
    if records.requested_grid_ids:
        for edge in connections:
            left, right = int(edge["grid_a_id"]), int(edge["grid_b_id"])
            if (
                (left in records.requested_grid_ids or right in records.requested_grid_ids)
                and left in balances
                and right in balances
            ):
                shown_ids.update((left, right))
    grid_by_id = {int(grid["grid_id"]): grid for grid in grids}
    missing_coordinates = shown_ids - grid_by_id.keys()
    if missing_coordinates:
        raise ValueError(
            f"Network coordinates are missing for grids {sorted(missing_coordinates)}."
        )
    node_records = [grid_by_id[grid_id] for grid_id in sorted(shown_ids)]
    coordinates = {
        int(grid["grid_id"]): (
            float(grid["centroid_longitude"]),
            float(grid["centroid_latitude"]),
        )
        for grid in node_records
    }

    edge_keys = {
        tuple(sorted((int(edge["grid_a_id"]), int(edge["grid_b_id"]))))
        for edge in connections
    }
    transfer_totals: dict[tuple[int, int], dict[str, float]] = {}
    for transfer in records.transfers:
        source, destination = (
            int(transfer["source_grid_id"]),
            int(transfer["destination_grid_id"]),
        )
        if tuple(sorted((source, destination))) not in edge_keys:
            raise ValueError("Image transfer references a connection absent from network.")
        values = transfer_totals.setdefault(
            (source, destination),
            {"sent": 0.0, "received": 0.0, "lost": 0.0},
        )
        values["sent"] += float(transfer["energy_sent_kwh"])
        values["received"] += float(transfer["energy_received_kwh"])
        values["lost"] += float(transfer["energy_lost_kwh"])
    recommendation_totals: dict[tuple[int, int], dict[str, float]] = {}
    for transfer in recommended_transfers or []:
        source, destination = (
            int(transfer["source_grid_id"]),
            int(transfer["destination_grid_id"]),
        )
        if tuple(sorted((source, destination))) not in edge_keys:
            raise ValueError(
                "Recommended transfer references a connection absent from network."
            )
        values = recommendation_totals.setdefault(
            (source, destination),
            {"sent": 0.0, "received": 0.0, "lost": 0.0},
        )
        values["sent"] += float(transfer["recommended_energy_sent_kwh"])
        values["received"] += float(transfer["recommended_energy_received_kwh"])
        values["lost"] += float(transfer["estimated_energy_lost_kwh"])

    destination = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else _output_path(records, "png", output_dir=output_dir)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(13, 9), constrained_layout=True)
    try:
        for edge in connections:
            left, right = int(edge["grid_a_id"]), int(edge["grid_b_id"])
            if left not in shown_ids or right not in shown_ids:
                continue
            x_values = [coordinates[left][0], coordinates[right][0]]
            y_values = [coordinates[left][1], coordinates[right][1]]
            axis.plot(x_values, y_values, color="#c5ccd3", linewidth=0.8, zorder=1)

        colors = []
        sizes = []
        for grid_id in sorted(shown_ids):
            balance = balances.get(grid_id, {})
            surplus = balance.get("initial_surplus_kwh", 0.0)
            deficit = balance.get("initial_deficit_kwh", 0.0)
            if surplus > GRID_TOLERANCE_KWH and deficit <= GRID_TOLERANCE_KWH:
                colors.append("#26834a")
            elif deficit > GRID_TOLERANCE_KWH:
                colors.append("#c33b35")
            else:
                colors.append("#5071a5")
            sizes.append(110 if grid_id in records.requested_grid_ids else 75)
        ordered_ids = sorted(shown_ids)
        axis.scatter(
            [coordinates[grid_id][0] for grid_id in ordered_ids],
            [coordinates[grid_id][1] for grid_id in ordered_ids],
            c=colors,
            s=sizes,
            edgecolors="white",
            linewidths=0.7,
            zorder=3,
        )
        for grid_id in ordered_ids:
            x, y = coordinates[grid_id]
            axis.annotate(
                str(grid_id),
                (x, y),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
                zorder=4,
            )

        for (source, target), values in sorted(transfer_totals.items()):
            source_x, source_y = coordinates[source]
            target_x, target_y = coordinates[target]
            axis.annotate(
                "",
                xy=(target_x, target_y),
                xytext=(source_x, source_y),
                arrowprops={
                    "arrowstyle": "->",
                    "color": "#3e4c59",
                    "linewidth": 1.3,
                    "shrinkA": 9,
                    "shrinkB": 9,
                    "connectionstyle": "arc3,rad=0.08",
                },
                zorder=2,
            )
            center_x = (source_x + target_x) / 2
            center_y = (source_y + target_y) / 2
            loss_pct = values["lost"] / values["sent"] if values["sent"] else 0
            label = (
                f"{source} → {target}\n"
                f"sent {values['sent']:.1f} kWh | "
                f"received {values['received']:.1f} kWh\n"
                f"lost {values['lost']:.1f} kWh ({loss_pct:.2%})"
            )
            axis.annotate(
                label,
                (center_x, center_y),
                xytext=(2, -4),
                textcoords="offset points",
                fontsize=6.5,
                color="#263238",
                bbox={"boxstyle": "round,pad=0.25", "fc": "white", "alpha": 0.82},
                zorder=5,
            )

        for (source, target), values in sorted(recommendation_totals.items()):
            source_x, source_y = coordinates[source]
            target_x, target_y = coordinates[target]
            axis.annotate(
                "",
                xy=(target_x, target_y),
                xytext=(source_x, source_y),
                arrowprops={
                    "arrowstyle": "->",
                    "color": "#e67e22",
                    "linewidth": 1.8,
                    "linestyle": "--",
                    "shrinkA": 10,
                    "shrinkB": 10,
                    "connectionstyle": "arc3,rad=-0.12",
                },
                zorder=3,
            )
            center_x = (source_x + target_x) / 2
            center_y = (source_y + target_y) / 2
            loss_pct = values["lost"] / values["sent"] if values["sent"] else 0
            label = (
                f"Suggested {source} → {target}\n"
                f"sent {values['sent']:.1f} kWh | "
                f"received {values['received']:.1f} kWh\n"
                f"lost {values['lost']:.1f} kWh ({loss_pct:.2%})"
            )
            axis.annotate(
                label,
                (center_x, center_y),
                xytext=(2, 8),
                textcoords="offset points",
                fontsize=6.5,
                color="#9b4d00",
                bbox={"boxstyle": "round,pad=0.25", "fc": "white", "alpha": 0.88},
                zorder=6,
            )

        axis.set_title(
            "Synthetic energy redistribution\n"
            f"Forecast {records.forecast_date} | "
            f"{records.start_timestamp} through {records.end_timestamp}"
        )
        axis.set_xlabel("Centroid longitude")
        axis.set_ylabel("Centroid latitude")
        axis.grid(True, color="#e7eaee", linewidth=0.6)
        axis.set_aspect("equal", adjustable="datalim")
        axis.scatter([], [], color="#26834a", label="Initial surplus")
        axis.scatter([], [], color="#c33b35", label="Initial deficit")
        axis.scatter([], [], color="#5071a5", label="No initial imbalance")
        if recommendation_totals:
            axis.plot([], [], color="#e67e22", linestyle="--", label="Suggested transfer")
        axis.legend(loc="best")
        figure.savefig(destination, dpi=180, bbox_inches="tight")
    finally:
        plt.close(figure)
    return destination
