"""Evidence-preserving final response node."""

from __future__ import annotations

from typing import Any

from ai.commercial.schemas.communication import (
    FinalResponse,
    ValidationReport,
)
from ai.commercial.schemas.state import CommercialState


def finalize_response(state: CommercialState) -> dict[str, Any]:
    report = state.get("validation_status") or ValidationReport(
        status="escalated",
        issues=("Workflow ended without a validation result.",),
    )
    results = state.get("specialist_results", {})
    findings = [
        finding
        for result in results.values()
        for finding in result.findings
    ]
    assumptions = list(state.get("assumptions", []))
    conflicts = list(state.get("conflicts", []))

    if report.status == "passed":
        summary = "The requested analysis completed with validated evidence."
    elif report.status == "incomplete":
        summary = (
            "The workflow could not complete an evidence-backed analysis. "
            "No unsupported numeric results or savings are reported."
        )
    elif report.status == "needs_rework":
        summary = "The workflow stopped before its bounded rework cycle completed."
    else:
        summary = "The request was escalated; no unsupported recommendation was produced."

    response = FinalResponse(
        request_id=state.get("request_id"),
        factory_id=state.get("factory_id"),
        status=report.status,
        summary=summary,
        findings=tuple(findings),
        evidence_refs=tuple(state.get("evidence_refs", [])),
        assumptions=tuple(assumptions),
        conflicts=tuple(conflicts),
        validation=report,
        errors=tuple(state.get("errors", [])),
    )
    return {
        "final_response": response.model_dump(mode="json"),
        "step_count": 1,
    }
