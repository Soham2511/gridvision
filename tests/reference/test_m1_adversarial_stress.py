"""Empirical Adversarial Stress Harness for Milestone 1: Document Knowledge Infrastructure.

Stress-tests:
1. StructureAwareExtractor:
   - Realistic multi-page PDF generation and extraction (cross-page sections, clauses, tables, footnotes, provenance).
   - Paragraph retention in clauses and sections (identifying silent paragraph drops).
   - Cross-page table continuations.
2. Complex Table Parsing:
   - Multi-line cells, missing values/empty cells, whitespace alignment vs pipe syntax.
   - Empty rows in table body.
   - Irregular headers, varying column counts, headerless tables.
3. DocumentService Ingestion, Concurrency, and Lifecycle:
   - Identical SHA-256 vs slightly altered documents.
   - Concurrency race conditions (multi-threaded ingestion of identical documents).
   - Ghost checksum index corruption on explicit source_id re-use with altered content.
   - Orphan file leakage on extraction failure.
   - Complete delete lifecycle, storage cleanliness, and re-acquisition.
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.infrastructure.storage.local import LocalFileSystemStorageAdapter
from app.services.reference.document_service import DocumentService
from app.services.reference.exceptions import (
    DocumentValidationError,
    DuplicateDocumentError,
    ExtractionError,
)
from app.services.reference.extractor import StructureAwareExtractor
from app.services.reference.security import DocumentValidator, SSRFSafeFetcher


def build_complex_multipage_pdf() -> bytes:
    """Generate a realistic 5-page standards PDF covering diverse structural features."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # --- Page 1: Regulatory Header, Section 1, Clauses with multi-paragraph text ---
    c.drawString(72, 750, "BEE/S&L/AC/2026-M1 DRAFT REGULATORY STANDARD")
    c.drawString(72, 720, "1.0 SCOPE AND GENERAL DEFINITIONS")
    c.drawString(72, 695, "1.1 Room Air Conditioner Appliance Scope")
    c.drawString(72, 675, "This schedule specifies energy labeling requirements for unitary and split ACs.")
    c.drawString(72, 655, "Subsequent paragraph: It applies to vapor compression systems up to 11 kW rated cooling.")
    c.drawString(72, 635, "1.2 Reference Standards and Normative Directives")
    c.drawString(72, 615, "Compliance requires testing under IS 1391 (Part 1 and Part 2) with amendments.")
    c.drawString(72, 595, "Note 1: Supercedes the 2022 interim guidance for commercial split units.")
    c.showPage()

    # --- Page 2: Section 2, Table 1 with pipes and multi-line notes ---
    c.drawString(72, 750, "2.0 STAR RATING BANDS AND PERFORMANCE METRICS")
    c.drawString(72, 725, "Table 1 - Minimum ISEER Requirements for Variable Speed ACs")
    c.drawString(72, 700, "| Star Rating | Cooling Capacity (W) | Min ISEER | Max ISEER |")
    c.drawString(72, 680, "| 1 Star | 3500 | 3.30 | 3.79 |")
    c.drawString(72, 660, "| 2 Star | 3500 | 3.80 | 4.39 |")
    c.drawString(72, 640, "| 3 Star | 3500 | 4.40 | 4.99 |")
    c.drawString(72, 620, "| 4 Star | 5000 | 5.00 | 5.49 |")
    c.drawString(72, 600, "| 5 Star | 5000 | 5.50 | None |")
    c.drawString(72, 570, "Note 2: Values evaluated at standard test conditions (indoor 27C DB / 19C WB).")
    c.showPage()

    # --- Page 3: Section 3, Table 2 (Part A) ---
    c.drawString(72, 750, "3.0 ANNUAL ENERGY CONSUMPTION BENCHMARKS")
    c.drawString(72, 725, "Table 2 - Baseline Electricity Consumption Benchmarks")
    c.drawString(72, 700, "| Category | Rated Capacity (Tons) | Star Tier | Annual kWh |")
    c.drawString(72, 680, "| Split Inverter | 1.0 Ton | 3 Star | 650.5 |")
    c.drawString(72, 660, "| Split Inverter | 1.5 Ton | 3 Star | 845.2 |")
    c.drawString(72, 640, "| Split Inverter | 1.5 Ton | 5 Star | 620.0 |")
    c.drawString(72, 610, "Table continues on subsequent page...")
    c.showPage()

    # --- Page 4: Table 2 (Part B - Continuation without title) ---
    c.drawString(72, 750, "| Category | Rated Capacity (Tons) | Star Tier | Annual kWh |")
    c.drawString(72, 730, "| Split Inverter | 2.0 Ton | 3 Star | 1100.8 |")
    c.drawString(72, 710, "| Split Inverter | 2.0 Ton | 5 Star | 815.0 |")
    c.drawString(72, 680, "Clause 3.1 Operating Hours Basis")
    c.drawString(72, 660, "Calculations assume an operational duty cycle of 1600 hours per calendar year.")
    c.showPage()

    # --- Page 5: Section 4, Whitespace-aligned Table and Final Footnotes ---
    c.drawString(72, 750, "4.0 TESTING TOLERANCES AND DEVIATIONS")
    c.drawString(72, 720, "Table 3 - Allowable Measurement Uncertainties")
    c.drawString(72, 695, "Parameter               Tolerance       Standard")
    c.drawString(72, 675, "Cooling Capacity        -5%             IS 1391")
    c.drawString(72, 655, "Power Input             +5%             IS 1391")
    c.drawString(72, 635, "ISEER Calculation       -3%             BEE Annex 1")
    c.drawString(72, 600, "* : Deviations exceeding allowable limits constitute non-compliance.")
    c.save()

    return buf.getvalue()


class TestStructureAwareExtractorMultiPageStress(unittest.TestCase):
    """Stress tests for StructureAwareExtractor on multi-page PDFs, hierarchy, and text continuity."""

    def setUp(self) -> None:
        self.extractor = StructureAwareExtractor()

    def test_multipage_pdf_page_count_and_provenance_coverage(self) -> None:
        """Verify 5-page PDF extraction captures all 5 pages, sections, clauses, and provenance."""
        pdf_bytes = build_complex_multipage_pdf()
        source_id = "SRC_BEE_AC_2026"
        doc_id = "BEE/S&L/AC/2026-M1"

        extracted = self.extractor.extract(
            content=pdf_bytes,
            doc_format="pdf",
            source_id=source_id,
            document_identifier=doc_id,
        )

        self.assertEqual(len(extracted["pages"]), 5, "Expected exactly 5 pages extracted")
        self.assertEqual(extracted["metadata"]["page_count"], 5)

        # Check sections extracted across pages
        sec_titles = [s["title"] for s in extracted["sections"]]
        self.assertTrue(any("SCOPE AND GENERAL DEFINITIONS" in t for t in sec_titles))
        self.assertTrue(any("STAR RATING BANDS" in t for t in sec_titles))
        self.assertTrue(any("ANNUAL ENERGY CONSUMPTION" in t for t in sec_titles))
        self.assertTrue(any("TESTING TOLERANCES" in t for t in sec_titles))

        # Check footnotes extracted across pages
        self.assertGreaterEqual(len(extracted["footnotes"]), 2)
        fn_pages = {f["page_number"] for f in extracted["footnotes"]}
        self.assertIn(1, fn_pages)
        self.assertIn(2, fn_pages)

        # Verify provenance map covers all pages
        prov_map = extracted["provenance_map"]
        self.assertGreater(len(prov_map), 10, "Expected robust provenance map entries")
        pages_in_prov = {item["page_number"] for item in prov_map.values()}
        self.assertEqual(pages_in_prov, {1, 2, 3, 4, 5}, "Provenance must span every page")

    def test_multipage_section_cross_page_page_index_association(self) -> None:
        """Inspect whether a section spanning across pages is recorded in the second page's sections list."""
        # On Page 3 Section 3.0 starts; on Page 4 Table 2 continues and Clause 3.1 appears
        pdf_bytes = build_complex_multipage_pdf()
        extracted = self.extractor.extract(pdf_bytes, "pdf", "SRC_TEST", "DOC_TEST")

        page_4 = extracted["pages"][3]  # 0-indexed page 4
        # Clause 3.1 appears on page 4. Let's check whether page_4["sections"] includes the section
        # or if page_4["sections"] is empty because no section header was on page 4
        sec_3 = [s for s in extracted["sections"] if "3.0" in s["title"] or "ANNUAL ENERGY" in s["title"]]
        self.assertTrue(len(sec_3) > 0)
        sec_3_id = sec_3[0]["section_id"]

        # Note the architectural behavior: does page 4 report sec_3_id?
        # In current extractor: page_section_ids only appends on RE_SECTION match on that page
        # This is an important structural observation.
        print(f"\n[Observation] Page 4 sections list: {page_4['sections']}, Section 3 ID: {sec_3_id}")

    def test_multi_paragraph_clause_text_retention(self) -> None:
        """Adversarial test: Does the extractor preserve multiple paragraphs within a single clause?"""
        # In legal and regulatory standards, a clause frequently has multiple paragraphs separated by blank lines
        text_with_multi_para_clause = (
            "1.0 REQUIREMENTS\n"
            "1.1 Energy Efficiency Ratio\n"
            "The minimum seasonal energy efficiency ratio (ISEER) for 5-star ACs shall be 5.00.\n"
            "\n"
            "This efficiency shall be maintained across both 100% and 50% rated cooling capacities.\n"
            "\n"
            "Testing must be performed in a NABL-accredited test laboratory pursuant to BEE schedule.\n"
            "\n"
            "1.2 Sound Power Level Limits\n"
            "Indoor noise levels shall not exceed 42 dB(A).\n"
        )
        extracted = self.extractor.extract(text_with_multi_para_clause.encode("utf-8"), "text", "SRC_1", "DOC_1")
        clauses = extracted["sections"][0]["clauses"]
        cl_1_1 = next((c for c in clauses if c["clause_id"] == "clause_1_1"), None)
        self.assertIsNotNone(cl_1_1, "Clause 1.1 must be extracted")

        # Check if subsequent paragraphs of clause 1.1 were captured or dropped
        has_para_2 = "50% rated cooling capacities" in cl_1_1["text"]
        has_para_3 = "NABL-accredited" in cl_1_1["text"]

        print(f"\n[Clause Multi-Paragraph Test] Clause 1.1 text length: {len(cl_1_1['text'])}")
        print(f"[Clause Multi-Paragraph Test] Retained Para 2: {has_para_2}, Retained Para 3: {has_para_3}")

        # In current extractor, line 450 has `if not next_line: break`,
        # so paragraph 2 and 3 are terminated when a blank line occurs.
        # Check clause provenance map entry
        cl_prov_key = next((k for k in extracted["provenance_map"] if "clause_1_1" in k), None)
        self.assertIsNotNone(cl_prov_key)
        prov_entry = extracted["provenance_map"][cl_prov_key]
        prov_has_para2 = "50% rated cooling capacities" in prov_entry["excerpt"]

        # EMPIRICAL FIX VERIFICATION:
        # Paragraphs 2 and 3 are retained in clause text and in clause provenance
        self.assertTrue(has_para_2, "Paragraph 2 must be retained in clause text")
        self.assertTrue(has_para_3, "Paragraph 3 must be retained in clause text")
        self.assertTrue(prov_has_para2, "Paragraph 2 must be retained in clause provenance")

    def test_section_with_multiple_introductory_paragraphs(self) -> None:
        """Adversarial test: Section with multiple body paragraphs before any clause."""
        text_content = (
            "1.0 GENERAL BACKGROUND\n"
            "First introductory paragraph describing the regulatory mandate under the Energy Conservation Act.\n"
            "\n"
            "Second introductory paragraph detailing the historical transition from fixed to inverter compressors.\n"
            "\n"
            "Third introductory paragraph setting out the scope for manufacturing facilities.\n"
            "\n"
            "1.1 Scope Definition\n"
            "Applicable to all split ACs.\n"
        )
        extracted = self.extractor.extract(text_content.encode("utf-8"), "text", "SRC_INTRO", "DOC_INTRO")
        full_output = json.dumps(extracted)
        has_para1 = "First introductory paragraph" in full_output
        has_para2 = "Second introductory paragraph" in full_output
        has_para3 = "Third introductory paragraph" in full_output

        print(f"\n[Section Body Test] Para 1 captured: {has_para1}, Para 2 captured: {has_para2}, Para 3 captured: {has_para3}")
        self.assertTrue(has_para1)
        self.assertTrue(has_para2)
        self.assertTrue(has_para3)


class TestComplexTableParsingStress(unittest.TestCase):
    """Stress tests for complex table topologies: multi-line cells, missing values, empty rows, irregular headers."""

    def setUp(self) -> None:
        self.extractor = StructureAwareExtractor()

    def test_table_with_multi_line_wrapped_cells(self) -> None:
        """Adversarial test: Table cells spanning multiple lines."""
        table_text = (
            "Table 1 - Metric Definitions\n"
            "| Parameter | Description | Standard Value |\n"
            "| ISEER | Indian Seasonal Energy\n"
            "Efficiency Ratio | 5.0 |\n"
            "| Max Temp | Maximum Outdoor Dry Bulb\n"
            "Operating Temperature | 43 C |\n"
        )
        extracted = self.extractor.extract(table_text.encode("utf-8"), "text", "SRC_TBL", "DOC_TBL")
        tables = extracted.get("tables", [])

        print(f"\n[Table Multi-Line Cells] Tables extracted: {len(tables)}")
        if tables:
            tbl = tables[0]
            print(f"[Table Multi-Line Cells] Headers: {tbl['headers']}")
            print(f"[Table Multi-Line Cells] Rows ({len(tbl['rows'])}): {tbl['rows']}")
            self.assertEqual(len(tbl["rows"]), 2, "Multi-line wrapped cells must be parsed into 2 rows")
            self.assertEqual(tbl["rows"][0], ["ISEER", "Indian Seasonal Energy Efficiency Ratio", "5.0"])
            self.assertEqual(tbl["rows"][1], ["Max Temp", "Maximum Outdoor Dry Bulb Operating Temperature", "43 C"])

    def test_table_with_missing_values_pipe_delimited(self) -> None:
        """Adversarial test: Missing values (empty cells) in pipe-delimited table."""
        table_text = (
            "Table 2 - AC Ratings with Optional Limits\n"
            "| Model Tier | Min Capacity | Max Capacity | Auxiliary Heat |\n"
            "| Tier 1 | 2500 | 3500 | |\n"
            "| Tier 2 | | 5000 | 1000 |\n"
            "| Tier 3 | 5000 | | |\n"
        )
        extracted = self.extractor.extract(table_text.encode("utf-8"), "text", "SRC_TBL", "DOC_TBL")
        self.assertEqual(len(extracted["tables"]), 1)
        tbl = extracted["tables"][0]
        self.assertEqual(len(tbl["headers"]), 4)
        self.assertEqual(len(tbl["rows"]), 3)

        # Check row 1: Auxiliary Heat is empty string ''
        self.assertEqual(tbl["rows"][0][0], "Tier 1")
        self.assertEqual(tbl["rows"][0][1], "2500")
        self.assertEqual(tbl["rows"][0][2], "3500")
        self.assertEqual(tbl["rows"][0][3], "")

        # Check row 2: Min Capacity is empty string ''
        self.assertEqual(tbl["rows"][1][0], "Tier 2")
        self.assertEqual(tbl["rows"][1][1], "")
        self.assertEqual(tbl["rows"][1][2], "5000")
        self.assertEqual(tbl["rows"][1][3], "1000")

    def test_table_with_missing_values_whitespace_delimited(self) -> None:
        """Adversarial test: Missing values in whitespace/tab delimited table."""
        # Col 2 is empty for Tier 2:
        table_text = (
            "Table 3 - Whitespace Table with Missing Values\n"
            "ModelTier    MinCapacity    MaxCapacity    AuxHeat\n"
            "Tier1        2500           3500           500\n"
            "Tier2                       5000           1000\n"
            "Tier3        5000           6000           1500\n"
        )
        extracted = self.extractor.extract(table_text.encode("utf-8"), "text", "SRC_TBL", "DOC_TBL")
        tables = extracted.get("tables", [])
        self.assertGreaterEqual(len(tables), 1)
        tbl = tables[0]
        print(f"\n[Whitespace Missing Values] Headers ({len(tbl['headers'])}): {tbl['headers']}")
        for idx, row in enumerate(tbl["rows"]):
            print(f"[Whitespace Missing Values] Row {idx} ({len(row)} cols): {row}")

        self.assertEqual(len(tbl["rows"][1]), 4, "Whitespace table row with missing value must preserve 4 columns")
        self.assertEqual(tbl["rows"][1], ["Tier2", "", "5000", "1000"])

    def test_table_with_empty_row_in_body(self) -> None:
        """Adversarial test: Table containing an empty line separating logical row groups."""
        table_text = (
            "Table 4 - Grouped Standards\n"
            "| Group | Standard | Value |\n"
            "| G1 | IS 1391-1 | 3.3 |\n"
            "| G1 | IS 1391-2 | 3.8 |\n"
            "\n"
            "| G2 | ISO 5151 | 4.2 |\n"
            "| G2 | ISO 16358 | 5.0 |\n"
        )
        extracted = self.extractor.extract(table_text.encode("utf-8"), "text", "SRC_TBL", "DOC_TBL")
        tables = extracted.get("tables", [])
        total_rows = sum(len(t["rows"]) for t in tables)
        print(f"\n[Empty Row in Table] Tables count: {len(tables)}, Total rows extracted: {total_rows}")
        # The empty line causes while loop to break (line 345: if not tbl_line: break)
        # G2 rows become either a new table without title or dropped
        if len(tables) > 1:
            print(f"[Empty Row in Table] Result: Split into {len(tables)} tables. Second table title: {tables[1]['title']}")
        elif total_rows < 4:
            print("[Empty Row in Table] GAP CONFIRMED: Rows after empty line were completely discarded!")

    def test_irregular_headers_and_column_counts(self) -> None:
        """Adversarial test: Irregular headers (header has 3 cols, rows have 2 and 4 cols)."""
        table_text = (
            "Table 5 - Irregular Column Counts\n"
            "| Header A | Header B | Header C |\n"
            "| Val 1 | Val 2 |\n"
            "| Val 1 | Val 2 | Val 3 | Extra 4 |\n"
        )
        extracted = self.extractor.extract(table_text.encode("utf-8"), "text", "SRC_TBL", "DOC_TBL")
        self.assertEqual(len(extracted["tables"]), 1)
        tbl = extracted["tables"][0]
        self.assertEqual(len(tbl["headers"]), 3)
        self.assertEqual(len(tbl["rows"][0]), 2)
        self.assertEqual(len(tbl["rows"][1]), 4)

        # Provenance mapping check: does it construct provenance for mismatched rows without crashing?
        prov = extracted["provenance_map"]
        r0_key = next((k for k in prov if "tbl_table_5:r0" in k), None)
        r1_key = next((k for k in prov if "tbl_table_5:r1" in k), None)
        self.assertIsNotNone(r0_key)
        self.assertIsNotNone(r1_key)
        print(f"\n[Irregular Columns] Provenance row 0 headers vs values: {len(prov[r0_key]['headers'])} vs {len(prov[r0_key]['row_values'])}")
        print(f"[Irregular Columns] Provenance row 1 headers vs values: {len(prov[r1_key]['headers'])} vs {len(prov[r1_key]['row_values'])}")

    def test_headerless_table(self) -> None:
        """Adversarial test: Table starting immediately with data rows (no column names)."""
        table_text = (
            "Table 6 - Headerless Numerical Lookup\n"
            "| 1.0 | 3.30 | 650 |\n"
            "| 1.5 | 3.80 | 850 |\n"
            "| 2.0 | 4.40 | 1100 |\n"
        )
        extracted = self.extractor.extract(table_text.encode("utf-8"), "text", "SRC_TBL", "DOC_TBL")
        self.assertEqual(len(extracted["tables"]), 1)
        tbl = extracted["tables"][0]
        # In current logic: if not headers: headers = cells
        # So row 1 ('1.0', '3.30', '650') is treated as headers, and rows has only 2 rows!
        print(f"\n[Headerless Table] Headers extracted: {tbl['headers']}")
        print(f"[Headerless Table] Data rows count: {len(tbl['rows'])} (Expected 3 if headers recognized as data)")
        self.assertEqual(tbl["headers"], ["1.0", "3.30", "650"])
        self.assertEqual(len(tbl["rows"]), 2)


class TestDocumentServiceConcurrencyAndDeduplicationStress(unittest.TestCase):
    """Stress tests for DocumentService: concurrency, deduplication, lifecycle, and orphan leakage."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="gridvision_stress_doc_svc_")
        self.storage = LocalFileSystemStorageAdapter(base_dir=self.temp_dir)
        self.validator = DocumentValidator(max_file_size=10 * 1024 * 1024)
        self.extractor = StructureAwareExtractor()
        self.fetcher = SSRFSafeFetcher()

        self.service = DocumentService(
            storage=self.storage,
            fetcher=self.fetcher,
            validator=self.validator,
            extractor=self.extractor,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_identical_sha256_duplicate_rejection(self) -> None:
        """Verify identical SHA-256 is strictly rejected with DuplicateDocumentError."""
        pdf_bytes = build_complex_multipage_pdf()
        meta = {"issuing_organization": "BEE", "document_identifier": "BEE-AC-2026"}

        rec1 = self.service.acquire_from_file(meta, "bee_standard.pdf", pdf_bytes)
        self.assertIsNotNone(rec1)
        sha = rec1["content_checksum_sha256"]

        with self.assertRaises(DuplicateDocumentError) as cm:
            self.service.acquire_from_file(meta, "bee_standard_copy.pdf", pdf_bytes)

        self.assertEqual(cm.exception.checksum, sha)
        self.assertEqual(cm.exception.existing_source_id, rec1["source_id"])

    def test_slightly_altered_document_ingestion(self) -> None:
        """Verify slightly altered document (1-byte difference) is accepted with distinct SHA-256."""
        pdf_bytes = build_complex_multipage_pdf()
        # Create altered content by modifying 1 character in the text stream
        altered_bytes = pdf_bytes + b"\n% amendment 2026.1\n"

        meta = {"issuing_organization": "BEE", "document_identifier": "BEE-AC-2026"}
        rec1 = self.service.acquire_from_file(meta, "v1.pdf", pdf_bytes)
        rec2 = self.service.acquire_from_file(meta, "v2.pdf", altered_bytes)

        self.assertNotEqual(rec1["source_id"], rec2["source_id"])
        self.assertNotEqual(rec1["content_checksum_sha256"], rec2["content_checksum_sha256"])
        self.assertEqual(len(self.service.list_sources()), 2)

    def test_explicit_source_id_reuse_with_altered_document_ghost_checksum(self) -> None:
        """Adversarial test: Explicit source_id reuse with altered content corrupts checksum index."""
        pdf_v1 = build_complex_multipage_pdf()
        pdf_v2 = pdf_v1 + b"\n% amendment\n"

        meta_v1 = {
            "source_id": "SRC_FIXED_ID",
            "issuing_organization": "BEE",
            "document_identifier": "BEE-2026",
        }
        meta_v2 = {
            "source_id": "SRC_FIXED_ID",
            "issuing_organization": "BEE",
            "document_identifier": "BEE-2026-REV",
        }

        rec1 = self.service.acquire_from_file(meta_v1, "doc_v1.pdf", pdf_v1)
        sha_v1 = rec1["content_checksum_sha256"]

        # Ingest altered version with SAME source_id
        rec2 = self.service.acquire_from_file(meta_v2, "doc_v2.pdf", pdf_v2)
        sha_v2 = rec2["content_checksum_sha256"]

        self.assertNotEqual(sha_v1, sha_v2)
        self.assertEqual(rec2["source_id"], "SRC_FIXED_ID")

        # Now test index consistency: what does find_by_checksum(sha_v1) return?
        source_by_old_sha = self.service.find_by_checksum(sha_v1)
        print(f"\n[Ghost Checksum Test] Lookup by old SHA-256 returned: {source_by_old_sha is not None}")
        self.assertIsNone(source_by_old_sha, "Old SHA-256 must be purged from index upon source update")

    def test_concurrent_ingestion_race_condition(self) -> None:
        """Adversarial stress test: Concurrent acquisition of the exact same document.

        Checks whether race conditions allow multiple threads to bypass duplicate detection
        and create duplicate source entries.
        """
        pdf_bytes = build_complex_multipage_pdf()
        meta = {"issuing_organization": "CEA", "document_identifier": "CEA-CONCURRENT-2026"}

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        results = []
        errors = []

        def worker(thread_idx: int) -> None:
            barrier.wait()  # Synchronize start to maximize race probability
            try:
                rec = self.service.acquire_from_file(
                    meta,
                    f"doc_thread_{thread_idx}.pdf",
                    pdf_bytes,
                    raise_on_duplicate=True,
                )
                results.append((thread_idx, rec))
            except Exception as exc:
                errors.append((thread_idx, exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        duplicate_errors = [e for e in errors if isinstance(e[1], DuplicateDocumentError)]
        print(f"\n[Concurrency Stress Test] Threads: {num_threads}")
        print(f"[Concurrency Stress Test] Successful acquisitions: {len(results)}")
        print(f"[Concurrency Stress Test] DuplicateDocumentError raised: {len(duplicate_errors)}")
        print(f"[Concurrency Stress Test] Other errors: {[type(e[1]).__name__ for e in errors if not isinstance(e[1], DuplicateDocumentError)]}")

        # In a fully thread-safe system with duplicate locking: exactly 1 succeeds, 9 fail with DuplicateDocumentError
        sources_in_registry = self.service.list_sources()
        print(f"[Concurrency Stress Test] Sources registered in service: {len(sources_in_registry)}")
        self.assertEqual(len(results), 1, "Expected exactly 1 successful ingestion under lock")
        self.assertEqual(len(duplicate_errors), num_threads - 1, "Expected 9 DuplicateDocumentErrors")
        self.assertEqual(len(sources_in_registry), 1, "Expected exactly 1 source registered")

    def test_orphan_file_leakage_on_extraction_failure(self) -> None:
        """Adversarial test: If extraction raises ExtractionError, is the original file leaked on disk?"""
        # We craft content that passes DocumentValidator (valid text/json) but fails during extractor.extract()
        content = b"{\"key\": \"valid_json_for_validator\"}"
        meta = {"issuing_organization": "BIS", "document_identifier": "BIS-CRASH-TEST"}

        with patch.object(self.extractor, "extract", side_effect=ExtractionError("Simulated parser crash")):
            with self.assertRaises(ExtractionError):
                self.service.acquire_from_file(meta, "crash_test.json", content)

        # Check if original file was left in storage
        orig_dir = Path(self.temp_dir) / "original"
        subdirs = list(orig_dir.glob("*"))
        print(f"\n[Orphan Leakage Test] Subdirectories in original/ after crash: {[s.name for s in subdirs]}")

        # Check if files exist inside
        orphan_files = list(orig_dir.rglob("crash_test.json"))
        print(f"[Orphan Leakage Test] Orphan files found: {orphan_files}")
        self.assertEqual(len(orphan_files), 0, "Original file must be deleted upon extraction failure")

    def test_complete_source_lifecycle_and_reacquisition(self) -> None:
        """Verify acquire -> retrieve -> delete -> re-acquire lifecycle."""
        pdf_bytes = build_complex_multipage_pdf()
        meta = {"issuing_organization": "BEE", "document_identifier": "BEE-LIFECYCLE-1"}

        rec = self.service.acquire_from_file(meta, "lifecycle.pdf", pdf_bytes)
        source_id = rec["source_id"]
        sha = rec["content_checksum_sha256"]

        orig_path = rec["original_file_path"]
        ext_path = rec["extracted_file_path"]

        # Verify retrieval
        self.assertEqual(self.service.get_original_bytes(source_id), pdf_bytes)
        self.assertIsNotNone(self.service.get_extracted_structure(source_id))

        # Delete source
        deleted = self.service.delete_source(source_id)
        self.assertTrue(deleted)

        # Verify deregistered
        self.assertIsNone(self.service.get_source(source_id))
        self.assertIsNone(self.service.find_by_checksum(sha))
        self.assertFalse(self.storage.exists(orig_path))
        self.assertFalse(self.storage.exists(ext_path))

        # Re-acquisition of same content must now succeed without DuplicateDocumentError
        rec_reacquired = self.service.acquire_from_file(meta, "lifecycle_reacquired.pdf", pdf_bytes)
        self.assertIsNotNone(rec_reacquired)
        self.assertEqual(rec_reacquired["content_checksum_sha256"], sha)
        self.assertEqual(len(self.service.list_sources()), 1)


if __name__ == "__main__":
    unittest.main()
