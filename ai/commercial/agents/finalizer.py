"""Evidence-preserving final response node."""

from __future__ import annotations

from typing import Any

from ai.commercial.agents.planner import GroqAnswerError, GroqPlanner
from ai.commercial.schemas.communication import (
    FinalResponse,
    ValidationReport,
)
from ai.commercial.schemas.state import CommercialState


def finalize_response(
    state: CommercialState,
    answer_generator: GroqPlanner | None = None,
) -> dict[str, Any]:
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
    errors = list(state.get("errors", []))
    evidence_refs = list(state.get("evidence_refs", []))
    llm_call_count = 0

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
        summary = (
            "The request was escalated; no unsupported recommendation "
            "was produced."
        )

    has_completed_result = any(
        result.status == "completed" for result in results.values()
    )
    if (
        answer_generator is not None
        and report.status in {"passed", "incomplete"}
        and has_completed_result
    ):
        tool_results = [
            {
                "specialist": result.specialist,
                "status": result.status,
                "findings": list(result.findings),
                "data": (
                    result.data
                    if result.specialist != "operations"
                    else {}
                ),
                "error": (
                    result.error.model_dump(mode="json")
                    if result.error is not None
                    else None
                ),
            }
            for result in results.values()
        ]
        llm_call_count = 1
        try:
            summary, evidence_refs = answer_generator.synthesize_answer(
                question=state.get("user_goal", ""),
                conversation_history=state.get("conversation_history", []),
                specialist_results=tool_results,
                evidence_refs=evidence_refs,
                assumptions=assumptions,
                conflicts=conflicts,
                status=report.status,
            )
        except GroqAnswerError as exc:
            error = f"ANSWER_GENERATION_FAILED: {exc}"
            errors.append(error)
            report = report.model_copy(
                update={
                    "status": "incomplete",
                    "issues": tuple(dict.fromkeys((*report.issues, error))),
                }
            )
            summary = (
                "I found relevant tool results, but could not produce a "
                f"grounded answer. {exc}"
            )

    response = FinalResponse(
        request_id=state.get("request_id"),
        factory_id=state.get("factory_id"),
        status=report.status,
        summary=summary,
        findings=tuple(findings),
        evidence_refs=tuple(evidence_refs),
        assumptions=tuple(assumptions),
        conflicts=tuple(conflicts),
        validation=report,
        errors=tuple(errors),
    )
    return {
        "final_response": response.model_dump(mode="json"),
        "step_count": 1,
        "llm_call_count": llm_call_count,
    }
