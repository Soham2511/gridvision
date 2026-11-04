"""Provenance-aware document section and chunk construction."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ai.commercial.rag.ingestion import IngestedDocument

MAX_CHUNK_CHARACTERS = 700
MAX_REGISTER_CHUNK_CHARACTERS = 2500
CHUNKER_VERSION = 10
SECTION_HEADER = re.compile(
    r"^(?:\d+\.\s+|"
    r"Compressed-air systems:|Motors and pumps:|Cooling and HVAC:|"
    r"Furnaces and process heating:|Lighting:)",
    re.IGNORECASE,
)
PAGE_MARKER = re.compile(
    r"^(?:GRIDVISION \| DEMONSTRATION DATA|Page \d+)",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass(frozen=True)
class DocumentChunk:
    """A passage carrying document identity, page, and section provenance."""

    chunk_id: str
    source_id: str
    document_sha256: str
    page_number: int
    section: str | None
    text: str
    extraction_method: str
    synthetic: bool


def _split_text(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal current_heading, body_lines
        separator = (
            "\n"
            if current_heading
            and "machine register" in current_heading.casefold()
            else " "
        )
        body = separator.join(
            " ".join(line.split()) for line in body_lines if line.strip()
        )
        if body:
            sections.append((current_heading, body))
        elif current_heading:
            sections.append((current_heading, current_heading))
        current_heading = None
        body_lines = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line or PAGE_MARKER.match(line):
            continue
        if SECTION_HEADER.match(line):
            flush()
            current_heading = line
        else:
            body_lines.append(line)
    flush()

    chunks: list[tuple[str | None, str]] = []
    for heading, body in sections:
        if heading and "machine register" in heading.casefold():
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            current_lines: list[str] = []
            prefix = f"{heading}\n"
            for line in lines:
                candidate = prefix + "\n".join((*current_lines, line))
                if (
                    current_lines
                    and len(candidate) > MAX_REGISTER_CHUNK_CHARACTERS
                ):
                    chunks.append((heading, prefix + "\n".join(current_lines)))
                    current_lines = [line]
                else:
                    current_lines.append(line)
            if current_lines:
                chunks.append((heading, prefix + "\n".join(current_lines)))
            continue

        sentences = SENTENCE_BOUNDARY.split(body)
        current: list[str] = []
        for sentence in sentences:
            candidate = " ".join((*current, sentence))
            prefix = f"{heading} " if heading else ""
            if current and len(prefix) + len(candidate) > MAX_CHUNK_CHARACTERS:
                chunks.append((heading, f"{prefix}{' '.join(current)}".strip()))
                current = [sentence]
            else:
                current.append(sentence)
        if current:
            prefix = f"{heading} " if heading else ""
            chunks.append((heading, f"{prefix}{' '.join(current)}".strip()))
    return chunks


def chunk_document(document: IngestedDocument) -> list[DocumentChunk]:
    """Split extracted pages while preserving page and section provenance."""
    document_text = " ".join(
        " ".join(page.text.split()).casefold()
        for page in document.pages
    )
    is_synthetic = document.synthetic or (
        "not an actual factory record" in document_text
        or (
            "fictional" in document_text
            and (
                "demonstration" in document_text
                or "not measured" in document_text
            )
        )
    )
    chunks: list[DocumentChunk] = []
    for page in document.pages:
        if not page.text.strip():
            continue
        for position, (section, text) in enumerate(_split_text(page.text)):
            if page.extraction_method == "local_ocr":
                text = re.sub(
                    r"(?<=\d)kW\b",
                    " kW",
                    text,
                    flags=re.IGNORECASE,
                )
            chunk_id = hashlib.sha256(
                (
                    f"{document.source_id}\0{document.sha256}\0"
                    f"{page.page_number}\0{position}"
                ).encode("utf-8")
            ).hexdigest()
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    source_id=document.source_id,
                    document_sha256=document.sha256,
                    page_number=page.page_number,
                    section=section,
                    text=text,
                    extraction_method=page.extraction_method,
                    synthetic=is_synthetic,
                )
            )
    return chunks
