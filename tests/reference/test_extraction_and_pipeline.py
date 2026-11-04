"""Unit and integration tests for Structure-Aware Extraction and Document Acquisition Pipeline."""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

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


def generate_sample_pdf_bytes() -> bytes:
    """Helper to generate a realistic 2-page standards PDF with sections, clauses, tables, and notes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)

    # Page 1: Scope, Clauses, Table 1, Note 1
    c.drawString(72, 750, "1.0 SCOPE AND APPLICABILITY")
    c.drawString(72, 730, "1.1 General Equipment Scope")
    c.drawString(72, 710, "This standard applies to variable speed room air conditioners up to 10.5 kW capacity.")
    c.drawString(72, 680, "Table 1 - Star Rating Bands for Inverter Room ACs")
    c.drawString(72, 660, "| Star Rating | Min ISEER | Max ISEER |")
    c.drawString(72, 640, "| 1 Star | 3.30 | 3.79 |")
    c.drawString(72, 620, "| 2 Star | 3.80 | 4.39 |")
    c.drawString(72, 600, "| 5 Star | 5.00 | None |")
    c.drawString(72, 570, "Note 1: Valid for appliances manufactured after 1st January 2024.")
    c.showPage()

    # Page 2: Testing and Metric Requirements
    c.drawString(72, 750, "2.0 COMPLIANCE AND TESTING METHODOLOGY")
    c.drawString(72, 730, "2.1 Test Standard Harmonization")
    c.drawString(72, 710, "Testing shall be conducted strictly in accordance with IS 1391 Part 2 Annexure B.")
    c.drawString(72, 680, "Clause 2.2 Duty Factor and Operating Hours")
    c.drawString(72, 660, "The standard baseline operating duty factor shall be assumed as 1600 annual operating hours.")
    c.save()

    return buf.getvalue()


class TestStructureAwareExtractor(unittest.TestCase):
    """Verifies StructureAwareExtractor with PDF, plain text, and JSON documents."""

    def setUp(self) -> None:
        self.extractor = StructureAwareExtractor()

    def test_extract_pdf_pages_sections_clauses_tables_footnotes_provenance(self) -> None:
        """Verify extraction from a genuine multi-page PDF document."""
        pdf_bytes = generate_sample_pdf_bytes()
        source_id = "SRC_BEE_AC_2024"
        doc_id = "BEE/S&L/AC/2024"

        result = self.extractor.extract(
            content=pdf_bytes,
            doc_format="pdf",
            source_id=source_id,
            document_identifier=doc_id,
        )

        # 1. Structure envelope
        self.assertEqual(result["source_id"], source_id)
        self.assertEqual(result["document_identifier"], doc_id)
        self.assertEqual(len(result["pages"]), 2)

        # 2. Sections
        section_titles = [s["title"] for s in result["sections"]]
        self.assertIn("SCOPE AND APPLICABILITY", section_titles)
        self.assertIn("COMPLIANCE AND TESTING METHODOLOGY", section_titles)

        # 3. Clauses
        all_clauses = [c for s in result["sections"] for c in s["clauses"]]
        clause_ids = [c["clause_id"] for c in all_clauses]
        self.assertIn("clause_1_1", clause_ids)
        self.assertIn("clause_2_1", clause_ids)

        # 4. Tables
        self.assertTrue(len(result["tables"]) >= 1)
        tbl = result["tables"][0]
        self.assertEqual(tbl["page_number"], 1)
        self.assertIn("Star Rating", tbl["headers"])
        self.assertIn("Min ISEER", tbl["headers"])
        self.assertEqual(len(tbl["rows"]), 3)
        self.assertEqual(tbl["rows"][0][0], "1 Star")
        self.assertEqual(tbl["rows"][0][1], "3.30")
        self.assertEqual(tbl["rows"][2][0], "5 Star")
        self.assertEqual(tbl["rows"][2][1], "5.00")

        # 5. Footnotes
        self.assertTrue(len(result["footnotes"]) >= 1)
        fn = result["footnotes"][0]
        self.assertEqual(fn["page_number"], 1)
        self.assertIn("Valid for appliances", fn["text"])

        # 6. Provenance Map
        prov = result["provenance_map"]
        self.assertTrue(len(prov) > 0)

        # Check section provenance
        sec_prov_keys = [k for k in prov if "sec_" in k]
        self.assertTrue(len(sec_prov_keys) >= 2)
        self.assertIn("SCOPE", prov[sec_prov_keys[0]]["excerpt"])

        # Check table row provenance
        tbl_row_keys = [k for k in prov if ":r0" in k]
        self.assertTrue(len(tbl_row_keys) >= 1)
        self.assertIn("3.30", prov[tbl_row_keys[0]]["excerpt"])

    def test_extract_text_document_with_form_feed(self) -> None:
        """Verify extraction from paginated plain text with form-feed page delimiters."""
        text_content = (
            "1.0 CEA EMISSION FACTORS\n"
            "1.1 Grid Weighted Average\n"
            "The national baseline grid emission factor is 0.82 kg CO2 per kWh.\n"
            "\f"
            "2.0 RENEWABLE NORMS\n"
            "2.1 Solar PV Benchmark\n"
            "MNRE benchmark capacity yields 1450 kWh per kWp annually.\n"
            "Note 1: Based on standard global solar irradiation data.\n"
        )
        content_bytes = text_content.encode("utf-8")

        result = self.extractor.extract(
            content=content_bytes,
            doc_format="text",
            source_id="SRC_CEA_CO2",
            document_identifier="CEA-2023-V19",
        )

        self.assertEqual(len(result["pages"]), 2)
        self.assertEqual(len(result["sections"]), 2)
        self.assertEqual(len(result["footnotes"]), 1)
        self.assertIn("0.82 kg CO2", result["sections"][0]["clauses"][0]["text"])

        # Provenance check
        prov_entries = result["provenance_map"]
        self.assertTrue(len(prov_entries) >= 3)

    def test_extract_json_document(self) -> None:
        """Verify extraction from structured JSON."""
        data = {
            "standards_scope": "Building Energy Code 2017",
            "lighting_power_density": [
                {"room_type": "Living Room", "lpd_w_m2": 4.5},
                {"room_type": "Bedroom", "lpd_w_m2": 3.5},
                {"room_type": "Kitchen", "lpd_w_m2": 6.0},
            ],
        }
        content_bytes = json.dumps(data).encode("utf-8")

        result = self.extractor.extract(
            content=content_bytes,
            doc_format="json",
            source_id="SRC_NBC_2016",
            document_identifier="NBC-2016-PART8",
        )

        self.assertEqual(len(result["pages"]), 1)
        self.assertEqual(len(result["tables"]), 1)
        table = result["tables"][0]
        self.assertEqual(table["headers"], ["room_type", "lpd_w_m2"])
        self.assertEqual(len(table["rows"]), 3)
        self.assertEqual(table["rows"][0], ["Living Room", 4.5])

    def test_extract_empty_or_corrupt_content(self) -> None:
        """Verify ExtractionError on empty or corrupted content."""
        with self.assertRaises(ExtractionError):
            self.extractor.extract(b"", doc_format="pdf")

        with self.assertRaises(ExtractionError):
            self.extractor.extract(b"Not a real PDF file at all", doc_format="pdf")

    def test_extract_multi_paragraph_clause_retention(self) -> None:
        """Verify consecutive paragraphs within a clause are retained without premature termination."""
        text = (
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
        res = self.extractor.extract(text.encode("utf-8"), doc_format="text")
        clauses = res["sections"][0]["clauses"]
        self.assertEqual(len(clauses), 2)
        cl_1_1 = clauses[0]
        self.assertEqual(cl_1_1["clause_id"], "clause_1_1")
        self.assertIn("50% rated cooling capacities", cl_1_1["text"])
        self.assertIn("NABL-accredited", cl_1_1["text"])

        # Check provenance map
        prov_key = [k for k in res["provenance_map"] if "clause_1_1" in k][0]
        self.assertIn("50% rated cooling capacities", res["provenance_map"][prov_key]["excerpt"])

    def test_extract_unnumbered_section_with_multiple_paragraphs(self) -> None:
        """Verify unnumbered section body text with multiple paragraphs is captured in intro clause."""
        text = (
            "1.0 GENERAL BACKGROUND\n"
            "First introductory paragraph describing the regulatory mandate.\n"
            "\n"
            "Second introductory paragraph detailing compressor transitions.\n"
            "\n"
            "Third introductory paragraph setting out facility scope.\n"
            "\n"
            "1.1 Scope Definition\n"
            "Applicable to all split ACs.\n"
        )
        res = self.extractor.extract(text.encode("utf-8"), doc_format="text")
        clauses = res["sections"][0]["clauses"]
        self.assertEqual(len(clauses), 2)
        intro_cl = clauses[0]
        self.assertIn("First introductory paragraph", intro_cl["text"])
        self.assertIn("Second introductory paragraph", intro_cl["text"])
        self.assertIn("Third introductory paragraph", intro_cl["text"])
        self.assertEqual(clauses[1]["clause_id"], "clause_1_1")

    def test_extract_table_with_multi_line_wrapped_cells(self) -> None:
        """Verify pipe table rows with wrapped multi-line cell content are fully parsed."""
        text = (
            "Table 1 - Metric Definitions\n"
            "| Parameter | Description | Standard Value |\n"
            "| ISEER | Indian Seasonal Energy\n"
            "Efficiency Ratio | 5.0 |\n"
            "| Max Temp | Maximum Outdoor Dry Bulb\n"
            "Operating Temperature | 43 C |\n"
        )
        res = self.extractor.extract(text.encode("utf-8"), doc_format="text")
        self.assertEqual(len(res["tables"]), 1)
        tbl = res["tables"][0]
        self.assertEqual(tbl["headers"], ["Parameter", "Description", "Standard Value"])
        self.assertEqual(len(tbl["rows"]), 2)
        self.assertEqual(tbl["rows"][0], ["ISEER", "Indian Seasonal Energy Efficiency Ratio", "5.0"])
        self.assertEqual(tbl["rows"][1], ["Max Temp", "Maximum Outdoor Dry Bulb Operating Temperature", "43 C"])

    def test_extract_whitespace_table_with_missing_values(self) -> None:
        """Verify whitespace/tab table with missing column values preserves column alignment."""
        text = (
            "Table 3 - Whitespace Table with Missing Values\n"
            "ModelTier    MinCapacity    MaxCapacity    AuxHeat\n"
            "Tier1        2500           3500           500\n"
            "Tier2                       5000           1000\n"
            "Tier3        5000           6000           1500\n"
        )
        res = self.extractor.extract(text.encode("utf-8"), doc_format="text")
        self.assertEqual(len(res["tables"]), 1)
        tbl = res["tables"][0]
        self.assertEqual(tbl["headers"], ["ModelTier", "MinCapacity", "MaxCapacity", "AuxHeat"])
        self.assertEqual(len(tbl["rows"]), 3)
        self.assertEqual(tbl["rows"][0], ["Tier1", "2500", "3500", "500"])
        self.assertEqual(tbl["rows"][1], ["Tier2", "", "5000", "1000"])
        self.assertEqual(tbl["rows"][2], ["Tier3", "5000", "6000", "1500"])


class TestDocumentService(unittest.TestCase):
    """Verifies end-to-end DocumentService acquisition, deduplication, and persistence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="gridvision_test_doc_svc_")
        self.storage = LocalFileSystemStorageAdapter(base_dir=self.temp_dir)
        self.validator = DocumentValidator(max_file_size=5 * 1024 * 1024)
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

    def test_acquire_from_file_full_lifecycle(self) -> None:
        """Verify uploading and ingesting a document file end-to-end."""
        pdf_bytes = generate_sample_pdf_bytes()
        source_meta = {
            "issuing_organization": "Bureau of Energy Efficiency",
            "document_identifier": "BEE/S&L/AC/2024",
            "edition_revision": "Revision 4",
            "publication_date": "2024-01-01",
            "licensing": "Government Open Data License (GODL)",
        }

        record = self.service.acquire_from_file(
            source_meta=source_meta,
            filename="bee_ac_standard.pdf",
            file_bytes=pdf_bytes,
        )

        # 1. Verify source record
        self.assertIn("source_id", record)
        source_id = record["source_id"]
        self.assertEqual(record["issuing_organization"], "Bureau of Energy Efficiency")
        self.assertEqual(record["document_identifier"], "BEE/S&L/AC/2024")
        self.assertEqual(record["format"], "pdf")
        self.assertEqual(record["status"], "active")

        # 2. Verify storage persistence of original and extracted
        orig_path = record["original_file_path"]
        ext_path = record["extracted_file_path"]
        self.assertTrue(self.storage.exists(orig_path))
        self.assertTrue(self.storage.exists(ext_path))

        # 3. Verify retrieved original bytes match exactly
        retrieved_bytes = self.service.get_original_bytes(source_id)
        self.assertEqual(retrieved_bytes, pdf_bytes)

        # 4. Verify retrieved extracted structure has pages and sections
        struct = self.service.get_extracted_structure(source_id)
        self.assertIsNotNone(struct)
        self.assertEqual(len(struct["pages"]), 2)
        self.assertTrue(len(struct["provenance_map"]) > 0)

    def test_duplicate_detection_rejects_identical_checksum(self) -> None:
        """Verify ingesting a duplicate file raises DuplicateDocumentError."""
        pdf_bytes = generate_sample_pdf_bytes()
        meta = {
            "issuing_organization": "CEA",
            "document_identifier": "CEA-CO2-2023",
        }

        # First acquisition succeeds
        rec1 = self.service.acquire_from_file(meta, "doc.pdf", pdf_bytes)
        self.assertIsNotNone(rec1)

        # Second acquisition of identical content raises DuplicateDocumentError
        with self.assertRaises(DuplicateDocumentError) as cm:
            self.service.acquire_from_file(meta, "duplicate_doc.pdf", pdf_bytes)

        self.assertEqual(cm.exception.existing_source_id, rec1["source_id"])
        self.assertEqual(cm.exception.checksum, rec1["content_checksum_sha256"])

    def test_duplicate_detection_allow_duplicate_flag(self) -> None:
        """Verify raise_on_duplicate=False returns existing source record."""
        pdf_bytes = generate_sample_pdf_bytes()
        meta = {"issuing_organization": "BEE", "document_identifier": "DOC-1"}

        rec1 = self.service.acquire_from_file(meta, "doc.pdf", pdf_bytes)
        rec2 = self.service.acquire_from_file(
            meta, "doc.pdf", pdf_bytes, raise_on_duplicate=False
        )

        self.assertEqual(rec1["source_id"], rec2["source_id"])
        self.assertEqual(len(self.service.list_sources()), 1)

    def test_acquire_from_url_with_mock_fetcher(self) -> None:
        """Verify acquiring a document via URL using a mock fetcher."""
        pdf_bytes = generate_sample_pdf_bytes()
        mock_fetcher = MagicMock(spec=SSRFSafeFetcher)
        mock_fetcher.fetch.return_value = (pdf_bytes, {"content-type": "application/pdf"})

        service = DocumentService(
            storage=self.storage,
            fetcher=mock_fetcher,
            validator=self.validator,
            extractor=self.extractor,
        )

        meta = {
            "issuing_organization": "CEA",
            "document_identifier": "CEA-GRID-2023",
        }
        url = "https://cea.gov.in/reports/co2_baseline_v19.pdf"

        record = service.acquire_from_url(meta, url)
        mock_fetcher.fetch.assert_called_once_with(url)

        self.assertEqual(record["official_url"], url)
        self.assertTrue(self.storage.exists(record["original_file_path"]))
        self.assertTrue(self.storage.exists(record["extracted_file_path"]))

    def test_list_and_delete_source(self) -> None:
        """Verify list_sources and delete_source lifecycle."""
        pdf_bytes = generate_sample_pdf_bytes()
        meta = {"issuing_organization": "BEE", "document_identifier": "BEE-1"}

        rec = self.service.acquire_from_file(meta, "doc.pdf", pdf_bytes)
        source_id = rec["source_id"]

        sources = self.service.list_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source_id"], source_id)

        # Delete source
        deleted = self.service.delete_source(source_id)
        self.assertTrue(deleted)

        self.assertEqual(len(self.service.list_sources()), 0)
        self.assertIsNone(self.service.get_source(source_id))
        self.assertFalse(self.storage.exists(rec["original_file_path"]))
        self.assertFalse(self.storage.exists(rec["extracted_file_path"]))

    def test_concurrent_acquisition_thread_safety(self) -> None:
        """Verify concurrent acquisition of identical document is serialized and thread-safe."""
        pdf_bytes = generate_sample_pdf_bytes()
        meta = {
            "issuing_organization": "CEA",
            "document_identifier": "CEA-CONCURRENT-TEST",
        }

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        results = []
        errors = []

        def worker(idx: int) -> None:
            barrier.wait()
            try:
                rec = self.service.acquire_from_file(
                    source_meta=meta,
                    filename=f"doc_thread_{idx}.pdf",
                    file_bytes=pdf_bytes,
                    raise_on_duplicate=True,
                )
                results.append(rec)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        duplicate_errors = [e for e in errors if isinstance(e, DuplicateDocumentError)]
        self.assertEqual(len(results), 1, "Exactly one thread must succeed in acquiring the document")
        self.assertEqual(len(duplicate_errors), num_threads - 1, "All concurrent attempts must raise DuplicateDocumentError")
        self.assertEqual(len(self.service.list_sources()), 1, "Only one source record should be registered")

    def test_acquire_from_file_extraction_failure_rollback(self) -> None:
        """Verify rollback deletes original file from storage if extraction fails in acquire_from_file."""
        pdf_bytes = generate_sample_pdf_bytes()
        meta = {"issuing_organization": "BIS", "document_identifier": "CRASH-TEST"}

        with patch.object(self.extractor, "extract", side_effect=ExtractionError("Extraction failed")):
            with self.assertRaises(ExtractionError):
                self.service.acquire_from_file(meta, "crash.pdf", pdf_bytes)

        orig_dir = Path(self.temp_dir) / "original"
        orphan_files = list(orig_dir.rglob("crash.pdf"))
        self.assertEqual(len(orphan_files), 0, "Original file must be deleted upon extraction failure")
        self.assertEqual(len(self.service.list_sources()), 0, "No source record should be registered")

    def test_acquire_from_url_extraction_failure_rollback(self) -> None:
        """Verify rollback deletes original file if extraction fails in acquire_from_url."""
        pdf_bytes = generate_sample_pdf_bytes()
        mock_fetcher = MagicMock(spec=SSRFSafeFetcher)
        mock_fetcher.fetch.return_value = (pdf_bytes, {"content-type": "application/pdf"})

        service = DocumentService(
            storage=self.storage,
            fetcher=mock_fetcher,
            validator=self.validator,
            extractor=self.extractor,
        )
        meta = {"issuing_organization": "BIS", "document_identifier": "URL-CRASH"}

        with patch.object(service.extractor, "extract", side_effect=ExtractionError("Extraction failed")):
            with self.assertRaises(ExtractionError):
                service.acquire_from_url(meta, "https://example.com/url_crash.pdf")

        orig_dir = Path(self.temp_dir) / "original"
        orphan_files = list(orig_dir.rglob("url_crash.pdf"))
        self.assertEqual(len(orphan_files), 0, "Original file from URL must be deleted upon extraction failure")
        self.assertEqual(len(service.list_sources()), 0)

    def test_source_update_purges_stale_checksum_from_index(self) -> None:
        """Verify updating existing source_id with altered content purges old checksum from index."""
        pdf_v1 = generate_sample_pdf_bytes()
        pdf_v2 = pdf_v1 + b"\n% amendment 2026\n"
        meta = {"source_id": "SRC_IMMUTABLE_ID", "issuing_organization": "BEE"}

        rec1 = self.service.acquire_from_file(meta, "doc_v1.pdf", pdf_v1)
        sha1 = rec1["content_checksum_sha256"]

        rec2 = self.service.acquire_from_file(meta, "doc_v2.pdf", pdf_v2)
        sha2 = rec2["content_checksum_sha256"]

        self.assertNotEqual(sha1, sha2)
        self.assertIsNone(self.service.find_by_checksum(sha1), "Stale checksum must be purged from index")
        found = self.service.find_by_checksum(sha2)
        self.assertIsNotNone(found)
        self.assertEqual(found["source_id"], "SRC_IMMUTABLE_ID")


if __name__ == "__main__":
    unittest.main()
