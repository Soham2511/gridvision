"""Structure-Aware Document Extractor for GridVision Reference Data Infrastructure.

Parses regulatory, standards, and technical documents (PDF, plain text, and JSON) into
structured representations preserving page numbers, sections, clauses, tables, footnotes,
and provenance excerpts.
"""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pypdf

from app.services.reference.exceptions import ExtractionError

logger = logging.getLogger(__name__)


class StructureAwareExtractor:
    """Extracts structured document representations preserving hierarchy and provenance."""

    # Regex patterns for structural identification
    RE_SECTION = re.compile(
        r"^(?:#+\s+|Section\s+(\d+(?:\.\d+)*)[:\s\-]+|Schedule\s+(\d+(?:\.\d+)*)[:\s\-]+|(\d+)\.0?\s+)(.*)$",
        re.IGNORECASE,
    )
    RE_CLAUSE = re.compile(
        r"^(?:Clause\s+)?(\d+\.\d+(?:\.\d+)*)\s*(?:[:\-]\s*)?(.*)$",
        re.IGNORECASE,
    )
    RE_TABLE_TITLE = re.compile(
        r"^(?:Table\s+(\d+(?:\.\d+)*)|Table\s+([A-Za-z0-9_\-]+))[:\s\-]+(.*)$",
        re.IGNORECASE,
    )
    RE_FOOTNOTE = re.compile(
        r"^(?:Note\s*(\d*)|Footnote\s*(\d*)|\*|\[\^?(\d+)\])\s*[:\-]\s*(.*)$",
        re.IGNORECASE,
    )
    RE_PIPE_ROW = re.compile(r"^\s*\|(.*)\|\s*$")
    RE_PIPE_SEPARATOR = re.compile(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$")

    def __init__(self) -> None:
        pass

    def extract(
        self,
        content: bytes,
        doc_format: str = "pdf",
        source_id: str = "source_default",
        document_identifier: str = "",
    ) -> Dict[str, Any]:
        """Extract structured representation from document content.

        Args:
            content: Raw document bytes.
            doc_format: 'pdf', 'text', 'json', or 'docx'.
            source_id: Unique source identifier.
            document_identifier: Regulatory document identifier (e.g. 'BEE/S&L/AC/2022').

        Returns:
            Dictionary adhering to ExtractedDocumentStructure interface contract.

        Raises:
            ExtractionError: If document extraction fails or content is unparseable.
        """
        if not content:
            raise ExtractionError("Cannot extract from empty content.")

        clean_format = doc_format.lower().strip()

        if clean_format == "pdf":
            return self._extract_pdf(content, source_id, document_identifier)
        elif clean_format in ("text", "txt"):
            return self._extract_text(content.decode("utf-8", errors="replace"), source_id, document_identifier)
        elif clean_format == "json":
            return self._extract_json(content, source_id, document_identifier)
        elif clean_format in ("docx", "zip"):
            # Fallback text extraction for docx XML text
            return self._extract_docx(content, source_id, document_identifier)
        else:
            # Fallback to UTF-8 text interpretation
            try:
                decoded = content.decode("utf-8")
                return self._extract_text(decoded, source_id, document_identifier)
            except Exception as exc:
                raise ExtractionError(f"Unsupported format '{doc_format}' for extraction: {exc}") from exc

    def _extract_pdf(self, content: bytes, source_id: str, document_identifier: str) -> Dict[str, Any]:
        """Extract structure from PDF document using pypdf."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
        except Exception as exc:
            raise ExtractionError(f"Failed to initialize PDF reader: {exc}") from exc

        num_pages = len(reader.pages)
        if num_pages == 0:
            raise ExtractionError("PDF contains 0 pages.")

        page_texts: List[Tuple[int, str]] = []
        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                logger.warning("Error extracting text from PDF page %d: %s", page_num, exc)
                text = ""
            page_texts.append((page_num, text))

        return self._build_structure_from_pages(page_texts, source_id, document_identifier, "pdf")

    def _extract_text(self, text: str, source_id: str, document_identifier: str) -> Dict[str, Any]:
        """Extract structure from plain text with page breaks or synthetic pagination."""
        # Split by form feed (\f) if present
        if "\f" in text:
            raw_pages = text.split("\f")
        else:
            # Check for explicit page markers like '--- Page 1 ---' or '=== Page 1 ==='
            page_marker_split = re.split(r"(?:---|\=\=\=)\s*Page\s+\d+\s*(?:---|\=\=\=)", text)
            if len(page_marker_split) > 1:
                raw_pages = [p for p in page_marker_split if p.strip()]
            else:
                # Group lines into pages of ~60 lines
                lines = text.splitlines()
                chunk_size = 60
                raw_pages = [
                    "\n".join(lines[i : i + chunk_size]) for i in range(0, len(lines), chunk_size)
                ] or [""]

        page_texts = [(idx + 1, page_content) for idx, page_content in enumerate(raw_pages)]
        return self._build_structure_from_pages(page_texts, source_id, document_identifier, "text")

    def _extract_docx(self, content: bytes, source_id: str, document_identifier: str) -> Dict[str, Any]:
        """Extract text from docx archive and parse structure."""
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                if "word/document.xml" not in zf.namelist():
                    raise ExtractionError("DOCX archive missing word/document.xml")
                xml_data = zf.read("word/document.xml")
                root = ET.fromstring(xml_data)
                # Extract all text elements
                paragraphs: List[str] = []
                for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    texts = [t.text for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if t.text]
                    if texts:
                        paragraphs.append("".join(texts))
                full_text = "\n".join(paragraphs)
                return self._extract_text(full_text, source_id, document_identifier)
        except Exception as exc:
            raise ExtractionError(f"Failed to extract DOCX structure: {exc}") from exc

    def _extract_json(self, content: bytes, source_id: str, document_identifier: str) -> Dict[str, Any]:
        """Extract structure from pre-formatted or arbitrary JSON."""
        try:
            parsed = json.loads(content.decode("utf-8"))
        except Exception as exc:
            raise ExtractionError(f"Failed to parse JSON document: {exc}") from exc

        # If it's already an ExtractedDocumentStructure representation
        if isinstance(parsed, dict) and "pages" in parsed and "sections" in parsed:
            # Ensure provenance map is populated
            if "provenance_map" not in parsed:
                parsed["provenance_map"] = {}
            return parsed

        # Otherwise convert key-values into sections/tables
        sections: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        provenance_map: Dict[str, Any] = {}
        pages: List[Dict[str, Any]] = []

        if isinstance(parsed, dict):
            page_text_lines = []
            for k, v in parsed.items():
                sec_id = f"sec_{k}"
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    # Convert list of dicts to a table
                    headers = list(v[0].keys())
                    rows = [[row.get(h) for h in headers] for row in v]
                    tbl_id = f"table_{k}"
                    table_obj = {
                        "table_id": tbl_id,
                        "title": f"Dataset for {k}",
                        "page_number": 1,
                        "headers": headers,
                        "rows": rows,
                        "section_id": sec_id,
                    }
                    tables.append(table_obj)
                    prov_key = f"{source_id}:p1:tbl_{tbl_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": 1,
                        "table_id": tbl_id,
                        "excerpt": f"Table: {table_obj['title']} ({len(rows)} rows)",
                        "context": k,
                    }
                else:
                    text_val = str(v)
                    sec_obj = {
                        "section_id": sec_id,
                        "title": k,
                        "page_number": 1,
                        "clauses": [
                            {
                                "clause_id": f"clause_{k}_1",
                                "title": k,
                                "text": text_val,
                                "page_number": 1,
                            }
                        ],
                    }
                    sections.append(sec_obj)
                    prov_key = f"{source_id}:p1:sec_{sec_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": 1,
                        "section_id": sec_id,
                        "excerpt": text_val[:200],
                        "context": k,
                    }
                page_text_lines.append(f"{k}: {v}")

            pages.append({
                "page_number": 1,
                "text": "\n".join(page_text_lines),
                "sections": [s["section_id"] for s in sections],
                "tables": [t["table_id"] for t in tables],
                "footnotes": [],
            })

        return {
            "source_id": source_id,
            "document_identifier": document_identifier,
            "pages": pages,
            "sections": sections,
            "tables": tables,
            "footnotes": [],
            "provenance_map": provenance_map,
            "metadata": {
                "page_count": len(pages),
                "section_count": len(sections),
                "table_count": len(tables),
                "footnote_count": 0,
                "format": "json",
            },
        }

    def _build_structure_from_pages(
        self,
        pages_data: List[Tuple[int, str]],
        source_id: str,
        document_identifier: str,
        detected_format: str,
    ) -> Dict[str, Any]:
        """Parse raw page texts into structured sections, clauses, tables, footnotes, and provenance."""
        extracted_pages: List[Dict[str, Any]] = []
        all_sections: List[Dict[str, Any]] = []
        all_tables: List[Dict[str, Any]] = []
        all_footnotes: List[Dict[str, Any]] = []
        provenance_map: Dict[str, Any] = {}

        current_section: Optional[Dict[str, Any]] = None
        current_clause: Optional[Dict[str, Any]] = None

        global_table_counter = 1
        global_footnote_counter = 1
        global_section_counter = 1

        for page_num, raw_text in pages_data:
            lines = raw_text.splitlines()
            page_section_ids: List[str] = []
            page_table_ids: List[str] = []
            page_footnote_ids: List[str] = []

            line_idx = 0
            while line_idx < len(lines):
                line = lines[line_idx].strip()
                if not line:
                    line_idx += 1
                    continue

                # 1. Check for Footnotes / Notes
                m_fn = self.RE_FOOTNOTE.match(line)
                if m_fn:
                    fn_num = m_fn.group(1) or m_fn.group(2) or m_fn.group(3) or str(global_footnote_counter)
                    fn_text = m_fn.group(4).strip()
                    fn_id = f"fn_p{page_num}_{fn_num}"
                    footnote_obj = {
                        "footnote_id": fn_id,
                        "page_number": page_num,
                        "marker": f"Note {fn_num}" if fn_num.isdigit() else "*",
                        "text": fn_text,
                    }
                    all_footnotes.append(footnote_obj)
                    page_footnote_ids.append(fn_id)
                    global_footnote_counter += 1

                    prov_key = f"{source_id}:p{page_num}:fn_{fn_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": page_num,
                        "footnote_id": fn_id,
                        "excerpt": fn_text,
                        "context": f"Footnote on Page {page_num}",
                    }
                    line_idx += 1
                    continue

                # 2. Check for Table Start
                m_tbl = self.RE_TABLE_TITLE.match(line)
                is_pipe_table_start = bool(self.RE_PIPE_ROW.match(line))

                if m_tbl or is_pipe_table_start:
                    table_title = ""
                    tbl_identifier = ""
                    if m_tbl:
                        tbl_identifier = m_tbl.group(1) or m_tbl.group(2) or str(global_table_counter)
                        table_title = m_tbl.group(3).strip()
                        line_idx += 1
                        # Skip blank lines between title and rows
                        while line_idx < len(lines) and not lines[line_idx].strip():
                            line_idx += 1
                    else:
                        tbl_identifier = str(global_table_counter)
                        table_title = f"Table on Page {page_num}"

                    table_id = f"table_{tbl_identifier}"
                    headers: List[str] = []
                    rows: List[List[Any]] = []

                    # Parse table rows (pipe-delimited or whitespace-separated)
                    col_starts: List[int] = []
                    while line_idx < len(lines):
                        tbl_line = lines[line_idx].strip()
                        if not tbl_line:
                            # Peek ahead across blank lines to see if table continues
                            peek_t = line_idx + 1
                            while peek_t < len(lines) and not lines[peek_t].strip():
                                peek_t += 1
                            if peek_t < len(lines):
                                cand = lines[peek_t].strip()
                                if headers and (self.RE_PIPE_ROW.match(cand) or (cand.startswith("|") and cand.endswith("|"))):
                                    line_idx = peek_t
                                    tbl_line = lines[line_idx].strip()
                                else:
                                    break
                            else:
                                break

                        # Check if line starts a new section or footnote
                        if self.RE_SECTION.match(tbl_line) or self.RE_FOOTNOTE.match(tbl_line):
                            break

                        # Check for pipe table row
                        if tbl_line.startswith("|"):
                            accum = tbl_line
                            while line_idx + 1 < len(lines):
                                next_raw = lines[line_idx + 1].strip()
                                if accum.startswith("|") and accum.endswith("|"):
                                    if headers:
                                        cells_peek = [c.strip() for c in accum[1:-1].split("|")]
                                        if len(cells_peek) >= len(headers) or next_raw.startswith("|"):
                                            break
                                    else:
                                        break
                                if not next_raw or self.RE_SECTION.match(next_raw) or self.RE_FOOTNOTE.match(next_raw) or self.RE_TABLE_TITLE.match(next_raw):
                                    break
                                line_idx += 1
                                accum = accum + " " + next_raw
                                if accum.startswith("|") and accum.endswith("|") and headers:
                                    cells_peek = [c.strip() for c in accum[1:-1].split("|")]
                                    if len(cells_peek) >= len(headers):
                                        break

                            # Skip markdown delimiter line |---|---|
                            if self.RE_PIPE_SEPARATOR.match(accum):
                                line_idx += 1
                                continue

                            pipe_m = self.RE_PIPE_ROW.match(accum)
                            if pipe_m:
                                cells = [c.strip() for c in pipe_m.group(1).split("|")]
                            else:
                                cells = [c.strip() for c in accum.strip("|").split("|")]

                            if not headers:
                                headers = cells
                            else:
                                rows.append(cells)
                            line_idx += 1

                        elif "\t" in tbl_line or "   " in tbl_line or (col_starts and len(tbl_line) >= col_starts[0]):
                            # Tabular line (tab-separated or whitespace-aligned)
                            if "\t" in tbl_line:
                                cells = [c.strip() for c in tbl_line.split("\t")]
                                if not headers:
                                    headers = cells
                                else:
                                    if len(cells) < len(headers):
                                        cells.extend([""] * (len(headers) - len(cells)))
                                    rows.append(cells)
                            else:
                                if not headers:
                                    matches = list(re.finditer(r"[^\t\s]+(?:\s[^\t\s]+)*", tbl_line))
                                    headers = [m.group().strip() for m in matches]
                                    col_starts = [m.start() for m in matches]
                                else:
                                    token_matches = list(re.finditer(r"[^\t\s]+(?:\s[^\t\s]+)*", tbl_line))
                                    if token_matches and col_starts:
                                        cells = [""] * len(headers)
                                        for tm in token_matches:
                                            t_start = tm.start()
                                            t_text = tm.group().strip()
                                            best_col = min(range(len(col_starts)), key=lambda i: abs(col_starts[i] - t_start))
                                            if cells[best_col]:
                                                cells[best_col] += " " + t_text
                                            else:
                                                cells[best_col] = t_text
                                        rows.append(cells)
                                    else:
                                        cells = [c.strip() for c in re.split(r"\t+|\s{2,}", tbl_line) if c.strip()]
                                        if cells:
                                            rows.append(cells)
                            line_idx += 1
                        else:
                            # Not a table row
                            break

                    if headers or rows:
                        table_obj = {
                            "table_id": table_id,
                            "title": table_title,
                            "page_number": page_num,
                            "headers": headers,
                            "rows": rows,
                            "section_id": current_section["section_id"] if current_section else None,
                        }
                        all_tables.append(table_obj)
                        page_table_ids.append(table_id)
                        global_table_counter += 1

                        # Record provenance for each row in the table
                        for r_idx, r_val in enumerate(rows):
                            row_excerpt = " | ".join(str(c) for c in r_val)
                            prov_key = f"{source_id}:p{page_num}:tbl_{table_id}:r{r_idx}"
                            provenance_map[prov_key] = {
                                "source_id": source_id,
                                "document_identifier": document_identifier,
                                "page_number": page_num,
                                "table_id": table_id,
                                "row_index": r_idx,
                                "headers": headers,
                                "row_values": r_val,
                                "excerpt": row_excerpt,
                                "context": f"{table_title} (Row {r_idx + 1})",
                            }
                    continue

                # 3. Check for Section Heading
                m_sec = self.RE_SECTION.match(line)
                if m_sec:
                    sec_token = m_sec.group(1) or m_sec.group(2) or m_sec.group(3) or str(global_section_counter)
                    sec_title = (m_sec.group(4) or "").strip()
                    if not sec_title:
                        sec_title = line

                    sec_id = f"sec_{sec_token.replace('.', '_')}"
                    current_section = {
                        "section_id": sec_id,
                        "title": sec_title,
                        "page_number": page_num,
                        "clauses": [],
                    }
                    all_sections.append(current_section)
                    page_section_ids.append(sec_id)
                    current_clause = None
                    global_section_counter += 1

                    prov_key = f"{source_id}:p{page_num}:sec_{sec_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": page_num,
                        "section_id": sec_id,
                        "excerpt": f"{line}",
                        "context": sec_title,
                    }
                    line_idx += 1
                    continue

                # 4. Check for Clause / Subclause
                m_cl = self.RE_CLAUSE.match(line)
                if m_cl:
                    cl_num = m_cl.group(1)
                    cl_title = m_cl.group(2).strip() or f"Clause {cl_num}"
                    cl_id = f"clause_{cl_num.replace('.', '_')}"

                    # Accumulate following paragraph lines belonging to this clause across blank lines
                    clause_paragraphs: List[str] = []
                    current_para: List[str] = [line]
                    line_idx += 1
                    while line_idx < len(lines):
                        peek_idx = line_idx
                        while peek_idx < len(lines) and not lines[peek_idx].strip():
                            peek_idx += 1
                        if peek_idx >= len(lines):
                            line_idx = peek_idx
                            break
                        next_candidate = lines[peek_idx].strip()
                        if (
                            self.RE_SECTION.match(next_candidate)
                            or self.RE_CLAUSE.match(next_candidate)
                            or self.RE_TABLE_TITLE.match(next_candidate)
                            or self.RE_FOOTNOTE.match(next_candidate)
                            or self.RE_PIPE_ROW.match(next_candidate)
                        ):
                            line_idx = peek_idx
                            break
                        if peek_idx > line_idx:
                            if current_para:
                                clause_paragraphs.append(" ".join(current_para))
                            current_para = [next_candidate]
                        else:
                            current_para.append(next_candidate)
                        line_idx = peek_idx + 1

                    if current_para:
                        clause_paragraphs.append(" ".join(current_para))
                    clause_text = "\n\n".join(clause_paragraphs)
                    clause_obj = {
                        "clause_id": cl_id,
                        "title": cl_title,
                        "text": clause_text,
                        "page_number": page_num,
                    }

                    if current_section is not None:
                        current_section["clauses"].append(clause_obj)
                    else:
                        # Auto-create default section if clause precedes formal section
                        default_sec = {
                            "section_id": f"sec_p{page_num}_intro",
                            "title": "General Requirements",
                            "page_number": page_num,
                            "clauses": [clause_obj],
                        }
                        all_sections.append(default_sec)
                        current_section = default_sec
                        page_section_ids.append(default_sec["section_id"])

                    prov_key = f"{source_id}:p{page_num}:clause_{cl_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": page_num,
                        "section_id": current_section["section_id"],
                        "clause_id": cl_id,
                        "excerpt": clause_text,
                        "context": cl_title,
                    }
                    continue

                # 5. General body paragraph / Unnumbered section body
                body_paragraphs: List[str] = []
                current_para = [line]
                line_idx += 1
                while line_idx < len(lines):
                    peek_idx = line_idx
                    while peek_idx < len(lines) and not lines[peek_idx].strip():
                        peek_idx += 1
                    if peek_idx >= len(lines):
                        line_idx = peek_idx
                        break
                    next_candidate = lines[peek_idx].strip()
                    if (
                        self.RE_SECTION.match(next_candidate)
                        or self.RE_CLAUSE.match(next_candidate)
                        or self.RE_TABLE_TITLE.match(next_candidate)
                        or self.RE_FOOTNOTE.match(next_candidate)
                        or self.RE_PIPE_ROW.match(next_candidate)
                    ):
                        line_idx = peek_idx
                        break
                    if peek_idx > line_idx:
                        if current_para:
                            body_paragraphs.append(" ".join(current_para))
                        current_para = [next_candidate]
                    else:
                        current_para.append(next_candidate)
                    line_idx = peek_idx + 1

                if current_para:
                    body_paragraphs.append(" ".join(current_para))
                body_text = "\n\n".join(body_paragraphs)

                if current_section is not None:
                    intro_id = f"clause_{current_section['section_id']}_body"
                    existing_intro = next(
                        (c for c in current_section["clauses"] if c["clause_id"] == intro_id),
                        None,
                    )
                    if existing_intro:
                        existing_intro["text"] += "\n\n" + body_text
                    else:
                        intro_clause = {
                            "clause_id": intro_id,
                            "title": current_section["title"],
                            "text": body_text,
                            "page_number": page_num,
                        }
                        current_section["clauses"].append(intro_clause)

                    prov_key = f"{source_id}:p{page_num}:clause_{intro_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": page_num,
                        "section_id": current_section["section_id"],
                        "clause_id": intro_id,
                        "excerpt": current_section["clauses"][0]["text"] if existing_intro else body_text,
                        "context": current_section["title"],
                    }
                else:
                    default_sec = {
                        "section_id": f"sec_p{page_num}_intro",
                        "title": "General Requirements",
                        "page_number": page_num,
                        "clauses": [],
                    }
                    intro_id = f"clause_{default_sec['section_id']}_body"
                    intro_clause = {
                        "clause_id": intro_id,
                        "title": default_sec["title"],
                        "text": body_text,
                        "page_number": page_num,
                    }
                    default_sec["clauses"].append(intro_clause)
                    all_sections.append(default_sec)
                    current_section = default_sec
                    page_section_ids.append(default_sec["section_id"])

                    prov_key = f"{source_id}:p{page_num}:clause_{intro_id}"
                    provenance_map[prov_key] = {
                        "source_id": source_id,
                        "document_identifier": document_identifier,
                        "page_number": page_num,
                        "section_id": default_sec["section_id"],
                        "clause_id": intro_id,
                        "excerpt": body_text,
                        "context": default_sec["title"],
                    }
                continue

            extracted_pages.append({
                "page_number": page_num,
                "text": raw_text,
                "sections": list(dict.fromkeys(page_section_ids)),
                "tables": page_table_ids,
                "footnotes": page_footnote_ids,
            })

        return {
            "source_id": source_id,
            "document_identifier": document_identifier,
            "pages": extracted_pages,
            "sections": all_sections,
            "tables": all_tables,
            "footnotes": all_footnotes,
            "provenance_map": provenance_map,
            "metadata": {
                "page_count": len(extracted_pages),
                "section_count": len(all_sections),
                "table_count": len(all_tables),
                "footnote_count": len(all_footnotes),
                "format": detected_format,
            },
        }
