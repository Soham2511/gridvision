"""Dataset-derived date validation shared by assistant tools and API services."""

from __future__ import annotations

from datetime import date
from typing import Any


MAX_RUN_DAYS = 7


def dataset_date_bounds(anomaly_service: Any) -> tuple[date, date]:
    summary = anomaly_service.get_summary()
    dataset = summary.get("dataset", {})
    start_value = dataset.get("startDate")
    end_value = dataset.get("endDate")
    if not start_value or not end_value:
        raise ValueError("The anomaly dataset's date range is unavailable.")
    try:
        start = date.fromisoformat(str(start_value)[:10])
        end = date.fromisoformat(str(end_value)[:10])
    except ValueError as exc:
        raise ValueError("The anomaly dataset has invalid date-bound metadata.") from exc
    if end < start:
        raise ValueError("The anomaly dataset's date range is invalid.")
    return start, end


def validate_requested_dates(
    anomaly_service: Any,
    start_value: str | date,
    end_value: str | date,
    *,
    max_days: int = MAX_RUN_DAYS,
) -> tuple[date, date]:
    """Validate an inclusive date range against the active dataset metadata."""
    try:
        start = start_value if isinstance(start_value, date) else date.fromisoformat(start_value)
        end = end_value if isinstance(end_value, date) else date.fromisoformat(end_value)
    except ValueError as exc:
        raise ValueError("Dates must use the ISO YYYY-MM-DD format.") from exc
    dataset_start, dataset_end = dataset_date_bounds(anomaly_service)
    if end < start:
        raise ValueError("end_date must be on or after start_date.")
    if start < dataset_start or end > dataset_end:
        raise ValueError(
            f"Requested dates must be within the available dataset range "
            f"{dataset_start.isoformat()} through {dataset_end.isoformat()}."
        )
    run_days = (end - start).days + 1
    if run_days > max_days:
        raise ValueError(f"Each analysis run may cover at most {max_days} days.")
    return start, end

