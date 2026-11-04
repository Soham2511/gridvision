"""Structure-Aware Document Chunker for Official Regulatory and Technical Documents.

Transforms structured document ASTs (sections, clauses, tables, footnotes) into
semantically coherent chunks preserving hierarchical context, table formatting,
and citation provenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DocumentChunk:
    """In-memory representation of a structured chunk ready for indexing."""

    chunk_id: str
    source_id: str
    document_identifier: str
    publisher: str
    chunk_type: str  # "section", "clause", "table", "footnote"
    section_id: Optional[str]
    clause_id: Optional[str]
    heading: Optional[str]
    page_number: int
    content: str
    tokens_est: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class StructureAwareChunker:
    """Decomposes extracted document ASTs into structure-preserving chunks."""

    def __init__(self, max_clause_words: int = 500, overlap_words: int = 50) -> None:
        self.max_clause_words = max_clause_words
        self.overlap_words = overlap_words

    def chunk_extracted_document(
        self,
        extracted_doc: Dict[str, Any],
        publisher: str = "BEE",
        effective_date: Optional[str] = None,
        jurisdiction: str = "IN",
        title: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Convert a StructureAwareExtractor output dictionary into DocumentChunk instances."""
        chunks: List[DocumentChunk] = []
        source_id = extracted_doc.get("source_id", "src_unknown")
        doc_id = extracted_doc.get("document_identifier", "doc_unknown")

        doc_category = extracted_doc.get("category", "regulatory")
        doc_tags = list(extracted_doc.get("tags", []))

        common_meta = {
            "source_id": source_id,
            "document_identifier": doc_id,
            "publisher": publisher,
            "effective_date": effective_date,
            "jurisdiction": jurisdiction,
            "title": title or doc_id,
            "category": doc_category,
            "tags": doc_tags,
        }

        # 1. Chunk Sections and Clauses
        sections = extracted_doc.get("sections", [])
        for sec in sections:
            sec_id = sec.get("id") or sec.get("section_id", "sec_root")
            sec_heading = sec.get("heading") or sec.get("title", "")
            sec_page = sec.get("page", 1)
            sec_clauses = sec.get("clauses", [])
            sec_body = sec.get("body", "")

            # If section has standalone body text before/without clauses, chunk it
            if sec_body and sec_body.strip():
                content_text = f"## {sec_heading}\n\n{sec_body.strip()}" if sec_heading else sec_body.strip()
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{source_id}_{sec_id}_body",
                        source_id=source_id,
                        document_identifier=doc_id,
                        publisher=publisher,
                        chunk_type="section",
                        section_id=sec_id,
                        clause_id=None,
                        heading=sec_heading,
                        page_number=sec_page,
                        content=content_text,
                        tokens_est=len(content_text.split()),
                        metadata={
                            **common_meta,
                            "section_heading": sec_heading,
                            "parent_path": sec_heading,
                            "parent_section_id": sec_id,
                            "parent_heading": sec_heading,
                            "parent_context": sec_body.strip() if sec_body else sec_heading,
                            "category": sec.get("category") or doc_category,
                            "tags": list(set(doc_tags + sec.get("tags", []))),
                        },
                    )
                )

            # Chunk each clause under the section with hierarchical prefix
            for clause in sec_clauses:
                c_id = clause.get("id") or clause.get("clause_id", "")
                c_title = clause.get("title") or clause.get("heading", "")
                c_text = clause.get("text") or clause.get("content", "")
                c_page = clause.get("page", sec_page)

                parent_prefix = f"[{sec_heading}] " if sec_heading else ""
                clause_header = f"### {parent_prefix}{c_title}\n\n" if c_title else (f"### {parent_prefix}Clause {c_id}\n\n" if c_id else "")
                full_clause_text = f"{clause_header}{c_text}".strip()

                words = full_clause_text.split()
                if len(words) <= self.max_clause_words:
                    chunks.append(
                        DocumentChunk(
                            chunk_id=f"{source_id}_{c_id or sec_id}_{len(chunks)}",
                            source_id=source_id,
                            document_identifier=doc_id,
                            publisher=publisher,
                            chunk_type="clause",
                            section_id=sec_id,
                            clause_id=c_id,
                            heading=c_title or sec_heading,
                            page_number=c_page,
                            content=full_clause_text,
                            tokens_est=len(words),
                            metadata={
                                **common_meta,
                                "section_heading": sec_heading,
                                "clause_title": c_title,
                                "parent_path": f"{sec_heading} > {c_title}" if sec_heading and c_title else (sec_heading or c_title),
                                "parent_section_id": sec_id,
                                "parent_heading": sec_heading,
                                "parent_context": sec_body.strip() if sec_body else sec_heading,
                                "category": clause.get("category") or sec.get("category") or doc_category,
                                "tags": list(set(doc_tags + sec.get("tags", []) + clause.get("tags", []))),
                            },
                        )
                    )
                else:
                    # Oversized clause: split across paragraphs while retaining prefix
                    paragraphs = full_clause_text.split("\n\n")
                    curr_para_block: List[str] = []
                    curr_words = 0
                    sub_idx = 1

                    for p in paragraphs:
                        p_words = len(p.split())
                        if curr_words + p_words > self.max_clause_words and curr_para_block:
                            block_content = f"{clause_header}(Part {sub_idx})\n\n" + "\n\n".join(curr_para_block)
                            chunks.append(
                                DocumentChunk(
                                    chunk_id=f"{source_id}_{c_id}_{sub_idx}",
                                    source_id=source_id,
                                    document_identifier=doc_id,
                                    publisher=publisher,
                                    chunk_type="clause",
                                    section_id=sec_id,
                                    clause_id=c_id,
                                    heading=f"{c_title} (Part {sub_idx})",
                                    page_number=c_page,
                                    content=block_content,
                                    tokens_est=len(block_content.split()),
                                    metadata={
                                        **common_meta,
                                        "section_heading": sec_heading,
                                        "clause_title": c_title,
                                        "part": sub_idx,
                                        "parent_path": f"{sec_heading} > {c_title} (Part {sub_idx})",
                                    },
                                )
                            )
                            sub_idx += 1
                            curr_para_block = [p]
                            curr_words = p_words
                        else:
                            curr_para_block.append(p)
                            curr_words += p_words

                    if curr_para_block:
                        block_content = f"{clause_header}(Part {sub_idx})\n\n" + "\n\n".join(curr_para_block)
                        chunks.append(
                            DocumentChunk(
                                chunk_id=f"{source_id}_{c_id}_{sub_idx}",
                                source_id=source_id,
                                document_identifier=doc_id,
                                publisher=publisher,
                                chunk_type="clause",
                                section_id=sec_id,
                                clause_id=c_id,
                                heading=f"{c_title} (Part {sub_idx})",
                                page_number=c_page,
                                content=block_content,
                                tokens_est=len(block_content.split()),
                                metadata={
                                    **common_meta,
                                    "section_heading": sec_heading,
                                    "clause_title": c_title,
                                    "part": sub_idx,
                                    "parent_path": f"{sec_heading} > {c_title} (Part {sub_idx})",
                                },
                            )
                        )

        # 2. Chunk Tables (preserve columns and structure with markdown)
        tables = extracted_doc.get("tables", [])
        for tbl_idx, tbl in enumerate(tables):
            t_id = tbl.get("id") or f"tbl_{tbl_idx + 1}"
            caption = tbl.get("caption") or tbl.get("title") or f"Table {tbl_idx + 1}"
            t_page = tbl.get("page", 1)
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])

            # Format markdown table
            lines: List[str] = [f"### Table: {caption}"]
            if headers:
                clean_headers = [str(h).strip().replace("\n", " ") for h in headers]
                lines.append("| " + " | ".join(clean_headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(clean_headers)) + " |")
            for r in rows:
                clean_row = [str(cell).strip().replace("\n", " ") for cell in r]
                # Pad row if uneven columns
                if headers and len(clean_row) < len(headers):
                    clean_row.extend([""] * (len(headers) - len(clean_row)))
                lines.append("| " + " | ".join(clean_row[: len(headers) if headers else None]) + " |")

            table_content = "\n".join(lines)
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{source_id}_{t_id}",
                    source_id=source_id,
                    document_identifier=doc_id,
                    publisher=publisher,
                    chunk_type="table",
                    section_id=None,
                    clause_id=None,
                    heading=caption,
                    page_number=t_page,
                    content=table_content,
                    tokens_est=len(table_content.split()),
                    metadata={
                        **common_meta,
                        "table_id": t_id,
                        "table_caption": caption,
                        "headers": headers,
                        "row_count": len(rows),
                        "parent_section_id": tbl.get("section_id"),
                        "parent_heading": tbl.get("section_heading") or caption,
                        "parent_context": tbl.get("caption") or caption,
                        "category": tbl.get("category") or doc_category,
                        "tags": list(set(doc_tags + tbl.get("tags", []))),
                    },
                )
            )

        # 3. Chunk Footnotes & Notes
        footnotes = extracted_doc.get("footnotes", [])
        for fn in footnotes:
            fn_id = fn.get("id") or f"fn_{len(chunks)}"
            fn_text = fn.get("text", "")
            fn_page = fn.get("page", 1)
            if not fn_text.strip():
                continue

            content_text = f"**Note / Footnote [{fn_id}]:** {fn_text.strip()}"
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{source_id}_{fn_id}",
                    source_id=source_id,
                    document_identifier=doc_id,
                    publisher=publisher,
                    chunk_type="footnote",
                    section_id=None,
                    clause_id=None,
                    heading=f"Note {fn_id}",
                    page_number=fn_page,
                    content=content_text,
                    tokens_est=len(content_text.split()),
                    metadata={
                        **common_meta,
                        "footnote_id": fn_id,
                    },
                )
            )

        return chunks

