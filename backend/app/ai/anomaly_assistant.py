"""Conservative reports over existing detector event output."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.ai.rag import ApprovedCorpus


def build_anomaly_report(
    run: dict[str, Any],
    event: dict[str, Any],
    *,
    corpus: ApprovedCorpus,
) -> dict[str, Any]:
    """Preserve detector labels and separate synthetic output from fault evidence."""
    anomaly_types = list(event.get("anomaly_types") or [])
    dominant = event.get("dominant_anomaly_type")
    query = " ".join(str(value) for value in [dominant, *anomaly_types] if value)
    retrieval = corpus.retrieve(query, jurisdiction="IN", top_k=4)
    run_id = str(run.get("analysis_id") or run.get("run_id") or "")
    event_id = str(event.get("event_id") or "")
    report_id = hashlib.sha256(f"{run_id}:{event_id}".encode()).hexdigest()[:32]
    return {
        "reportId": report_id,
        "runId": run_id,
        "eventId": event_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "available" if retrieval.passages else "partial",
        "summary": {
            "eventScope": event.get("event_scope"),
            "eventStart": event.get("event_start"),
            "eventEnd": event.get("event_end"),
            "anomalyTypes": anomaly_types,
            "dominantAnomalyType": dominant,
            "affectedCustomerCount": event.get("affected_customer_count"),
            "meanAnomalyScore": event.get("mean_anomaly_score"),
            "maxAnomalyScore": event.get("max_anomaly_score"),
        },
        "possibleCauses": [],
        "recommendedActions": [
            {
                "text": "Compare the event with source records before making an operational decision.",
                "kind": "caution",
                "citationIds": [],
            }
        ],
        "guidance": [
            passage.model_dump(mode="json") for passage in retrieval.passages
        ],
        "limitations": [
            "This event comes from the project's synthetic 2019 anomaly dataset.",
            "Synthetic detector output is not verified real-world electrical fault evidence.",
            "No live meter telemetry is configured.",
            "An anomaly category does not establish its physical cause.",
            "No approved, relevant guidance was retrieved."
            if not retrieval.passages
            else "Retrieved guidance is general and does not diagnose this event.",
        ],
        "sourceProvenance": "synthetic",
        "isLiveTelemetry": False,
        "verifiedFaultEvidence": False,
        "modelRunMetadata": {
            "modelVersion": (run.get("metadata") or {}).get("model_version"),
            "datasetVersion": "untracked",
        },
    }
