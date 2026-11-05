"""Comprehensive tests for the GridVision Complaint Management Platform.

Validates:
1. Complaint Categories Catalogue API
2. Deterministic Severity Benchmark calculations & statutory safety overrides
3. Telemetry AI Validation rules (outage invalidation, missing data inconclusiveness, voltage waveform limitations)
4. Safety Precedence enforcement (safety complaints never invalidated by meter data)
5. End-to-end complaint submission lifecycle (SUBMITTED -> VALIDATING -> INVALID or SCORING -> REGISTERED)
6. Strict customer data isolation and ownership enforcement
7. Assistant routing of complaint intents to the Complaint Centre
"""

from __future__ import annotations

from datetime import datetime
import json
from unittest.mock import MagicMock, patch
import pytest

from app.application.complaints.scoring_agent import ComplaintSeverityScoringAgent
from app.domain.complaints.benchmark import (
    BENCHMARK_VERSION,
    calculate_deterministic_severity,
)
from app.domain.complaints.categories import (
    RESIDENTIAL_COMPLAINT_CATEGORIES,
    get_categories_for_segment,
)
from app.domain.complaints.entities import (
    ComplaintStatus,
    CustomerSegment,
    ScoringFactorBreakdown,
    SeverityLevel,
    ValidationOutcome,
)
from app.domain.complaints.rules import ComplaintValidationPolicy
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models.complaint import ComplaintModel
from app.services.assistant.agentic_orchestrator import AgenticKnowledgeOrchestrator
from app.services.assistant.dialogue_state import resolve_dialogue_context
from app.services.assistant.intelligent_router import IntelligentRouter
from app.interfaces.assistant.tools.registry import create_residential_tools


@pytest.fixture(autouse=True)
def clean_complaints_db():
    """Ensure complaints table is completely wiped clean before and after every test run."""
    with get_session() as session:
        session.query(ComplaintModel).delete()
        session.commit()
    yield
    with get_session() as session:
        session.query(ComplaintModel).delete()
        session.commit()


class TestComplaintCategoriesCatalogue:
    """Tests for complaint categories definitions and API."""

    def test_catalogue_contains_eight_residential_categories(self, client):
        """Verify the 8 approved residential categories exist with required metadata."""
        resp = client.get("/api/v1/complaints/categories?segment=RESIDENTIAL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        categories = data["data"]
        assert len(categories) == 8

        cat_ids = [c["category_id"] for c in categories]
        expected_ids = [
            "power_supply_interruption",
            "voltage_fluctuation",
            "meter_issue",
            "billing_consumption",
            "electrical_safety",
            "solar_distributed_energy",
            "ev_charging",
            "other_issues",
        ]
        for exp in expected_ids:
            assert exp in cat_ids

        # Verify electrical safety is flagged as safety critical
        safety_cat = next(c for c in categories if c["category_id"] == "electrical_safety")
        assert safety_cat["safety_critical"] is True

        # Verify power supply interruption has relevant form fields
        outage_cat = next(c for c in categories if c["category_id"] == "power_supply_interruption")
        field_ids = [f["field_id"] for f in outage_cat["fields"]]
        assert "interruption_type" in field_ids
        assert "incident_start" in field_ids
        assert "scope_affected" in field_ids


class TestSeverityBenchmarkScoring:
    """Tests for the deterministic severity benchmark rubric and safety overrides."""

    def test_benchmark_weights_formula(self):
        """Test calculation of weighted sum across the 5 dimensions."""
        factors = ScoringFactorBreakdown(
            safety_risk=50.0,
            disruption_extent=40.0,
            duration_factor=30.0,
            recurrence_factor=20.0,
            essential_services_impact=10.0,
        )
        # Expected: 50*0.35 (17.5) + 40*0.25 (10.0) + 30*0.15 (4.5) + 20*0.15 (3.0) + 10*0.10 (1.0) = 36.0
        result = calculate_deterministic_severity(
            factors=factors,
            category_id="other_issues",
            category_data={},
        )
        assert result.benchmark_version == BENCHMARK_VERSION
        assert abs(result.severity_score - 36.0) < 0.1
        assert result.severity_level == SeverityLevel.MEDIUM

    def test_statutory_safety_override_sparking_or_shock(self):
        """Active hazard (sparking/burning/shock) must clamp score >= 90.0 and Critical level."""
        scoring_agent = ComplaintSeverityScoringAgent()
        result = scoring_agent.score_complaint(
            category_id="electrical_safety",
            category_data={
                "safety_issue_type": "sparking_visible",
                "is_condition_ongoing": True,
            },
            title="Sparks and burning smell from distribution board",
            description="Saw visible sparks and smell burning plastic from the main breaker.",
        )
        assert result.severity_score >= 90.0
        assert result.severity_level == SeverityLevel.CRITICAL
        assert result.factor_breakdown.safety_override_applied is True
        assert "Active ongoing electrical hazard" in (result.factor_breakdown.override_reason or "")

    def test_statutory_safety_override_general_electrical_safety(self):
        """General safety complaints must clamp to at least 72.0 (High priority)."""
        scoring_agent = ComplaintSeverityScoringAgent()
        result = scoring_agent.score_complaint(
            category_id="electrical_safety",
            category_data={
                "safety_issue_type": "exposed_wiring",
                "is_condition_ongoing": False,
            },
            title="Exposed wire near garden switch",
            description="Found damaged insulation exposing wire.",
        )
        assert result.severity_score >= 72.0
        assert result.severity_level in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)
        assert result.factor_breakdown.safety_override_applied is True

    def test_statutory_safety_override_ongoing_entire_house_outage(self):
        """Entire house outage currently ongoing must clamp to at least 75.0 (High priority)."""
        scoring_agent = ComplaintSeverityScoringAgent()
        result = scoring_agent.score_complaint(
            category_id="power_supply_interruption",
            category_data={
                "scope_affected": "entire_house",
                "power_currently_available": True,
            },
            title="Complete blackout in house",
            description="All power is out in the house right now.",
        )
        assert result.severity_score >= 75.0
        assert result.severity_level in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)


class TestValidationPolicyRules:
    """Tests for AI telemetry validation rules."""

    def test_safety_complaint_precedence(self):
        """Safety complaints must bypass automated telemetry invalidation."""
        val = ComplaintValidationPolicy.evaluate_electrical_safety(
            category_data={
                "safety_issue_type": "electric_shock_leakage",
                "hazard_location": "kitchen socket",
            }
        )
        assert val.outcome == ValidationOutcome.PLAUSIBLE
        assert "precedence" in val.reason.lower()
        assert any(e.finding and "safety" in e.finding.lower() for e in val.evidence_items)

    def test_voltage_fluctuation_inconclusive_due_to_waveform_limitation(self):
        """Voltage complaints must return INCONCLUSIVE because standard meters lack RMS waveform logging."""
        val = ComplaintValidationPolicy.evaluate_voltage_fluctuation(has_voltage_telemetry=False)
        assert val.outcome == ValidationOutcome.INCONCLUSIVE
        assert "voltage telemetry unavailable" in val.reason.lower()

    def test_outage_invalidated_when_meter_shows_continuous_consumption(self):
        """Outage complaint must be INVALID when active readings show uninterrupted energy draw."""
        readings = [
            {"timestamp": f"2026-11-04T0{i}:00:00", "consumption_kwh": 0.35}
            for i in range(1, 6)
        ]
        val = ComplaintValidationPolicy.evaluate_power_outage(
            reported_start="2026-11-04T01:00:00",
            reported_duration_hours=4.0,
            telemetry_hourly_records=readings,
            data_coverage="complete",
        )
        assert val.outcome == ValidationOutcome.INVALID
        assert "continuous active power" in val.reason.lower()
        assert any(e.supports_invalidation for e in val.evidence_items)

    def test_outage_inconclusive_when_telemetry_is_missing(self):
        """Outage complaint must be INCONCLUSIVE (conservative) when telemetry is absent."""
        val = ComplaintValidationPolicy.evaluate_power_outage(
            reported_start="2026-11-04T01:00:00",
            reported_duration_hours=2.0,
            telemetry_hourly_records=[],
            data_coverage="unavailable",
        )
        assert val.outcome == ValidationOutcome.INCONCLUSIVE
        assert "insufficient telemetry coverage" in val.reason.lower()

    def test_feeder_status_in_outage_evaluation(self):
        """Outage evaluation documents upstream feeder status when available."""
        zero_readings = [
            {"timestamp": f"2018-05-10T{h:02d}:00:00", "consumption_kwh": 0.0}
            for h in range(10, 14)
        ]
        # Case A: Feeder experienced wide outage
        val_feeder_down = ComplaintValidationPolicy.evaluate_power_outage(
            reported_start="2018-05-10T10:00:00",
            reported_duration_hours=4.0,
            telemetry_hourly_records=zero_readings,
            data_coverage="complete",
            feeder_status={"id_grid_coarse": 77, "avg_feeder_kwh": 45.0},
        )
        assert val_feeder_down.outcome == ValidationOutcome.PLAUSIBLE
        assert "upstream grid outage" in val_feeder_down.explanation.lower()

        # Case B: Feeder active, premises isolated
        val_feeder_up = ComplaintValidationPolicy.evaluate_power_outage(
            reported_start="2018-05-10T10:00:00",
            reported_duration_hours=4.0,
            telemetry_hourly_records=zero_readings,
            data_coverage="complete",
            feeder_status={"id_grid_coarse": 77, "avg_feeder_kwh": 9500.0},
        )
        assert val_feeder_up.outcome == ValidationOutcome.PLAUSIBLE
        assert "isolated service connection" in val_feeder_up.explanation.lower()

    def test_billing_dispute_invalidated_when_gold_shows_no_spike(self):
        """Billing complaint must be INVALID when gold record proves consumption decreased."""
        gold_rec = {
            "entity_id": 2254213,
            "month_start": "2018-02-01",
            "target_month_kwh": 319.89,
            "target_bill_inr": 3198.93,
            "prior_month_kwh": 365.54,
            "coverage_ratio": 0.958,
        }
        val = ComplaintValidationPolicy.evaluate_billing_consumption(
            category_data={
                "billing_issue_type": "unexpected_high_bill",
                "billing_period": "2018-02",
                "actual_bill_amount_inr": 8500.0,
            },
            gold_record=gold_rec,
        )
        assert val.outcome == ValidationOutcome.INVALID
        assert "contradicted" in val.reason.lower()
        assert any(e.supports_invalidation for e in val.evidence_items)

    def test_billing_dispute_plausible_when_gold_confirms_spike(self):
        """Billing complaint must be PLAUSIBLE when gold record verifies real consumption surge."""
        gold_rec = {
            "entity_id": 2254213,
            "month_start": "2018-07-01",
            "target_month_kwh": 815.36,
            "target_bill_inr": 8153.64,
            "prior_month_kwh": 498.37,
            "coverage_ratio": 0.958,
        }
        val = ComplaintValidationPolicy.evaluate_billing_consumption(
            category_data={
                "billing_issue_type": "consumption_spike",
                "billing_period": "2018-07",
                "actual_bill_amount_inr": 8150.0,
            },
            gold_record=gold_rec,
        )
        assert val.outcome == ValidationOutcome.PLAUSIBLE
        assert "verified consumption spike" in val.reason.lower()
        assert not any(e.supports_invalidation for e in val.evidence_items)

    def test_billing_dispute_inconclusive_when_gold_missing(self):
        """Billing complaint must be INCONCLUSIVE when gold record is unavailable."""
        val = ComplaintValidationPolicy.evaluate_billing_consumption(
            category_data={
                "billing_issue_type": "unexpected_high_bill",
                "billing_period": "2026-11",
            },
            gold_record=None,
        )
        assert val.outcome == ValidationOutcome.INCONCLUSIVE
        assert "unavailable" in val.reason.lower()

    def test_meter_communication_failure_invalidated_when_active(self):
        """Meter communication failure must be INVALID when active packets are streaming."""
        val = ComplaintValidationPolicy.evaluate_meter_issue(
            category_data={"meter_issue_type": "communication_failure"},
            comm_status={"active_telemetry": True, "intervals_recorded": 24},
        )
        assert val.outcome == ValidationOutcome.INVALID
        assert "continuous meter telemetry active" in val.reason.lower()

    def test_meter_communication_failure_plausible_when_missing(self):
        """Meter communication failure must be PLAUSIBLE when intervals are missing."""
        val = ComplaintValidationPolicy.evaluate_meter_issue(
            category_data={"meter_issue_type": "communication_failure"},
            comm_status={"active_telemetry": False, "intervals_recorded": 0},
        )
        assert val.outcome == ValidationOutcome.PLAUSIBLE
        assert "transmission gap confirmed" in val.reason.lower()

    def test_meter_physical_display_blank_inconclusive(self):
        """Meter LCD blank issue must return INCONCLUSIVE (physical review required)."""
        val = ComplaintValidationPolicy.evaluate_meter_issue(
            category_data={"meter_issue_type": "display_blank_error"},
            comm_status={"active_telemetry": True, "intervals_recorded": 24},
        )
        assert val.outcome == ValidationOutcome.INCONCLUSIVE
        assert "physical meter inspection required" in val.reason.lower()


class TestComplaintEndToEndEndpoints:
    """Integration tests for complaint submission and retrieval endpoints."""

    def test_submit_invalid_outage_complaint_unmocked_real_data(self, client):
        """Test submitting an outage complaint where real Parquet telemetry proves continuous power."""
        payload = {
            "category_id": "power_supply_interruption",
            "title": "Outage across entire house on Dec 10",
            "description": "We have had absolutely no electricity for the past 10 hours.",
            "category_data": {
                "interruption_type": "complete_outage",
                "incident_start": "2018-12-10T23:43",
                "approximate_duration_hours": 10.1,
                "scope_affected": "entire_house",
                "power_currently_available": True,
            },
            "meter_id": "2254213",
        }

        # Completely unmocked: queries live DuckDB Parquet telemetry directly
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "INVALID"
        assert data["validation_result"]["outcome"] == "INVALID"
        assert "continuous active power" in data["validation_result"]["reason"].lower()
        assert data["customer_care_escalation"]["escalation_available"] is True
        assert any(e["supports_invalidation"] for e in data["validation_result"]["evidence_items"])

    def test_submit_uninstrumented_outage_complaint_registers_inconclusive(self, client):
        """Test submitting an outage complaint for an unrecorded window safely registers as INCONCLUSIVE."""
        payload = {
            "category_id": "power_supply_interruption",
            "title": "Recent power outage in 2026",
            "description": "Power dropped recently during the morning.",
            "category_data": {
                "interruption_type": "complete_outage",
                "incident_start": "2026-11-04T01:00:00",
                "approximate_duration_hours": 3.0,
                "scope_affected": "entire_house",
                "power_currently_available": True,
            },
            "meter_id": "2254213",
        }

        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "REGISTERED"
        assert data["validation_result"]["outcome"] == "INCONCLUSIVE"
        assert "insufficient telemetry coverage" in data["validation_result"]["reason"].lower()

    def test_submit_valid_safety_complaint_registers_with_critical_priority(self, client):
        """Test submitting a safety complaint proceeds through precedence and registers with Critical priority."""
        payload = {
            "category_id": "electrical_safety",
            "title": "Sparking and burning smell from switchboard",
            "description": "Main breaker started sparking with smoke and burning smell.",
            "category_data": {
                "safety_issue_type": "sparking_visible",
                "hazard_location": "Main Distribution Board",
                "is_condition_ongoing": True,
            },
            "meter_id": "2254213",
        }

        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "REGISTERED"
        assert data["validation_result"]["outcome"] == "PLAUSIBLE"
        assert data["severity_result"]["severity_level"] == "Critical"
        assert data["severity_result"]["severity_score"] >= 90.0
        assert data["severity_result"]["factor_breakdown"]["safety_override_applied"] is True

    def test_strict_customer_ownership_isolation(self, client):
        """Verify Customer B cannot access Customer A's complaint."""
        payload = {
            "category_id": "meter_issue",
            "title": "Meter display blank",
            "description": "Digital screen on meter is totally blank and unresponsive.",
            "category_data": {
                "meter_issue_type": "display_blank_error",
                "observed_start_date": "2026-11-04",
                "display_operational": False,
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        complaint_a = resp.get_json()["data"]
        complaint_a_id = complaint_a["id"]

        # Customer A (2254213) can retrieve it
        resp_a = client.get(
            f"/api/v1/complaints/{complaint_a_id}",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp_a.status_code == 200

        # Customer B (293861) attempts to retrieve Customer A's complaint -> 403 Forbidden
        resp_b = client.get(
            f"/api/v1/complaints/{complaint_a_id}",
            headers={"X-Dev-User-Id": "293861"},
        )
        assert resp_b.status_code == 403
        assert resp_b.get_json()["success"] is False

        # Customer B listing complaints does not see Customer A's complaint
        resp_list_b = client.get(
            "/api/v1/complaints",
            headers={"X-Dev-User-Id": "293861"},
        )
        assert resp_list_b.status_code == 200
        complaints_b = resp_list_b.get_json()["data"]
        assert not any(c["id"] == complaint_a_id for c in complaints_b)

    def test_submit_invalid_billing_spike_with_real_gold_record(self, client):
        """Disputing a high bill for Feb 2018 is invalidated because real gold telemetry proves consumption decreased."""
        payload = {
            "category_id": "billing_consumption",
            "title": "Unexpected massive bill jump in February",
            "description": "My February bill was charged at ₹9,500 which is abnormally high.",
            "category_data": {
                "billing_issue_type": "unexpected_high_bill",
                "billing_period": "2018-02",
                "actual_bill_amount_inr": 9500.0,
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "INVALID"
        assert data["validation_result"]["outcome"] == "INVALID"
        assert "contradicted" in data["validation_result"]["reason"].lower()
        # Verify real values from customer_gold.parquet
        assert any("319.9" in e["observed_value"] or "3198.93" in e["observed_value"] for e in data["validation_result"]["evidence_items"])

    def test_submit_valid_billing_spike_with_real_gold_record(self, client):
        """Disputing July 2018 bill is validated as PLAUSIBLE because real gold telemetry confirms a +63.6% consumption surge."""
        payload = {
            "category_id": "billing_consumption",
            "title": "Severe consumption jump in July",
            "description": "My consumption shot up unexpectedly in July.",
            "category_data": {
                "billing_issue_type": "consumption_spike",
                "billing_period": "2018-07",
                "actual_bill_amount_inr": 8150.0,
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "REGISTERED"
        assert data["validation_result"]["outcome"] == "PLAUSIBLE"
        assert "verified consumption spike" in data["validation_result"]["reason"].lower()
        assert any("+63.6%" in e["observed_value"] or "815.4" in e["observed_value"] for e in data["validation_result"]["evidence_items"])

    def test_submit_invalid_meter_communication_failure_with_real_telemetry(self, client):
        """Reporting meter communication drop for a date with active telemetry is invalidated."""
        payload = {
            "category_id": "meter_issue",
            "title": "Smart meter communication failure",
            "description": "The meter is not communicating or sending readings.",
            "category_data": {
                "meter_issue_type": "communication_failure",
                "observed_start_date": "2018-05-10",
                "display_operational": True,
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "INVALID"
        assert data["validation_result"]["outcome"] == "INVALID"
        assert "continuous meter telemetry active" in data["validation_result"]["reason"].lower()

    def test_submit_voltage_fluctuation_inconclusive_registers(self, client):
        """Voltage complaints proceed as INCONCLUSIVE with power quality limitation."""
        payload = {
            "category_id": "voltage_fluctuation",
            "title": "Severe light flickering in evening",
            "description": "Lights flickering continuously during dinner time.",
            "category_data": {
                "voltage_issue_type": "lights_flickering",
                "observation_time": "2026-11-04T19:00:00",
                "pattern": "during_peak_hours",
                "is_currently_occurring": True,
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "REGISTERED"
        assert data["validation_result"]["outcome"] == "INCONCLUSIVE"
        assert "voltage telemetry unavailable" in data["validation_result"]["reason"].lower()

    def test_submit_solar_inconclusive_registers(self, client):
        """Solar PV complaint proceeds as INCONCLUSIVE due to sub-circuit limitation."""
        payload = {
            "category_id": "solar_distributed_energy",
            "title": "Solar generation dropped drastically",
            "description": "Rooftop solar appears to produce almost no power this week.",
            "category_data": {
                "solar_issue_type": "low_generation",
                "approximate_start_time": "2026-11-01",
                "is_system_operational": True,
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "REGISTERED"
        assert data["validation_result"]["outcome"] == "INCONCLUSIVE"
        assert "sub-circuit" in data["validation_result"]["reason"].lower()

    def test_submit_ev_charging_inconclusive_registers(self, client):
        """EV charging complaint proceeds as INCONCLUSIVE due to sub-circuit limitation."""
        payload = {
            "category_id": "ev_charging",
            "title": "EV charger breaker trips on connection",
            "description": "MCB trips immediately whenever the car is connected.",
            "category_data": {
                "ev_issue_type": "breaker_tripping_on_plug_in",
                "charger_type": "32a_level_2",
                "charging_starts": False,
                "approximate_start_time": "2026-11-04T08:00:00",
            },
            "meter_id": "2254213",
        }
        resp = client.post(
            "/api/v1/complaints",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Dev-User-Id": "2254213"},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]

        assert data["status"] == "REGISTERED"
        assert data["validation_result"]["outcome"] == "INCONCLUSIVE"
        assert "sub-circuit" in data["validation_result"]["reason"].lower()


class TestAssistantComplaintRouting:
    """Tests for LLM-routed, read-only Complaint Centre guidance."""

    def test_complaint_guidance_uses_llm_intent_and_live_catalogue_tool(self):
        class ComplaintIntentModel:
            def is_available(self):
                return True

            def generate_chat_completion(self, messages, temperature=0.2, max_tokens=800):
                return '{"intent":"complaint_center_guidance"}'

        prompt = "The sockets are dead in the kitchen. Where should I report it?"
        intent = IntelligentRouter.classify_intent(
            prompt,
            llm_provider=ComplaintIntentModel(),
        )
        plan = IntelligentRouter.create_routing_plan(
            prompt,
            resolve_dialogue_context(prompt),
            classified_intent=intent,
        )

        assert plan.primary_intent == "complaint_center_guidance"
        assert plan.requires_tool_execution is True
        assert plan.recommended_tools == ["get_residential_complaint_categories"]

        tools = create_residential_tools(
            authorized_meter_id="2254213",
            include_knowledge_tools=True,
            tool_scope=plan.resolved_tool_scope,
        )
        complaint_tool = next(
            tool for tool in tools
            if tool.name == "get_residential_complaint_categories"
        )
        categories = json.loads(complaint_tool.invoke({}))
        outage = next(
            category for category in categories
            if category["category_id"] == "power_supply_interruption"
        )
        assert outage["label"] == "Power Supply Interruption"
        assert any(field["field_id"] == "incident_start" for field in outage["fields"])
