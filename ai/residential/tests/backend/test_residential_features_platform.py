"""Comprehensive Test Suite for GridVision Residential Energy Intelligence Platform.

Validates:
1. Schema-driven questionnaire registry contracts and conditional visibility.
2. Building Energy Planning Engine (connected load, diversity, plan tiers, solar sizing).
3. Appliance Lifecycle Cost Engine (duty factors, cashflows, payback, TCO, sensitivities).
4. Tariff & Billing Engine (charges, duty, escalation, present value).
5. Energy Savings & Recommendation Engines (filtering, ranking, package recommendations).
6. Application Use Cases (house planning, appliance analysis, cost management).
7. REST API endpoints (/questionnaires, /plan-house-energy, /analyze-appliance, /manage-cost, /sessions).
8. Strict meter authorization and security enforcement.
"""

from __future__ import annotations

import json
import unittest

from app import create_app
from app.application.residential.analyze_appliance import AnalyzeApplianceScenarioUseCase
from app.application.residential.manage_cost import ManageEnergyCostUseCase
from app.application.residential.plan_house_energy import PlanHouseEnergyUseCase
from app.domain.residential.appliance_engine import ApplianceLifecycleCostEngine
from app.domain.residential.building_engine import BuildingEnergyPlanningEngine
from app.domain.residential.questionnaires import QUESTIONNAIRE_REGISTRY
from app.domain.residential.recommendation_engine import RecommendationEngine
from app.domain.residential.savings_engine import EnergySavingsEngine
from app.domain.residential.schemas import (
    ApplianceScenarioRequest,
    CostManagementRequest,
    ExistingApplianceSpec,
    HouseEnergyPlanningRequest,
    ProposedApplianceSpec,
    RoomSpec,
)
from app.domain.residential.tariff_engine import TariffBillingEngine


class TestQuestionnaireFramework(unittest.TestCase):
    """Validates the schema-driven questionnaire registry."""

    def test_registry_contains_all_three_features(self):
        self.assertIn("house_energy_planning", QUESTIONNAIRE_REGISTRY)
        self.assertIn("appliance_analysis", QUESTIONNAIRE_REGISTRY)
        self.assertIn("cost_management", QUESTIONNAIRE_REGISTRY)

    def test_house_planning_questionnaire_schema(self):
        q = QUESTIONNAIRE_REGISTRY["house_energy_planning"]
        self.assertEqual(q.feature_id, "house_energy_planning")
        field_ids = {f.field_id for f in q.fields}
        self.assertIn("property_type", field_ids)
        self.assertIn("built_up_area_m2", field_ids)
        self.assertIn("efficiency_priority", field_ids)
        self.assertIn("budget_inr", field_ids)

        # Check conditional field
        roof_field = next(f for f in q.fields if f.field_id == "roof_area_available_m2")
        self.assertIsNotNone(roof_field.conditional_visibility)
        self.assertEqual(roof_field.conditional_visibility.depends_on_field, "include_solar_pv")

    def test_appliance_analysis_questionnaire_schema(self):
        q = QUESTIONNAIRE_REGISTRY["appliance_analysis"]
        self.assertEqual(q.feature_id, "appliance_analysis")
        field_ids = {f.field_id for f in q.fields}
        self.assertIn("intention", field_ids)
        self.assertIn("appliance_category", field_ids)
        self.assertIn("daily_usage_hours", field_ids)
        self.assertIn("proposed_purchase_price_inr", field_ids)

    def test_cost_management_questionnaire_schema(self):
        q = QUESTIONNAIRE_REGISTRY["cost_management"]
        self.assertEqual(q.feature_id, "cost_management")
        field_ids = {f.field_id for f in q.fields}
        self.assertIn("available_investment_budget_inr", field_ids)
        self.assertIn("primary_objective", field_ids)
        self.assertIn("willingness_to_shift_schedules", field_ids)


class TestBuildingEnergyPlanningEngine(unittest.TestCase):
    """Validates the electrical planning and engineering engine."""

    def test_ac_sizing(self):
        self.assertEqual(BuildingEnergyPlanningEngine.size_ac_tonnage(10.0), 1.0)
        self.assertEqual(BuildingEnergyPlanningEngine.size_ac_tonnage(18.0), 1.5)
        self.assertEqual(BuildingEnergyPlanningEngine.size_ac_tonnage(30.0), 2.0)

    def test_room_layout_synthesis(self):
        rooms = BuildingEnergyPlanningEngine.plan_rooms_if_empty(150.0, "independent_house", 4)
        self.assertGreaterEqual(len(rooms), 4)
        total_area = sum(r.area_m2 for r in rooms)
        self.assertAlmostEqual(total_area, 150.0, delta=2.0)

    def test_full_house_planning_execution(self):
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=140.0,
            floors_count=1,
            occupancy_count=4,
            budget_inr=180000.0,
            efficiency_priority="balanced",
            include_solar_pv=True,
            roof_area_available_m2=50.0,
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)
        self.assertGreater(res.preliminary_connected_load_kw, 0.0)
        self.assertGreater(res.diversified_maximum_demand_kw, 0.0)
        # Diversified demand must be strictly less than connected load
        self.assertLess(res.diversified_maximum_demand_kw, res.preliminary_connected_load_kw)

        rec = res.recommended_plan
        self.assertEqual(rec.tier_name, "Balanced")
        self.assertGreater(rec.total_equipment_cost_inr, 0.0)
        self.assertGreater(rec.estimated_monthly_consumption_kwh, 0.0)
        self.assertGreater(rec.estimated_monthly_bill_inr, 0.0)
        self.assertIsNotNone(res.solar_potential_analysis)
        self.assertGreaterEqual(len(res.audit_trail), 3)

    def test_selective_appliance_scheduling(self):
        """Only explicitly selected appliances should appear in the schedule."""
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=120.0,
            bedrooms_count=3,
            bathrooms_count=2,
            living_dining_count=1,
            # Selected: 2 ACs, 3 Fans, 1 Geyser
            ac_required=True,
            ac_count=2,
            ac_intended_rooms=["Master Bedroom", "Bedroom 2"],
            fans_required=True,
            fans_count=3,
            geyser_required=True,
            geyser_count=1,
            # NOT selected:
            refrigerator_required=False,
            washing_machine_required=False,
            water_pump_required=False,
            induction_cooktop_required=False,
            microwave_required=False,
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)
        scheduled_items = res.recommended_plan.equipment_list
        item_names = [it.item_name.lower() for it in scheduled_items]
        categories = [it.category.lower() for it in scheduled_items]

        # Selected appliances must be present
        self.assertTrue(any("ac" in n or "cooling" in c for n, c in zip(item_names, categories)))
        self.assertTrue(any("fan" in n or "ventilation" in c for n, c in zip(item_names, categories)))
        self.assertTrue(any("water heater" in n or "geyser" in n or "water heating" in c for n, c in zip(item_names, categories)))

        # Unselected appliances must NOT be present
        self.assertFalse(any("refrigerator" in n or "fridge" in n for n in item_names))
        self.assertFalse(any("washing machine" in n for n in item_names))
        self.assertFalse(any("water pump" in n or "pump" in n for n in item_names))
        self.assertFalse(any("induction" in n for n in item_names))
        self.assertFalse(any("microwave" in n for n in item_names))

        # Connected load must equal exactly sum of nameplate wattage
        expected_watts = sum(item.rated_power_w * item.quantity for item in scheduled_items)
        self.assertAlmostEqual(res.preliminary_connected_load_kw, round(expected_watts / 1000.0, 2))

    def test_zero_fictitious_room_layout(self):
        """Without detailed room dimensions, an overall schedule is produced without fictitious layout synthesis."""
        req = HouseEnergyPlanningRequest(
            property_type="apartment",
            built_up_area_m2=95.0,
            bedrooms_count=2,
            bathrooms_count=2,
            living_dining_count=1,
            daytime_occupancy="home_during_day",
            ac_required=False,
            fans_required=True,
            fans_count=3,
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)
        # Property summary accurately captures user's stated counts
        self.assertEqual(res.property_summary["bedrooms_count"], 2)
        self.assertEqual(res.property_summary["bathrooms_count"], 2)
        self.assertEqual(res.property_summary["daytime_occupancy"], "home_during_day")
        # Ensure room_wise_schedule is clean and doesn't invent arbitrary coordinates
        room_names = [room.room_name for room in res.room_wise_schedule]
        self.assertTrue(any("Master Bedroom" in n for n in room_names))
        self.assertTrue(any("Bathrooms" in n for n in room_names))
        self.assertTrue(any("Kitchen" in n for n in room_names))

    def test_calculated_efficiency_savings(self):
        """Savings percentages and INR must be dynamically calculated, not hardcoded 28.5% or 42.0%."""
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=150.0,
            efficiency_priority="high_efficiency",
            ac_required=True,
            ac_count=2,
            fans_required=True,
            fans_count=4,
            geyser_required=True,
            geyser_count=2,
            refrigerator_required=True,
            refrigerator_count=1,
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)

        economy_tier = next(t for t in res.alternative_tiers if t.tier_name == "Economy")
        high_tier = res.recommended_plan

        # High tier bill must be strictly less than economy tier bill
        self.assertLess(high_tier.estimated_monthly_bill_inr, economy_tier.estimated_monthly_bill_inr)

        # Dynamic savings verification
        expected_diff = economy_tier.estimated_monthly_bill_inr - high_tier.estimated_monthly_bill_inr
        self.assertAlmostEqual(high_tier.monthly_savings_vs_economy_inr, expected_diff, delta=1.0)

        # Verify it is not the old hardcoded 42.0% or 28.5%
        self.assertNotEqual(high_tier.monthly_savings_pct, 42.0)
        self.assertNotEqual(high_tier.monthly_savings_pct, 28.5)

    def test_solar_readiness_without_roof_area(self):
        """When roof area is not provided, do not fabricate 3 kWp or payback; output preliminary readiness."""
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=160.0,
            include_solar_pv=True,
            roof_area_available_m2=None,  # Not provided
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)

        self.assertIsNotNone(res.solar_readiness)
        self.assertEqual(res.solar_readiness.status, "preliminary_readiness")
        self.assertIsNone(res.solar_readiness.feasible_capacity_kw)
        self.assertIsNone(res.solar_potential_analysis)
        self.assertTrue(len(res.solar_readiness.next_steps) > 0)

    def test_solar_readiness_with_roof_area(self):
        """When roof area is provided, calculate feasible capacity using verified standard benchmark (10 m2/kWp)."""
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=160.0,
            include_solar_pv=True,
            roof_area_available_m2=50.0,
            solar_roof_access="private",
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)

        self.assertIsNotNone(res.solar_readiness)
        self.assertIn(res.solar_readiness.status, ["feasibility_estimated", "feasible"])
        # 50 m2 / 10 m2/kWp = 5.0 kWp
        self.assertEqual(res.solar_readiness.feasible_capacity_kw, 5.0)
        self.assertIsNotNone(res.solar_potential_analysis)
        self.assertEqual(res.solar_potential_analysis["recommendedSystemKwp"], 5.0)

    def test_ev_readiness_analysis(self):
        """When EV charging is requested, evaluate supply readiness and provide IS 17017 guidance."""
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=160.0,
            include_ev_charging=True,
            ev_category="four_wheeler",
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)

        self.assertIsNotNone(res.ev_readiness)
        self.assertEqual(res.ev_readiness.ev_category, "four_wheeler")
        self.assertEqual(res.ev_readiness.recommended_charger_rating_kw, 7.4)
        self.assertEqual(res.ev_readiness.recommended_supply_phase, "Three-Phase (415V)")
        self.assertIn("IS 17017", res.ev_readiness.wiring_notes)

    def test_budget_summary_and_wiring_clarity(self):
        """Budget summary should clearly distinguish equipment cost from wiring and calculate variance."""
        req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=120.0,
            budget_inr=150000.0,
            ac_required=True,
            ac_count=2,
            fans_required=True,
            fans_count=4,
            geyser_required=True,
            geyser_count=1,
        )
        res = BuildingEnergyPlanningEngine.execute_planning(req)

        self.assertIsNotNone(res.budget_summary)
        self.assertEqual(res.budget_summary.allocated_budget_inr, 150000.0)
        self.assertGreater(res.budget_summary.estimated_equipment_cost_inr, 0.0)
        self.assertIn(res.budget_summary.budget_status, ["within_budget", "exceeds_budget", "incomplete"])
        self.assertIn("equipment", res.budget_summary.wiring_installation_note.lower())
        self.assertIn("wiring", res.budget_summary.wiring_installation_note.lower())

    def test_supply_phase_determination(self):
        """IS 732 standard: <= 5 kW single-phase, > 5 kW three-phase."""
        # Low load: 2 fans, 1 fridge
        low_req = HouseEnergyPlanningRequest(
            property_type="apartment",
            built_up_area_m2=60.0,
            ac_required=False,
            fans_required=True,
            fans_count=2,
            refrigerator_required=True,
            refrigerator_count=1,
            geyser_required=False,
        )
        low_res = BuildingEnergyPlanningEngine.execute_planning(low_req)
        self.assertLessEqual(low_res.diversified_maximum_demand_kw, 5.0)
        self.assertEqual(low_res.recommended_plan.recommended_supply_phase, "Single-Phase (230V)")

        # High load: 3 ACs, 2 geysers, 5 fans, water pump
        high_req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=200.0,
            ac_required=True,
            ac_count=3,
            geyser_required=True,
            geyser_count=2,
            fans_required=True,
            fans_count=5,
            water_pump_required=True,
        )
        high_res = BuildingEnergyPlanningEngine.execute_planning(high_req)
        self.assertGreater(high_res.diversified_maximum_demand_kw, 5.0)
        self.assertEqual(high_res.recommended_plan.recommended_supply_phase, "Three-Phase (415V)")

    def test_legacy_request_compatibility(self):
        """Legacy payloads missing new fields must execute cleanly with robust defaults."""
        legacy_req = HouseEnergyPlanningRequest(
            property_type="independent_house",
            built_up_area_m2=120.0,
            budget_inr=100000.0,
            efficiency_priority="economy",
        )
        res = BuildingEnergyPlanningEngine.execute_planning(legacy_req)
        self.assertIsNotNone(res.recommended_plan)
        self.assertGreater(res.preliminary_connected_load_kw, 0.0)
        self.assertIsNotNone(res.budget_summary)
        self.assertTrue(len(res.audit_trail) > 0)


class TestApplianceLifecycleCostEngine(unittest.TestCase):
    """Validates the appliance lifecycle and payback calculation engine."""

    def test_annual_consumption_calculation(self):
        # 1650W AC running 8h/day with 0.7 duty factor
        kwh = ApplianceLifecycleCostEngine.calculate_annual_consumption_kwh(1650.0, 8.0, "Air Conditioner")
        # 1650 * 0.7 * 8 * 365 / 1000 = 3372.6
        self.assertAlmostEqual(kwh, 3372.6, delta=5.0)

    def test_replacement_lifecycle_analysis(self):
        req = ApplianceScenarioRequest(
            intention="replace_existing",
            existing_appliance=ExistingApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1650.0,
                efficiency_label="1-Star Non-Inverter",
                daily_usage_hours=8.0,
                expected_resale_value_inr=2000.0,
            ),
            proposed_appliance=ProposedApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1200.0,
                efficiency_label="5-Star Dual-Inverter",
                purchase_price_inr=39000.0,
                installation_cost_inr=1500.0,
                daily_usage_hours=8.0,
            ),
            tariff_inr_per_kwh=10.0,
            annual_tariff_escalation_pct=4.0,
            analysis_period_years=7,
        )
        res = ApplianceLifecycleCostEngine.execute_analysis(req)
        self.assertGreater(res.annual_energy_savings_kwh, 0.0)
        self.assertGreater(res.annual_cost_savings_inr, 0.0)
        self.assertEqual(res.net_upfront_investment_inr, 39000.0 + 1500.0 - 2000.0)
        self.assertIsNotNone(res.simple_payback_years)
        self.assertLess(res.simple_payback_years, 7.0)
        self.assertEqual(len(res.cashflows), 7)
        self.assertGreater(res.co2_reduction_kg_per_year, 0.0)
        self.assertEqual(len(res.sensitivity_scenarios), 3)


class TestTariffAndSavingsEngines(unittest.TestCase):
    """Validates tariff calculations and energy savings delta."""

    def test_monthly_bill(self):
        bill = TariffBillingEngine.calculate_monthly_bill(
            consumption_kwh=300.0, tariff_rate_inr_per_kwh=10.0, fixed_charge_inr=100.0, electricity_duty_pct=5.0
        )
        self.assertEqual(bill["energy_charge_inr"], 3000.0)
        self.assertEqual(bill["electricity_duty_inr"], 150.0)
        self.assertEqual(bill["total_bill_inr"], 3250.0)

    def test_annual_bill(self):
        annual = TariffBillingEngine.calculate_annual_bill(3600.0, 10.0, 100.0)
        self.assertEqual(annual, 36000.0 + 1200.0)

    def test_scenario_delta(self):
        delta = EnergySavingsEngine.calculate_scenario_delta(500.0, 350.0, 10.0)
        self.assertEqual(delta["energy_saved_kwh"], 150.0)
        self.assertEqual(delta["percentage_reduction_pct"], 30.0)
        self.assertEqual(delta["financial_savings_inr"], 1500.0)

    def test_behavioral_ac_setback(self):
        res = EnergySavingsEngine.evaluate_behavioral_ac_setback(
            current_ac_temp_c=21.0, recommended_temp_c=24.0, ac_monthly_consumption_kwh=200.0
        )
        self.assertEqual(res["delta_temperature_c"], 3.0)
        self.assertEqual(res["energy_reduction_pct"], 18.0)
        self.assertEqual(res["monthly_savings_kwh"], 36.0)


class TestRecommendationEngine(unittest.TestCase):
    """Validates cost management recommendations and constraint filtering."""

    def test_zero_capex_filtering(self):
        req = CostManagementRequest(
            available_investment_budget_inr=0.0,
            primary_objective="low_upfront_cost",
        )
        res = RecommendationEngine.execute_cost_management(450.0, req)
        self.assertEqual(res.total_investment_required_inr, 0.0)
        self.assertGreater(res.achievable_monthly_savings_inr, 0.0)
        # Recommended package must have 0 upfront cost
        self.assertEqual(res.package_recommendations["totalUpfrontCostInr"], 0.0)

    def test_full_budget_recommendations(self):
        req = CostManagementRequest(
            available_investment_budget_inr=60000.0,
            primary_objective="maximize_savings",
            willingness_to_replace_appliances=True,
            solar_interest=True,
        )
        res = RecommendationEngine.execute_cost_management(500.0, req)
        self.assertGreater(len(res.strategies), 3)
        self.assertGreater(res.achievable_annual_savings_inr, 0.0)
        self.assertLessEqual(res.total_investment_required_inr, 60000.0)


class TestResidentialFeaturesAPI(unittest.TestCase):
    """Integration tests for the Flask REST API endpoints."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.headers = {"X-Dev-User": "usr-resident-1000"}

    def test_get_questionnaires(self):
        for fid in ("house_energy_planning", "appliance_analysis", "cost_management"):
            resp = self.client.get(f"/api/v1/residential/questionnaires/{fid}")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["feature_id"], fid)
            self.assertGreater(len(data["data"]["fields"]), 0)

    def test_api_plan_house_energy(self):
        payload = {
            "entity_id": "METER-1000",
            "property_type": "independent_house",
            "built_up_area_m2": 140.0,
            "occupancy_count": 4,
            "budget_inr": 150000.0,
            "efficiency_priority": "balanced",
        }
        resp = self.client.post("/api/v1/residential/plan-house-energy", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        res = data["data"]["results"]
        self.assertIn("recommended_plan", res)
        self.assertIn("preliminary_connected_load_kw", res)

    def test_api_plan_house_energy_with_new_sections(self):
        payload = {
            "entity_id": "METER-1000",
            "property_type": "independent_house",
            "built_up_area_m2": 150.0,
            "floors_count": 2,
            "occupancy_count": 4,
            "location_city": "Bengaluru",
            "bedrooms_count": 3,
            "bathrooms_count": 2,
            "living_dining_count": 1,
            "daytime_occupancy": "work_from_home",
            "ac_required": True,
            "ac_count": 2,
            "ac_intended_rooms": ["Master Bedroom", "Bedroom 2"],
            "ac_usage_range": "4_to_8_hours",
            "fans_required": True,
            "fans_count": 4,
            "geyser_required": True,
            "geyser_count": 2,
            "geyser_usage": "regular",
            "refrigerator_required": True,
            "refrigerator_count": 1,
            "washing_machine_required": True,
            "washing_machine_count": 1,
            "water_pump_required": True,
            "induction_cooktop_required": False,
            "microwave_required": True,
            "additional_high_load_notes": "1.5 HP garden irrigation pump planned later",
            "efficiency_priority": "balanced",
            "budget_inr": 250000.0,
            "include_solar_pv": True,
            "roof_area_available_m2": 45.0,
            "solar_roof_access": "private",
            "include_ev_charging": True,
            "ev_category": "four_wheeler",
        }
        resp = self.client.post("/api/v1/residential/plan-house-energy", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        res = data["data"]["results"]
        self.assertIn("room_wise_schedule", res)
        self.assertIn("budget_summary", res)
        self.assertIn("recommendations", res)
        self.assertIn("solar_readiness", res)
        self.assertEqual(res["solar_readiness"]["feasible_capacity_kw"], 4.5)
        self.assertIn("ev_readiness", res)
        self.assertEqual(res["ev_readiness"]["recommended_supply_phase"], "Three-Phase (415V)")
        self.assertIn("property_summary", res)
        self.assertEqual(res["property_summary"]["bedrooms_count"], 3)

    def test_api_analyze_appliance(self):
        payload = {
            "entity_id": "METER-1000",
            "intention": "replace_existing",
            "existing_appliance": {
                "category": "Air Conditioner",
                "rated_power_w": 1650.0,
                "daily_usage_hours": 8.0,
                "efficiency_label": "Non-Inverter",
            },
            "proposed_appliance": {
                "category": "Air Conditioner",
                "rated_power_w": 1250.0,
                "daily_usage_hours": 8.0,
                "efficiency_label": "5-Star Dual-Inverter",
                "purchase_price_inr": 38000.0,
            },
        }
        resp = self.client.post("/api/v1/residential/analyze-appliance", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        res = data["data"]["results"]
        self.assertGreater(res["annual_energy_savings_kwh"], 0.0)

    def test_api_manage_cost(self):
        payload = {
            "entity_id": "METER-1000",
            "available_investment_budget_inr": 40000.0,
            "primary_objective": "maximize_savings",
        }
        resp = self.client.post("/api/v1/residential/manage-cost", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        res = data["data"]["results"]
        self.assertIn("strategies", res)

    def test_api_session_lifecycle(self):
        # Create session
        create_resp = self.client.post(
            "/api/v1/residential/sessions",
            json={"entity_id": "METER-1000", "feature_id": "house_energy_planning"},
            headers=self.headers,
        )
        self.assertEqual(create_resp.status_code, 200)
        sess = create_resp.get_json()["data"]
        sess_id = sess["sessionId"]
        self.assertEqual(sess["featureId"], "house_energy_planning")

        # Update session
        put_resp = self.client.put(
            f"/api/v1/residential/sessions/{sess_id}",
            json={"entity_id": "METER-1000", "inputs": {"built_up_area_m2": 150.0}, "status": "ready_for_analysis"},
            headers=self.headers,
        )
        self.assertEqual(put_resp.status_code, 200)

        # Get session
        get_resp = self.client.get(f"/api/v1/residential/sessions/{sess_id}", headers=self.headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.get_json()["data"]["status"], "ready_for_analysis")

    def test_api_unauthorized_meter_blocked(self):
        payload = {
            "entity_id": "METER-9999",  # Unauthorized meter for resident 1000
            "property_type": "independent_house",
            "built_up_area_m2": 140.0,
        }
        resp = self.client.post("/api/v1/residential/plan-house-energy", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 403)

    def test_api_authorized_meter_1001_succeeds(self):
        payload = {
            "meter_id": "METER-1001",
            "property_type": "independent_house",
            "built_up_area_m2": 140.0,
        }
        resp = self.client.post("/api/v1/residential/plan-house-energy", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

    def test_api_resident_1000_blocked_from_meter_1001(self):
        payload = {
            "meter_id": "METER-1001",
            "property_type": "independent_house",
            "built_up_area_m2": 140.0,
        }
        # Explicit user 1000 attempting cross-tenant access to meter 1001
        resp = self.client.post("/api/v1/residential/plan-house-energy", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 403)

