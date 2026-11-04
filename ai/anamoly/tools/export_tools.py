"""Export saved GridVision analysis records through existing report storage."""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from typing import Any

from ai.anamoly.tools.registry import ToolDefinition, ToolRegistry
from ai.anamoly.date_guardrails import validate_requested_dates


def _records(run: dict[str, Any], dataset: str) -> list[dict[str, Any]]:
    if dataset == "consolidated":
        return [
            {"record_type": "anomaly", **record}
            for record in run.get("anomaly_windows", [])
        ] + [
            {"record_type": "event", **record}
            for record in run.get("events", [])
        ]
    source_key = "anomaly_windows" if dataset == "anomalies" else "events"
    records = run.get(source_key)
    if not isinstance(records, list):
        raise ValueError(f"No {dataset} records are available in this run.")
    return records


def _export(
    args: dict[str, Any],
    context: dict[str, Any],
    dataset: str,
    format_name: str,
) -> dict[str, Any]:
    service = context.get("anomaly_service")
    if service is None:
        raise RuntimeError("The GridVision anomaly analysis service is unavailable.")
    run_id = args["run_id"]
    try:
        uuid.UUID(hex=run_id)
    except ValueError as exc:
        raise ValueError("Invalid run ID.") from exc
    run = service.get_run(run_id)
    if run is None or run.get("status") != "completed":
        raise ValueError("Exports require a completed saved analysis run.")
    records = _records(run, dataset)
    run_request = run.get("request", {})
    if not run_request.get("start_date") or not run_request.get("end_date"):
        raise ValueError("The saved run is missing its date range.")
    validate_requested_dates(
        service, run_request["start_date"], run_request["end_date"]
    )
    if args.get("severity"):
        records = [
            row
            for row in records
            if str(row.get("severity", "")).lower() == args["severity"].lower()
        ]
    if args.get("anomaly_type"):
        records = [
            row
            for row in records
            if str(row.get("anomaly_type", row.get("event_type", ""))).lower()
            == args["anomaly_type"].lower()
        ]
    export_id = uuid.uuid4().hex
    suffix = "json" if format_name in {"json", "geojson"} else "csv"
    filename = f"assistant_export_{export_id}.{suffix}"
    run_directory = Path(service.runs_path).resolve() / run_id
    target = run_directory / filename
    if format_name == "json":
        with target.open("x", encoding="utf-8") as file:
            file.write(json.dumps(records, ensure_ascii=False, indent=2, default=str) + "\n")
    elif format_name == "geojson":
        features = []
        for record in records:
            latitude = record.get("latitude_center", record.get("latitude"))
            longitude = record.get("longitude_center", record.get("longitude"))
            if latitude is None or longitude is None:
                raise ValueError("GeoJSON export requires saved event coordinates.")
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(longitude), float(latitude)],
                    },
                    "properties": record,
                }
            )
        with target.open("x", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {"type": "FeatureCollection", "features": features},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
                + "\n"
            )
    else:
        columns = sorted({key for record in records for key in record})
        with target.open("x", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
    return {
        "run_id": run_id,
        "record_count": len(records),
        "format": format_name,
        "download_url": (
            f"/api/v1/models/anomaly-prediction/runs/{run_id}/download/{filename}"
        ),
    }


def register_export_tools(registry: ToolRegistry) -> None:
    personas = frozenset({"government"})
    for name, dataset in (
        ("export_anomaly_records", "anomalies"),
        ("export_events", "events"),
        ("export_event_details", "events"),
        ("export_consolidated_report", "consolidated"),
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description=f"Export saved {dataset} records from a completed run.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "format": {"type": "string", "enum": ["csv", "json", "geojson"]},
                        "severity": {"type": "string"},
                        "anomaly_type": {"type": "string"},
                    },
                    "required": ["run_id", "format"],
                    "additionalProperties": False,
                },
                handler=lambda args, context, kind=dataset: _export(
                    args, context, kind, args["format"]
                ),
                allowed_personas=personas,
                side_effects=True,
                user_confirmation_required=True,
                requires_authenticated_principal=False,
            )
        )
