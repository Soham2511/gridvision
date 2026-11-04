"""Conservative deterministic entity extraction for Operations passages."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from ai.commercial.context_graph.models import (
    ContextEntity,
    ContextEntityType,
    ContextRelationship,
    ContextRelationshipEdge,
    PassageGraph,
)
from ai.commercial.rag.chunking import DocumentChunk

ASSET_ID = re.compile(r"\b[A-Z]{3}-[A-Z0-9]{2}\b", re.IGNORECASE)
REGISTER_ROW = re.compile(
    r"^(?P<department>[A-Za-z][A-Za-z &/-]*?)\s+"
    r"(?P<asset>[A-Z]{3}-[A-Z0-9]{2})\s+"
    r"(?P<equipment>.+?)\s+"
    r"(?P<power>\d+(?:\.\d+)?)\s*kW\s+"
    r"(?P<window>\d{2}:\d{2}\s*[-–]\s*\d{2}:\d{2}|As required)"
    r"(?:\s+(?P<notes>.*))?$",
    re.IGNORECASE,
)
DIRECTIVE = re.compile(
    r"\b(?:must|must not|shall|should not|do not|"
    r"not to be|requires? approval|approval required|"
    r"minimum .{0,50} must be maintained|"
    r"maintain .{0,80}|approved process|quality-critical)\b",
    re.IGNORECASE,
)
OPERATIONAL_SECTIONS = (
    "constraint",
    "dependency",
    "maintenance",
    "restriction",
    "operating",
    "authority",
)
LABELED_RECORD = re.compile(
    r"(?im)(?P<kind>factory|site|department|production\s+line|operation|"
    r"energy\s+source|production\s+target|maintenance\s+procedure|guideline)"
    r"\s*:\s*(?P<value>[^\n.;]{3,240})"
)
DECLARED_RELATION = re.compile(
    r"\b(?P<verb>depends on|consumes|produces|requires|restricted by|"
    r"maintained by|optimizable by|performs|contains)\s+"
    r"(?:the\s+)?(?P<target>[A-Za-z0-9][A-Za-z0-9 _./-]{1,100})",
    re.IGNORECASE,
)
DECLARED_TYPES: dict[str, ContextEntityType] = {
    "factory": "Factory",
    "site": "Factory",
    "department": "Department",
    "production line": "ProductionLine",
    "operation": "Operation",
    "energy source": "EnergySource",
    "production target": "ProductionTarget",
    "maintenance procedure": "MaintenanceProcedure",
    "guideline": "Guideline",
}
DECLARED_RELATIONSHIPS: dict[str, ContextRelationship] = {
    "depends on": "DEPENDS_ON",
    "consumes": "CONSUMES",
    "produces": "PRODUCES",
    "requires": "REQUIRES",
    "restricted by": "RESTRICTED_BY",
    "maintained by": "MAINTAINED_BY",
    "optimizable by": "OPTIMIZABLE_BY",
    "performs": "PERFORMS",
    "contains": "CONTAINS",
}
RELATION_VERBS = "|".join(
    re.escape(value) for value in DECLARED_RELATIONSHIPS
)


def _record_parts(value: str) -> tuple[str, str]:
    parts = re.split(
        rf"\s+(?:[—–]|-)\s+|\s+(?=(?:{RELATION_VERBS})\b)",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    label = parts[0].strip()
    details = parts[1].strip() if len(parts) > 1 else ""
    return label, details


def _entity_id(source_id: str, kind: str, natural_key: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", natural_key.casefold()).strip("-")
    return f"entity:{source_id}:{kind.casefold()}:{key}"


def _confidence(chunk: DocumentChunk) -> float:
    return 0.65 if chunk.extraction_method == "local_ocr" else 0.95


def _entity(
    chunk: DocumentChunk,
    *,
    kind: ContextEntityType,
    natural_key: str,
    label: str,
    properties: dict[str, object] | None = None,
) -> ContextEntity:
    return ContextEntity(
        entity_id=_entity_id(chunk.source_id, kind, natural_key),
        entity_type=kind,
        label=label,
        properties=properties or {},
        source_id=chunk.source_id,
        page_number=chunk.page_number,
        section=chunk.section,
        evidence_chunk_id=chunk.chunk_id,
        extraction_confidence=_confidence(chunk),
    )


def _edge(
    chunk: DocumentChunk,
    source: ContextEntity,
    target: ContextEntity,
    relationship: ContextRelationship,
    confidence: float | None = None,
) -> ContextRelationshipEdge:
    return ContextRelationshipEdge(
        source_entity_id=source.entity_id,
        target_entity_id=target.entity_id,
        relationship=relationship,
        source_id=chunk.source_id,
        page_number=chunk.page_number,
        section=chunk.section,
        evidence_chunk_id=chunk.chunk_id,
        extraction_confidence=(
            _confidence(chunk) if confidence is None else confidence
        ),
    )


def _machine_reference(chunk: DocumentChunk, asset_id: str) -> ContextEntity:
    return _entity(
        chunk,
        kind="Machine",
        natural_key=asset_id,
        label=asset_id.upper(),
        properties={"asset_id": asset_id.upper(), "reference_only": True},
    )


def _register_graph(chunk: DocumentChunk) -> PassageGraph:
    entities: dict[str, ContextEntity] = {}
    relationships: dict[tuple[str, str, str], ContextRelationshipEdge] = {}
    rows = chunk.text.splitlines()

    def add_entity(entity: ContextEntity) -> None:
        previous = entities.get(entity.entity_id)
        if previous is None or (
            previous.properties.get("reference_only")
            and not entity.properties.get("reference_only")
        ):
            entities[entity.entity_id] = entity

    def add_edge(edge: ContextRelationshipEdge) -> None:
        relationships[
            (edge.source_entity_id, edge.target_entity_id, edge.relationship)
        ] = edge

    parsed_rows: list[tuple[ContextEntity, str]] = []
    for line in rows:
        match = REGISTER_ROW.match(line.strip())
        if not match:
            continue
        data = match.groupdict()
        asset_id = data["asset"].upper()
        machine = _entity(
            chunk,
            kind="Machine",
            natural_key=asset_id,
            label=data["equipment"].strip(),
            properties={
                "asset_id": asset_id,
                "department": data["department"].strip(),
                "rated_power_kw": float(data["power"]),
                "normal_operating_window": data["window"].strip(),
                "notes": (data["notes"] or "").strip(),
                "reference_only": False,
            },
        )
        department_name = data["department"].strip()
        department = _entity(
            chunk,
            kind="Department",
            natural_key=department_name,
            label=department_name,
        )
        add_entity(machine)
        add_entity(department)
        add_edge(_edge(chunk, department, machine, "CONTAINS"))
        parsed_rows.append((machine, data["notes"] or ""))

    for machine, notes in parsed_rows:
        requirement = re.search(
            r"\brequires?\b(?P<required>.*)",
            notes,
            re.IGNORECASE,
        )
        if requirement:
            asset_id = ASSET_ID.search(requirement.group("required"))
            if asset_id:
                prerequisite = _machine_reference(chunk, asset_id.group())
                add_entity(prerequisite)
                add_edge(
                    _edge(chunk, machine, prerequisite, "DEPENDS_ON")
                )
        feeds = re.search(
            r"\bfeeds?\b.*?\bto\s+(?P<target>[A-Z]{3}-[A-Z0-9]{2})\b",
            notes,
            re.IGNORECASE,
        )
        if feeds:
            target = _machine_reference(chunk, feeds.group("target"))
            add_entity(target)
            add_edge(_edge(chunk, machine, target, "FEEDS"))

    return PassageGraph(
        entities=tuple(entities.values()),
        relationships=tuple(relationships.values()),
    )


def _constraint_graph(chunk: DocumentChunk) -> PassageGraph:
    section = (chunk.section or "").casefold()
    if not any(term in section for term in OPERATIONAL_SECTIONS):
        return PassageGraph()

    entities: dict[str, ContextEntity] = {}
    relationships: dict[tuple[str, str, str], ContextRelationshipEdge] = {}
    fragments: Iterable[str] = re.split(
        r"(?<=[.!?])\s+|[\r\n]+|;\s*",
        chunk.text,
    )
    for fragment in fragments:
        clause = " ".join(fragment.split()).strip(" +-")
        if len(clause) < 12 or not DIRECTIVE.search(clause):
            continue
        digest = hashlib.sha256(clause.casefold().encode("utf-8")).hexdigest()[:16]
        constraint = _entity(
            chunk,
            kind="Constraint",
            natural_key=digest,
            label=clause[:400],
            properties={"statement": clause, "reference_only": False},
        )
        entities[constraint.entity_id] = constraint

        asset_ids = list(dict.fromkeys(match.upper() for match in ASSET_ID.findall(clause)))
        for asset_id in asset_ids:
            machine = _machine_reference(chunk, asset_id)
            entities.setdefault(machine.entity_id, machine)
            edge = _edge(chunk, machine, constraint, "RESTRICTED_BY")
            relationships[
                (edge.source_entity_id, edge.target_entity_id, edge.relationship)
            ] = edge

    return PassageGraph(
        entities=tuple(entities.values()),
        relationships=tuple(relationships.values()),
    )


def _declared_records_graph(chunk: DocumentChunk) -> PassageGraph:
    """Extract only explicitly labeled records and named links in their text."""
    entities: dict[str, ContextEntity] = {}
    relationships: dict[tuple[str, str, str], ContextRelationshipEdge] = {}
    declarations = list(LABELED_RECORD.finditer(chunk.text))
    for declaration in declarations:
        kind = " ".join(declaration.group("kind").casefold().split())
        value = " ".join(declaration.group("value").split()).strip(" -:")
        if not value:
            continue
        label, _ = _record_parts(value)
        if len(label) < 2:
            continue
        entity = _entity(
            chunk,
            kind=DECLARED_TYPES[kind],
            natural_key=label,
            label=label,
            properties={"statement": value, "reference_only": False},
        )
        entities[entity.entity_id] = entity

    entities_by_label = {
        entity.label.casefold(): entity for entity in entities.values()
    }
    for declaration in declarations:
        source_value = " ".join(declaration.group("value").split()).strip(" -:")
        source_label, details = _record_parts(source_value)
        source = entities_by_label.get(source_label.casefold())
        if source is None:
            continue
        for relation in DECLARED_RELATION.finditer(details):
            target_label = relation.group("target").strip(" .,:;")
            target = entities_by_label.get(target_label.casefold())
            if target is None:
                continue
            edge = _edge(
                chunk,
                source,
                target,
                DECLARED_RELATIONSHIPS[relation.group("verb").casefold()],
            )
            relationships[
                (edge.source_entity_id, edge.target_entity_id, edge.relationship)
            ] = edge

    return PassageGraph(
        entities=tuple(entities.values()),
        relationships=tuple(relationships.values()),
    )


def extract_passage_graph(chunk: DocumentChunk) -> PassageGraph:
    """Extract labeled records, machine registers, and stated constraints."""
    register = _register_graph(chunk)
    constraints = _constraint_graph(chunk)
    declared = _declared_records_graph(chunk)
    entities = {
        entity.entity_id: entity
        for entity in (
            *register.entities,
            *constraints.entities,
            *declared.entities,
        )
    }
    relationships = {
        (edge.source_entity_id, edge.target_entity_id, edge.relationship): edge
        for edge in (
            *register.relationships,
            *constraints.relationships,
            *declared.relationships,
        )
    }
    passage = _entity(
        chunk,
        kind="Passage",
        natural_key=chunk.chunk_id,
        label=f"{chunk.source_id} page {chunk.page_number}",
        properties={
            "chunk_id": chunk.chunk_id,
            "section": chunk.section,
            "synthetic": chunk.synthetic,
        },
    )
    passage = passage.model_copy(
        update={"entity_id": f"chunk:{chunk.chunk_id}"}
    )
    entities[passage.entity_id] = passage
    for entity in tuple(entities.values()):
        if entity.entity_type == "Passage":
            continue
        evidence_edge = _edge(chunk, entity, passage, "SUPPORTED_BY")
        relationships[
            (
                evidence_edge.source_entity_id,
                evidence_edge.target_entity_id,
                evidence_edge.relationship,
            )
        ] = evidence_edge
    return PassageGraph(
        entities=tuple(entities.values()),
        relationships=tuple(relationships.values()),
    )
