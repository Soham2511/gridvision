"""Complaint Validator Agent.

Evaluates whether a complaint is demonstrably invalid using the customer's available
current and historical energy data, meter information, and premises context.
Reuses existing QueryConsumptionUseCase and HouseholdEnergyRepository without duplicate query layers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.application.energy_analytics.query_consumption import QueryConsumptionUseCase
from app.domain.complaints.entities import (
    EvidenceItem,
    ValidationOutcome,
    ValidationResult,
)
from app.domain.complaints.rules import ComplaintValidationPolicy
from app.domain.energy.metrics import AggregationGranularity
from app.domain.energy.schemas import ConsumptionQueryRequest
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)

logger = logging.getLogger("gridvision.application.complaints.validator_agent")


class ComplaintValidatorAgent:
    """Agent evaluating whether a customer complaint is conclusively invalid."""

    def __init__(
        self,
        repository: Optional[BaseHouseholdEnergyRepository] = None,
        query_consumption_uc: Optional[QueryConsumptionUseCase] = None,
    ) -> None:
        self.repo = repository or HouseholdEnergyRepository()
        self.query_uc = query_consumption_uc or QueryConsumptionUseCase(repository=self.repo)

    def validate_complaint(
        self,
        meter_id: str,
        category_id: str,
        category_data: Dict[str, Any],
        title: str,
        description: str,
    ) -> ValidationResult:
        """Execute validation against existing authorized telemetry and domain rules."""
        clean_cat = (category_id or "").strip().lower()

        # 1. Electrical Safety: Never invalidated by normal telemetry
        if clean_cat == "electrical_safety":
            return ComplaintValidationPolicy.evaluate_electrical_safety(category_data)

        # 2. Voltage Fluctuation: Non-instrumented waveform power quality
        if clean_cat == "voltage_fluctuation":
            return ComplaintValidationPolicy.evaluate_voltage_fluctuation(has_voltage_telemetry=False)

        # 3. Meter Hardware / Display / Communication
        if clean_cat == "meter_issue":
            return self._validate_meter_issue(meter_id, category_data)

        # 4. Power Outage Validation
        if clean_cat == "power_supply_interruption":
            return self._validate_power_outage(meter_id, category_data)

        # 5. Billing & Consumption Issues
        if clean_cat == "billing_consumption":
            return self._validate_billing_consumption(meter_id, category_data)

        # 6. Solar & EV & Other: Sub-circuit telemetry is typically not isolated on residential aggregate meters
        return ValidationResult(
            outcome=ValidationOutcome.INCONCLUSIVE,
            reason="Sub-circuit Level Diagnostics Unavailable",
            explanation=(
                f"Complaint for category '{category_id}' accepted. Household smart meter records aggregate whole-home load; "
                "sub-metered appliance telemetry is not instrumented. The complaint proceeds to severity assessment."
            ),
            data_coverage="unavailable",
            evidence_items=[
                EvidenceItem(
                    source_tool="meter_telemetry_catalog",
                    metric_name="sub_metering_coverage",
                    observed_value="aggregate_only",
                    finding="Dedicated sub-circuit monitoring unavailable; proceeding to severity assessment.",
                    supports_invalidation=False,
                )
            ],
        )

    def _validate_meter_issue(
        self,
        meter_id: str,
        category_data: Dict[str, Any],
    ) -> ValidationResult:
        """Validate meter issues distinguishing physical LCD inspection from telemetry continuity."""
        issue_type = category_data.get("meter_issue_type", "display_blank_error")
        observed_date = category_data.get("observed_start_date")

        comm_status = None
        if issue_type == "communication_failure":
            try:
                date_str = str(observed_date)[:10] if observed_date else None
                comm_status = self.repo.get_meter_communication_status(
                    meter_id, start_date=date_str, end_date=date_str
                )
            except Exception as e:
                logger.debug("Communication status query failed: %s", e)

        return ComplaintValidationPolicy.evaluate_meter_issue(
            category_data=category_data,
            comm_status=comm_status,
        )

    def _validate_power_outage(
        self,
        meter_id: str,
        category_data: Dict[str, Any],
    ) -> ValidationResult:
        """Validate power outage report against hourly consumption telemetry and feeder status."""
        incident_start_raw = category_data.get("incident_start")
        duration_hours = category_data.get("approximate_duration_hours")

        if not incident_start_raw:
            return ValidationResult(
                outcome=ValidationOutcome.INCONCLUSIVE,
                reason="Unspecified Incident Time",
                explanation="No exact start date or time was provided. Outage complaint proceeds to severity assessment.",
                data_coverage="unavailable",
            )

        try:
            start_clean = str(incident_start_raw).strip()
            dt_start = None
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt_start = datetime.strptime(start_clean, fmt)
                    break
                except ValueError:
                    pass

            if dt_start is None:
                dt_start = datetime.strptime(start_clean[:10], "%Y-%m-%d")

            dur = float(duration_hours) if duration_hours else 4.0
            dt_end = dt_start + timedelta(hours=dur)

            date_start_str = dt_start.strftime("%Y-%m-%d")
            date_end_str = dt_end.strftime("%Y-%m-%d")

            # Try query_uc first (supporting both mocked .series and real AnalyticsToolResponse)
            hourly_records = []
            try:
                query_req = ConsumptionQueryRequest(
                    start_date=date_start_str,
                    end_date=date_end_str,
                    granularity=AggregationGranularity.HOURLY,
                )
                response = self.query_uc.execute(meter_id=meter_id, request=query_req)
                if hasattr(response, "series") and response.series:
                    for p in response.series:
                        ts = getattr(p, "timestamp", None)
                        kwh = getattr(p, "consumption_kwh", 0.0)
                        hourly_records.append({
                            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                            "consumption_kwh": float(kwh or 0.0),
                        })
                elif hasattr(response, "results") and isinstance(response.results, dict):
                    data_points = response.results.get("dataPoints", [])
                    for dp in data_points:
                        ts = dp.get("period_key") or dp.get("timestamp")
                        kwh = dp.get("value") or dp.get("consumption_kwh") or 0.0
                        hourly_records.append({
                            "timestamp": str(ts),
                            "consumption_kwh": float(kwh or 0.0),
                        })
            except Exception as q_err:
                logger.debug("Query consumption use case encountered: %s", q_err)

            # If hourly_records is still empty, query repository intervals directly
            if not hourly_records:
                intervals = self.repo.get_meter_intervals(
                    meter_id=meter_id,
                    start_date=date_start_str,
                    end_date=date_end_str,
                )
                for r in intervals:
                    ts = r.get("timestamp")
                    kwh = r.get("kwh", 0.0)
                    hourly_records.append({
                        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                        "consumption_kwh": float(kwh or 0.0),
                    })

            # Filter records that fall within the incident start and incident end window (or whole day if no time)
            if hourly_records and len(start_clean) > 10:
                filtered = []
                for r in hourly_records:
                    ts_val = r.get("timestamp", "")
                    try:
                        ts_clean = ts_val.replace("T", " ")[:19]
                        r_dt = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S" if len(ts_clean) == 19 else "%Y-%m-%d %H:%M")
                        if (dt_start - timedelta(minutes=30)) <= r_dt <= (dt_end + timedelta(minutes=30)):
                            filtered.append(r)
                    except Exception:
                        filtered.append(r)
                if filtered:
                    hourly_records = filtered

            expected_pts = max(3, int(dur * 0.7))
            data_coverage = "complete" if len(hourly_records) >= expected_pts else ("partial" if hourly_records else "unavailable")

            # Check upstream feeder grid status if available
            feeder_status = None
            try:
                gold_billing = self.repo.get_gold_monthly_billing(meter_id, date_start_str[:7])
                if gold_billing and "id_grid_coarse" in gold_billing:
                    grid_id = int(gold_billing["id_grid_coarse"])
                    start_ts = f"{date_start_str} 00:00:00"
                    end_ts = f"{date_end_str} 23:59:59"
                    feeder_status = self.repo.get_feeder_grid_status(grid_id, start_ts, end_ts)
            except Exception as fe:
                logger.debug("Feeder status lookup skipped: %s", fe)

            return ComplaintValidationPolicy.evaluate_power_outage(
                reported_start=incident_start_raw,
                reported_duration_hours=float(duration_hours) if duration_hours else None,
                telemetry_hourly_records=hourly_records,
                data_coverage=data_coverage,
                feeder_status=feeder_status,
            )
        except Exception as e:
            logger.warning("Telemetry query failed during outage validation: %s", e)
            return ValidationResult(
                outcome=ValidationOutcome.INCONCLUSIVE,
                reason="Telemetry Lookup Encountered Exception",
                explanation="Could not query historical telemetry for the specified window. Proceeding to severity scoring.",
                data_coverage="unavailable",
            )

    def _validate_billing_consumption(
        self,
        meter_id: str,
        category_data: Dict[str, Any],
    ) -> ValidationResult:
        """Validate billing complaint by comparing actual meter consumption and authoritative gold records."""
        billing_period = str(category_data.get("billing_period", "")).strip()

        try:
            gold_record = self.repo.get_gold_monthly_billing(meter_id, billing_period)
            return ComplaintValidationPolicy.evaluate_billing_consumption(
                category_data=category_data,
                gold_record=gold_record,
            )
        except Exception as e:
            logger.warning("Failed to query authoritative gold billing: %s", e)
            return ValidationResult(
                outcome=ValidationOutcome.INCONCLUSIVE,
                reason="Billing Query Unavailable",
                explanation="Could not retrieve historical monthly billing telemetry. Proceeding to severity assessment.",
                data_coverage="unavailable",
            )

