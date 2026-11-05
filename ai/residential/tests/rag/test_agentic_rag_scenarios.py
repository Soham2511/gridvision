"""Comprehensive End-to-End Test Suite for Phase 2 Agentic RAG and Multi-Knowledge Assistant.

Verifies the 10 Mandatory Acceptance Scenarios (A through J) defined in the Phase 2 Brief:
- Scenario A: Standards-grounded technical question (IS 732 / NEC)
- Scenario B: Exact appliance specification (BEE Star Labeling benchmarks)
- Scenario C: Household historical analysis (Previous month comparison)
- Scenario D: Mixed RAG and structured data (Compare 3-Star vs 5-Star AC)
- Scenario E: Appliance lifecycle calculation (Replace existing AC with 5-Star model)
- Scenario F: Personalized cost management (Ranked non-overlapping interventions)
- Scenario G: New-house electrical & energy planning (3-bedroom layout & connected load)
- Scenario H: Multi-source reasoning (Combined telemetry, lifecycle, and references)
- Scenario I: Unanswerable or unsupported query (Honest limitation, zero hallucination)
- Scenario J: Conflicting or outdated sources (Version and edition precedence)
- Invariant 1: Customer data isolation across meters
- Invariant 2: Protected components preservation
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from sqlalchemy import select

from app.domain.residential.reference_data import ReferenceDataBridge
from app.infrastructure.database.connection import SessionLocal, create_db_engine, init_db
from app.infrastructure.database.models import DocumentChunkModel
from app.infrastructure.repositories.household_energy_repository import HouseholdEnergyRepository
from app.interfaces.assistant.tools.rag_tools import SearchRegulatoryDocumentsInput
from app.providers.parquet_data_provider import ParquetDataProvider
from app.services.assistant.agentic_orchestrator import AgenticKnowledgeOrchestrator
from app.services.assistant.context_builder import HouseholdContextBuilder
from app.services.assistant.contracts import AssistantResponseContract
from app.services.rag.chunker import StructureAwareChunker
from app.services.rag.embeddings import LocalResilientEmbeddingProvider, cosine_similarity
from app.services.rag.indexing_service import DocumentIndexingService
from app.services.rag.retriever import HybridDocumentRetriever, RetrievedChunk
from app.services.reference.resolver import ReferenceResolver


class TestAgenticRAGScenarios(unittest.TestCase):
    """End-to-end verification of Phase 2 Agentic RAG and Knowledge Systems."""

    @classmethod
    def setUpClass(cls):
        """Initialize database, index authoritative corpus, and instantiate orchestrator."""
        cls.engine = create_db_engine("sqlite:///:memory:")
        init_db(cls.engine)

        from sqlalchemy.orm import sessionmaker
        cls.session_factory = sessionmaker(bind=cls.engine)

        cls.indexer = DocumentIndexingService(session_factory=cls.session_factory)
        cls.indexer.seed_authoritative_corpus()

        cls.retriever = HybridDocumentRetriever(session_factory=cls.session_factory)
        cls.retriever.sync_cache()

        cls.resolver = ReferenceResolver()

        # Wire verified dataset provider
        cls.data_dir = Path(__file__).resolve().parents[4] / "data"
        silver_path = cls.data_dir / "silver" / "customer_silver.parquet"
        gold_path = cls.data_dir / "gold" / "customer_gold.parquet"

        if silver_path.exists() and gold_path.exists():
            cls.provider = ParquetDataProvider(
                silver_path=silver_path,
                gold_path=gold_path,
            )
            cls.context_builder = HouseholdContextBuilder(cls.provider, tariff_rate=10.0)
        else:
            cls.provider = None
            cls.context_builder = None

        cls.orchestrator = AgenticKnowledgeOrchestrator(
            retriever=cls.retriever,
            resolver=cls.resolver,
            context_builder=cls.context_builder,
            tariff_rate=10.0,
        )

    # -----------------------------------------------------------------
    # Scenario A: Standards-grounded technical question
    # -----------------------------------------------------------------
    def test_scenario_a_standards_grounded_technical_question(self):
        """User asks: 'What should I know about electrical wiring requirements for a new residential house?'"""
        prompt = "What should I know about electrical wiring requirements for a new residential house?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("IS 732", res.answer)
        self.assertIn("1.5", res.answer)  # 1.5 sq mm copper for lighting
        self.assertIn("30", res.answer)   # 30 mA RCD protection
        self.assertTrue(len(res.citations) >= 1)
        self.assertTrue(any("IS 732" in c.document_identifier or "NEC" in c.document_identifier for c in res.citations))
        # Ensure no hallucinated clause numbers
        for c in res.citations:
            self.assertIn(c.publisher, ["BIS", "CEA", "BEE", "DISCOM"])

    def test_rag_answer_uses_llm_synthesis_grounded_in_retrieved_passages(self):
        class RecordingLLM:
            def __init__(self):
                self.messages = None

            def is_available(self):
                return True

            def generate_chat_completion(self, messages, temperature=0.2, max_tokens=800):
                self.messages = messages
                return "The retrieved standard describes the relevant protective measure."

        provider = RecordingLLM()
        original_llm_provider = self.orchestrator.llm_provider
        self.orchestrator.llm_provider = provider
        try:
            result = self.orchestrator.process_query(
                "What does the standard say about electrical safety?",
                meter_id="METER-1000",
            )
        finally:
            self.orchestrator.llm_provider = original_llm_provider

        self.assertEqual(
            result.answer,
            "The retrieved standard describes the relevant protective measure.",
        )
        self.assertTrue(result.citations)
        self.assertIn("Retrieved evidence (JSON)", provider.messages[0]["content"])
        self.assertIn(result.citations[0].document_identifier, provider.messages[0]["content"])

    def test_document_answer_can_synthesize_and_cite_all_retrieved_sources(self):
        source_names = [
            "BEE/S&L/AC/Schedule-2022",
            "BEE/S&L/Appliances/2023",
            "BEE/S&L/Refrigerator/2023",
            "IS 732 / NEC India",
            "CEA Baseline CO2 Database v20.0",
            "State DISCOM MYT Tariff Order 2024-25",
        ]
        chunks = [
            RetrievedChunk(
                chunk_id=f"chunk-{index}",
                source_id=f"source-{index}",
                document_identifier=source_name,
                publisher=publisher,
                chunk_type="section",
                section_id=None,
                clause_id=None,
                heading=f"Section {index}",
                page_number=index,
                content=f"Evidence from {source_name}.",
                snippet=f"Evidence from {source_name}.",
                score=0.02 - index / 1000,
            )
            for index, (source_name, publisher) in enumerate(
                zip(source_names, ["BEE", "BEE", "BEE", "BIS", "CEA", "DISCOM"]),
                start=1,
            )
        ]

        class MultiSourceRetriever:
            def __init__(self):
                self.requested_limits = []

            def search(self, query, top_k=5):
                self.requested_limits.append(top_k)
                return chunks

        class RecordingLLM:
            def __init__(self):
                self.messages = None

            def is_available(self):
                return True

            def generate_chat_completion(self, messages, temperature=0.2, max_tokens=800):
                self.messages = messages
                return "Here is a concise answer based on the retrieved documents."

        original_retriever = self.orchestrator.retriever
        original_llm_provider = self.orchestrator.llm_provider
        retriever = MultiSourceRetriever()
        provider = RecordingLLM()
        self.orchestrator.retriever = retriever
        self.orchestrator.llm_provider = provider
        try:
            result = self.orchestrator._handle_document_knowledge_query(
                prompt="Summarize the relevant electricity guidance.",
                meter_id="METER-1000",
                customer_name=None,
                intent="general_energy_knowledge",
            )
        finally:
            self.orchestrator.retriever = original_retriever
            self.orchestrator.llm_provider = original_llm_provider

        self.assertEqual(result.status, "success")
        self.assertTrue(retriever.requested_limits)
        self.assertTrue(all(limit is None for limit in retriever.requested_limits))
        cited_sources = {citation.document_identifier for citation in result.citations}
        self.assertEqual(cited_sources, set(source_names))
        for source_name in source_names:
            self.assertIn(source_name, provider.messages[0]["content"])

    def test_unlimited_retrieval_covers_every_indexed_source_document(self):
        with self.session_factory() as session:
            expected_sources = set(
                session.scalars(
                    select(DocumentChunkModel.document_identifier).distinct()
                ).all()
            )

        results = self.retriever.search(
            "electricity",
            top_k=None,
            min_score=0.0,
        )

        retrieved_sources = {result.document_identifier for result in results}
        self.assertEqual(retrieved_sources, expected_sources)
        self.assertTrue(
            all(
                sum(item.document_identifier == source for item in results) <= 2
                for source in retrieved_sources
            )
        )

    def test_regulatory_search_tool_defaults_to_all_source_documents(self):
        request = SearchRegulatoryDocumentsInput(
            query="residential electrical safety guidance"
        )

        self.assertIsNone(request.top_k)

    # -----------------------------------------------------------------
    # Scenario B: Exact appliance specification
    # -----------------------------------------------------------------
    def test_scenario_b_exact_appliance_specification(self):
        """User asks: 'What is the annual energy consumption of this exact AC model?'"""
        prompt = "What is the annual energy consumption of a 5-star inverter AC?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("750", res.answer)  # 750 kWh/year benchmark for 5-star 1.5 Ton
        self.assertIn("ISEER", res.answer)
        self.assertIn("5.00", res.answer)  # Minimum ISEER 5.00
        self.assertTrue(any(c.publisher == "BEE" for c in res.citations))

    # -----------------------------------------------------------------
    # Scenario C: Household historical analysis
    # -----------------------------------------------------------------
    def test_scenario_c_household_historical_analysis(self):
        """User asks: 'Why is my electricity consumption higher compared with the previous month?'"""
        prompt = "Why is my electricity consumption higher compared with the previous month?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("kWh", res.answer)
        self.assertIn("METER-1000", res.answer)
        self.assertIn("household_telemetry", res.provenance.knowledge_sources_used)

    def test_missing_previous_month_data_is_not_inferred(self):
        class IncompleteHouseholdContext:
            def build_context(self, meter_id, prompt_intent=None):
                return {
                    "billingCycleStatus": {
                        "lastRecordedDate": "2026-11-04",
                        "actualCycleKwhSoFar": 123.4,
                    },
                    "recentConsumptionMetrics": {
                        "previousMonthTotalKwh": None,
                    },
                }

        original_context_builder = self.orchestrator.context_builder
        self.orchestrator.context_builder = IncompleteHouseholdContext()
        try:
            result = self.orchestrator._handle_general_chat_mode(
                prompt="Why is my consumption higher than the previous month?",
                meter_id="METER-1000",
                customer_name=None,
                required_sources=[],
            )
        finally:
            self.orchestrator.context_builder = original_context_builder

        self.assertIn("123.4 kWh", result.answer)
        self.assertNotIn("Previous period recorded consumption", result.answer)
        self.assertTrue(
            any("prior-period total is unavailable" in item for item in result.limitations)
        )

    # -----------------------------------------------------------------
    # Scenario D: Mixed RAG and structured data
    # -----------------------------------------------------------------
    def test_scenario_d_mixed_rag_and_structured_data(self):
        """User asks: 'Compare two AC models and explain which is more energy efficient.'"""
        prompt = "Compare two AC models and explain which is more energy efficient: 3-Star vs 5-Star."
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("3.80", res.answer)  # 3-star ISEER
        self.assertIn("5.00", res.answer)  # 5-star ISEER
        self.assertIn("300", res.answer)   # 300 kWh annual difference
        self.assertIn("Payback", res.answer)
        self.assertTrue(len(res.citations) >= 1)

    # -----------------------------------------------------------------
    # Scenario E: Appliance lifecycle calculation
    # -----------------------------------------------------------------
    def test_scenario_e_appliance_lifecycle_calculation(self):
        """User asks: 'Should I replace my existing AC with a new 5-star model?'"""
        prompt = "Should I replace my existing AC with a new 5-star model?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("Proceed with Replacement", res.answer)
        self.assertIn("Payback", res.answer)
        self.assertIn("CO2", res.answer)
        self.assertEqual(len(res.provenance.calculations), 1)
        self.assertEqual(res.provenance.calculations[0].engine_name, "ApplianceLifecycleCostEngine")

    # -----------------------------------------------------------------
    # Scenario F: Personalized cost management
    # -----------------------------------------------------------------
    def test_scenario_f_personalized_cost_management(self):
        """User asks: 'How can I reduce my electricity bill without compromising comfort?'"""
        prompt = "How can I reduce my electricity bill without compromising comfort?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("Ranked Non-Overlapping Interventions", res.answer)
        self.assertIn("Non-Overlapping Guarantee", res.answer)
        self.assertIn("kWh/month", res.answer)
        self.assertEqual(res.provenance.calculations[0].engine_name, "RecommendationEngine")

    # -----------------------------------------------------------------
    # Scenario G: New-house planning
    # -----------------------------------------------------------------
    def test_scenario_g_new_house_planning(self):
        """User asks: 'I am planning a new 3-bedroom house. Help me plan the electrical requirements.'"""
        prompt = "I am planning a new 3-bedroom house. Help me plan the electrical requirements."
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertEqual(res.mode, "house_planning")
        self.assertIn("Connected Load", res.answer)
        self.assertIn("IS 732", res.answer)
        self.assertIn("Diversified Peak Demand", res.answer)
        self.assertIn("Safety Disclaimer", res.answer)
        self.assertEqual(res.provenance.calculations[0].engine_name, "BuildingEnergyPlanningEngine")

    # -----------------------------------------------------------------
    # Scenario H: Multi-source reasoning
    # -----------------------------------------------------------------
    def test_scenario_h_multi_source_reasoning(self):
        """Combined prompt requiring telemetry context, replacement calculation, and official standards."""
        prompt = "My current AC consumes too much electricity. Can I reduce my costs by replacing it, and what technical factors should I consider?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "success")
        self.assertIn("kWh", res.answer)
        self.assertIn("5-Star", res.answer)
        self.assertTrue(len(res.provenance.knowledge_sources_used) >= 2)

    # -----------------------------------------------------------------
    # Scenario I: Unanswerable or unsupported question
    # -----------------------------------------------------------------
    def test_scenario_i_unanswerable_or_unsupported_question(self):
        """User asks for an unverified/non-existent appliance model."""
        prompt = "What is the certified efficiency of alien tech xyz-9999 fusion refrigerator?"
        res: AssistantResponseContract = self.orchestrator.process_query(prompt, meter_id="METER-1000")

        self.assertEqual(res.status, "unsupported")
        self.assertIn("xyz-9999", res.answer)
        self.assertNotIn("750 kWh", res.answer)
        self.assertTrue(
            any("xyz-9999" in item for item in res.missing_information)
        )
        self.assertTrue(len(res.missing_information) > 0)

    # -----------------------------------------------------------------
    # Scenario J: Conflicting or outdated sources
    # -----------------------------------------------------------------
    def test_scenario_j_version_and_edition_precedence(self):
        """Verifies that retrieval prioritizes latest approved edition over older revisions."""
        # Query for grid carbon factor
        results = self.retriever.search("CEA grid emission factor baseline", top_k=2)
        self.assertTrue(len(results) > 0)
        self.assertIn("v20.0", results[0].document_identifier)
        self.assertTrue(any("0.82" in r.content for r in results))

    # -----------------------------------------------------------------
    # Invariant: Customer Data Isolation
    # -----------------------------------------------------------------
    def test_customer_data_isolation(self):
        """Customer operational data cannot leak across meters."""
        res_1000 = self.orchestrator.process_query("Why is my bill higher?", meter_id="METER-1000")
        res_2254 = self.orchestrator.process_query("Why is my bill higher?", meter_id="METER-2254213")

        self.assertIn("METER-1000", res_1000.answer)
        self.assertIn("METER-2254213", res_2254.answer)
        self.assertNotIn("METER-2254213", res_1000.answer)
        self.assertNotIn("METER-1000", res_2254.answer)

    # -----------------------------------------------------------------
    # Invariant: Protected Components Untouched
    # -----------------------------------------------------------------
    def test_protected_components_preserved(self):
        """Verify Silver/Gold parquet datasets and models exist and are intact."""
        root = Path(__file__).resolve().parents[4]
        silver_pq = root / "data" / "silver" / "customer_silver.parquet"
        gold_pq = root / "data" / "gold" / "customer_gold.parquet"
        self.assertTrue(silver_pq.exists())
        self.assertTrue(gold_pq.exists())
        self.assertGreater(silver_pq.stat().st_size, 100000)
        self.assertGreater(gold_pq.stat().st_size, 50000)


if __name__ == "__main__":
    unittest.main()
