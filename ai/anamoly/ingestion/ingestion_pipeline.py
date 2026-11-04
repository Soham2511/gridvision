"""Incrementally ingest web-scraped and manually supplied knowledge files."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ai.anamoly.config import get_settings
from ai.anamoly.ingestion.chunking import chunk_document
from ai.anamoly.ingestion.document_loader import discover_documents, load_document
from ai.anamoly.vector_store.indexer import VectorIndexer

logger = logging.getLogger(__name__)


def _read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    entries: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as manifest:
        for line_number, line in enumerate(manifest, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid source manifest line {line_number}.") from exc
            local_path = record.get("local_path")
            if local_path:
                normalized = str(local_path).replace("\\", "/").lstrip("./")
                entries[normalized] = record
                entries[f"crawled/{normalized}"] = record
    return entries


def ingest_directory(source_root: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    """Discover and incrementally index every supported document in a directory."""
    source_root = source_root.expanduser().resolve()
    files = discover_documents(source_root)
    manifest = _read_manifest(manifest_path) if manifest_path else {}
    indexer = VectorIndexer()
    outcome: dict[str, Any] = {
        "source": str(source_root),
        "discovered": len(files),
        "indexed_documents": 0,
        "indexed_chunks": 0,
        "unchanged_documents": 0,
        "failed": [],
    }

    for path in files:
        relative = path.relative_to(source_root).as_posix()
        source_metadata = manifest.get(relative, {})
        try:
            document = load_document(path, source_root, source_metadata)
            chunks = chunk_document(document, source_root=str(source_root))
            result = indexer.index_document(
                document.document_id, document.content_sha256, chunks
            )
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("Failed to ingest knowledge document %s", relative)
            outcome["failed"].append({"source_path": relative, "error": str(exc)})
            continue
        if result["unchanged"]:
            outcome["unchanged_documents"] += 1
        else:
            outcome["indexed_documents"] += 1
            outcome["indexed_chunks"] += int(result["indexed"])

    if outcome["failed"]:
        outcome["status"] = "partial_failure"
    else:
        outcome["status"] = "completed"
    return outcome


def ingest_knowledge_base() -> dict[str, Any]:
    """Ingest existing scraped files and the manual source directory, if present."""
    settings = get_settings()
    sources = [
        (settings.knowledge_base_path, settings.knowledge_base_path / "manifest.jsonl"),
        (
            settings.raw_knowledge_base_path,
            settings.raw_knowledge_base_path / "crawled" / "manifest.jsonl",
        ),
    ]
    results = [ingest_directory(source, manifest) for source, manifest in sources if source.exists()]
    if not results:
        raise FileNotFoundError(
            "No anomaly knowledge directory was found. Expected knowledge_base/raw "
            "or raw_knowledge_base."
        )
    return {
        "status": "completed" if all(item["status"] == "completed" for item in results) else "partial_failure",
        "sources": results,
        "documents_discovered": sum(item["discovered"] for item in results),
        "documents_indexed": sum(item["indexed_documents"] for item in results),
        "chunks_indexed": sum(item["indexed_chunks"] for item in results),
        "documents_unchanged": sum(item["unchanged_documents"] for item in results),
        "failures": [failure for item in results for failure in item["failed"]],
    }


def delete_source_document(source_root: Path, source_path: Path) -> int:
    """Delete an indexed source by its path relative to the configured source root."""
    import hashlib

    if not source_path.is_absolute():
        source_path = source_root / source_path
    relative = source_path.expanduser().resolve().relative_to(
        source_root.expanduser().resolve()
    )
    document_id = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()
    return VectorIndexer().delete_document(document_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Ingest just this source directory.")
    parser.add_argument("--manifest", type=Path, help="JSONL source manifest for --source.")
    parser.add_argument(
        "--delete-source",
        type=Path,
        help="Delete one indexed source using its path relative to --source-root.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=get_settings().knowledge_base_path,
        help="Root that was used to generate the source's stable document ID.",
    )
    args = parser.parse_args()
    if args.delete_source:
        deleted_chunks = delete_source_document(args.source_root, args.delete_source)
        print(json.dumps({"status": "completed", "deleted_chunks": deleted_chunks}))
        return
    result = (
        ingest_directory(args.source, args.manifest)
        if args.source
        else ingest_knowledge_base()
    )
    print(json.dumps(result, indent=2))
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
