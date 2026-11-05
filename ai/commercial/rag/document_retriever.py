"""Local document ingestion and hybrid, provenance-preserving RAG retrieval."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai.commercial.rag.chunking import chunk_document
from ai.commercial.rag.embeddings import EmbeddingProvider, create_embedder
from ai.commercial.rag.ingestion import (
    DocumentIngestionError,
    IMAGE_EXTENSIONS,
    fingerprint_document,
    ingest_document,
)
from ai.commercial.rag.neo4j_graph import Neo4jTopicGraph
from ai.commercial.rag.query_planner import (
    MACHINE_STATUS_QUERY,
    RetrievalQuery,
    build_retrieval_query,
)
from ai.commercial.rag.store import LocalRAGIndex
from ai.commercial.schemas.communication import (
    AgentError,
    EvidenceRef,
    ToolObservation,
)

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]*", re.IGNORECASE)
NORMALIZE_ANCHOR = re.compile(r"[^a-z0-9_]+")
ANCHOR_TOKEN = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
ASSET_IDENTIFIER = re.compile(r"\b[A-Z]{3}-[A-Z0-9]{2}\b")
MACHINE_STATUS_RECORD = re.compile(
    r"\b(?:machine\s*(?:id\s*)?[#:-]?\s*"
    r"(?P<machine_id>[a-z0-9][a-z0-9._/-]*)|"
    r"(?P<asset_id>[a-z]{2,6}-[a-z0-9]+))"
    r"[^.;\r\n|]{0,80}?\b"
    r"(?P<status>running|working|operational|active|online|stopped|idle|"
    r"offline|maintenance|fault|broken|down|inactive)\b",
    re.IGNORECASE,
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".md",
    ".txt",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".csv",
} | set(IMAGE_EXTENSIONS)


@dataclass(frozen=True)
class DocumentLoadIssue:
    """A configured source that is missing or cannot provide searchable text."""

    source_id: str
    message: str


def _tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def _normalize_anchor(text: str) -> str:
    return NORMALIZE_ANCHOR.sub(
        " ",
        text.casefold().replace("-", " "),
    ).strip()


def _matches_anchor(phrase: str, text: str) -> bool:
    normalized_text = _normalize_anchor(text)
    normalized_phrase = _normalize_anchor(phrase)
    if normalized_phrase in normalized_text:
        return True
    phrase_tokens = set(ANCHOR_TOKEN.findall(normalized_phrase))
    text_tokens = set(ANCHOR_TOKEN.findall(normalized_text))
    return bool(phrase_tokens) and phrase_tokens.issubset(text_tokens)


def _machine_status_summaries(
    query: str,
    matches: list[sqlite3.Row],
) -> list[str]:
    if not MACHINE_STATUS_QUERY.search(query):
        return []

    records_by_source: dict[str, dict[str, set[str]]] = {}
    synthetic_sources: set[str] = set()
    for row in matches:
        source_id = str(row["source_id"])
        if bool(row["synthetic"]):
            synthetic_sources.add(source_id)
        for segment in re.split(r"[\r\n;|]+|(?<=[.!?])\s+", str(row["text"])):
            for record in MACHINE_STATUS_RECORD.finditer(segment):
                machine_id = (
                    record.group("machine_id") or record.group("asset_id")
                )
                status = record.group("status")
                if machine_id and status:
                    records_by_source.setdefault(source_id, {}).setdefault(
                        machine_id.casefold(), set()
                    ).add(status.casefold())

    summaries = []
    working_statuses = {
        "running",
        "working",
        "operational",
        "active",
        "online",
    }
    for source_id, records in records_by_source.items():
        if not records or any(len(statuses) != 1 for statuses in records.values()):
            continue
        working_count = sum(
            next(iter(statuses)) in working_statuses
            for statuses in records.values()
        )
        label = (
            "the uploaded synthetic demonstration document"
            if source_id in synthetic_sources
            else "the uploaded document"
        )
        summaries.append(
            f"According to {label}, {working_count} of {len(records)} "
            "identified machine records are marked as running, working, "
            "operational, active, or online."
        )
    return summaries


class PDFDocumentRetriever:
    """Ingest local documents and search persistent hybrid indexes."""

    def __init__(
        self,
        document_paths: tuple[Path, ...],
        *,
        max_results: int = 4,
        min_score: float = 0.25,
        allowed_root: Path | None = None,
        upload_root: Path | None = None,
        index_path: Path | None = None,
        max_document_bytes: int = 50_000_000,
        max_pdf_pages: int = 1000,
        max_ocr_pages: int = 20,
        max_extracted_characters: int = 10_000_000,
        conversion_timeout_seconds: int = 120,
        ocr_enabled: bool = True,
        ocr_timeout_seconds: int = 30,
        ocr_render_scale: float = 3.0,
        tesseract_cmd: Path | None = None,
        embedding_provider: str = "hash",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_cache_dir: str | None = None,
        graph_backend: Literal["sqlite", "neo4j"] = "sqlite",
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "",
        neo4j_password: str = "",
        neo4j_database: str = "neo4j",
    ) -> None:
        if not document_paths:
            raise ValueError("At least one configured PDF document is required.")
        source_ids = [Path(path).name for path in document_paths]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError(
                "Configured PDF filenames must be unique within the retrieval scope."
            )
        if max_results < 1:
            raise ValueError("max_results must be positive.")
        if not 0 <= min_score <= 1:
            raise ValueError("min_score must be between zero and one.")
        self.document_paths = tuple(Path(path) for path in document_paths)
        self.max_results = max_results
        self.min_score = min_score
        self.allowed_root = (
            allowed_root
            or PROJECT_ROOT / "docs" / "ai_commercial"
        )
        self.upload_root = upload_root
        if self.upload_root is not None:
            self.upload_root.mkdir(parents=True, exist_ok=True)
        self.max_document_bytes = max_document_bytes
        self.max_pdf_pages = max_pdf_pages
        self.max_ocr_pages = max_ocr_pages
        self.max_extracted_characters = max_extracted_characters
        self.conversion_timeout_seconds = conversion_timeout_seconds
        self.ocr_enabled = ocr_enabled
        self.ocr_timeout_seconds = ocr_timeout_seconds
        self.ocr_render_scale = ocr_render_scale
        self.tesseract_cmd = tesseract_cmd
        cache_dir = embedding_cache_dir or str(
            PROJECT_ROOT / "data" / "commercial" / "rag" / "models"
        )
        self.embedder: EmbeddingProvider = create_embedder(
            embedding_provider,
            embedding_model,
            cache_dir,
        )
        self.index = LocalRAGIndex(
            index_path
            or PROJECT_ROOT / "data" / "commercial" / "rag" / "index.sqlite3"
        )
        self._processed_hashes: dict[str, str] = {}
        self._processed_file_stats: dict[str, tuple[int, int]] = {}
        self.graph_backend = graph_backend
        self.neo4j_graph: Neo4jTopicGraph | None = None
        self._neo4j_synced_hashes: dict[str, str] = {}
        if graph_backend == "neo4j":
            self.neo4j_graph = Neo4jTopicGraph(
                uri=neo4j_uri,
                username=neo4j_username,
                password=neo4j_password,
                database=neo4j_database,
            )
        elif graph_backend != "sqlite":
            raise ValueError(f"Unsupported graph backend: {graph_backend!r}")

    def index_documents(self, *, force: bool = False) -> dict[str, object]:
        """Validate, extract, chunk, and persist configured and uploaded sources."""
        report: list[dict[str, object]] = []
        paths = list(self.document_paths)
        if self.upload_root is not None:
            paths.extend(
                path
                for path in self.upload_root.iterdir()
                if path.is_file()
                and path.suffix.casefold() in UPLOAD_DOCUMENT_EXTENSIONS
            )
        for path in paths:
            source_id = path.name
            try:
                resolved = path.resolve(strict=True)
                root = (
                    self.upload_root
                    if self.upload_root is not None
                    and resolved.is_relative_to(self.upload_root.resolve())
                    else self.allowed_root
                )
                resolved.relative_to(root.resolve(strict=True))
            except (OSError, ValueError):
                root = self.allowed_root
            if not path.is_file():
                self.index.remove_document(source_id)
                self._processed_hashes.pop(source_id, None)
                self._processed_file_stats.pop(source_id, None)
                if self.neo4j_graph is not None:
                    self.neo4j_graph.remove_document(source_id)
                    self._neo4j_synced_hashes.pop(source_id, None)
                report.append(
                    {
                        "source_id": source_id,
                        "status": "unavailable",
                        "message": "Document is missing; its data is not available.",
                    }
                )
                continue
            try:
                file_stat = path.stat()
            except OSError as exc:
                self.index.remove_document(source_id)
                self._processed_hashes.pop(source_id, None)
                self._processed_file_stats.pop(source_id, None)
                if self.neo4j_graph is not None:
                    self.neo4j_graph.remove_document(source_id)
                    self._neo4j_synced_hashes.pop(source_id, None)
                report.append(
                    {
                        "source_id": source_id,
                        "status": "unavailable",
                        "message": (
                            "Document metadata could not be read "
                            f"({type(exc).__name__})."
                        ),
                    }
                )
                continue
            current_file_stats = (file_stat.st_size, file_stat.st_mtime_ns)
            if (
                not force
                and source_id in self._processed_hashes
                and self._processed_file_stats.get(source_id)
                == current_file_stats
            ):
                report.append({"source_id": source_id, "status": "unchanged"})
                continue
            try:
                resolved_path, _, content_hash = fingerprint_document(
                    path,
                    allowed_root=root,
                    max_document_bytes=self.max_document_bytes,
                )
                if (
                    not force
                    and self._processed_hashes.get(source_id) == content_hash
                ):
                    self._processed_file_stats[source_id] = current_file_stats
                    report.append(
                        {"source_id": source_id, "status": "unchanged"}
                    )
                    continue
                if (
                    not force
                    and self.index.is_current(
                        source_id,
                        content_hash,
                        self.embedder.model_id,
                        retry_ocr=self.ocr_enabled,
                    )
                ):
                    self._processed_hashes[source_id] = content_hash
                    self._processed_file_stats[source_id] = current_file_stats
                    self._sync_neo4j_document(source_id)
                    report.append(
                        {"source_id": source_id, "status": "unchanged"}
                    )
                    continue
                document = ingest_document(
                    resolved_path,
                    allowed_root=root,
                    max_document_bytes=self.max_document_bytes,
                    max_pdf_pages=self.max_pdf_pages,
                    max_ocr_pages=self.max_ocr_pages,
                    max_extracted_characters=self.max_extracted_characters,
                    conversion_timeout_seconds=self.conversion_timeout_seconds,
                    ocr_enabled=self.ocr_enabled,
                    ocr_timeout_seconds=self.ocr_timeout_seconds,
                    ocr_render_scale=self.ocr_render_scale,
                    tesseract_cmd=self.tesseract_cmd,
                )
                chunks = chunk_document(document)
                self.index.index_document(
                    source_id=document.source_id,
                    source_path=document.path,
                    content_sha256=document.sha256,
                    size_bytes=document.size_bytes,
                    page_count=len(document.pages),
                    extraction_methods=[
                        page.extraction_method for page in document.pages
                    ],
                    ingestion_issues=document.issues,
                    chunks=chunks,
                    embedder=self.embedder,
                )
                self._processed_hashes[source_id] = content_hash
                indexed_stat = resolved_path.stat()
                self._processed_file_stats[source_id] = (
                    indexed_stat.st_size,
                    indexed_stat.st_mtime_ns,
                )
                self._sync_neo4j_document(source_id)
                report.append(
                    {
                        "source_id": source_id,
                        "status": "indexed",
                        "page_count": len(document.pages),
                        "chunk_count": len(chunks),
                        "extraction_methods": sorted(
                            {
                                page.extraction_method
                                for page in document.pages
                            }
                        ),
                        "issues": list(document.issues),
                    }
                )
            except DocumentIngestionError as exc:
                self.index.remove_document(source_id)
                self._processed_hashes.pop(source_id, None)
                self._processed_file_stats.pop(source_id, None)
                if self.neo4j_graph is not None:
                    self.neo4j_graph.remove_document(source_id)
                    self._neo4j_synced_hashes.pop(source_id, None)
                report.append(
                    {
                        "source_id": source_id,
                        "status": "unavailable",
                        "message": str(exc),
                    }
                )
        return {
            "documents": report,
            "index_counts": self.index.index_counts(),
        }

    def remove_uploaded_document(self, source_id: str) -> bool:
        """Remove an indexed upload and all of its local and graph index data."""
        if self.upload_root is None:
            return False

        document = next(
            (
                item
                for item in self.index.indexed_documents()
                if item["source_id"] == source_id
            ),
            None,
        )
        if document is None:
            return False

        upload_root = self.upload_root.resolve(strict=True)
        document_path = Path(str(document["path"])).resolve()
        try:
            document_path.relative_to(upload_root)
        except ValueError as exc:
            raise ValueError("The indexed document is outside the upload directory.") from exc
        if document_path.parent != upload_root or document_path.name != source_id:
            raise ValueError("The indexed upload path does not match its source ID.")

        if self.neo4j_graph is not None:
            self.neo4j_graph.remove_document(source_id)
        self.index.remove_document(source_id)
        self._processed_hashes.pop(source_id, None)
        self._processed_file_stats.pop(source_id, None)
        self._neo4j_synced_hashes.pop(source_id, None)
        document_path.unlink(missing_ok=True)
        return True

    def clear_uploaded_documents(self) -> int:
        """Remove all files and index entries contained in the upload directory."""
        if self.upload_root is None:
            return 0

        upload_root = self.upload_root.resolve(strict=True)
        removed_files = 0
        for document in self.index.indexed_documents():
            source_id = str(document["source_id"])
            document_path = Path(str(document["path"])).resolve()
            if document_path.parent != upload_root or document_path.name != source_id:
                continue
            if self.remove_uploaded_document(source_id):
                removed_files += 1

        for path in upload_root.iterdir():
            if not path.is_file() and not path.is_symlink():
                continue
            if (
                path.suffix.casefold() not in UPLOAD_DOCUMENT_EXTENSIONS
                and not path.name.endswith(".upload")
            ):
                continue
            if path.exists() or path.is_symlink():
                path.unlink()
                removed_files += 1
        return removed_files

    def _sync_neo4j_document(self, source_id: str) -> None:
        if self.neo4j_graph is None:
            return
        document = next(
            (
                item
                for item in self.index.indexed_documents()
                if item["source_id"] == source_id
            ),
            None,
        )
        if document is None:
            self.neo4j_graph.remove_document(source_id)
            self._neo4j_synced_hashes.pop(source_id, None)
            return
        content_sha256 = str(document["sha256"])
        if self._neo4j_synced_hashes.get(source_id) == content_sha256:
            return
        self.neo4j_graph.sync_document(
            source_id=source_id,
            content_sha256=content_sha256,
            source_path=str(document["path"]),
            pages=int(document["page_count"]),
            passages=self.index.chunks_for_document(source_id),
            context_graph=self.index.context_graph_for_document(source_id),
        )
        self._neo4j_synced_hashes[source_id] = content_sha256

    def retrieve(self, query: str) -> ToolObservation:
        """Return focused, cited passages or a structured unavailable result."""
        retrieval_query = build_retrieval_query(query)
        if retrieval_query.status == "needs_clarification":
            return self._unavailable(
                "QUERY_NEEDS_CLARIFICATION",
                retrieval_query.reason or "A more specific query is required.",
                [],
                retrieval_query=retrieval_query,
                original_query=query,
            )

        index_report = self.index_documents()
        source_ids = tuple(
            dict.fromkeys(
                path.name
                for path in (
                    self.document_paths
                    + tuple(
                        path
                        for path in (
                            self.upload_root.iterdir()
                            if self.upload_root is not None
                            else ()
                        )
                        if path.is_file()
                    )
                )
            )
        )
        configured_source_ids = {path.name for path in self.document_paths}
        issues = self._document_issues(index_report, source_ids)
        query_terms = _tokenize(retrieval_query.search_text)
        if not query_terms:
            return self._unavailable(
                "DATA_NOT_AVAILABLE",
                "No searchable terms were found in the request.",
                issues,
                retrieval_query=retrieval_query,
                original_query=query,
            )

        lexical = self.index.lexical_search(
            query_terms,
            self.max_results * 4,
            source_ids,
        )
        query_vector = self.embedder.embed(retrieval_query.search_text)
        vector = self.index.vector_search(
            query_vector,
            self.embedder.model_id,
            self.max_results * 4,
            source_ids,
        )
        vector_ranked = [
            chunk_id
            for chunk_id, score in vector
            if score >= self.min_score
        ]
        graph = (
            self.neo4j_graph.search(
                retrieval_query.topics,
                source_ids,
                self.max_results * 4,
            )
            if self.neo4j_graph is not None
            else self.index.graph_search(
                retrieval_query.topics,
                self.max_results * 4,
                source_ids,
            )
        )
        asset_ids = ASSET_IDENTIFIER.findall(query)
        context_graph = (
            self.neo4j_graph.search_entities(
                asset_ids,
                source_ids,
                self.max_results * 4,
            )
            if self.neo4j_graph is not None
            else self.index.context_graph_search(
                asset_ids,
                self.max_results * 4,
                source_ids,
            )
        )
        ranked_ids = self.index.reciprocal_rank_fusion(
            (lexical, vector_ranked, graph, context_graph),
            self.max_results * 8,
        )
        rows = self.index.get_chunks(ranked_ids, source_ids)
        by_id = {str(row["chunk_id"]): row for row in rows}
        if "equipment_register" in retrieval_query.topics:
            rank = {chunk_id: position for position, chunk_id in enumerate(ranked_ids)}
            ranked_ids.sort(
                key=lambda chunk_id: self._equipment_register_priority(
                    by_id.get(chunk_id),
                    rank.get(chunk_id, len(rank)),
                )
            )

        eligible_rows = []
        seen_content: set[tuple[str, int, str | None, str]] = set()
        for chunk_id in ranked_ids:
            row = by_id.get(chunk_id)
            if row is None:
                continue
            if (
                retrieval_query.status == "factory_specific"
                and bool(row["synthetic"])
                and str(row["source_id"]) in configured_source_ids
            ):
                continue
            content_key = (
                str(row["document_sha256"]),
                int(row["page_number"]),
                str(row["section"]) if row["section"] is not None else None,
                str(row["text"]),
            )
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            eligible_rows.append(row)

        anchor_rows = [
            row
            for row in eligible_rows
            if retrieval_query.anchor_phrases
            and any(
                _matches_anchor(phrase, str(row["text"]))
                for phrase in retrieval_query.anchor_phrases
            )
        ]
        if retrieval_query.anchor_phrases:
            anchor_sections = {
                (
                    str(row["document_sha256"]),
                    int(row["page_number"]),
                    str(row["section"]) if row["section"] is not None else None,
                )
                for row in anchor_rows
            }
            anchor_chunk_ids = {str(row["chunk_id"]) for row in anchor_rows}
            candidates = [
                *anchor_rows,
                *(
                    row
                    for row in eligible_rows
                    if str(row["chunk_id"]) not in anchor_chunk_ids
                    and (
                        str(row["document_sha256"]),
                        int(row["page_number"]),
                        str(row["section"]) if row["section"] is not None else None,
                    )
                    in anchor_sections
                ),
            ]
        else:
            candidates = eligible_rows
        matches = candidates[: self.max_results]

        if not matches:
            if not self.index.index_counts()["chunks"]:
                message = "No readable document text is available for retrieval."
            elif retrieval_query.status == "factory_specific":
                message = (
                    "No factory-specific data is available from an actual, "
                    "non-demonstration operations record. Configured demonstration "
                    "documents are not treated as real factory data."
                )
            else:
                message = (
                    "The provided documents do not contain matching information."
                )
            return self._unavailable(
                "DATA_NOT_AVAILABLE",
                message,
                issues,
                retrieval_query=retrieval_query,
                original_query=query,
            )

        findings = _machine_status_summaries(query, matches)
        references: list[EvidenceRef] = []
        passages: list[dict[str, object]] = []
        for row in matches:
            section = str(row["section"]) if row["section"] else None
            page_number = int(row["page_number"])
            text = str(row["text"])
            source_id = str(row["source_id"])
            synthetic = bool(row["synthetic"])
            method = str(row["extraction_method"])
            label = (
                "Fictional demonstration data only; not measured or actual "
                "factory data. "
                if synthetic
                else ""
            )
            findings.append(
                f"{label}Source excerpt (page {page_number}): {text}"
            )
            locator = f"page:{page_number}"
            if section:
                locator += f";section:{section[:350]}"
            locator += f";sha256:{row['document_sha256']}"
            references.append(
                EvidenceRef(
                    source_id=source_id,
                    source_type=(
                        "local_pdf"
                        if source_id.casefold().endswith(".pdf")
                        else "local_document"
                    ),
                    locator=locator,
                    excerpt=text,
                    extraction_confidence=0.6 if method == "local_ocr" else 1.0,
                    synthetic=synthetic,
                )
            )
            passages.append(
                {
                    "source_id": source_id,
                    "page": page_number,
                    "section": section,
                    "text": text,
                    "extraction_method": method,
                    "document_sha256": str(row["document_sha256"]),
                    "topics": json.loads(row["topics_json"]),
                    "synthetic": synthetic,
                }
            )

        return ToolObservation(
            status="available",
            findings=tuple(findings),
            data={
                "retrieved_passages": passages,
                "retrieval_methods": [
                    "bm25",
                    "local_vector",
                    "topic_graph",
                    "context_graph",
                    "reciprocal_rank_fusion",
                ],
                "index_counts": self.index.index_counts(),
                "query": {
                    "original": query,
                    "search_text": retrieval_query.search_text,
                    "topics": list(retrieval_query.topics),
                    "anchor_phrases": list(retrieval_query.anchor_phrases),
                    "status": retrieval_query.status,
                },
            },
            evidence_refs=tuple(references),
            assumptions=tuple(issue.message for issue in issues),
        )

    @staticmethod
    def _equipment_register_priority(
        row: sqlite3.Row | None,
        rank: int,
    ) -> tuple[int, int]:
        if row is None:
            return (3, rank)
        section = str(row["section"] or "").casefold()
        text = str(row["text"])
        if (
            "machine register" in section
            and ASSET_IDENTIFIER.search(text)
            and re.search(r"\d+(?:\.\d+)?\s*kW", text, re.IGNORECASE)
        ):
            return (0, rank)
        if "machine register" in section:
            return (1, rank)
        return (2, rank)

    def _document_issues(
        self,
        index_report: dict[str, object],
        source_ids: tuple[str, ...],
    ) -> list[DocumentLoadIssue]:
        issues: list[DocumentLoadIssue] = []
        documents = index_report.get("documents", [])
        if isinstance(documents, list):
            for item in documents:
                if not isinstance(item, dict):
                    continue
                if item.get("status") == "unavailable":
                    issues.append(
                        DocumentLoadIssue(
                            str(item.get("source_id", "unknown")),
                            str(item.get("message", "Document is unavailable.")),
                        )
                    )
                for message in item.get("issues", []):
                    if isinstance(message, str):
                        issues.append(
                            DocumentLoadIssue(
                                str(item.get("source_id", "unknown")),
                                message,
                            )
                        )
        for document in self.index.indexed_documents():
            if document["source_id"] not in source_ids:
                continue
            methods = document["extraction_methods"]
            if "unavailable" in methods:
                issues.append(
                    DocumentLoadIssue(
                        str(document["source_id"]),
                        "No searchable text was extracted; the source needs "
                        "readable text before it can provide evidence.",
                    )
                )
            for message in document["ingestion_issues"]:
                issues.append(
                    DocumentLoadIssue(
                        str(document["source_id"]),
                        str(message),
                    )
                )
        unique: dict[tuple[str, str], DocumentLoadIssue] = {}
        for issue in issues:
            unique[(issue.source_id, issue.message)] = issue
        return list(unique.values())

    @staticmethod
    def _unavailable(
        code: str,
        message: str,
        issues: list[DocumentLoadIssue],
        *,
        retrieval_query: RetrievalQuery,
        original_query: str,
    ) -> ToolObservation:
        details = "; ".join(issue.message for issue in issues)
        return ToolObservation(
            status="unavailable",
            error=AgentError(
                code=code,
                message=f"{message} {details}".strip(),
            ),
            data={
                "query": {
                    "original": original_query,
                    "search_text": retrieval_query.search_text,
                    "topics": list(retrieval_query.topics),
                    "anchor_phrases": list(retrieval_query.anchor_phrases),
                    "status": retrieval_query.status,
                    "reason": retrieval_query.reason,
                }
            },
            assumptions=tuple(issue.message for issue in issues),
        )
