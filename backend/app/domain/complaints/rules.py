"""Authoritative Complaint Validation Policy and Invalidation Rules.

Governs when the Complaint Validator Agent may conclusively mark a complaint INVALID,
guaranteeing that missing or incomplete telemetry is classified as INCONCLUSIVE and
proceeds to severity scoring rather than being rejected.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.domain.complaints.entities import (
    EvidenceItem,
    ValidationOutcome,
    ValidationResult,
)


class ComplaintValidationPolicy:
    """Enforces conservative, evidence-grounded validation boundaries."""

    @staticmethod
    def evaluate_electrical_safety(
        category_data: Dict[str, Any],
    ) -> ValidationResult:
        """Safety complaints must never be disproven by normal meter readings."""
        hazard_type = category_data.get("safety_issue_type", "unspecified safety concern")
        location = category_data.get("hazard_location", "premises")
        return ValidationResult(
            outcome=ValidationOutcome.PLAUSIBLE,
            reason="Safety Precedence Rule",
            explanation=(
                f"Electrical safety report ({hazard_type} at {location}) accepted for urgent severity assessment. "
                "Per GridVision Safety Policy, potential electrical shock or fire hazards cannot be dismissed "
                "or invalidated by aggregate meter telemetry."
            ),
            data_coverage="safety_override",
            timestamps_checked=[],
            evidence_items=[
                EvidenceItem(
                    source_tool="safety_policy_guardrail",
                    metric_name="safety_hazard_reported",
                    observed_value=hazard_type,
                    finding="Mandatory escalation: Electrical safety allegations bypass automated telemetry invalidation.",
                    supports_invalidation=False,
                )
            ],
        )

    @staticmethod
    def evaluate_voltage_fluctuation(
        has_voltage_telemetry: bool,
    ) -> ValidationResult:
        """Voltage complaints cannot be disproved if only energy consumption is recorded."""
        if not has_voltage_telemetry:
            return ValidationResult(
                outcome=ValidationOutcome.INCONCLUSIVE,
                reason="Voltage Telemetry Unavailable",
                explanation=(
                    "Residential smart meter records active energy consumption (kWh) but does not record high-speed "
                    "power quality waveform transients or RMS voltage logging. The complaint cannot be disproved "
                    "and proceeds to severity assessment."
                ),
                data_coverage="unavailable",
                timestamps_checked=[],
                evidence_items=[
                    EvidenceItem(
                        source_tool="meter_telemetry_catalog",
                        metric_name="rms_voltage_waveform",
                        observed_value="not_instrumented",
                        finding="Voltage transients cannot be refuted from aggregate energy readings alone.",
                        supports_invalidation=False,
                    )
                ],
            )
        return ValidationResult(
            outcome=ValidationOutcome.PLAUSIBLE,
            reason="Voltage Data Consistent",
            explanation="Voltage monitoring confirms anomalous conditions or data is consistent with complaint.",
        )

    @staticmethod
    def evaluate_power_outage(
        reported_start: Optional[str],
        reported_duration_hours: Optional[float],
        telemetry_hourly_records: List[Dict[str, Any]],
        data_coverage: str,
        feeder_status: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Evaluate complete power outage against hourly telemetry readings and upstream feeder load."""
        if data_coverage in ("unavailable", "partial") or not telemetry_hourly_records:
            return ValidationResult(
                outcome=ValidationOutcome.INCONCLUSIVE,
                reason="Insufficient Telemetry Coverage",
                explanation=(
                    "Historical meter telemetry for the reported incident window is unavailable, incomplete, or missing. "
                    "In accordance with GridVision policy, missing telemetry is not evidence of invalidity. "
                    "The complaint proceeds to severity scoring."
                ),
                data_coverage=data_coverage,
                timestamps_checked=[r.get("timestamp", "") for r in telemetry_hourly_records if r.get("timestamp")],
                evidence_items=[
                    EvidenceItem(
                        source_tool="query_consumption_history",
                        metric_name="data_coverage",
                        observed_value=data_coverage,
                        finding="Telemetry gap during incident window prevents conclusive verification or invalidation.",
                        supports_invalidation=False,
                    )
                ],
            )

        # Check if every single hour in the reported outage had confirmed positive energy consumption
        total_hours = len(telemetry_hourly_records)
        hours_with_active_draw = [
            r for r in telemetry_hourly_records
            if float(r.get("consumption_kwh", 0.0) or 0.0) >= 0.20
        ]

        if total_hours >= 3 and len(hours_with_active_draw) == total_hours:
            # Active electricity draw throughout alleged outage window
            avg_kwh = sum(float(r.get("consumption_kwh", 0.0)) for r in telemetry_hourly_records) / total_hours
            return ValidationResult(
                outcome=ValidationOutcome.INVALID,
                reason="Continuous Active Power Draw Recorded",
                explanation=(
                    f"Verified smart meter telemetry for {reported_start or 'the reported window'} recorded continuous, "
                    f"uninterrupted electricity consumption across all {total_hours} hours (average {avg_kwh:.2f} kWh/hour). "
                    "The premises drew power consistently throughout the alleged outage period, contradicting a total power supply failure."
                ),
                data_coverage="complete",
                timestamps_checked=[r.get("timestamp", "") for r in telemetry_hourly_records[:6]],
                evidence_items=[
                    EvidenceItem(
                        source_tool="query_consumption_history",
                        metric_name="hourly_active_consumption_kwh",
                        observed_value=f"{avg_kwh:.2f} kWh/h across {total_hours} consecutive hours",
                        expected_or_contradicting_value="0.00 kWh (Power Outage)",
                        timestamp_range=reported_start,
                        finding="Confirmed positive active load throughout reported total outage.",
                        supports_invalidation=True,
                    )
                ],
            )

        # If zero or reduced consumption is seen, complaint is plausible
        zero_hours = [r for r in telemetry_hourly_records if float(r.get("consumption_kwh", 0.0) or 0.0) == 0.0]
        evidence_items = [
            EvidenceItem(
                source_tool="query_consumption_history",
                metric_name="zero_consumption_intervals",
                observed_value=f"{len(zero_hours)} intervals at 0 kWh",
                finding="Observed consumption drop aligns with reported power interruption.",
                supports_invalidation=False,
            )
        ]

        explanation_msg = (
            f"Telemetry records during the incident window show {len(zero_hours)} zero-consumption intervals "
            "or significantly diminished grid draw consistent with a power disruption."
        )

        if feeder_status:
            grid_id = feeder_status.get("id_grid_coarse")
            avg_feeder = feeder_status.get("avg_feeder_kwh", 0.0)
            if avg_feeder < 100.0:
                explanation_msg += f" Regional feeder {grid_id} experienced a simultaneous drop ({avg_feeder:.1f} kWh average), confirming an upstream grid outage."
                evidence_items.append(
                    EvidenceItem(
                        source_tool="grid_level_energy_feeder",
                        metric_name=f"feeder_{grid_id}_status",
                        observed_value=f"{avg_feeder:.1f} kWh",
                        finding=f"Upstream coarse feeder {grid_id} experienced widespread outage.",
                        supports_invalidation=False,
                    )
                )
            else:
                explanation_msg += f" Upstream regional feeder {grid_id} remained energized ({avg_feeder:.1f} kWh average), indicating an isolated service connection or premises breaker issue."
                evidence_items.append(
                    EvidenceItem(
                        source_tool="grid_level_energy_feeder",
                        metric_name=f"feeder_{grid_id}_status",
                        observed_value=f"{avg_feeder:.1f} kWh",
                        finding=f"Upstream feeder {grid_id} active; issue localized to premises service line.",
                        supports_invalidation=False,
                    )
                )

        return ValidationResult(
            outcome=ValidationOutcome.PLAUSIBLE,
            reason="Telemetry Consistent with Outage",
            explanation=explanation_msg,
            data_coverage="complete",
            timestamps_checked=[r.get("timestamp", "") for r in telemetry_hourly_records[:6]],
            evidence_items=evidence_items,
        )

    @staticmethod
    def evaluate_billing_consumption(
        category_data: Dict[str, Any],
        gold_record: Optional[Dict[str, Any]],
    ) -> ValidationResult:
        """Evaluate billing and consumption complaints against gold historical billing telemetry."""
        issue_type = category_data.get("billing_issue_type", "unexpected_high_bill")
        period_str = category_data.get("billing_period", "unspecified")
        actual_inr = category_data.get("actual_bill_amount_inr")

        if not gold_record:
            return ValidationResult(
                outcome=ValidationOutcome.INCONCLUSIVE,
                reason="Billing Record Unavailable for Disputed Period",
                explanation=(
                    f"Official utility billing telemetry for period '{period_str}' could not be located in historical "
                    "records. In accordance with GridVision policy, unverified billing records proceed to manual review and scoring."
                ),
                data_coverage="unavailable",
            )

        target_kwh = float(gold_record.get("target_month_kwh", 0.0))
        target_bill = float(gold_record.get("target_bill_inr", 0.0))
        prior_kwh = gold_record.get("prior_month_kwh")
        prior_kwh_val = float(prior_kwh) if prior_kwh is not None else None

        # Check for unexpected high bill or consumption spike
        if issue_type in ("unexpected_high_bill", "consumption_spike"):
            # If prior month kWh exists and target month kWh decreased or was flat
            if prior_kwh_val is not None and target_kwh <= (prior_kwh_val * 1.05):
                pct_change = ((target_kwh - prior_kwh_val) / prior_kwh_val) * 100.0

                is_contradicted = False
                if actual_inr and float(actual_inr) > (target_bill * 1.25):
                    is_contradicted = True
                elif pct_change <= 0.0:
                    is_contradicted = True

                if is_contradicted:
                    return ValidationResult(
                        outcome=ValidationOutcome.INVALID,
                        reason="Billing Spike Contradicted by Official Telemetry",
                        explanation=(
                            f"Verified smart-meter billing records for {gold_record['month_start']} show monthly consumption "
                            f"was {target_kwh:.1f} kWh ({pct_change:+.1f}% compared to prior month {prior_kwh_val:.1f} kWh) "
                            f"with an official recorded bill of ₹{target_bill:.2f}. "
                            "No unexplained surge or tariff discrepancy occurred in the verified meter records."
                        ),
                        data_coverage="complete",
                        evidence_items=[
                            EvidenceItem(
                                source_tool="customer_gold_billing_records",
                                metric_name="target_month_kwh",
                                observed_value=f"{target_kwh:.1f} kWh (Prior: {prior_kwh_val:.1f} kWh, {pct_change:+.1f}%)",
                                expected_or_contradicting_value="Significant Consumption Spike",
                                timestamp_range=gold_record["month_start"],
                                finding=f"Official telemetry records confirmed consumption change was {pct_change:+.1f}%, refuting an unexpected spike.",
                                supports_invalidation=True,
                            ),
                            EvidenceItem(
                                source_tool="customer_gold_billing_records",
                                metric_name="target_bill_inr",
                                observed_value=f"₹{target_bill:.2f}",
                                expected_or_contradicting_value=f"₹{actual_inr:.2f}" if actual_inr else "Unusually High Bill",
                                timestamp_range=gold_record["month_start"],
                                finding=f"Official billing invoice on record is ₹{target_bill:.2f}.",
                                supports_invalidation=True,
                            ),
                        ],
                    )

            # If consumption increased significantly (> 20%)
            if prior_kwh_val is not None and target_kwh > (prior_kwh_val * 1.20):
                pct_surge = ((target_kwh - prior_kwh_val) / prior_kwh_val) * 100.0
                return ValidationResult(
                    outcome=ValidationOutcome.PLAUSIBLE,
                    reason="Verified Consumption Spike in Official Telemetry",
                    explanation=(
                        f"Official meter records confirm consumption for {gold_record['month_start']} rose by +{pct_surge:.1f}% "
                        f"from {prior_kwh_val:.1f} kWh to {target_kwh:.1f} kWh (official bill: ₹{target_bill:.2f}). "
                        "The reported surge is verified in telemetry and proceeds to tariff rate audit."
                    ),
                    data_coverage="complete",
                    evidence_items=[
                        EvidenceItem(
                            source_tool="customer_gold_billing_records",
                            metric_name="consumption_increase_pct",
                            observed_value=f"+{pct_surge:.1f}% surge ({target_kwh:.1f} kWh vs {prior_kwh_val:.1f} kWh)",
                            finding="Telemetry confirms authentic period-over-period consumption spike.",
                            supports_invalidation=False,
                        )
                    ],
                )

        # For normal billing inquiries or other sub-types with verified gold record
        return ValidationResult(
            outcome=ValidationOutcome.PLAUSIBLE,
            reason="Authoritative Billing Data Retrieved for Review",
            explanation=(
                f"Retrieved official recorded consumption of {target_kwh:.1f} kWh (₹{target_bill:.2f}) for billing cycle {gold_record['month_start']}. "
                "Dispute proceeds to tariff rate audit and severity assessment."
            ),
            data_coverage="complete",
            evidence_items=[
                EvidenceItem(
                    source_tool="customer_gold_billing_records",
                    metric_name="target_bill_inr",
                    observed_value=f"₹{target_bill:.2f} ({target_kwh:.1f} kWh)",
                    finding="Official tariff and consumption baseline compiled from customer gold dataset.",
                    supports_invalidation=False,
                )
            ],
        )

    @staticmethod
    def evaluate_meter_issue(
        category_data: Dict[str, Any],
        comm_status: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Evaluate meter issues distinguishing physical display limitations from communication status."""
        issue_type = category_data.get("meter_issue_type", "display_blank_error")

        if issue_type == "communication_failure":
            if comm_status and comm_status.get("active_telemetry") and comm_status.get("intervals_recorded", 0) >= 12:
                count = comm_status["intervals_recorded"]
                return ValidationResult(
                    outcome=ValidationOutcome.INVALID,
                    reason="Continuous Meter Telemetry Active",
                    explanation=(
                        f"Verified smart meter communication stream indicates {count} consecutive hourly telemetry readings "
                        "actively received during the queried window. No communication blackout or data transmission stoppage occurred."
                    ),
                    data_coverage="complete",
                    evidence_items=[
                        EvidenceItem(
                            source_tool="meter_telemetry_stream",
                            metric_name="received_intervals_count",
                            observed_value=f"{count} hourly packets",
                            expected_or_contradicting_value="0 packets (Communication Failure)",
                            finding="Meter communication link is active and transmitting telemetry continuously.",
                            supports_invalidation=True,
                        )
                    ],
                )
            elif comm_status and not comm_status.get("active_telemetry"):
                return ValidationResult(
                    outcome=ValidationOutcome.PLAUSIBLE,
                    reason="Telemetry Transmission Gap Confirmed",
                    explanation=(
                        "Historical smart meter telemetry records show a genuine gap in transmitted intervals during the reported period. "
                        "Communication failure is confirmed plausible and proceeds to severity assessment."
                    ),
                    data_coverage="unavailable",
                    evidence_items=[
                        EvidenceItem(
                            source_tool="meter_telemetry_stream",
                            metric_name="telemetry_packet_stream",
                            observed_value="0 intervals",
                            finding="Confirmed missing data packets consistent with communication failure.",
                            supports_invalidation=False,
                        )
                    ],
                )

        # For physical display, terminal damage, or tamper alerts: optical/physical on-site inspection is required
        return ValidationResult(
            outcome=ValidationOutcome.INCONCLUSIVE,
            reason="Physical Meter Inspection Required",
            explanation=(
                f"Reported meter issue ('{issue_type}') requires physical diagnostic testing or on-site visual inspection. "
                "Cumulative smart-meter energy readings cannot inspect LCD screen crystals or physical terminals. Complaint proceeds to severity assessment."
            ),
            data_coverage="partial",
            evidence_items=[
                EvidenceItem(
                    source_tool="meter_telemetry_catalog",
                    metric_name="meter_hardware_health",
                    observed_value="telemetry_active",
                    finding="Energy pulses present, but optical display and physical casing require on-site diagnostic review.",
                    supports_invalidation=False,
                )
            ],
        )

