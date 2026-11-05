"""Complaint Severity Scoring Agent.

Evaluates complaints that are not conclusively invalid (PLAUSIBLE or INCONCLUSIVE)
and assigns a reproducible severity score using the approved, configurable benchmark.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.complaints.benchmark import calculate_deterministic_severity
from app.domain.complaints.entities import (
    ScoringFactorBreakdown,
    SeverityResult,
)

logger = logging.getLogger("gridvision.application.complaints.scoring_agent")


class ComplaintSeverityScoringAgent:
    """Agent orchestrating factor extraction and deterministic benchmark scoring."""

    def score_complaint(
        self,
        category_id: str,
        category_data: Dict[str, Any],
        title: str,
        description: str,
    ) -> SeverityResult:
        """Extract structured factors from complaint and calculate deterministic score."""
        factors = self._extract_scoring_factors(category_id, category_data, title, description)
        return calculate_deterministic_severity(
            factors=factors,
            category_id=category_id,
            category_data=category_data,
        )

    def _extract_scoring_factors(
        self,
        category_id: str,
        category_data: Dict[str, Any],
        title: str,
        description: str,
    ) -> ScoringFactorBreakdown:
        """Derive normalized 0-100 dimension factors from structured inputs and text context."""
        clean_cat = (category_id or "").strip().lower()
        combined_text = f"{title} {description}".lower()

        # 1. Safety Risk (0-100)
        safety_risk = 0.0
        if clean_cat == "electrical_safety":
            safety_type = str(category_data.get("safety_issue_type", "")).lower()
            if any(k in safety_type for k in ["sparking", "shock", "burning", "exposed"]):
                safety_risk = 95.0
            else:
                safety_risk = 75.0
        elif any(w in combined_text for w in ["spark", "smoke", "shock", "fire", "burning", "hazard", "burn"]):
            safety_risk = 80.0
        elif clean_cat == "voltage_fluctuation":
            safety_risk = 35.0  # High voltage can risk appliance fires/damage
        elif clean_cat in ("meter_issue", "ev_charging"):
            safety_risk = 25.0
        else:
            safety_risk = 10.0

        # 2. Disruption Extent (0-100)
        scope = str(category_data.get("scope_affected", "")).lower()
        if scope == "entire_house" or "entire house" in combined_text or "whole house" in combined_text:
            disruption_extent = 100.0
        elif scope == "partial_house" or "partial" in combined_text:
            disruption_extent = 55.0
        elif clean_cat == "power_supply_interruption":
            disruption_extent = 85.0
        elif clean_cat == "voltage_fluctuation":
            disruption_extent = 60.0
        elif clean_cat in ("billing_consumption", "meter_issue"):
            disruption_extent = 30.0  # Administrative/billing impact
        else:
            disruption_extent = 25.0

        # 3. Duration Factor (0-100)
        is_ongoing = bool(
            category_data.get("is_currently_occurring", True)
            if "is_currently_occurring" in category_data
            else category_data.get("is_condition_ongoing", True)
            if "is_condition_ongoing" in category_data
            else category_data.get("power_currently_available", True)
            if "power_currently_available" in category_data
            else category_data.get("is_ongoing", True)
        )
        dur_hours = float(category_data.get("approximate_duration_hours", 0.0) or 0.0)

        if is_ongoing:
            if dur_hours > 24.0:
                duration_factor = 95.0
            elif dur_hours > 6.0:
                duration_factor = 85.0
            else:
                duration_factor = 75.0  # Ongoing active condition
        else:
            if dur_hours > 24.0:
                duration_factor = 65.0
            elif dur_hours > 6.0:
                duration_factor = 45.0
            else:
                duration_factor = 25.0

        # 4. Recurrence Factor (0-100)
        is_rec = bool(
            category_data.get("is_recurring", False)
            or category_data.get("previous_bills_affected", False)
            or "frequent" in str(category_data.get("interruption_type", "")).lower()
            or "frequent" in str(category_data.get("voltage_issue_type", "")).lower()
            or any(w in combined_text for w in ["frequent", "daily", "again", "repeated", "every day", "recurring"])
        )
        if is_rec:
            recurrence_factor = 85.0
        elif str(category_data.get("pattern", "")) == "continuous":
            recurrence_factor = 75.0
        else:
            recurrence_factor = 25.0

        # 5. Essential Services Impact (0-100)
        essential_services_impact = 15.0
        if any(w in combined_text for w in ["medical", "oxygen", "dialysis", "infant", "patient", "elderly"]):
            essential_services_impact = 100.0
        elif any(w in combined_text for w in ["refrigerator", "fridge", "food", "pump", "water", "freezer", "medicine"]):
            essential_services_impact = 65.0
        elif clean_cat in ("power_supply_interruption", "electrical_safety"):
            essential_services_impact = 50.0

        return ScoringFactorBreakdown(
            safety_risk=round(safety_risk, 1),
            disruption_extent=round(disruption_extent, 1),
            duration_factor=round(duration_factor, 1),
            recurrence_factor=round(recurrence_factor, 1),
            essential_services_impact=round(essential_services_impact, 1),
        )

