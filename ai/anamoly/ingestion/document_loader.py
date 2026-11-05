"""Load supported reference documents into page-aware text records."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".json"}
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class DocumentPage:
    text: str
    page_number: int | None


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    document_id: str
    content_sha256: str
    title: str
    pages: tuple[DocumentPage, ...]
    metadata: dict[str, Any]


class _VisibleTextParser(HTMLParser):
    """Extract visible body text while ignoring scripts and styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def _html_text(raw: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw)
    parser.close()
    return "\n".join(
        line.strip() for line in "".join(parser.parts).splitlines() if line.strip()
    )


def discover_documents(source_root: Path) -> list[Path]:
    """Return supported files in stable order, excluding oversized files."""
    if not source_root.exists():
        return []
    if not source_root.is_dir():
        raise ValueError(f"Knowledge source must be a directory: {source_root}")
    return sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and path.stat().st_size <= MAX_DOCUMENT_BYTES
        and path.name.lower() != "manifest.jsonl"
    )


def _extract_pages(path: Path) -> tuple[DocumentPage, ...]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF ingestion requires the pypdf dependency.") from exc
        reader = PdfReader(str(path))
        return tuple(
            DocumentPage(page.extract_text() or "", page_number=index)
            for index, page in enumerate(reader.pages, start=1)
        )

    raw = path.read_text(encoding="utf-8")
    if suffix in {".html", ".htm"}:
        raw = _html_text(raw)
    elif suffix == ".json":
        raw = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    return (DocumentPage(raw, page_number=None),)


def load_document(
    path: Path,
    source_root: Path,
    metadata: dict[str, Any] | None = None,
) -> SourceDocument:
    """Extract one supported document while preserving source metadata."""
    if not path.is_file():
        raise FileNotFoundError(f"Knowledge document does not exist: {path}")
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Knowledge document exceeds the 20 MiB limit: {path.name}")
    relative_path = path.resolve().relative_to(source_root.resolve()).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source_metadata = dict(metadata or {})
    source_metadata.setdefault("source_url", source_metadata.get("url", ""))
    source_metadata.setdefault(
        "publisher",
        source_metadata.get("source_domain", source_metadata.get("publisher", "")),
    )
    source_metadata.setdefault(
        "publication_date",
        source_metadata.get("published_date", source_metadata.get("publication_date", "")),
    )
    title = str(source_metadata.get("title") or path.stem.replace("_", " "))
    source_metadata.update(
        {
            "document_id": hashlib.sha256(relative_path.encode("utf-8")).hexdigest(),
            "content_sha256": digest,
            "source_path": relative_path,
            "title": title,
        }
    )
    return SourceDocument(
        path=path,
        document_id=source_metadata["document_id"],
        content_sha256=digest,
        title=title,
        pages=_extract_pages(path),
        metadata=source_metadata,
    )
