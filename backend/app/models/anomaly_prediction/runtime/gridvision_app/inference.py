"""Saved-model inference over selected records from the configured parquet source."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from gridvision_event_localization import (
    EventLocalizationConfig,
    form_events,
    generate_event_summary,
    prepare_anomaly_records,
)
from gridvision_pipeline import (
    CUSTOMER,
    ENERGY,
    INPUT_COLUMNS,
    LATITUDE,
    LONGITUDE,
    TIMESTAMP,
    load_model_bundle,
    predict_anomaly_events_from_bundle,
)

MAX_ANALYSIS_ROWS = 2_100_000
HISTORY_HOURS = 168
POST_EVENT_HOURS = 12


def json_safe(value: Any) -> Any:
    """Convert NumPy and pandas values to strict JSON-compatible values."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (pd.Timedelta,)):
        return value.total_seconds()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


class InferenceService:
    """Owns the loaded artifact and reads only model input columns from parquet."""

    def __init__(self, data_path: str | Path, model_path: str | Path) -> None:
        self.data_path = Path(data_path).resolve()
        self.model_path = Path(model_path).resolve()
        if not self.data_path.is_file():
            raise FileNotFoundError(f"Parquet input was not found: {self.data_path}")
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Model artifact was not found: {self.model_path}")
        self.bundle = load_model_bundle(self.model_path)
        self.parquet = pq.ParquetFile(self.data_path)
        if not set(INPUT_COLUMNS).issubset(self.parquet.schema.names):
            missing = sorted(set(INPUT_COLUMNS) - set(self.parquet.schema.names))
            raise ValueError(f"Parquet input is missing model columns: {missing}")
        self.customer_locations = self._read_customer_locations()
        self.customer_ids = set(self.customer_locations[CUSTOMER].astype(int))
        self.start_time, self.end_time = self._read_time_bounds()

    def model_metadata(self) -> dict[str, Any]:
        return {
            "model_path": str(self.model_path),
            "data_path": str(self.data_path),
            "detector_threshold": float(self.bundle["detector_threshold"]),
            "point_feature_count": len(self.bundle["point_features"]),
            "point_features": list(self.bundle["point_features"]),
            "anomaly_types": list(self.bundle.get("anomaly_types", [])),
            "source_columns": list(INPUT_COLUMNS),
            "source_rows": int(self.parquet.metadata.num_rows),
            "source_customer_count": len(self.customer_ids),
            "max_analysis_rows": MAX_ANALYSIS_ROWS,
            "source_start": self.start_time.isoformat(),
            "source_end": self.end_time.isoformat(),
            "saved_evaluation_metrics": self.bundle.get("evaluation_metrics", {}),
        }

    def customer_page(self, query: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        rows = self.customer_locations
        if query.strip():
            rows = rows.loc[
                rows[CUSTOMER].astype(str).str.contains(query.strip(), case=False, regex=False)
            ]
        page = rows.iloc[offset : offset + limit]
        return {
            "items": json_safe(page.to_dict(orient="records")),
            "offset": offset,
            "limit": limit,
            "total": len(rows),
        }

    def analyze(
        self,
        *,
        customer_ids: list[int] | None,
        start_date: date,
        end_date: date,
        localization: EventLocalizationConfig,
    ) -> dict[str, Any]:
        selected_ids = sorted(self.customer_ids if customer_ids is None else set(customer_ids))
        unknown_ids = sorted(set(selected_ids) - self.customer_ids)
        if unknown_ids:
            raise ValueError(f"Unknown customer IDs: {unknown_ids[:20]}")
        if not selected_ids:
            raise ValueError("Select at least one customer or choose all customers.")

        start = pd.Timestamp(start_date)
        end_exclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        source_start = self.start_time.normalize()
        source_end_exclusive = self.end_time + pd.Timedelta(hours=1)
        if start < source_start or end_exclusive > source_end_exclusive:
            raise ValueError(
                f"Requested dates must be within {source_start.date()} and "
                f"{self.end_time.date()}."
            )
        history_start = max(start - pd.Timedelta(hours=HISTORY_HOURS), source_start)
        read_end = min(
            end_exclusive + pd.Timedelta(hours=POST_EVENT_HOURS),
            source_end_exclusive,
        )
        expected_rows = len(selected_ids) * int(
            (read_end - history_start) / pd.Timedelta(hours=1)
        )
        if expected_rows > MAX_ANALYSIS_ROWS:
            raise ValueError(
                f"Analysis requires about {expected_rows:,} hourly rows including "
                f"feature history; the per-run limit is {MAX_ANALYSIS_ROWS:,}. "
                "Choose fewer customers or a shorter date range."
            )

        data = self._read_selected_rows(
            selected_ids, history_start, read_end
        )
        event_windows = predict_anomaly_events_from_bundle(data, self.bundle)
        if event_windows.empty:
            requested_windows = event_windows
        else:
            requested_windows = event_windows.loc[
                (pd.to_datetime(event_windows["start_time"]) < end_exclusive)
                & (pd.to_datetime(event_windows["end_time"]) > start)
            ].copy()
        anomaly_records = prepare_anomaly_records(requested_windows)
        localized_records, _ = form_events(anomaly_records, localization)
        event_summary = generate_event_summary(
            localized_records,
            population_customer_count=len(selected_ids),
            config=localization,
        )

        if not localized_records.empty:
            scope_by_event = event_summary.set_index("event_id")["event_scope"]
            localized_records["event_scope"] = localized_records["event_id"].map(
                scope_by_event
            )
            localized_records["severity"] = localized_records["anomaly_score"]

        type_counts = (
            localized_records["anomaly_type"].value_counts().to_dict()
            if not localized_records.empty
            else {}
        )
        scope_counts = (
            event_summary["event_scope"].value_counts().to_dict()
            if not event_summary.empty
            else {}
        )
        event_size_counts = (
            {
                "1 customer": int((event_summary["affected_customer_count"] == 1).sum()),
                "2-5 customers": int(
                    event_summary["affected_customer_count"].between(2, 5).sum()
                ),
                "6-20 customers": int(
                    event_summary["affected_customer_count"].between(6, 20).sum()
                ),
                "21+ customers": int(
                    (event_summary["affected_customer_count"] >= 21).sum()
                ),
            }
            if not event_summary.empty
            else {}
        )
        return {
            "metadata": {
                "source_data": str(self.data_path),
                "model_artifact": str(self.model_path),
                "requested_start": start.isoformat(),
                "requested_end_exclusive": end_exclusive.isoformat(),
                "history_start": history_start.isoformat(),
                "read_end_exclusive": read_end.isoformat(),
                "selected_customer_count": len(selected_ids),
                "input_rows_scored": len(data),
                "detector_threshold": float(self.bundle["detector_threshold"]),
                "point_feature_count": len(self.bundle["point_features"]),
                "localization": asdict(localization),
                "note": (
                    "Ground-truth columns and source anomaly metadata were not read "
                    "or used by inference."
                ),
            },
            "metrics": {
                "input_rows_scored": len(data),
                "selected_customer_count": len(selected_ids),
                "anomaly_window_count": len(localized_records),
                "localized_event_count": len(event_summary),
                "affected_customer_count": int(
                    localized_records["customer_id"].nunique()
                    if not localized_records.empty
                    else 0
                ),
                "anomaly_type_counts": type_counts,
                "event_scope_counts": scope_counts,
                "event_size_distribution": event_size_counts,
            },
            "events": json_safe(event_summary.to_dict(orient="records")),
            "anomaly_windows": json_safe(
                localized_records.to_dict(orient="records")
            ),
            "affected_customer_ids": (
                sorted(localized_records["customer_id"].unique().tolist())
                if not localized_records.empty
                else []
            ),
        }

    def _read_customer_locations(self) -> pd.DataFrame:
        columns = [CUSTOMER, LATITUDE, LONGITUDE]
        frame = self.parquet.read_row_group(0, columns=columns).to_pandas()
        locations = frame.drop_duplicates(CUSTOMER, keep="first").sort_values(
            CUSTOMER
        )
        if locations.empty or locations[columns].isna().any().any():
            raise ValueError("The first parquet row group has no valid customer locations.")
        return locations.reset_index(drop=True)

    def _read_time_bounds(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        timestamp_index = self.parquet.schema.names.index(TIMESTAMP)
        first = self.parquet.metadata.row_group(0).column(timestamp_index).statistics
        last = self.parquet.metadata.row_group(
            self.parquet.metadata.num_row_groups - 1
        ).column(timestamp_index).statistics
        if first is not None and last is not None and first.has_min_max and last.has_min_max:
            return pd.Timestamp(first.min), pd.Timestamp(last.max)
        first_frame = self.parquet.read_row_group(
            0, columns=[TIMESTAMP]
        ).to_pandas()
        last_frame = self.parquet.read_row_group(
            self.parquet.metadata.num_row_groups - 1, columns=[TIMESTAMP]
        ).to_pandas()
        return (
            pd.to_datetime(first_frame[TIMESTAMP]).min(),
            pd.to_datetime(last_frame[TIMESTAMP]).max(),
        )

    def _read_selected_rows(
        self,
        customer_ids: list[int],
        start: pd.Timestamp,
        end_exclusive: pd.Timestamp,
    ) -> pd.DataFrame:
        timestamp_index = self.parquet.schema.names.index(TIMESTAMP)
        selected = set(customer_ids)
        parts: list[pd.DataFrame] = []
        for row_group_index in range(self.parquet.metadata.num_row_groups):
            statistics = self.parquet.metadata.row_group(row_group_index).column(
                timestamp_index
            ).statistics
            if statistics is not None and statistics.has_min_max:
                row_min = pd.Timestamp(statistics.min)
                row_max = pd.Timestamp(statistics.max)
                if row_max < start or row_min >= end_exclusive:
                    continue
            frame = self.parquet.read_row_group(
                row_group_index, columns=INPUT_COLUMNS
            ).to_pandas()
            frame[TIMESTAMP] = pd.to_datetime(frame[TIMESTAMP], errors="coerce")
            frame = frame.loc[
                frame[CUSTOMER].isin(selected)
                & frame[TIMESTAMP].ge(start)
                & frame[TIMESTAMP].lt(end_exclusive),
                INPUT_COLUMNS,
            ]
            if not frame.empty:
                parts.append(frame)
        if not parts:
            raise ValueError("No matching rows were found for the requested customers and dates.")
        data = pd.concat(parts, ignore_index=True)
        data[CUSTOMER] = pd.to_numeric(data[CUSTOMER], errors="coerce")
        data[ENERGY] = pd.to_numeric(data[ENERGY], errors="coerce")
        for column in (LATITUDE, LONGITUDE):
            data[column] = pd.to_numeric(data[column], errors="coerce")
        invalid = (
            data[INPUT_COLUMNS].isna().any(axis=1)
            | ~np.isfinite(data[ENERGY])
            | ~np.isfinite(data[LATITUDE])
            | ~np.isfinite(data[LONGITUDE])
        )
        if invalid.any():
            raise ValueError(
                f"Input contains {int(invalid.sum())} rows with missing or non-finite model values."
            )
        data[CUSTOMER] = data[CUSTOMER].astype("int64")
        data[ENERGY] = data[ENERGY].astype("float32")
        data = data.sort_values([CUSTOMER, TIMESTAMP], kind="mergesort").reset_index(
            drop=True
        )
        duplicates = data.duplicated([CUSTOMER, TIMESTAMP])
        if duplicates.any():
            raise ValueError(
                f"Input contains {int(duplicates.sum())} duplicate customer-hour records."
            )
        gaps = data.groupby(CUSTOMER, sort=False)[TIMESTAMP].diff()
        irregular = gaps.notna() & gaps.ne(pd.Timedelta(hours=1))
        if irregular.any():
            raise ValueError(
                "Selected customer history contains missing or irregular hourly intervals."
            )
        missing_customers = set(customer_ids) - set(data[CUSTOMER].unique())
        if missing_customers:
            raise ValueError(
                f"No hourly readings found for customer IDs: {sorted(missing_customers)[:20]}"
            )
        return data
