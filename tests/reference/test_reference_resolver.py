"""Comprehensive Unit Tests for Deterministic ReferenceResolver.

Covers:
- 5-Tier hierarchical matching policy (DISCOM > State > National)
- Typed value and provenance citations
- Formal exception hierarchy and proof of zero silent defaults
- Conflict and ambiguity detection
- Versioning and temporal boundary conditions
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from typing import Any, Dict

from app.services.reference.exceptions import (
    AmbiguousReferenceError,
    ExpiredReferenceError,
    MissingReferenceError,
    OutOfJurisdictionError,
    ReferenceResolutionError,
    UnapprovedReferenceError,
)
from app.services.reference.resolver import (
    ReferenceResolutionContext,
    ReferenceResolver,
    ResolvedReference,
)


class TestPrecedenceTiers(unittest.TestCase):
    """Test 5-tier hierarchical matching policy."""

    def setUp(self) -> None:
        self.resolver = ReferenceResolver()
        # Seed tariffs across multiple tiers
        # Tier 1: BESCOM + Domestic Slab (Exact DISCOM + Exact Spec)
        self.resolver.register_reference({
            "parameter_key": "residential_tariff_energy_rate",
            "value": 8.15,
            "unit": "INR/kWh",
            "jurisdiction": "KA",
            "region": "BESCOM",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "specifications": {"consumer_category": "domestic", "slab": "101-200"},
            "provenance": {"document_identifier": "KERC/BESCOM/2024/01", "page": 45},
        })
        # Tier 2: BESCOM general (Exact DISCOM + General Applicability)
        self.resolver.register_reference({
            "parameter_key": "residential_tariff_energy_rate",
            "value": 7.90,
            "unit": "INR/kWh",
            "jurisdiction": "KA",
            "region": "BESCOM",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "specifications": {},
            "provenance": {"document_identifier": "KERC/BESCOM/2024/01", "page": 40},
        })
        # Tier 3: Karnataka state default + Domestic Slab (State Wildcard + Exact Spec)
        self.resolver.register_reference({
            "parameter_key": "residential_tariff_energy_rate",
            "value": 7.50,
            "unit": "INR/kWh",
            "jurisdiction": "KA",
            "region": None,
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "specifications": {"consumer_category": "domestic", "slab": "101-200"},
            "provenance": {"document_identifier": "KERC/GEN/2024/02", "page": 12},
        })
        # Tier 4: Karnataka state default general (State Wildcard + General Applicability)
        self.resolver.register_reference({
            "parameter_key": "residential_tariff_energy_rate",
            "value": 7.20,
            "unit": "INR/kWh",
            "jurisdiction": "KA",
            "region": None,
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "specifications": {},
            "provenance": {"document_identifier": "KERC/GEN/2024/02", "page": 10},
        })
        # Tier 5: National Standard ("IN")
        self.resolver.register_reference({
            "parameter_key": "residential_tariff_energy_rate",
            "value": 6.80,
            "unit": "INR/kWh",
            "jurisdiction": "IN",
            "region": None,
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "specifications": {},
            "provenance": {"document_identifier": "CEA/TARIFF/2024/01", "page": 5},
        })

    def test_tier1_discom_exact_spec_takes_precedence(self) -> None:
        """Verify Tier 1 (DISCOM exact + spec exact) resolves over all lower tiers."""
        ctx = ReferenceResolutionContext(
            category="tariff",
            identifier="residential_tariff_energy_rate",
            jurisdiction="KA",
            region_or_discom="BESCOM",
            effective_date=date(2025, 6, 1),
            specifications={"consumer_category": "domestic", "slab": "101-200"},
        )
        res = self.resolver.resolve(ctx)
        self.assertEqual(res.value, 8.15)
        self.assertEqual(res.unit, "INR/kWh")
        self.assertEqual(res.jurisdiction, "KA")
        self.assertEqual(res.region, "BESCOM")
        self.assertEqual(res.provenance["document_identifier"], "KERC/BESCOM/2024/01")

    def test_tier2_discom_general_precedence_over_state_exact(self) -> None:
        """Verify Tier 2 (DISCOM general) resolves when query does not match DISCOM exact spec."""
        ctx = ReferenceResolutionContext(
            category="tariff",
            identifier="residential_tariff_energy_rate",
            jurisdiction="KA",
            region_or_discom="BESCOM",
            effective_date=date(2025, 6, 1),
            specifications={"consumer_category": "commercial"},  # does not match 101-200 domestic
        )
        res = self.resolver.resolve(ctx)
        self.assertEqual(res.value, 7.90)
        self.assertEqual(res.region, "BESCOM")

    def test_tier3_state_exact_spec_precedence_over_national(self) -> None:
        """Verify Tier 3 (State + exact spec) resolves when region is not specified."""
        ctx = ReferenceResolutionContext(
            category="tariff",
            identifier="residential_tariff_energy_rate",
            jurisdiction="KA",
            region_or_discom=None,
            effective_date=date(2025, 6, 1),
            specifications={"consumer_category": "domestic", "slab": "101-200"},
        )
        res = self.resolver.resolve(ctx)
        self.assertEqual(res.value, 7.50)
        self.assertEqual(res.jurisdiction, "KA")

    def test_tier4_state_general_precedence_over_national(self) -> None:
        """Verify Tier 4 (State general) resolves over National when region is None."""
        ctx = ReferenceResolutionContext(
            category="tariff",
            identifier="residential_tariff_energy_rate",
            jurisdiction="KA",
            region_or_discom=None,
            effective_date=date(2025, 6, 1),
            specifications={"consumer_category": "industrial"},
        )
        res = self.resolver.resolve(ctx)
        self.assertEqual(res.value, 7.20)
        self.assertEqual(res.jurisdiction, "KA")

    def test_tier5_national_fallback_for_other_indian_states(self) -> None:
        """Verify Tier 5 (National 'IN') resolves when state has no local rule."""
        ctx = ReferenceResolutionContext(
            category="tariff",
            identifier="residential_tariff_energy_rate",
            jurisdiction="MH",  # Maharashtra has no state or discom rule seeded above
            region_or_discom="MSEDCL",
            effective_date=date(2025, 6, 1),
        )
        res = self.resolver.resolve(ctx)
        self.assertEqual(res.value, 6.80)
        self.assertEqual(res.jurisdiction, "IN")


class TestTypedResolutionAndProvenance(unittest.TestCase):
    """Test typed return and comprehensive provenance citations."""

    def test_float_typed_resolution(self) -> None:
        resolver = ReferenceResolver()
        resolver.register_reference({
            "parameter_key": "room_ac_1.5t_5star_iseer",
            "value": 5.20,
            "unit": "Wh/Wh",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "provenance": {
                "source_id": "src-bee-ac-2024",
                "issuing_organization": "Bureau of Energy Efficiency",
                "document_identifier": "BEE/S&L/AC/2024/001",
                "page": 14,
                "clause": "Table 2.1",
                "table": "2.1",
                "excerpt": "5-Star Room Air Conditioners: ISEER >= 5.00",
            },
        })
        res = resolver.resolve(parameter_key="room_ac_1.5t_5star_iseer", jurisdiction="IN")
        self.assertIsInstance(res.value, float)
        self.assertEqual(res.value, 5.20)
        self.assertEqual(res.unit, "Wh/Wh")
        # Subscripting compatibility
        self.assertEqual(res["value"], 5.20)
        self.assertEqual(res["unit"], "Wh/Wh")
        # Provenance checks
        self.assertEqual(res.provenance["document_identifier"], "BEE/S&L/AC/2024/001")
        self.assertEqual(res.provenance["page"], 14)
        self.assertEqual(res.provenance["clause"], "Table 2.1")
        self.assertEqual(res.provenance["table"], "2.1")
        self.assertIn("5-Star", res.provenance["excerpt"])

    def test_dict_typed_resolution(self) -> None:
        resolver = ReferenceResolver()
        resolver.register_reference({
            "parameter_key": "solar_pv_benchmarks",
            "value": {
                "system_cost_per_kwp": 52000.0,
                "annual_generation_per_kwp": 1450.0,
                "lifespan_years": 25,
            },
            "unit": "complex",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "provenance": {"document_identifier": "MNRE/SOLAR/2024/01", "page": 8},
        })
        res = resolver.resolve(parameter_key="solar_pv_benchmarks", jurisdiction="IN")
        self.assertIsInstance(res.value, dict)
        self.assertEqual(res.value["system_cost_per_kwp"], 52000.0)
        self.assertEqual(res.value["lifespan_years"], 25)


class TestStrictZeroSilentDefaults(unittest.TestCase):
    """Verify ZERO silent defaults: explicit typed errors for every invalid condition."""

    def setUp(self) -> None:
        self.resolver = ReferenceResolver()
        self.resolver.register_reference({
            "parameter_key": "valid_approved_param",
            "value": 42.0,
            "unit": "W",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2025, 12, 31),
            "status": "approved",
            "provenance": {"document_identifier": "DOC/01", "page": 1},
        })
        self.resolver.register_reference({
            "parameter_key": "unapproved_draft_param",
            "value": 100.0,
            "unit": "W",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2025, 12, 31),
            "status": "draft",
            "provenance": {"document_identifier": "DOC/02", "page": 1},
        })

    def test_missing_parameter_raises_missing_reference_error(self) -> None:
        """Querying a missing parameter must NEVER return None or fallback scalar."""
        with self.assertRaises(MissingReferenceError) as ctx:
            self.resolver.resolve(parameter_key="completely_non_existent_parameter")
        self.assertIn("completely_non_existent_parameter", str(ctx.exception))
        self.assertTrue(issubclass(MissingReferenceError, ReferenceResolutionError))

    def test_unapproved_reference_raises_unapproved_error(self) -> None:
        """Querying an unapproved draft record must raise UnapprovedReferenceError."""
        with self.assertRaises(UnapprovedReferenceError) as ctx:
            self.resolver.resolve(parameter_key="unapproved_draft_param")
        self.assertIn("unapproved_draft_param", str(ctx.exception))
        self.assertTrue(issubclass(UnapprovedReferenceError, ReferenceResolutionError))

    def test_expired_date_raises_expired_reference_error(self) -> None:
        """Querying on date after effective_to must raise ExpiredReferenceError."""
        future_date = date(2026, 1, 1)
        with self.assertRaises(ExpiredReferenceError) as ctx:
            self.resolver.resolve(
                parameter_key="valid_approved_param",
                effective_date=future_date,
            )
        self.assertIn("2025-12-31", str(ctx.exception))
        self.assertTrue(issubclass(ExpiredReferenceError, ReferenceResolutionError))

    def test_before_effective_date_raises_expired_reference_error(self) -> None:
        """Querying on date before effective_from must raise ExpiredReferenceError."""
        past_date = date(2023, 12, 31)
        with self.assertRaises(ExpiredReferenceError) as ctx:
            self.resolver.resolve(
                parameter_key="valid_approved_param",
                effective_date=past_date,
            )
        self.assertIn("2024-01-01", str(ctx.exception))

    def test_out_of_jurisdiction_query_raises_out_of_jurisdiction_error(self) -> None:
        """Querying foreign or non-applicable jurisdiction must raise OutOfJurisdictionError."""
        with self.assertRaises(OutOfJurisdictionError) as ctx:
            self.resolver.resolve(
                parameter_key="valid_approved_param",
                jurisdiction="US",  # foreign jurisdiction: Indian national rule cannot apply
            )
        self.assertIn("US", str(ctx.exception))
        self.assertTrue(issubclass(OutOfJurisdictionError, ReferenceResolutionError))

    def test_conflicting_ambiguous_records_raise_ambiguous_reference_error(self) -> None:
        """Two identical precedence records with conflicting values must raise AmbiguousReferenceError."""
        conflict_resolver = ReferenceResolver()
        conflict_resolver.register_reference({
            "parameter_key": "conflicted_param",
            "value": 10.5,
            "unit": "kWh",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "version": 1,
            "is_latest": True,
            "provenance": {"document_identifier": "SRC/A", "page": 1},
        })
        conflict_resolver.register_reference({
            "parameter_key": "conflicted_param",
            "value": 15.0,  # DIFFERENT VALUE!
            "unit": "kWh",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "version": 1,
            "is_latest": True,
            "provenance": {"document_identifier": "SRC/B", "page": 2},
        })

        with self.assertRaises(AmbiguousReferenceError) as ctx:
            conflict_resolver.resolve(parameter_key="conflicted_param")
        self.assertIn("Ambiguous", str(ctx.exception))
        self.assertTrue(issubclass(AmbiguousReferenceError, ReferenceResolutionError))


class TestVersioningAndDeterminism(unittest.TestCase):
    """Test versioning resolution and temporal boundaries."""

    def test_higher_version_supersedes_older_version(self) -> None:
        """When v1 and v2 both exist, resolver selects latest approved version."""
        resolver = ReferenceResolver()
        resolver.register_reference({
            "parameter_key": "cea_grid_emission_factor",
            "value": 0.82,
            "unit": "kg CO2/kWh",
            "jurisdiction": "IN",
            "effective_from": date(2020, 1, 1),
            "effective_to": None,
            "status": "approved",
            "version": 1,
            "is_latest": False,
            "provenance": {"document_identifier": "CEA/DB/v16", "page": 1},
        })
        resolver.register_reference({
            "parameter_key": "cea_grid_emission_factor",
            "value": 0.72,
            "unit": "kg CO2/kWh",
            "jurisdiction": "IN",
            "effective_from": date(2023, 11, 1),
            "effective_to": None,
            "status": "approved",
            "version": 2,
            "is_latest": True,
            "provenance": {"document_identifier": "CEA/DB/v19", "page": 1},
        })
        res = resolver.resolve(parameter_key="cea_grid_emission_factor", jurisdiction="IN")
        self.assertEqual(res.value, 0.72)
        self.assertEqual(res.version, 2)
        self.assertEqual(res.provenance["document_identifier"], "CEA/DB/v19")

    def test_identical_values_at_same_precedence_resolve_cleanly(self) -> None:
        """Multiple duplicate approved entries with identical value do not cause ambiguity error."""
        resolver = ReferenceResolver()
        for i in range(3):
            resolver.register_reference({
                "parameter_key": "lpd_norm_living_room",
                "value": 5.0,
                "unit": "W/m2",
                "jurisdiction": "IN",
                "effective_from": date(2024, 1, 1),
                "effective_to": date(2026, 12, 31),
                "status": "approved",
                "version": 1,
                "provenance": {"document_identifier": f"NBC/2016/COPY{i}", "page": 5},
            })
        res = resolver.resolve(parameter_key="lpd_norm_living_room", jurisdiction="IN")
        self.assertEqual(res.value, 5.0)

    def test_exact_boundary_dates(self) -> None:
        """Test exact boundary inclusion on effective_from and effective_to."""
        resolver = ReferenceResolver()
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        resolver.register_reference({
            "parameter_key": "bounded_param",
            "value": 12.5,
            "unit": "W",
            "jurisdiction": "IN",
            "effective_from": start,
            "effective_to": end,
            "status": "approved",
            "provenance": {"document_identifier": "DOC/BOUND", "page": 1},
        })
        # Exact start date resolves
        res_start = resolver.resolve(parameter_key="bounded_param", effective_date=start)
        self.assertEqual(res_start.value, 12.5)
        # Exact end date resolves
        res_end = resolver.resolve(parameter_key="bounded_param", effective_date=end)
        self.assertEqual(res_end.value, 12.5)

    def test_case_insensitive_jurisdiction_and_discom(self) -> None:
        """Verify queries with lowercase jurisdiction/region match uppercase records."""
        resolver = ReferenceResolver()
        resolver.register_reference({
            "parameter_key": "case_test_param",
            "value": 99.9,
            "unit": "ratio",
            "jurisdiction": "KA",
            "region": "BESCOM",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "status": "approved",
            "provenance": {"document_identifier": "DOC/CASE", "page": 1},
        })
        res = resolver.resolve(
            parameter_key="case_test_param",
            jurisdiction="ka",
            region_or_discom="bescom",
        )
        self.assertEqual(res.value, 99.9)


if __name__ == "__main__":
    unittest.main()
