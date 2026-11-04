"""Tests for local Commercial PDF retrieval and unavailable-data behavior."""

from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

import pytest

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.graph import build_commercial_graph
from ai.commercial.rag.document_retriever import PDFDocumentRetriever
from ai.commercial.rag.ingestion import (
    DocumentIngestionError,
    _resolve_tesseract_command,
    ingest_document,
)
from ai.commercial.rag.neo4j_graph import Neo4jTopicGraph


def test_default_documents_return_cited_demonstration_knowledge() -> None:
    settings = CommercialSettings()
    retriever = PDFDocumentRetriever(
        settings.rag_documents,
        max_results=settings.rag_max_results,
        min_score=settings.rag_min_score,
    )

    observation = retriever.retrieve("compressed air system leak reduction")

    assert observation.status == "available"
    assert observation.findings
    assert all(reference.synthetic for reference in observation.evidence_refs)
    assert {
        reference.source_id for reference in observation.evidence_refs
    } >= {"GridVision_Commercial_Energy_Knowledge_RAG.pdf"}
    assert all(reference.locator.startswith("page:") for reference in observation.evidence_refs)


def test_automotive_parts_demo_document_is_explicitly_synthetic(
    tmp_path: Path,
) -> None:
    source = CommercialSettings().rag_documents[2]
    retriever = PDFDocumentRetriever(
        (source,),
        index_path=tmp_path / "index.sqlite3",
    )

    observation = retriever.retrieve(
        "Explain automotive parts metal stamping and CNC machining."
    )

    assert observation.status == "available"
    assert observation.evidence_refs
    assert all(reference.synthetic for reference in observation.evidence_refs)
    assert all(
        reference.source_type == "local_document"
        for reference in observation.evidence_refs
    )
    assert any("Fictional demonstration data only" in item for item in observation.findings)


def test_uploaded_text_document_is_indexed_and_retrievable(
    tmp_path: Path,
) -> None:
    settings = CommercialSettings()
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    uploaded = upload_root / "factory-notes.txt"
    uploaded.write_text(
        "Compressed air leaks increase factory energy use. "
        "Inspect filters, dryers, and pressure settings.",
        encoding="utf-8",
    )
    retriever = PDFDocumentRetriever(
        (settings.rag_documents[2],),
        allowed_root=settings.rag_allowed_root,
        upload_root=upload_root,
        index_path=tmp_path / "index.sqlite3",
    )

    report = retriever.index_documents()
    observation = retriever.retrieve(
        "How can compressed air leaks be reduced?"
    )

    assert any(
        item["source_id"] == uploaded.name and item["status"] == "indexed"
        for item in report["documents"]
    )
    assert observation.status == "available"
    assert any(
        reference.source_id == uploaded.name
        for reference in observation.evidence_refs
    )


def test_factory_specific_query_can_use_uploaded_synthetic_document(
    tmp_path: Path,
) -> None:
    settings = CommercialSettings()
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    uploaded = upload_root / "machine-register.txt"
    uploaded.write_text(
        "Fictional demonstration record. "
        "Machine 1 status: running. Machine 2 status: stopped. "
        "Machine 3 status: running.",
        encoding="utf-8",
    )
    retriever = PDFDocumentRetriever(
        (settings.rag_documents[2],),
        allowed_root=settings.rag_allowed_root,
        upload_root=upload_root,
        index_path=tmp_path / "index.sqlite3",
    )

    observation = retriever.retrieve(
        "How many machines are working according to the uploaded pdf?"
    )

    assert observation.status == "available"
    assert observation.evidence_refs
    assert any(
        reference.source_id == uploaded.name and reference.synthetic
        for reference in observation.evidence_refs
    )
    assert any("Machine 1 status: running" in finding for finding in observation.findings)
    assert any(
        "2 of 3 identified machine records" in finding
        and "synthetic demonstration document" in finding
        for finding in observation.findings
    )
    assert observation.data["query"]["topics"] == ["equipment_register"]


def test_plain_text_ingestion_preserves_one_page_provenance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "maintenance.txt"
    source.write_text("Machine maintenance starts at 08:00.", encoding="utf-8")

    document = ingest_document(source, allowed_root=tmp_path)

    assert len(document.pages) == 1
    assert document.pages[0].page_number == 1
    assert document.pages[0].text == "Machine maintenance starts at 08:00."
    assert document.pages[0].extraction_method == "plain_text"


def test_unmatched_query_returns_structured_data_unavailable() -> None:
    settings = CommercialSettings()
    retriever = PDFDocumentRetriever(settings.rag_documents)

    observation = retriever.retrieve("ZQX991 quantum chronometer unobtanium")

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "DATA_NOT_AVAILABLE"
    assert observation.findings == ()
    assert observation.evidence_refs == ()


def test_vague_request_returns_specific_query_suggestions() -> None:
    settings = CommercialSettings()
    retriever = PDFDocumentRetriever(settings.rag_documents)

    observation = retriever.retrieve("Check factory operations")

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "QUERY_NEEDS_CLARIFICATION"
    query = observation.data["query"]
    assert query["original"] == "Check factory operations"
    assert query["status"] == "needs_clarification"
    assert query["search_text"] == ""
    assert "compressed air" in observation.error.message
    assert observation.findings == ()


def test_question_is_expanded_to_a_topic_specific_document_query() -> None:
    settings = CommercialSettings()
    retriever = PDFDocumentRetriever(settings.rag_documents)

    observation = retriever.retrieve(
        "How can I reduce energy use from compressed air leaks?"
    )

    assert observation.status == "available"
    query = observation.data["query"]
    assert query["original"] == (
        "How can I reduce energy use from compressed air leaks?"
    )
    assert query["topics"] == ["compressed_air"]
    assert "filters dryers" in query["search_text"]
    assert observation.data["retrieved_passages"]
    assert all(
        (
            "compressed air" in passage["text"].casefold().replace("-", " ")
            or (
                "air" in passage["text"].casefold()
                and "leak" in passage["text"].casefold()
            )
        )
        for passage in observation.data["retrieved_passages"]
    )


def test_factory_specific_query_does_not_substitute_generic_guidance() -> None:
    settings = CommercialSettings()
    retriever = PDFDocumentRetriever(settings.rag_documents)

    observation = retriever.retrieve(
        "What is the maintenance schedule for our factory machine?"
    )

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "DATA_NOT_AVAILABLE"
    assert "factory-specific data" in (
        observation.error.message
    )
    assert observation.findings == ()


def test_missing_factory_energy_reading_returns_data_unavailable() -> None:
    settings = CommercialSettings()
    retriever = PDFDocumentRetriever(settings.rag_documents)

    observation = retriever.retrieve(
        "What is the energy consumption of our factory?"
    )

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "DATA_NOT_AVAILABLE"
    assert observation.findings == ()


def test_missing_document_reports_unavailable_without_fabricated_findings(
    tmp_path: Path,
) -> None:
    retriever = PDFDocumentRetriever((tmp_path / "missing.pdf",))

    observation = retriever.retrieve("compressed air")

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "DATA_NOT_AVAILABLE"
    assert "Document is missing" in observation.error.message
    assert observation.findings == ()


def test_local_hybrid_index_is_persistent_and_incremental(tmp_path: Path) -> None:
    settings = CommercialSettings()
    source = settings.rag_documents[0]
    allowed_root = tmp_path / "documents"
    allowed_root.mkdir()
    document = allowed_root / source.name
    shutil.copyfile(source, document)
    index_path = tmp_path / "index.sqlite3"

    retriever = PDFDocumentRetriever(
        (document,),
        allowed_root=allowed_root,
        index_path=index_path,
    )
    initial = retriever.index_documents()

    assert initial["documents"][0]["status"] == "indexed"
    assert "docling_pdf_text" in initial["documents"][0]["extraction_methods"]
    assert initial["index_counts"]["chunks"] > 0
    assert initial["index_counts"]["graph_nodes"] > 0
    assert retriever.index_documents()["documents"][0]["status"] == "unchanged"

    reopened = PDFDocumentRetriever(
        (document,),
        allowed_root=allowed_root,
        index_path=index_path,
    )
    observation = reopened.retrieve("compressed air leak reduction")

    assert observation.status == "available"
    assert observation.data["retrieval_methods"] == [
        "bm25",
        "local_vector",
        "topic_graph",
        "context_graph",
        "reciprocal_rank_fusion",
    ]
    assert observation.evidence_refs


def test_configured_source_scope_does_not_read_other_indexed_documents(
    tmp_path: Path,
) -> None:
    settings = CommercialSettings()
    allowed_root = tmp_path / "documents"
    allowed_root.mkdir()
    indexed_document = allowed_root / settings.rag_documents[0].name
    shutil.copyfile(settings.rag_documents[0], indexed_document)
    index_path = tmp_path / "index.sqlite3"

    indexed_retriever = PDFDocumentRetriever(
        (indexed_document,),
        allowed_root=allowed_root,
        index_path=index_path,
    )
    assert indexed_retriever.index_documents()["index_counts"]["chunks"] > 0

    missing_retriever = PDFDocumentRetriever(
        (allowed_root / "not-configured.pdf",),
        allowed_root=allowed_root,
        index_path=index_path,
    )
    observation = missing_retriever.retrieve("compressed air leak reduction")

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "DATA_NOT_AVAILABLE"
    assert "Document is missing" in observation.error.message
    assert observation.evidence_refs == ()


def test_source_outside_allowed_root_is_rejected(tmp_path: Path) -> None:
    settings = CommercialSettings()
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_document = tmp_path / "outside.pdf"
    shutil.copyfile(settings.rag_documents[0], outside_document)
    retriever = PDFDocumentRetriever(
        (outside_document,),
        allowed_root=allowed_root,
        index_path=tmp_path / "index.sqlite3",
    )

    report = retriever.index_documents()
    observation = retriever.retrieve("compressed air leak reduction")

    assert report["documents"][0]["status"] == "unavailable"
    assert "inside the configured document root" in report["documents"][0]["message"]
    assert observation.status == "unavailable"
    assert observation.evidence_refs == ()


def test_tesseract_autodiscovery_checks_user_install_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local"
    executable = (
        local_app_data
        / "Programs"
        / "Tesseract-OCR"
        / "tesseract.exe"
    )
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "program-files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "program-files-x86"))
    monkeypatch.delenv("COMMERCIAL_TESSERACT_CMD", raising=False)

    assert _resolve_tesseract_command(None) == str(executable)


def test_missing_configured_tesseract_path_fails_explicitly(
    tmp_path: Path,
) -> None:
    with pytest.raises(DocumentIngestionError, match="does not exist"):
        _resolve_tesseract_command(tmp_path / "missing-tesseract.exe")


def test_scanned_operations_pdf_is_ocr_indexed_with_provenance(
    tmp_path: Path,
) -> None:
    tesseract = _resolve_tesseract_command(None)
    if tesseract is None:
        pytest.skip("A local Tesseract executable is required for this test.")

    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = tesseract
    try:
        if "eng" not in pytesseract.get_languages(config=""):
            pytest.skip("The local Tesseract English model is unavailable.")
    except pytesseract.TesseractError:
        pytest.skip("The local Tesseract engine is unavailable.")

    settings = CommercialSettings()
    source = settings.rag_documents[1]
    allowed_root = tmp_path / "documents"
    allowed_root.mkdir()
    document = allowed_root / source.name
    shutil.copyfile(source, document)
    retriever = PDFDocumentRetriever(
        (document,),
        allowed_root=allowed_root,
        index_path=tmp_path / "index.sqlite3",
        ocr_render_scale=3.0,
    )

    report = retriever.index_documents()
    observation = retriever.retrieve(
        "What equipment and operating windows are listed in the operations register?"
    )

    assert report["documents"][0]["extraction_methods"] == ["local_ocr"]
    passages = retriever.index.chunks_for_document(document.name)
    assert passages
    assert all(passage["synthetic"] for passage in passages)
    assert any(
        "CUT-01" in passage["text"] and "45 kW" in passage["text"]
        for passage in passages
    )
    assert observation.status == "available"
    assert observation.evidence_refs
    first_passage = observation.data["retrieved_passages"][0]
    assert first_passage["section"] == "2. Production areas and machine register"
    assert "CUT-01" in first_passage["text"]
    assert "45 kW" in first_passage["text"]
    assert "\nProduction CUT-01" in first_passage["text"]
    assert "LGT-01 Plant lighting 12 kW" in first_passage["text"]
    assert all(
        asset_id in first_passage["text"]
        for asset_id in (
            "CUT-01",
            "CNC-02",
            "ASM-01",
            "FUR-O1",
            "CHL-01",
            "CMP-01",
            "CON-01",
            "PMP-01",
            "LGT-01",
        )
    )
    context_graph_matches = retriever.index.context_graph_search(
        ["CUT-01"],
        10,
        [document.name],
    )
    assert first_passage["source_id"] == document.name
    assert first_passage["text"]
    assert context_graph_matches
    assert any(
        "CUT-01" in str(row["text"])
        for row in retriever.index.get_chunks(
            context_graph_matches,
            [document.name],
        )
    )
    assert first_passage["section"] == "2. Production areas and machine register"
    assert retriever.index.index_counts()["graph_nodes"] > len(passages)
    assert observation.evidence_refs[0].excerpt == first_passage["text"]
    assert all(reference.synthetic for reference in observation.evidence_refs)
    assert all(reference.extraction_confidence == 0.6 for reference in observation.evidence_refs)

    factory_observation = retriever.retrieve(
        "What rated power does our machine have?"
    )
    assert factory_observation.status == "unavailable"
    assert factory_observation.error is not None
    assert factory_observation.error.code == "DATA_NOT_AVAILABLE"
    retriever.index.remove_document(document.name)
    assert (
        retriever.index.context_graph_search(
            ["CUT-01"],
            10,
            [document.name],
        )
        == []
    )


def test_neo4j_graph_backend_rejects_non_local_endpoints() -> None:
    with pytest.raises(ValueError, match="only supports a local"):
        Neo4jTopicGraph(
            uri="neo4j+s://graph.example.com",
            username="neo4j",
            password="test-password",
            database="neo4j",
        )


def test_neo4j_graph_queries_bind_source_and_topic_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeTransaction:
        def run(self, query: str, **parameters: object) -> list[object]:
            calls.append((query, parameters))
            return []

    class FakeResult:
        def __init__(self, records: list[dict[str, str]] | None = None) -> None:
            self.records = records or [{"chunk_id": "chunk-1"}]

        def __iter__(self):
            return iter(self.records)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            del args
            return None

        def execute_write(self, callback, *_args: object):
            return callback(FakeTransaction(), *_args)

        def run(self, query: str, **parameters: object):
            calls.append((query, parameters))
            if "passage.entity_id AS passage_id" in query:
                return FakeResult([{"passage_id": "chunk:chunk-1"}])
            return FakeResult()

    class FakeDriver:
        def verify_connectivity(self) -> None:
            return None

        def session(self, *, database: str) -> FakeSession:
            assert database == "commercial"
            return FakeSession()

        def close(self) -> None:
            return None

    def create_driver(*args: object, **kwargs: object) -> FakeDriver:
        assert args[0] == "bolt://127.0.0.1:7687"
        assert kwargs["auth"] == ("neo4j", "test-password")
        return FakeDriver()

    neo4j_module = types.ModuleType("neo4j")
    neo4j_module.GraphDatabase = types.SimpleNamespace(
        driver=create_driver
    )
    monkeypatch.setitem(sys.modules, "neo4j", neo4j_module)

    graph = Neo4jTopicGraph(
        uri="bolt://127.0.0.1:7687",
        username="neo4j",
        password="test-password",
        database="commercial",
    )
    graph.sync_document(
        source_id="guide.pdf",
        content_sha256="hash",
        source_path="guide.pdf",
        pages=1,
        passages=[
            {
                "chunk_id": "chunk-1",
                "sha256": "hash",
                "page_number": 1,
                "section": "compressed air",
                "text": "Untrusted document text",
                "extraction_method": "pdf_text",
                "synthetic": True,
                "topics": ["compressed_air"],
            }
        ],
        context_graph={
            "entities": [
                {
                    "entity_id": "entity:guide.pdf:machine:cmp-01",
                    "entity_type": "Machine",
                    "label": "CMP-01",
                    "properties_json": "{}",
                    "page_number": 1,
                    "section": "machine register",
                    "extraction_confidence": 0.95,
                },
                {
                    "entity_id": "chunk:chunk-1",
                    "entity_type": "Passage",
                    "label": "guide.pdf page 1",
                    "properties_json": '{"chunk_id":"chunk-1"}',
                    "page_number": 1,
                    "section": "machine register",
                    "extraction_confidence": 0.95,
                },
            ],
            "relationships": [
                {
                    "source_entity_id": "entity:guide.pdf:machine:cmp-01",
                    "target_entity_id": "chunk:chunk-1",
                    "relationship": "SUPPORTED_BY",
                    "source_id": "guide.pdf",
                    "page_number": 1,
                    "section": "machine register",
                    "extraction_confidence": 0.95,
                    "evidence_chunk_id": "chunk-1",
                },
            ],
        },
    )
    found = graph.search(["compressed_air"], ["guide.pdf"], 4)
    graph_found = graph.search_entities(["CMP-01"], ["guide.pdf"], 4)
    graph.remove_document("guide.pdf")
    graph.close()

    assert found == ["chunk-1"]
    assert graph_found == ["chunk-1"]
    assert any("CG_RELATION" in query for query, _ in calls)
    search_call = next(
        parameters
        for query, parameters in calls
        if "RETURN DISTINCT passage.chunk_id" in query
    )
    assert search_call == {
        "topic_ids": ["compressed_air"],
        "source_ids": ["guide.pdf"],
        "limit": 4,
    }
    passage_sync = next(
        parameters
        for query, parameters in calls
        if "UNWIND $passages AS row" in query
    )
    assert passage_sync["passages"][0]["text"] == "Untrusted document text"


def test_operations_workflow_uses_documents_and_preserves_citations() -> None:
    graph = build_commercial_graph()

    result = graph.invoke(
        {
            "request_id": "pdf-rag-request",
            "factory_id": "not-provided",
            "user_goal": "Find guidance on compressed air leakage reduction.",
        }
    )

    assert result["validation_status"].status == "passed"
    assert result["final_response"]["findings"]
    references = result["final_response"]["evidence_refs"]
    assert references
    assert {
        reference["source_id"] for reference in references
    } >= {"GridVision_Commercial_Energy_Knowledge_RAG.pdf"}
    assert all(reference["synthetic"] for reference in references)
