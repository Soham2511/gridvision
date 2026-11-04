"""Approved Severity Scoring Benchmark and Deterministic Calculator for GridVision.

Version: v1.0-approved
Defines explicit scoring dimensions, weights, priority bands, and mandatory electrical safety overrides.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from app.domain.complaints.entities import (
    ScoringFactorBreakdown,
    SeverityLevel,
    SeverityResult,
)

BENCHMARK_VERSION = "GRIDVISION_RESIDENTIAL_SEVERITY_BENCHMARK_V1_0"

# Dimension Weights (Total = 1.00)
DIMENSION_WEIGHTS = {
    "safety_risk": 0.35,
    "disruption_extent": 0.25,
    "duration_factor": 0.15,
    "recurrence_factor": 0.15,
    "essential_services_impact": 0.10,
}

# Priority Bands
PRIORITY_BANDS: list[Tuple[float, float, SeverityLevel]] = [
    (85.0, 100.0, SeverityLevel.CRITICAL),
    (66.0, 84.99, SeverityLevel.HIGH),
    (36.0, 65.99, SeverityLevel.MEDIUM),
    (0.0, 35.99, SeverityLevel.LOW),
]


def resolve_severity_level(score: float) -> SeverityLevel:
    """Map numeric score (0-100) to approved Priority Band."""
    clamped = max(0.0, min(100.0, score))
    for lower, upper, level in PRIORITY_BANDS:
        if lower <= clamped <= upper:
            return level
    return SeverityLevel.LOW


def calculate_deterministic_severity(
    factors: ScoringFactorBreakdown,
    category_id: str,
    category_data: Optional[Dict[str, Any]] = None,
) -> SeverityResult:
    """Compute reproducible severity score using approved benchmark weights and safety rules.

    The actual numeric score is calculated deterministically by this function,
    never by arbitrary LLM hallucination.
    """
    cat_data = category_data or {}
    clean_cat = (category_id or "").strip().lower()

    # 1. Base Weighted Score
    raw_score = (
        (factors.safety_risk * DIMENSION_WEIGHTS["safety_risk"])
        + (factors.disruption_extent * DIMENSION_WEIGHTS["disruption_extent"])
        + (factors.duration_factor * DIMENSION_WEIGHTS["duration_factor"])
        + (factors.recurrence_factor * DIMENSION_WEIGHTS["recurrence_factor"])
        + (factors.essential_services_impact * DIMENSION_WEIGHTS["essential_services_impact"])
    )
    final_score = round(max(0.0, min(100.0, raw_score)), 1)
    override_applied = False
    override_note = None

    # 2. Mandatory Electrical Safety Override Rules
    if clean_cat == "electrical_safety":
        safety_type = str(cat_data.get("safety_issue_type", "")).lower()
        is_ongoing = bool(cat_data.get("is_condition_ongoing", True))
        is_shock_spark_smoke = any(
            t in safety_type for t in ["sparking", "burning", "shock", "exposed", "overheating"]
        )

        if is_ongoing and is_shock_spark_smoke:
            override_applied = True
            final_score = max(final_score, 90.0)  # Guaranteed CRITICAL
            override_note = (
                "Statutory Safety Override: Active ongoing electrical hazard "
                f"({safety_type}) clamped score to minimum 90.0 (CRITICAL)."
            )
        else:
            override_applied = True
            final_score = max(final_score, 72.0)  # Guaranteed HIGH
            override_note = (
                "Statutory Safety Override: Reported electrical safety hazard "
                "clamped score to minimum 72.0 (HIGH) for urgent inspection."
            )

    # 3. Complete Outage Entire House Override
    elif clean_cat == "power_supply_interruption":
        if cat_data.get("scope_affected") == "entire_house" and cat_data.get("power_currently_available") is True:
            # Active complete outage
            if final_score < 70.0:
                override_applied = True
                final_score = 75.0
                override_note = "Feeder Outage Override: Ongoing total household power cut assigned High priority (75.0)."

    level = resolve_severity_level(final_score)

    factors_copy = factors.model_copy(
        update={
            "safety_override_applied": override_applied,
            "override_reason": override_note,
        }
    )

    rationale_parts = [
        f"Calculated under {BENCHMARK_VERSION}.",
        f"Base weighted score: {raw_score:.1f}/100.",
        f"Evaluated dimensions: Safety Risk ({factors.safety_risk:.0f}%), "
        f"Disruption Extent ({factors.disruption_extent:.0f}%), "
        f"Duration ({factors.duration_factor:.0f}%), "
        f"Recurrence ({factors.recurrence_factor:.0f}%), "
        f"Essential Services Impact ({factors.essential_services_impact:.0f}%).",
    ]
    if override_note:
        rationale_parts.append(override_note)
    rationale_parts.append(f"Final assigned priority: {level.value} ({final_score:.1f}).")

    return SeverityResult(
        severity_score=final_score,
        severity_level=level,
        scoring_rationale=" ".join(rationale_parts),
        factor_breakdown=factors_copy,
        benchmark_version=BENCHMARK_VERSION,
    )

