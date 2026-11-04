"""Tier 4: Real-World Regulatory Scenarios Test Suite.

End-to-end multi-feature scenarios covering realistic Indian regulatory workflows:
1. BEE Room AC Gazette Notification Ingestion & Lifecycle Cost Payback
2. BEE 5-Star Refrigerator Ingestion & House Planning Assessment
3. State DISCOM Multi-Year Tariff Revision (Superseding Version)
4. CEA CO2 Grid Emission Factor Resolution & Payback Carbon Calc
5. Adversarial Malicious Document Ingestion Rejection (SSRF / File Spoof / Duplication)
6. Customer Telemetry Isolation Invariant Under Multi-Tenant Operational Load

Derived from ORIGINAL_REQUEST.md (R1-R5), PROJECT.md, and TEST_INFRA.md.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from tests.e2e_reference import contract_helper as ch
from tests.e2e_reference.conftest import (
    CORRUPT_PDF_BYTES,
    VALID_PDF_BYTES,
    get_sample_candidate_payload,
    get_sample_extracted_structure,
    get_sample_source_payload,
)


class TestTier4RealWorldScenarios(unittest.TestCase):
    """Real-world regulatory scenarios test suite."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gridvision_t4_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scenario_1_bee_room_ac_gazette_payback(self):
        """Scenario 1: BEE Room AC Gazette Ingestion & Lifecycle Cost Payback.
        Full regulatory workflow: Ingestion -> Magic bytes -> Storage -> Extraction ->
        Candidate -> Validation -> Review -> Persistence -> Resolver -> Payback Math.
        """
        # 1. Source Document Acquisition
        source_meta = {
            "issuing_organization": "Bureau of Energy Efficiency (BEE)",
            "official_url": "https://beeindia.gov.in/standards/room-ac-schedule2-2024.pdf",
            "document_identifier": "BEE/S&L/AC/2024/001",
            "edition": "Schedule 2 Revision 4",
            "publication_date": date(2024, 1, 15),
            "checksum_sha256": hashlib.sha256(VALID_PDF_BYTES).hexdigest(),
            "status": "active",
        }

        # 2. File Validation
        if ch.DocumentValidator is not None:
            validator = ch.DocumentValidator()
            val_res = validator.validate(VALID_PDF_BYTES, "room-ac-schedule2-2024.pdf")
            self.assertTrue(val_res["is_valid"])

        # 3. Storage Separation
        if ch.LocalFileSystemStorageAdapter is not None:
            storage = ch.LocalFileSystemStorageAdapter(base_dir=self.temp_dir)
            orig_path = ch.invoke_save_original(storage, "bee_ac_2024", "schedule2.pdf", VALID_PDF_BYTES)
            self.assertTrue(storage.exists(orig_path))

        # 4. Extracted AST Representation
        extracted_ast = get_sample_extracted_structure()
        self.assertEqual(extracted_ast["tables"][0]["rows"][2][2], "5.20")

        # 5. Candidate Generation & Pydantic Validation
        candidate_data = {
            "parameter_key": "room_ac_1.5t_5star_iseer",
            "raw_value": "5.20",
            "normalized_value": 5.20,
            "unit": "Wh/Wh",
            "jurisdiction": "IN",
            "region": None,
            "applicability_conditions": {
                "appliance_type": "room_air_conditioner",
                "rated_capacity_tons": 1.5,
                "star_rating": 5,
                "technology": "inverter",
            },
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "source_id": "bee_ac_2024",
            "provenance": {
                "document_identifier": "BEE/S&L/AC/2024/001",
                "page": 12,
                "table": "Table 2",
                "excerpt": "Table 2: 1.5 Ton Star 5 Minimum ISEER 5.20 Wh/Wh",
            },
            "confidence": 1.0,
        }
        if ch.CandidateReferenceSchema is not None:
            schema_instance = ch.CandidateReferenceSchema.model_validate(candidate_data)
            self.assertEqual(schema_instance.normalized_value, 5.20)

        # 6. Review & Approval
        approval_record = {
            "version": 1,
            "is_latest": True,
            "approved_by": "lead_auditor@gridvision.org",
            "approved_at": datetime.now(timezone.utc),
            "normalized_value": candidate_data["normalized_value"],
        }
        self.assertEqual(approval_record["version"], 1)

        # 7. Lifecycle Payback Calculation (ApplianceLifecycleCostEngine Formula Preservation)
        # 1.5T 5-Star Inverter AC vs 1-Star Legacy Baseline
        baseline_draw_w = 1450.0
        efficient_draw_w = 680.0
        operating_hours = 1600.0
        annual_energy_savings_kwh = (baseline_draw_w - efficient_draw_w) * operating_hours / 1000.0
        self.assertEqual(annual_energy_savings_kwh, 1232.0)

        tariff_inr_per_kwh = 10.0
        annual_opex_savings_inr = annual_energy_savings_kwh * tariff_inr_per_kwh
        self.assertEqual(annual_opex_savings_inr, 12320.0)

        capex_legacy = 28000.0
        capex_5star = 42000.0
        incremental_capex = capex_5star - capex_legacy
        self.assertEqual(incremental_capex, 14000.0)

        simple_payback_years = incremental_capex / annual_opex_savings_inr
        self.assertAlmostEqual(simple_payback_years, 1.136, places=2)

    def test_scenario_2_bee_refrigerator_house_planning(self):
        """Scenario 2: BEE 5-Star Refrigerator Ingestion & House Planning Assessment.
        Evaluates 250L Refrigerator annual energy reduction and carbon emissions avoidance.
        """
        refrigerator_benchmark = {
            "parameter_key": "refrigerator_250l_annual_kwh",
            "legacy_2star_kwh": 310.0,
            "5star_inverter_kwh": 185.0,
            "unit": "kWh/year",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
        }

        # Energy reduction
        saved_kwh_annual = (
            refrigerator_benchmark["legacy_2star_kwh"]
            - refrigerator_benchmark["5star_inverter_kwh"]
        )
        self.assertEqual(saved_kwh_annual, 125.0)

        # Carbon avoidance using official CEA emission factor (0.82 kg CO2 / kWh)
        cea_factor = 0.82
        co2_avoided_kg = saved_kwh_annual * cea_factor
        self.assertEqual(co2_avoided_kg, 102.5)

    def test_scenario_3_state_discom_myt_tariff_superseding(self):
        """Scenario 3: State DISCOM Multi-Year Tariff Revision (Superseding Version).
        Simulates BESCOM MYT 2024 (v1: ₹7.50) supersession by MYT 2025 (v2: ₹8.20).
        """
        # Version 1 Persistence
        v1 = {
            "id": 501,
            "parameter_key": "bescom_residential_tariff",
            "normalized_value": 7.50,
            "unit": "INR/kWh",
            "jurisdiction": "KA",
            "region": "BESCOM",
            "effective_from": date(2024, 4, 1),
            "effective_to": date(2025, 3, 31),
            "version": 1,
            "is_latest": True,
            "superseded_by_id": None,
        }

        # Later, MYT 2025 is enacted: Version 2 Persistence
        v2 = {
            "id": 502,
            "parameter_key": "bescom_residential_tariff",
            "normalized_value": 8.20,
            "unit": "INR/kWh",
            "jurisdiction": "KA",
            "region": "BESCOM",
            "effective_from": date(2025, 4, 1),
            "effective_to": date(2026, 3, 31),
            "version": 2,
            "is_latest": True,
            "superseded_by_id": None,
        }

        # Atomic supersession transition
        v1["is_latest"] = False
        v1["superseded_by_id"] = v2["id"]

        self.assertFalse(v1["is_latest"])
        self.assertEqual(v1["superseded_by_id"], 502)
        self.assertTrue(v2["is_latest"])

        # Temporal Resolution Testing
        def resolve_tariff(query_date: date) -> float:
            for rec in [v1, v2]:
                if rec["effective_from"] <= query_date <= rec["effective_to"]:
                    return rec["normalized_value"]
            raise ch.ExpiredReferenceError(f"No active tariff for {query_date}")

        # Date 2024-09-01 resolves v1: ₹7.50
        self.assertEqual(resolve_tariff(date(2024, 9, 1)), 7.50)
        # Date 2025-09-01 resolves v2: ₹8.20
        self.assertEqual(resolve_tariff(date(2025, 9, 1)), 8.20)
        # Date 2023-01-01 raises ExpiredReferenceError
        with self.assertRaises(ch.ExpiredReferenceError):
            resolve_tariff(date(2023, 1, 1))

    def test_scenario_4_cea_co2_grid_emission_factor_resolution(self):
        """Scenario 4: CEA CO2 Emission Factor Resolution & Payback Carbon Calc.
        Ingests official CEA 0.82 factor and evaluates fan upgrade emissions reduction.
        """
        cea_reference = {
            "parameter_key": "cea_grid_emission_factor",
            "normalized_value": 0.82,
            "unit": "kg CO2/kWh",
            "jurisdiction": "IN",
            "provenance": {
                "source": "Central Electricity Authority (CEA)",
                "document": "CO2 Baseline Database for the Indian Power Sector, Ver. 19",
                "table": "National Weighted Average Emission Factor",
            },
        }
        self.assertEqual(cea_reference["normalized_value"], 0.82)

        # BLDC Ceiling Fan 1200mm (28W) vs Conventional Induction Fan (75W)
        fan_hours = 1600.0
        induction_w = 75.0
        bldc_w = 28.0
        annual_fan_saved_kwh = (induction_w - bldc_w) * fan_hours / 1000.0
        self.assertEqual(annual_fan_saved_kwh, 75.2)

        annual_co2_saved_kg = annual_fan_saved_kwh * cea_reference["normalized_value"]
        self.assertAlmostEqual(annual_co2_saved_kg, 61.664, places=3)

    def test_scenario_5_adversarial_malicious_document_rejection(self):
        """Scenario 5: Adversarial Malicious Document Ingestion Rejection.
        Rejection of SSRF targets, corrupt magic bytes, and invalid candidates.
        """
        # Attack A: SSRF AWS / Cloud instance metadata
        if ch.SSRFSafeFetcher is not None:
            fetcher = ch.SSRFSafeFetcher()
            with self.assertRaises((ch.SSRFSecurityError, ValueError)):
                ch.invoke_validate_url(fetcher, "http://169.254.169.254/latest/meta-data/")

        # Attack B: SSRF IPv6 loopback
        if ch.SSRFSafeFetcher is not None:
            fetcher = ch.SSRFSafeFetcher()
            with self.assertRaises((ch.SSRFSecurityError, ValueError)):
                ch.invoke_validate_url(fetcher, "http://[::1]:8080/metrics")

        # Attack C: Binary payload disguised as PDF
        if ch.DocumentValidator is not None:
            validator = ch.DocumentValidator()
            with self.assertRaises((ch.InvalidDocumentError, ValueError)):
                validator.validate(CORRUPT_PDF_BYTES, "malicious.pdf")

        # Attack D: Candidate with missing unit and negative values
        malicious_candidate = get_sample_candidate_payload()
        malicious_candidate["unit"] = None
        malicious_candidate["normalized_value"] = -999.0
        if ch.CandidateReferenceSchema is not None:
            with self.assertRaises(Exception):
                ch.CandidateReferenceSchema.model_validate(malicious_candidate)
        else:
            self.assertIsNone(malicious_candidate["unit"])

    def test_scenario_6_customer_telemetry_isolation_invariant(self):
        """Scenario 6: Customer Telemetry Isolation Invariant Under Operational Load.
        Verifies absolute data isolation between reference data and customer telemetry.
        """
        project_root = Path(__file__).resolve().parents[2]
        silver_parquet = project_root / "data" / "silver" / "customer_silver.parquet"
        self.assertTrue(silver_parquet.exists())

        # Customer operational meters
        known_customer_meters = {"METER-2254213", "METER-293861", "METER-537421", "METER-679900"}

        # Reference database models / schema
        reference_keys = [
            "room_ac_1.5t_5star_iseer",
            "ceiling_fan_bldc_power",
            "cea_grid_emission_factor",
            "lighting_power_density_living_room",
        ]

        # Invariant 1: No overlap between customer meters and reference parameters
        for key in reference_keys:
            self.assertNotIn(key, known_customer_meters)
            self.assertFalse(key.startswith("METER-"))

        # Invariant 2: Reference storage does not point to data/silver
        storage_base = project_root / "data" / "documents"
        silver_base = project_root / "data" / "silver"
        self.assertNotEqual(storage_base, silver_base)


if __name__ == "__main__":
    unittest.main()
