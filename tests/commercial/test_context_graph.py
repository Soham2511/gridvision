"""Tests for provenance-aware Operations Context Graph extraction."""

from __future__ import annotations

from ai.commercial.context_graph.extraction import extract_passage_graph
from ai.commercial.rag.chunking import DocumentChunk


def _chunk(text: str, section: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id="chunk-test-register",
        source_id="operations.pdf",
        document_sha256="document-hash",
        page_number=1,
        section=section,
        text=text,
        extraction_method="pdf_text",
        synthetic=True,
    )


def test_register_extracts_machines_dependencies_and_cited_provenance() -> None:
    graph = extract_passage_graph(
        _chunk(
            "2. Production areas and machine register\n"
            "Production CUT-01 CNC cutting machine 45 kW "
            "06:00-22:00 Feeds machined components to CNC-02\n"
            "Production CNC-02 CNC machining centre 60 kW "
            "06:00-22:00 Requires CUT-01 output",
            "2. Production areas and machine register",
        )
    )

    machines = {
        entity.properties.get("asset_id"): entity
        for entity in graph.entities
        if entity.entity_type == "Machine"
        and not entity.properties.get("reference_only")
    }
    assert machines["CUT-01"].properties["rated_power_kw"] == 45.0
    assert machines["CUT-01"].properties["normal_operating_window"] == (
        "06:00-22:00"
    )
    assert machines["CNC-02"].properties["rated_power_kw"] == 60.0
    assert all(
        entity.source_id == "operations.pdf"
        and entity.page_number == 1
        and entity.evidence_chunk_id == "chunk-test-register"
        for entity in machines.values()
    )
    relationships = {
        (
            edge.source_entity_id,
            edge.target_entity_id,
            edge.relationship,
        )
        for edge in graph.relationships
    }
    assert (
        machines["CNC-02"].entity_id,
        machines["CUT-01"].entity_id,
        "DEPENDS_ON",
    ) in relationships
    assert (
        machines["CUT-01"].entity_id,
        machines["CNC-02"].entity_id,
        "FEEDS",
    ) in relationships


def test_constraints_are_extracted_only_with_explicit_provenance() -> None:
    graph = extract_passage_graph(
        _chunk(
            "CMP-01 pressure must remain within the approved operating band. "
            "Leak repairs and pressure optimization require maintenance "
            "authorization.",
            "4. Operating constraints and flexibility",
        )
    )

    constraints = [
        entity for entity in graph.entities
        if entity.entity_type == "Constraint"
    ]
    assert constraints
    assert all(
        entity.source_id == "operations.pdf"
        and entity.page_number == 1
        and entity.properties["statement"] in entity.label
        for entity in constraints
    )
    assert any(
        edge.relationship == "RESTRICTED_BY"
        and edge.source_entity_id.endswith(":machine:cmp-01")
        for edge in graph.relationships
    )


def test_graph_extraction_skips_incomplete_machine_register_rows() -> None:
    graph = extract_passage_graph(
        _chunk(
            "Production CUT-01 machine without rated power or hours",
            "2. Production areas and machine register",
        )
    )

    assert not any(entity.entity_type == "Machine" for entity in graph.entities)


def test_explicit_labeled_factory_records_and_named_relationships_are_extracted() -> None:
    graph = extract_passage_graph(
        _chunk(
            "Factory: North Plant\n"
            "Department: Milling\n"
            "Production Line: Line-A\n"
            "Operation: Milling performs Line-A\n"
            "Energy Source: Grid electricity\n"
            "Production Target: 400 units per shift\n"
            "Maintenance Procedure: Filter inspection\n"
            "Guideline: Approved pressure range",
            "Factory profile",
        )
    )

    entity_types = {entity.entity_type for entity in graph.entities}
    assert {
        "Factory",
        "Department",
        "ProductionLine",
        "Operation",
        "EnergySource",
        "ProductionTarget",
        "MaintenanceProcedure",
        "Guideline",
        "Passage",
    }.issubset(entity_types)
    operation = next(
        entity for entity in graph.entities
        if entity.entity_type == "Operation"
    )
    line = next(
        entity for entity in graph.entities
        if entity.entity_type == "ProductionLine"
    )
    assert any(
        edge.source_entity_id == operation.entity_id
        and edge.target_entity_id == line.entity_id
        and edge.relationship == "PERFORMS"
        for edge in graph.relationships
    )
    assert all(
        entity.source_id == "operations.pdf"
        and entity.evidence_chunk_id == "chunk-test-register"
        for entity in graph.entities
    )
