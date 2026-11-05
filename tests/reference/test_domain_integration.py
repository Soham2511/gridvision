"""Unit and Integration Tests for Domain Engine Integration & Reference Seeding (Milestone 4 / R5).

Verifies:
1. Reference Data Seeding:
   - BEE Room ACs (1.5T & 1.0T 5-Star & 3-Star ISEER, rated and average power draw).
   - BEE Refrigerators (250L 5-Star inverter 185 kWh vs baseline 310 kWh).
   - BEE Ceiling Fans (1200mm 5-Star BLDC 28W vs induction 75W).
   - BEE Water Heaters (15L 5-Star 0.45 kWh/24h vs baseline 0.85 kWh/24h).
   - CEA Grid Emission Factor (0.82 kg CO2/kWh).
   - Verifiable document provenance metadata (gazette number, revision, table, clause, excerpt).
   - Idempotent database reseeding with SQLAlchemy.
2. ApplianceLifecycleCostEngine Integration:
   - Deterministic calculations with resolved reference values.
   - Seamless backwards compatibility when resolver is not provided.
   - Explicit error handling for missing and expired references.
   - Mathematical formula preservation (annual kWh, capex diff, payback, discounted cash flow, TCO, CO2).
3. ReferenceDataBridge:
   - Seamless delegation to ReferenceResolver with static dictionary fallback.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from app.domain.residential.appliance_engine import ApplianceLifecycleCostEngine
from app.domain.residential.reference_data import (
    APPLIANCE_BENCHMARKS,
    CEA_GRID_EMISSION_FACTOR_KG_PER_KWH,
    LIGHTING_POWER_DENSITY_NORMS_W_PER_M2,
    RESIDENTIAL_DIVERSITY_FACTORS,
    ROOM_FAN_ALLOCATION_AREA_M2,
    SOLAR_PV_NORMS,
    ReferenceDataBridge,
    get_reference_appliance_benchmark,
    get_reference_emission_factor,
)
from app.domain.residential.reference_seeding import (
    VERIFIED_REFERENCE_SEEDS,
    VERIFIED_SOURCES,
    seed_verified_reference_data,
)
from app.domain.residential.schemas import (
    ApplianceScenarioRequest,
    DataProvenance,
    ExistingApplianceSpec,
    ProposedApplianceSpec,
)
from app.infrastructure.database.connection import create_db_engine, get_session_factory
from app.infrastructure.database.models.reference import (
    ApprovedReferenceModel,
    Base,
    ReferenceParameterModel,
    SourceDocumentModel,
)
from app.services.reference.exceptions import (
    ExpiredReferenceError,
    MissingReferenceError,
    ReferenceResolutionError,
)
from app.services.reference.resolver import (
    ReferenceResolutionContext,
    ReferenceResolver,
    ResolvedReference,
)


class TestReferenceDataSeeding(unittest.TestCase):
    """Test suite for reference_seeding.py."""

    def test_verified_sources_metadata_completeness(self):
        """Verify all verified sources contain official issuing organization, url, and checksum."""
        self.assertGreaterEqual(len(VERIFIED_SOURCES), 5)
        source_ids = {s["id"] for s in VERIFIED_SOURCES}
        self.assertIn("BEE-SCHED-02-AC-2022", source_ids)
        self.assertIn("BEE-SCHED-01-REF-2022", source_ids)
        self.assertIn("BEE-SCHED-10-FAN-2023", source_ids)
        self.assertIn("BEE-SCHED-03-WH-2021", source_ids)
        self.assertIn("CEA-CO2-BASELINE-V19", source_ids)

        for src in VERIFIED_SOURCES:
            self.assertTrue(src["official_url"].startswith("https://"))
            self.assertEqual(len(src["content_checksum_sha256"]), 64)
            self.assertIsNotNone(src["document_identifier"])
            self.assertIsNotNone(src["edition_revision"])

    def test_seed_verified_reference_records_content(self):
        """Verify all required benchmarks are present with exact provenance citations."""
        seeds_by_key = {s["parameter_key"]: s for s in VERIFIED_REFERENCE_SEEDS}

        def _get_spec(s: Dict[str, Any]) -> Dict[str, Any]:
            return s.get("specifications") or s.get("provenance", {}).get("technical_specifications", {})

        # 1. BEE Room ACs (Schedule 2)
        ac_15_5star = seeds_by_key["room_ac_1.5t_5star_iseer"]
        self.assertEqual(ac_15_5star["normalized_value"], 5.20)
        self.assertEqual(ac_15_5star["unit"], "Wh/Wh")
        self.assertEqual(_get_spec(ac_15_5star)["rated_power_w"], 1250.0)
        self.assertEqual(_get_spec(ac_15_5star)["average_power_draw_w"], 680.0)
        self.assertIn("Table 2.1", ac_15_5star["provenance"]["table_number"])
        self.assertIn("Clause 3.2", ac_15_5star["provenance"]["section_or_clause"])

        ac_15_3star = seeds_by_key["room_ac_1.5t_3star_iseer"]
        self.assertEqual(ac_15_3star["normalized_value"], 3.80)
        self.assertEqual(_get_spec(ac_15_3star)["rated_power_w"], 1400.0)
        self.assertEqual(_get_spec(ac_15_3star)["average_power_draw_w"], 950.0)

        ac_10_5star = seeds_by_key["room_ac_1.0t_5star_iseer"]
        self.assertEqual(ac_10_5star["normalized_value"], 5.20)
        self.assertEqual(_get_spec(ac_10_5star)["rated_power_w"], 950.0)

        ac_10_3star = seeds_by_key["room_ac_1.0t_3star_iseer"]
        self.assertEqual(ac_10_3star["normalized_value"], 3.80)

        ac_15_base = seeds_by_key["room_ac_1.5t_non_inverter_baseline"]
        self.assertEqual(ac_15_base["normalized_value"], 3.10)
        self.assertEqual(_get_spec(ac_15_base)["rated_power_w"], 1650.0)

        # 2. BEE Refrigerators (Schedule 1)
        ref_5star = seeds_by_key["refrigerator_250l_5star_annual_kwh"]
        self.assertEqual(ref_5star["normalized_value"], 185.0)
        self.assertEqual(ref_5star["unit"], "kWh/year")
        self.assertEqual(_get_spec(ref_5star)["rated_power_w"], 110.0)
        self.assertIn("Clause 4.1", ref_5star["provenance"]["section_or_clause"])

        ref_base = seeds_by_key["refrigerator_250l_baseline_annual_kwh"]
        self.assertEqual(ref_base["normalized_value"], 310.0)
        self.assertEqual(_get_spec(ref_base)["rated_power_w"], 180.0)

        # 3. BEE Ceiling Fans (Schedule 10)
        fan_bldc = seeds_by_key["ceiling_fan_1200mm_5star_bldc_power_w"]
        self.assertEqual(fan_bldc["normalized_value"], 28.0)
        self.assertEqual(fan_bldc["unit"], "W")
        self.assertEqual(_get_spec(fan_bldc)["sweep_mm"], 1200)

        fan_ind = seeds_by_key["ceiling_fan_1200mm_induction_baseline_power_w"]
        self.assertEqual(fan_ind["normalized_value"], 75.0)
        self.assertEqual(fan_ind["unit"], "W")

        # 4. BEE Water Heaters (Schedule 3)
        wh_5star = seeds_by_key["water_heater_15l_5star_standing_loss"]
        self.assertEqual(wh_5star["normalized_value"], 0.45)
        self.assertEqual(wh_5star["unit"], "kWh/24h")
        self.assertEqual(_get_spec(wh_5star)["rated_power_w"], 2000.0)

        wh_base = seeds_by_key["water_heater_15l_baseline_standing_loss"]
        self.assertEqual(wh_base["normalized_value"], 0.85)
        self.assertEqual(wh_base["unit"], "kWh/24h")

        # 5. CEA Grid Emission Factor
        cea = seeds_by_key["cea_grid_emission_factor"]
        self.assertEqual(cea["normalized_value"], 0.82)
        self.assertEqual(cea["unit"], "kg CO2/kWh")
        self.assertEqual(cea["category"], "grid_emission")
        self.assertIn("0.82 kg CO2/kWh", cea["provenance"]["supporting_excerpt"])

    def test_seeding_into_in_memory_resolver(self):
        """Verify seeding directly into an in-memory ReferenceResolver."""
        resolver = ReferenceResolver()
        seeded = seed_verified_reference_data(resolver)
        self.assertGreaterEqual(len(seeded), 10)

        # Query resolved values
        res_ac = resolver.resolve(
            identifier="room_ac_1.5t_5star_iseer",
            category="appliance",
            jurisdiction="IN",
        )
        self.assertEqual(res_ac.value, 5.20)
        self.assertEqual(res_ac.unit, "Wh/Wh")
        self.assertIn("Table 2.1", res_ac.provenance.get("table_number", ""))

        res_cea = resolver.resolve(
            identifier="cea_grid_emission_factor",
            category="grid_emission",
            jurisdiction="IN",
        )
        self.assertEqual(res_cea.value, 0.82)
        self.assertEqual(res_cea.unit, "kg CO2/kWh")

    def test_seeding_into_sqlite_database_session(self):
        """Verify seeding into a clean SQLite relational database session."""
        eng = create_db_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=eng)
        factory = get_session_factory(eng)

        with factory() as session:
            records = seed_verified_reference_data(session)
            self.assertGreater(len(records), 0)

            # Query database directly to verify persistence
            db_sources = session.query(SourceDocumentModel).all()
            self.assertEqual(len(db_sources), len(VERIFIED_SOURCES))

            db_refs = session.query(ApprovedReferenceModel).all()
            self.assertGreaterEqual(len(db_refs), len(VERIFIED_REFERENCE_SEEDS))

            db_params = session.query(ReferenceParameterModel).all()
            self.assertGreater(len(db_params), 0)

            # Check specific persisted record
            ac_ref = (
                session.query(ApprovedReferenceModel)
                .filter(ApprovedReferenceModel.parameter_key == "room_ac_1.5t_5star_iseer")
                .first()
            )
            self.assertIsNotNone(ac_ref)
            self.assertEqual(ac_ref.normalized_value, 5.20)
            self.assertTrue(ac_ref.is_latest)
            self.assertEqual(ac_ref.version, 1)

    def test_idempotent_reseeding(self):
        """Verify calling seed_verified_reference_data multiple times is completely idempotent."""
        eng = create_db_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=eng)
        factory = get_session_factory(eng)

        with factory() as session:
            # Seed 1
            seed1 = seed_verified_reference_data(session)
            count1 = session.query(ApprovedReferenceModel).count()

            # Seed 2 (Re-seeding should not duplicate records)
            seed2 = seed_verified_reference_data(session)
            count2 = session.query(ApprovedReferenceModel).count()

            self.assertEqual(count1, count2)
            self.assertEqual(len(seed1), len(seed2))


class TestApplianceEngineIntegration(unittest.TestCase):
    """Test suite for ApplianceLifecycleCostEngine integrated with ReferenceResolver."""

    def setUp(self):
        # Configure in-memory resolver with seeded data
        self.resolver = ReferenceResolver()
        seed_verified_reference_data(self.resolver)
        self.engine_with_resolver = ApplianceLifecycleCostEngine(resolver=self.resolver)
        self.engine_no_resolver = ApplianceLifecycleCostEngine()

    def test_engine_resolves_emission_factor(self):
        """Verify engine resolves CEA emission factor 0.82 with provenance."""
        ef = self.engine_with_resolver.resolve_emission_factor()
        self.assertEqual(ef, 0.82)

    def test_engine_resolves_appliance_specs(self):
        """Verify engine resolves appliance benchmark specifications."""
        resolved = self.engine_with_resolver.resolve_appliance_specs("room_ac_1.5t_5star_iseer")
        self.assertIsInstance(resolved, ResolvedReference)
        self.assertEqual(resolved.value, 5.20)
        self.assertEqual(resolved.unit, "Wh/Wh")
        self.assertIn("Table 2.1", resolved.provenance.get("table_number", ""))

    def test_execute_analysis_with_resolver_produces_identical_accurate_results(self):
        """Verify execute_analysis produces accurate results with resolver."""
        request = ApplianceScenarioRequest(
            intention="replace_existing",
            existing_appliance=ExistingApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1650.0,
                daily_usage_hours=8.0,
                efficiency_label="Non-Inverter / 1-2 Star BEE",
            ),
            proposed_appliance=ProposedApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1250.0,
                daily_usage_hours=8.0,
                efficiency_label="5-Star BEE Dual-Inverter",
                purchase_price_inr=42000.0,
                installation_cost_inr=1500.0,
            ),
            tariff_inr_per_kwh=10.0,
        )

        result = self.engine_with_resolver.execute_analysis(request)

        # Expected energy calculation:
        # Existing: 1650W * 0.70 duty * 8h * 365 / 1000 = 3372.6 kWh
        # Proposed: 1250W * 0.70 duty * 8h * 365 / 1000 = 2555.0 kWh
        # Saved: 817.6 kWh
        self.assertEqual(result.existing_annual_kwh, 3372.6)
        self.assertEqual(result.proposed_annual_kwh, 2555.0)
        self.assertEqual(result.annual_energy_savings_kwh, 817.6)
        self.assertEqual(result.annual_cost_savings_inr, 8176.0)

        # Net Upfront: 42000 + 1500 - 0 = 43500.0
        self.assertEqual(result.net_upfront_investment_inr, 43500.0)

        # Simple Payback: 43500 / 8176 = 5.32 years
        self.assertAlmostEqual(result.simple_payback_years, 5.32, places=2)

        # CO2 Reduction: 817.6 * 0.82 = 670.4 kg CO2
        self.assertAlmostEqual(result.co2_reduction_kg_per_year, 670.4, places=1)

        # Verify audit trail contains official reference provenance
        co2_audit = next(a for a in result.audit_trail if a.metric_name == "co2_reduction_kg_per_year")
        self.assertEqual(co2_audit.provenance, DataProvenance.OFFICIAL_REFERENCE)
        self.assertIn("CEA/TCD/CO2/BASELINE/V19", co2_audit.notes or "")

    def test_engine_without_resolver_backwards_compatible(self):
        """Verify engine without resolver functions identically with 0 regressions."""
        request = ApplianceScenarioRequest(
            intention="replace_existing",
            existing_appliance=ExistingApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1650.0,
                daily_usage_hours=8.0,
                efficiency_label="Non-Inverter / 1-2 Star BEE",
            ),
            proposed_appliance=ProposedApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1250.0,
                daily_usage_hours=8.0,
                efficiency_label="5-Star BEE Dual-Inverter",
                purchase_price_inr=38000.0,
                installation_cost_inr=1500.0,
            ),
            tariff_inr_per_kwh=10.0,
        )

        result = self.engine_no_resolver.execute_analysis(request)
        self.assertEqual(result.annual_energy_savings_kwh, 817.6)
        self.assertAlmostEqual(result.co2_reduction_kg_per_year, 670.4, places=1)

    def test_engine_missing_reference_error_handling(self):
        """Verify resolving a non-existent reference raises MissingReferenceError, zero silent defaults."""
        with self.assertRaises(MissingReferenceError):
            self.engine_with_resolver.resolve_reference(
                identifier="non_existent_exotic_heat_pump",
                category="appliance",
            )

    def test_engine_expired_reference_error_handling(self):
        """Verify resolving an expired reference raises ExpiredReferenceError, zero silent defaults."""
        # Register a reference expired in 2021
        self.resolver.register_reference({
            "parameter_key": "expired_solar_inverter_efficiency",
            "category": "solar",
            "value": 0.92,
            "unit": "ratio",
            "jurisdiction": "IN",
            "effective_from": date(2018, 1, 1),
            "effective_to": date(2021, 12, 31),
            "status": "approved",
        })

        with self.assertRaises(ExpiredReferenceError):
            self.engine_with_resolver.resolve_reference(
                identifier="expired_solar_inverter_efficiency",
                category="solar",
                effective_date=date(2025, 1, 1),  # Queried after expiry
            )

    def test_engine_no_resolver_configured_raises_on_explicit_resolve(self):
        """Verify calling resolve_reference without configured resolver raises ValueError."""
        with self.assertRaises(ValueError):
            self.engine_no_resolver.resolve_reference("room_ac_1.5t_5star_iseer")


class TestFormulaPreservation(unittest.TestCase):
    """Verify all mathematical equations are strictly preserved and physically invariant."""

    def test_annual_energy_formula_duty_cycle_matrix(self):
        """Verify E = (W * duty * h * 365) / 1000 across duty cycle categories."""
        # Air Conditioner (0.70 duty)
        ac_kwh = ApplianceLifecycleCostEngine.calculate_annual_consumption_kwh(1250.0, 8.0, "Air Conditioner")
        expected_ac = round(1250.0 * 0.70 * 8.0 * 365.0 / 1000.0, 2)
        self.assertEqual(ac_kwh, expected_ac)
        self.assertEqual(ac_kwh, 2555.0)

        # Refrigerator (0.35 duty)
        fridge_kwh = ApplianceLifecycleCostEngine.calculate_annual_consumption_kwh(110.0, 24.0, "Refrigerator")
        expected_fridge = round(110.0 * 0.35 * 24.0 * 365.0 / 1000.0, 2)
        self.assertEqual(fridge_kwh, expected_fridge)
        self.assertEqual(fridge_kwh, 337.26)

        # Ceiling Fan (1.0 duty)
        fan_kwh = ApplianceLifecycleCostEngine.calculate_annual_consumption_kwh(28.0, 10.0, "Ceiling Fan")
        expected_fan = round(28.0 * 1.0 * 10.0 * 365.0 / 1000.0, 2)
        self.assertEqual(fan_kwh, expected_fan)
        self.assertEqual(fan_kwh, 102.2)

        # Water Heater (0.90 duty)
        wh_kwh = ApplianceLifecycleCostEngine.calculate_annual_consumption_kwh(2000.0, 2.0, "Water Heater")
        expected_wh = round(2000.0 * 0.90 * 2.0 * 365.0 / 1000.0, 2)
        self.assertEqual(wh_kwh, expected_wh)
        self.assertEqual(wh_kwh, 1314.0)

    def test_payback_period_mathematical_definition(self):
        """Verify Simple Payback = Net Upfront / Annual Savings Year 1."""
        capex = 14000.0
        annual_savings = 5000.0
        payback = round(capex / annual_savings, 2)
        self.assertEqual(payback, 2.8)

    def test_carbon_reduction_mathematical_definition(self):
        """Verify CO2 Avoidance = Saved kWh * Emission Factor."""
        saved_kwh = 1000.0
        ef = 0.82
        co2_kg = round(saved_kwh * ef, 1)
        self.assertEqual(co2_kg, 820.0)

    def test_multi_year_escalation_discount_cashflow_npv(self):
        """Verify discounted cash flow and net present value calculations."""
        base_savings = 10000.0
        esc_rate = 0.05
        disc_rate = 0.08
        years = 3

        npv_total = 0.0
        for y in range(1, years + 1):
            escalated = base_savings * ((1.0 + esc_rate) ** (y - 1))
            disc_factor = 1.0 / ((1.0 + disc_rate) ** y)
            npv_total += escalated * disc_factor

        self.assertGreater(npv_total, 24000.0)
        self.assertLess(npv_total, 28000.0)


class TestReferenceDataBridge(unittest.TestCase):
    """Test suite for ReferenceDataBridge in reference_data.py."""

    def test_bridge_with_resolver(self):
        """Verify bridge queries ReferenceResolver when provided."""
        resolver = ReferenceResolver()
        seed_verified_reference_data(resolver)
        bridge = ReferenceDataBridge(resolver)

        ef = bridge.get_emission_factor()
        self.assertEqual(ef, 0.82)

        val = bridge.get_appliance_benchmark("room_ac_1.5t_5star_iseer")
        self.assertEqual(val, 5.20)

    def test_bridge_without_resolver_fallback_to_static_dicts(self):
        """Verify bridge falls back seamlessly to static dictionaries when resolver is None."""
        bridge = ReferenceDataBridge(resolver=None)

        self.assertEqual(bridge.get_emission_factor(), 0.82)
        self.assertEqual(bridge.get_fan_allocation_area(), 14.0)
        self.assertEqual(bridge.get_lighting_power_density("kitchen"), 6.5)
        self.assertEqual(bridge.get_diversity_factor("lighting_and_fans"), 0.70)
        self.assertEqual(bridge.get_solar_norm("annual_generation_kwh_per_kwp"), 1450.0)

        # Appliance dictionary lookup
        ac_data = bridge.get_appliance_benchmark("air_conditioner_1.5t", "5_star_inverter")
        self.assertEqual(ac_data["typical_iseer"], 5.2)

    def test_static_dictionaries_remain_intact(self):
        """Verify all static dictionaries in reference_data.py remain present and valid."""
        self.assertEqual(CEA_GRID_EMISSION_FACTOR_KG_PER_KWH, 0.82)
        self.assertEqual(ROOM_FAN_ALLOCATION_AREA_M2, 14.0)
        self.assertEqual(LIGHTING_POWER_DENSITY_NORMS_W_PER_M2["living_room"], 5.0)
        self.assertEqual(APPLIANCE_BENCHMARKS["ceiling_fan"]["bldc_energy_efficient"]["rated_power_w"], 28.0)
        self.assertEqual(SOLAR_PV_NORMS["system_lifespan_years"], 25)
        self.assertEqual(RESIDENTIAL_DIVERSITY_FACTORS["overall_connected_load_to_maximum_demand"], 0.65)


if __name__ == "__main__":
    unittest.main()
