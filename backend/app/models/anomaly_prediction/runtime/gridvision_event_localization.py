"""Spatial-temporal localization and event-scope classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h3
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import DBSCAN


@dataclass(frozen=True)
class EventLocalizationConfig:
    """Configurable spatial and temporal grouping policy."""

    h3_resolution: int = 8
    spatial_radius_km: float = 5.0
    dbscan_min_customers: int = 2
    maximum_start_time_difference: pd.Timedelta = pd.Timedelta(minutes=30)
    minimum_temporal_overlap: float = 0.25
    maximum_interval_gap: pd.Timedelta = pd.Timedelta(hours=1)
    earth_radius_km: float = 6371.0088

    def __post_init__(self) -> None:
        if not 0 <= self.h3_resolution <= 15:
            raise ValueError("h3_resolution must be between 0 and 15.")
        if self.spatial_radius_km <= 0:
            raise ValueError("spatial_radius_km must be positive.")
        if self.dbscan_min_customers < 2:
            raise ValueError("dbscan_min_customers must be at least 2.")
        if not 0 <= self.minimum_temporal_overlap <= 1:
            raise ValueError("minimum_temporal_overlap must be between 0 and 1.")
        if self.maximum_start_time_difference < pd.Timedelta(0):
            raise ValueError("maximum_start_time_difference must be non-negative.")
        if self.maximum_interval_gap < pd.Timedelta(0):
            raise ValueError("maximum_interval_gap must be non-negative.")


ANOMALY_COLUMNS = [
    "customer_id",
    "anomaly_type",
    "anomaly_start",
    "anomaly_end",
    "anomaly_duration",
    "latitude",
    "longitude",
    "anomaly_score",
    "severity",
]
GROUND_TRUTH_COLUMNS = [
    "event_id",
    "customer_id",
    "anomaly_start",
    "anomaly_end",
]
EVENT_SUMMARY_COLUMNS = [
    "event_id",
    "event_scope",
    "event_start",
    "event_end",
    "event_duration",
    "affected_customer_count",
    "affected_customer_percentage",
    "customer_ids",
    "anomaly_types",
    "anomaly_type_distribution",
    "dominant_anomaly_type",
    "spatial_cluster_count",
    "spatial_cluster_ids",
    "spatial_clusters",
    "h3_cells",
    "latitude_center",
    "longitude_center",
    "spatial_extent_km",
    "mean_anomaly_score",
    "max_anomaly_score",
]


def _column(frame: pd.DataFrame, *candidates: str) -> str | None:
    return next((name for name in candidates if name in frame.columns), None)


def prepare_anomaly_records(
    detected: pd.DataFrame,
    default_interval: pd.Timedelta = pd.Timedelta(hours=1),
) -> pd.DataFrame:
    """Normalize point alerts or per-customer anomaly windows to one event schema."""
    if "is_detected" in detected:
        detected = detected.loc[detected["is_detected"]].copy()
    if detected.empty:
        return pd.DataFrame(columns=ANOMALY_COLUMNS)

    customer_column = _column(detected, "customer_id", "OBJECTID")
    start_column = _column(detected, "anomaly_start", "start_time", "timestamp")
    end_column = _column(detected, "anomaly_end", "end_time")
    type_column = _column(detected, "anomaly_type", "predicted_anomaly_type")
    latitude_column = _column(detected, "latitude", "lat")
    longitude_column = _column(detected, "longitude", "lon", "lng")
    score_column = _column(
        detected, "anomaly_score", "max_anomaly_score", "severity"
    )
    severity_column = _column(detected, "severity")
    required = {
        "customer_id": customer_column,
        "anomaly start/timestamp": start_column,
        "anomaly type": type_column,
        "latitude": latitude_column,
        "longitude": longitude_column,
        "anomaly score/severity": score_column,
    }
    missing = [label for label, column in required.items() if column is None]
    if missing:
        raise ValueError(f"Detected anomaly dataframe is missing: {', '.join(missing)}")
    if default_interval <= pd.Timedelta(0):
        raise ValueError("default_interval must be positive.")

    records = pd.DataFrame(
        {
            "customer_id": detected[customer_column],
            "anomaly_type": detected[type_column].astype("string"),
            "anomaly_start": pd.to_datetime(detected[start_column], errors="coerce"),
            "latitude": pd.to_numeric(detected[latitude_column], errors="coerce"),
            "longitude": pd.to_numeric(detected[longitude_column], errors="coerce"),
            "anomaly_score": pd.to_numeric(detected[score_column], errors="coerce"),
        }
    )
    if end_column:
        records["anomaly_end"] = pd.to_datetime(detected[end_column], errors="coerce")
    else:
        records["anomaly_end"] = records["anomaly_start"] + default_interval

    for column in ANOMALY_COLUMNS:
        if column not in records:
            records[column] = np.nan
    records["severity"] = (
        pd.to_numeric(detected[severity_column], errors="coerce")
        if severity_column
        else records["anomaly_score"]
    )
    records["severity"] = records["severity"].fillna(records["anomaly_score"])

    invalid = (
        records[ANOMALY_COLUMNS]
        .drop(columns=["anomaly_duration", "severity"])
        .isna()
        .any(axis=1)
        | (records["anomaly_end"] <= records["anomaly_start"])
        | ~records["latitude"].between(-90, 90)
        | ~records["longitude"].between(-180, 180)
    )
    if invalid.any():
        raise ValueError(
            "Detected anomaly records contain missing/invalid required values, "
            f"invalid coordinates, or non-positive intervals ({int(invalid.sum())} rows)."
        )
    if (records[["anomaly_score", "severity"]] < 0).any().any():
        raise ValueError("Anomaly scores/severity must be non-negative.")
    records["anomaly_duration"] = (
        records["anomaly_end"] - records["anomaly_start"]
    )
    return records[ANOMALY_COLUMNS].sort_values(
        ["anomaly_start", "customer_id"], kind="mergesort"
    ).reset_index(drop=True)


def assign_spatial_cells(
    anomaly_records: pd.DataFrame,
    h3_resolution: int = 8,
) -> pd.DataFrame:
    """Add deterministic H3 cell IDs without changing record coordinates."""
    if not 0 <= h3_resolution <= 15:
        raise ValueError("h3_resolution must be between 0 and 15.")
    records = anomaly_records.copy()
    if records.empty:
        records["h3_cell"] = pd.Series(dtype="string")
        return records
    records["h3_cell"] = [
        h3.latlng_to_cell(float(latitude), float(longitude), h3_resolution)
        for latitude, longitude in zip(records["latitude"], records["longitude"])
    ]
    return records


def spatial_clustering(
    anomaly_records: pd.DataFrame,
    config: EventLocalizationConfig = EventLocalizationConfig(),
) -> pd.DataFrame:
    """Cluster unique customer locations so repeat alerts cannot inflate density."""
    records = assign_spatial_cells(anomaly_records, config.h3_resolution)
    records["spatial_cluster_id"] = pd.Series(index=records.index, dtype="string")
    if records.empty:
        return records
    locations = (
        records.groupby("customer_id", sort=True)[["latitude", "longitude"]]
        .mean()
        .reset_index()
    )
    coordinates = np.radians(locations[["latitude", "longitude"]].to_numpy(dtype=float))
    labels = DBSCAN(
        eps=config.spatial_radius_km / config.earth_radius_km,
        min_samples=config.dbscan_min_customers,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(coordinates)
    cluster_by_customer = {
        customer_id: (
            f"DBSCAN_{label:04d}"
            if label >= 0
            else f"SPATIAL_NOISE_{index:06d}"
        )
        for index, (customer_id, label) in enumerate(
            zip(locations["customer_id"], labels)
        )
    }
    records["spatial_cluster_id"] = records["customer_id"].map(cluster_by_customer)
    return records


def temporal_correlation(
    first: pd.Series | dict[str, Any],
    second: pd.Series | dict[str, Any],
    config: EventLocalizationConfig = EventLocalizationConfig(),
) -> bool:
    """Return whether two anomaly intervals meet any configured temporal rule."""
    first_start = pd.Timestamp(first["anomaly_start"])
    first_end = pd.Timestamp(first["anomaly_end"])
    second_start = pd.Timestamp(second["anomaly_start"])
    second_end = pd.Timestamp(second["anomaly_end"])
    if first_end <= first_start or second_end <= second_start:
        raise ValueError("Temporal correlation requires positive anomaly intervals.")

    start_difference = abs(first_start - second_start)
    if start_difference <= config.maximum_start_time_difference:
        return True

    overlap = max(
        pd.Timedelta(0),
        min(first_end, second_end) - max(first_start, second_start),
    )
    shorter_interval = min(first_end - first_start, second_end - second_start)
    if overlap / shorter_interval >= config.minimum_temporal_overlap:
        return True

    interval_gap = max(
        pd.Timedelta(0),
        max(first_start, second_start) - min(first_end, second_end),
    )
    return interval_gap <= config.maximum_interval_gap


def _temporal_components(
    records: pd.DataFrame,
    config: EventLocalizationConfig,
) -> list[list[int]]:
    if records.empty:
        return []
    order = np.argsort(pd.to_datetime(records["anomaly_start"]).to_numpy())
    parents = list(range(len(records)))
    temporal_lookback = max(
        config.maximum_interval_gap,
        config.maximum_start_time_difference,
    )

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    active: list[int] = []
    for current in order:
        current_start = pd.Timestamp(records.iloc[current]["anomaly_start"])
        active = [
            previous
            for previous in active
            if pd.Timestamp(records.iloc[previous]["anomaly_end"])
            + temporal_lookback
            >= current_start
        ]
        current_record = records.iloc[current]
        for previous in active:
            previous_record = records.iloc[previous]
            previous_cluster = str(previous_record["spatial_cluster_id"])
            current_cluster = str(current_record["spatial_cluster_id"])
            same_customer = (
                previous_record["customer_id"] == current_record["customer_id"]
            )
            same_dense_cluster = (
                previous_cluster == current_cluster
                and previous_cluster.startswith("DBSCAN_")
            )
            related_dense_clusters = (
                previous_cluster.startswith("DBSCAN_")
                and current_cluster.startswith("DBSCAN_")
            )
            if (
                (same_customer or same_dense_cluster or related_dense_clusters)
                and temporal_correlation(previous_record, current_record, config)
            ):
                union(int(previous), int(current))
        active.append(int(current))

    components: dict[int, list[int]] = {}
    for index in range(len(records)):
        components.setdefault(find(index), []).append(index)
    return sorted(components.values(), key=lambda values: min(values))


def classify_event_scope(
    affected_customer_count: int,
    spatial_cluster_count: int,
) -> str:
    """Classify scope from customer cardinality and separated geographic clusters."""
    if affected_customer_count < 1 or spatial_cluster_count < 1:
        raise ValueError("Event scope requires at least one customer and spatial cluster.")
    if affected_customer_count == 1:
        return "SINGLE_CUSTOMER"
    if spatial_cluster_count == 1:
        return "LOCAL_AREA"
    return "MULTI_AREA"


def form_events(
    anomaly_records: pd.DataFrame,
    config: EventLocalizationConfig = EventLocalizationConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Form connected spatial-temporal events and attach event/cluster IDs to records."""
    records = spatial_clustering(anomaly_records, config)
    records["event_id"] = pd.Series(index=records.index, dtype="string")
    records["event_spatial_cluster_id"] = pd.Series(
        index=records.index, dtype="string"
    )
    event_rows: list[dict[str, Any]] = []
    for event_number, component in enumerate(_temporal_components(records, config), 1):
        event_id = f"EVT_{event_number:06d}"
        event = records.iloc[component].copy()
        cluster_mapping: dict[str, str] = {}
        for cluster_number, source_cluster_id in enumerate(
            sorted(event["spatial_cluster_id"].unique()), 1
        ):
            cluster_mapping[source_cluster_id] = (
                f"{event_id}_SPC_{cluster_number:03d}"
            )
        records.loc[event.index, "event_id"] = event_id
        records.loc[event.index, "event_spatial_cluster_id"] = event[
            "spatial_cluster_id"
        ].map(cluster_mapping)
        event_rows.append(
            {
                "event_id": event_id,
                "customer_ids": sorted(event["customer_id"].unique().tolist()),
                "anomaly_records": event.index.tolist(),
                "spatial_cluster_ids": sorted(cluster_mapping.values()),
            }
        )
    return records, pd.DataFrame(event_rows)


def _haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
    earth_radius_km: float,
) -> float:
    coordinates = np.radians([latitude_a, longitude_a, latitude_b, longitude_b])
    lat_a, lon_a, lat_b, lon_b = coordinates
    value = (
        np.sin((lat_b - lat_a) / 2) ** 2
        + np.cos(lat_a) * np.cos(lat_b) * np.sin((lon_b - lon_a) / 2) ** 2
    )
    return float(2 * earth_radius_km * np.arcsin(np.sqrt(value)))


def generate_event_summary(
    anomaly_records: pd.DataFrame,
    population_customer_count: int | None = None,
    config: EventLocalizationConfig = EventLocalizationConfig(),
) -> pd.DataFrame:
    """Build user-facing event summaries from records already assigned to events."""
    if anomaly_records.empty:
        return pd.DataFrame(columns=EVENT_SUMMARY_COLUMNS)
    if "event_id" not in anomaly_records or "event_spatial_cluster_id" not in anomaly_records:
        raise ValueError("Call form_events before generating event summaries.")
    if population_customer_count is None:
        population_customer_count = int(anomaly_records["customer_id"].nunique())
    if population_customer_count < anomaly_records["customer_id"].nunique():
        raise ValueError("population_customer_count cannot be smaller than observed customers.")

    summaries: list[dict[str, Any]] = []
    for event_id, group in anomaly_records.groupby("event_id", sort=True):
        customer_ids = sorted(group["customer_id"].unique().tolist())
        cluster_ids = sorted(group["event_spatial_cluster_id"].unique().tolist())
        type_distribution = {
            str(kind): int(count)
            for kind, count in group["anomaly_type"].value_counts().sort_index().items()
        }
        dominant_type = min(
            type_distribution,
            key=lambda kind: (-type_distribution[kind], kind),
        )
        latitude_center = float(group["latitude"].mean())
        longitude_center = float(group["longitude"].mean())
        spatial_clusters: list[dict[str, Any]] = []
        for cluster_id, cluster_records in group.groupby(
            "event_spatial_cluster_id", sort=True
        ):
            customer_locations = cluster_records[
                ["customer_id", "latitude", "longitude"]
            ].drop_duplicates("customer_id")
            cluster_latitude = float(customer_locations["latitude"].mean())
            cluster_longitude = float(customer_locations["longitude"].mean())
            cluster_extent_km = max(
                (
                    _haversine_km(
                        cluster_latitude,
                        cluster_longitude,
                        float(row.latitude),
                        float(row.longitude),
                        config.earth_radius_km,
                    )
                    * 2
                    for row in customer_locations.itertuples(index=False)
                ),
                default=0.0,
            )
            spatial_clusters.append(
                {
                    "cluster_id": str(cluster_id),
                    "customer_ids": sorted(
                        customer_locations["customer_id"].unique().tolist()
                    ),
                    "latitude_center": cluster_latitude,
                    "longitude_center": cluster_longitude,
                    "spatial_extent_km": cluster_extent_km,
                }
            )
        extent_km = max(
            (
                _haversine_km(
                    latitude_center,
                    longitude_center,
                    float(row.latitude),
                    float(row.longitude),
                    config.earth_radius_km,
                )
                * 2
                for row in group[["latitude", "longitude"]].itertuples(index=False)
            ),
            default=0.0,
        )
        event_start = group["anomaly_start"].min()
        event_end = group["anomaly_end"].max()
        summaries.append(
            {
                "event_id": event_id,
                "event_scope": classify_event_scope(
                    len(customer_ids), len(cluster_ids)
                ),
                "event_start": event_start,
                "event_end": event_end,
                "event_duration": event_end - event_start,
                "affected_customer_count": len(customer_ids),
                "affected_customer_percentage": (
                    100 * len(customer_ids) / population_customer_count
                ),
                "customer_ids": customer_ids,
                "anomaly_types": sorted(type_distribution),
                "anomaly_type_distribution": type_distribution,
                "dominant_anomaly_type": dominant_type,
                "spatial_cluster_count": len(cluster_ids),
                "spatial_cluster_ids": cluster_ids,
                "spatial_clusters": spatial_clusters,
                "h3_cells": sorted(group["h3_cell"].unique().tolist()),
                "latitude_center": latitude_center,
                "longitude_center": longitude_center,
                "spatial_extent_km": extent_km,
                "mean_anomaly_score": float(group["anomaly_score"].mean()),
                "max_anomaly_score": float(group["anomaly_score"].max()),
            }
        )
    return pd.DataFrame(summaries, columns=EVENT_SUMMARY_COLUMNS)


def prepare_ground_truth_events(
    ground_truth: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize known injected-event IDs and intervals for evaluation only."""
    if ground_truth.empty:
        return pd.DataFrame(columns=GROUND_TRUTH_COLUMNS)
    id_column = _column(ground_truth, "event_id", "anomaly_event_id")
    customer_column = _column(ground_truth, "customer_id", "OBJECTID")
    start_column = _column(ground_truth, "anomaly_start", "timestamp", "start_time")
    end_column = _column(ground_truth, "anomaly_end", "end_time")
    missing = [
        name
        for name, value in {
            "event identifier": id_column,
            "customer identifier": customer_column,
            "start time": start_column,
            "end time": end_column,
        }.items()
        if value is None
    ]
    if missing:
        raise ValueError(f"Ground-truth events are missing: {', '.join(missing)}")
    truth = pd.DataFrame(
        {
            "event_id": ground_truth[id_column].astype("string"),
            "customer_id": ground_truth[customer_column],
            "anomaly_start": pd.to_datetime(ground_truth[start_column], errors="coerce"),
            "anomaly_end": pd.to_datetime(ground_truth[end_column], errors="coerce"),
        }
    )
    if truth.isna().any().any() or (truth["anomaly_end"] <= truth["anomaly_start"]).any():
        raise ValueError("Ground-truth events contain invalid IDs or intervals.")
    return truth


def evaluate_events(
    predicted_events: pd.DataFrame,
    ground_truth: pd.DataFrame,
    config: EventLocalizationConfig = EventLocalizationConfig(),
) -> dict[str, Any]:
    """One-to-one event matching and event reconstruction metrics; labels used only here."""
    truth = prepare_ground_truth_events(ground_truth)
    if predicted_events.empty or truth.empty:
        return {
            "event_precision": 0.0,
            "event_recall": 0.0,
            "event_f1": 0.0,
            "event_detection_delay_hours": None,
            "cluster_event_purity": 0.0,
            "false_events": int(len(predicted_events)),
            "missed_events": int(len(truth)),
            "matched_events": 0,
            "note": "No predicted events or no usable ground-truth events.",
        }

    scores = np.zeros((len(predicted_events), len(truth)), dtype=float)
    delays = np.full((len(predicted_events), len(truth)), np.nan, dtype=float)
    for prediction_index, prediction in predicted_events.reset_index(drop=True).iterrows():
        predicted_customers = set(prediction["customer_ids"])
        predicted_start = pd.Timestamp(prediction["event_start"])
        predicted_end = pd.Timestamp(prediction["event_end"])
        for truth_index, known in truth.reset_index(drop=True).iterrows():
            if known["customer_id"] not in predicted_customers:
                continue
            if not temporal_correlation(
                {
                    "anomaly_start": predicted_start,
                    "anomaly_end": predicted_end,
                },
                known,
                config,
            ):
                continue
            known_duration = known["anomaly_end"] - known["anomaly_start"]
            prediction_duration = predicted_end - predicted_start
            overlap = max(
                pd.Timedelta(0),
                min(predicted_end, known["anomaly_end"])
                - max(predicted_start, known["anomaly_start"]),
            )
            temporal_iou = float(
                overlap
                / (prediction_duration + known_duration - overlap)
            )
            scores[prediction_index, truth_index] = (
                1.0 + temporal_iou
            )
            delays[prediction_index, truth_index] = (
                predicted_start - known["anomaly_start"]
            ).total_seconds() / 3600

    row_indices, column_indices = linear_sum_assignment(-scores)
    matches = [
        (row, column)
        for row, column in zip(row_indices, column_indices)
        if scores[row, column] > 0
    ]
    true_positive = len(matches)
    precision = true_positive / max(len(predicted_events), 1)
    recall = true_positive / max(len(truth), 1)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    matched_delays = [delays[row, column] for row, column in matches]

    purity_values: list[float] = []
    for prediction_index, prediction in predicted_events.reset_index(drop=True).iterrows():
        if scores[prediction_index].max() <= 0:
            purity_values.append(0.0)
            continue
        start = pd.Timestamp(prediction["event_start"])
        end = pd.Timestamp(prediction["event_end"])
        customers = set(prediction["customer_ids"])
        labels_in_event = truth.loc[
            truth["customer_id"].isin(customers)
            & (truth["anomaly_start"] < end)
            & (truth["anomaly_end"] > start),
            "event_id",
        ]
        purity_values.append(
            float(labels_in_event.value_counts().max() / max(len(customers), 1))
            if len(labels_in_event)
            else 0.0
        )
    return {
        "event_precision": float(precision),
        "event_recall": float(recall),
        "event_f1": float(f1),
        "event_detection_delay_hours": (
            float(np.mean(matched_delays)) if matched_delays else None
        ),
        "cluster_event_purity": float(np.mean(purity_values)) if purity_values else 0.0,
        "false_events": int(len(predicted_events) - true_positive),
        "missed_events": int(len(truth) - true_positive),
        "matched_events": true_positive,
        "ground_truth_event_count": int(len(truth)),
        "predicted_event_count": int(len(predicted_events)),
    }


def visualize_events(
    anomaly_records: pd.DataFrame,
    event_summary: pd.DataFrame,
    output_dir: str | Path,
    normal_customers: pd.DataFrame | None = None,
    selected_event_id: str | None = None,
) -> dict[str, str]:
    """Save geographic scatter, event map, selected timeline, size, and scope plots."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    saved: dict[str, str] = {}

    fig, axis = plt.subplots(figsize=(10, 7))
    if normal_customers is not None and not normal_customers.empty:
        axis.scatter(
            normal_customers["longitude"],
            normal_customers["latitude"],
            c="#cbd5e1",
            s=12,
            alpha=0.5,
            label="Not detected",
        )
    if not anomaly_records.empty:
        scatter = axis.scatter(
            anomaly_records["longitude"],
            anomaly_records["latitude"],
            c=pd.factorize(anomaly_records["event_spatial_cluster_id"])[0],
            cmap="tab20",
            s=32,
            edgecolors="black",
            linewidths=0.25,
            label="Detected anomaly",
        )
        fig.colorbar(scatter, ax=axis, label="Spatial cluster index")
    axis.set(title="Detected anomalies and geographic clusters", xlabel="Longitude", ylabel="Latitude")
    axis.legend(loc="best")
    fig.tight_layout()
    path = destination / "geographic_anomalies.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    saved["geographic_scatter"] = str(path)

    fig, axis = plt.subplots(figsize=(10, 7))
    if not event_summary.empty:
        colors = {
            "SINGLE_CUSTOMER": "#2563eb",
            "LOCAL_AREA": "#16a34a",
            "MULTI_AREA": "#dc2626",
        }
        for scope, group in event_summary.groupby("event_scope", sort=True):
            axis.scatter(
                group["longitude_center"],
                group["latitude_center"],
                label=scope,
                s=30 + 8 * np.sqrt(group["affected_customer_count"]),
                alpha=0.8,
                c=colors.get(scope, "#64748b"),
            )
            for row in group.itertuples(index=False):
                axis.annotate(row.event_id, (row.longitude_center, row.latitude_center), fontsize=6)
    axis.set(title="Localized events by event scope", xlabel="Longitude", ylabel="Latitude")
    if not event_summary.empty:
        axis.legend(loc="best")
    fig.tight_layout()
    path = destination / "geographic_event_map.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    saved["event_map"] = str(path)

    if selected_event_id is None and not event_summary.empty:
        selected_event_id = str(event_summary.iloc[0]["event_id"])
    selected = (
        anomaly_records.loc[anomaly_records["event_id"] == selected_event_id]
        if selected_event_id is not None
        else anomaly_records.iloc[0:0]
    )
    fig, axis = plt.subplots(figsize=(11, 6))
    if not selected.empty:
        customers = sorted(selected["customer_id"].unique())
        y_positions = {customer: position for position, customer in enumerate(customers)}
        for row in selected.itertuples(index=False):
            axis.broken_barh(
                [
                    (
                        matplotlib.dates.date2num(row.anomaly_start),
                        (row.anomaly_end - row.anomaly_start).total_seconds() / 86400,
                    )
                ],
                (y_positions[row.customer_id] - 0.35, 0.7),
                facecolors="#dc2626",
            )
        axis.set_yticks(range(len(customers)), [str(customer) for customer in customers])
        axis.xaxis_date()
        axis.set_title(f"Anomaly timeline: {selected_event_id}")
        axis.set_xlabel("Time")
        axis.set_ylabel("Customer ID")
        fig.autofmt_xdate()
    else:
        axis.text(0.5, 0.5, "No selected event records", ha="center", va="center")
        axis.set_axis_off()
    fig.tight_layout()
    path = destination / "event_timeline.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    saved["event_timeline"] = str(path)

    fig, axis = plt.subplots(figsize=(9, 5))
    if not event_summary.empty:
        sizes = event_summary["affected_customer_count"].value_counts().sort_index()
        axis.bar(sizes.index.astype(str), sizes.values, color="#2563eb")
    axis.set(title="Event-size distribution", xlabel="Affected customers", ylabel="Event count")
    fig.tight_layout()
    path = destination / "event_size_distribution.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    saved["event_size_distribution"] = str(path)

    fig, axis = plt.subplots(figsize=(8, 5))
    scope_order = ["SINGLE_CUSTOMER", "LOCAL_AREA", "MULTI_AREA"]
    counts = (
        event_summary["event_scope"].value_counts().reindex(scope_order, fill_value=0)
        if not event_summary.empty
        else pd.Series(0, index=scope_order)
    )
    axis.bar(counts.index, counts.values, color=["#2563eb", "#16a34a", "#dc2626"])
    axis.set(title="Event-scope distribution", xlabel="Event scope", ylabel="Event count")
    axis.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    path = destination / "event_scope_distribution.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    saved["event_scope_distribution"] = str(path)
    return saved
