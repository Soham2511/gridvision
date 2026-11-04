"""Evidence and result validator with one bounded specialist rework round."""

from __future__ import annotations

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.schemas.communication import ValidationReport
from ai.commercial.schemas.state import CommercialState


def validate_results(
    state: CommercialState,
    settings: CommercialSettings,
) -> dict:
    results = state.get("specialist_results", {})
    errors = list(state.get("errors", []))
    issues = list(errors)
    retryable_failed = []
    unavailable = []

    for result in results.values():
        if result.status == "failed":
            message = (
                result.error.message
                if result.error
                else f"{result.specialist} returned a failed result."
            )
            issues.append(message)
            if (
                result.specialist != "cost_optimization"
                and result.error is not None
                and result.error.retryable
            ):
                retryable_failed.append(result)
        elif result.status == "unavailable":
            unavailable.append(result)
            message = (
                result.error.message
                if result.error
                else f"{result.specialist} data is unavailable."
            )
            issues.append(message)
        elif result.findings and not result.evidence_refs:
            issues.append(
                f"{result.specialist} returned findings without evidence references."
            )

    rework_count = state.get("rework_count", 0)
    if state.get("conflicts"):
        issues.extend(
            f"Unresolved conflict: {conflict}"
            for conflict in state["conflicts"]
        )
    if errors:
        status = "escalated"
    elif retryable_failed and rework_count < settings.max_rework_attempts:
        status = "needs_rework"
        rework_count += 1
    elif any(result.status == "failed" for result in results.values()):
        status = "escalated"
    elif unavailable or not results:
        status = "incomplete"
    elif issues:
        status = "incomplete"
    else:
        status = "passed"

    report = ValidationReport(
        status=status,
        issues=tuple(dict.fromkeys(issues)),
        evidence_count=len(state.get("evidence_refs", [])),
    )
    updated_assignments = []
    for assignment in state.get("assignments", []):
        result = results.get(assignment.task_id)
        if result is None:
            updated_assignments.append(assignment)
        else:
            assignment_status = (
                "completed" if result.status == "completed" else "failed"
            )
            updated_assignments.append(
                assignment.model_copy(update={"status": assignment_status})
            )
    return {
        "validation_status": report,
        "rework_count": rework_count,
        "assignments": updated_assignments,
        "step_count": 1,
    }
