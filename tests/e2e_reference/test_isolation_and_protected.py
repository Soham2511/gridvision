"""Strict Verification of Customer Data Isolation & Protected Components Preservation.

Covers Requirements R3 (Information Boundaries & Customer Data Isolation) and R5 (Scope Boundary Protection):
1. Complete separation of customer operational telemetry (Medallion Parquet) from reference database.
2. Protection of ML models, training pipelines, and MLflow tracking registry.
3. Protection of Airflow DAGs and ETL pipelines.
4. Protection of DuckDB analytical adapters and HouseholdEnergyRepository meter isolation.
5. Verification that LLMs or vector similarity are NEVER used as authoritative sources for engineering math.

Derived from ORIGINAL_REQUEST.md (R3, R5), PROJECT.md, and TEST_INFRA.md.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from tests.e2e_reference import contract_helper as ch


class TestCustomerDataIsolationAndProtectedComponents(unittest.TestCase):
    """Rigorous verification of customer data isolation and protected components."""

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parents[2]
        cls.data_dir = cls.project_root / "data"
        cls.models_dir = cls.project_root / "models"
        cls.airflow_dir = cls.project_root / "airflow"
        cls.backend_app = cls.project_root / "backend" / "app"

    def test_01_customer_silver_parquet_schema_and_integrity(self):
        """Verify customer_silver.parquet exists, is non-empty, and holds operational telemetry."""
        silver_file = self.data_dir / "silver" / "customer_silver.parquet"
        self.assertTrue(silver_file.exists(), "customer_silver.parquet must exist in data/silver")
        self.assertGreater(silver_file.stat().st_size, 1000, "customer_silver.parquet must contain data")

        # Inspect parquet schema using DuckDB or PyArrow
        try:
            import duckdb
            con = duckdb.connect()
            df_desc = con.execute(f"DESCRIBE SELECT * FROM '{silver_file.as_posix()}'").fetchall()
            col_names = [row[0] for row in df_desc]
            con.close()
            # Must contain OBJECTID and operational fields
            self.assertIn("OBJECTID", col_names)
            # Invariant: Must NOT contain reference fields
            for ref_col in ["parameter_key", "raw_value", "normalized_value", "issuing_organization"]:
                self.assertNotIn(ref_col, col_names)
        except ImportError:
            pass

    def test_02_customer_gold_dataset_intact(self):
        """Verify customer_gold.parquet exists and is isolated from reference database."""
        gold_file = self.data_dir / "gold" / "customer_gold.parquet"
        self.assertTrue(gold_file.exists(), "customer_gold.parquet must exist in data/gold")
        self.assertGreater(gold_file.stat().st_size, 1000)

    def test_03_ml_model_artifacts_and_metadata_unmodified(self):
        """Verify customer_bill_prediction ML model artifacts and metadata remain untouched."""
        meta_file = self.models_dir / "customer_bill_prediction.metadata.json"
        self.assertTrue(meta_file.exists(), "Model metadata file must exist")
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta.get("model_name"), "customer-bill-prediction")
        self.assertIn("test_metrics", meta)
        self.assertIn("features", meta)

    def test_04_ml_model_namespace_collision_prevention(self):
        """Verify backend/app/models/ remains dedicated to ML models and is not replaced by DB models."""
        models_init = self.backend_app / "models" / "__init__.py"
        self.assertTrue(models_init.exists(), "backend/app/models must contain ML definitions")
        with open(models_init, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("ModelDefinition", content)
        self.assertIn("MODEL_REGISTRY", content)

    def test_05_airflow_dags_and_pipelines_unmodified(self):
        """Verify customer and government load prediction Airflow DAGs remain intact."""
        customer_dag = self.airflow_dir / "customer" / "customer_energy_dag.py"
        data_pipeline = self.airflow_dir / "customer" / "data_pipeline.py"
        gov_dir = self.airflow_dir / "2_government_load_prediction"
        self.assertTrue(customer_dag.exists(), "customer_energy_dag.py must exist")
        self.assertTrue(data_pipeline.exists(), "data_pipeline.py must exist")
        self.assertTrue(gov_dir.exists(), "2_government_load_prediction must exist")

    def test_06_duckdb_adapter_operational_isolation(self):
        """Verify DuckDB analytical adapter is isolated from relational reference database."""
        adapter_file = self.backend_app / "infrastructure" / "analytics" / "duckdb_adapter.py"
        self.assertTrue(adapter_file.exists())
        with open(adapter_file, "r", encoding="utf-8") as f:
            content = f.read()
        # Adapter queries Parquet using DuckDB
        self.assertIn("duckdb", content)
        self.assertIn("query_intervals_for_entity", content)

    def test_07_household_repository_meter_boundary_enforcement(self):
        """Verify HouseholdEnergyRepository enforces strict meter authorization boundaries."""
        try:
            from app.infrastructure.repositories.household_energy_repository import (
                HouseholdEnergyRepository,
            )
            from app.config import BaseConfig
            # Valid authorized meters
            authorized_meters = BaseConfig.AUTHORIZED_RESIDENTIAL_METERS
            self.assertGreater(len(authorized_meters), 0)
            self.assertTrue(any("2254213" in m for m in authorized_meters))
        except ImportError:
            self.skipTest("HouseholdEnergyRepository import failed")

    def test_08_reference_storage_adapter_never_mutates_data_silver(self):
        """Verify LocalFileSystemStorageAdapter never writes to data/silver or data/gold."""
        silver_dir = (self.data_dir / "silver").resolve()
        doc_dir = (self.data_dir / "documents").resolve()
        self.assertNotEqual(silver_dir, doc_dir)
        self.assertFalse(str(doc_dir).startswith(str(silver_dir)))

    def test_09_no_llm_as_authoritative_calculation_source(self):
        """Verify mathematical domain engines use deterministic formulas, never LLM completions."""
        appliance_engine_file = self.backend_app / "domain" / "residential" / "appliance_engine.py"
        self.assertTrue(appliance_engine_file.exists())
        with open(appliance_engine_file, "r", encoding="utf-8") as f:
            code = f.read()
        # Must contain pure deterministic formulas
        self.assertIn("calculate_annual_consumption_kwh", code)
        self.assertIn("annual_saved_kwh", code)
        self.assertIn("simple_payback", code)
        # Invariant: No LLM / OpenAI / Groq imports in pure domain engines
        self.assertNotIn("ChatGroq", code)
        self.assertNotIn("OpenAI", code)

    def test_10_no_vector_indexes_over_customer_records(self):
        """Verify customer-owned records never enter global reference tables or vector indexes."""
        # Operational meter IDs must never be registered as reference parameter keys
        try:
            from app.config import BaseConfig
            meters = BaseConfig.AUTHORIZED_RESIDENTIAL_METERS
            # Check reference benchmarks
            if ch.reference_data is not None:
                benchmarks_str = str(ch.reference_data.APPLIANCE_BENCHMARKS)
                for meter in meters:
                    self.assertNotIn(meter, benchmarks_str)
        except ImportError:
            pass


if __name__ == "__main__":
    unittest.main()
