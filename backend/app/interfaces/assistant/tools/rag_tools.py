"""LangChain tools for Document Knowledge and Regulatory Standards Retrieval (RAG).

Provides tools for querying official regulations, standards, gazette notifications,
and technical manuals with full citation and provenance tracking.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.rag.retriever import HybridDocumentRetriever, RetrievedChunk


class SearchRegulatoryDocumentsInput(BaseModel):
    """Input for searching authoritative regulatory documents and standards."""

    query: str = Field(
        ...,
        description="Search query describing the technical regulation, standard, or requirement (e.g. 'electrical wiring conductor size IS 732', '5 star AC ISEER criteria')",
    )
    publisher: Optional[str] = Field(
        default=None,
        description="Optional filter by issuing body: 'BIS', 'BEE', 'CEA', or 'DISCOM'",
    )
    document_identifier: Optional[str] = Field(
        default=None,
        description="Optional specific document code (e.g. 'IS 732', 'BEE/S&L/AC/Schedule-2022')",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional maximum number of relevant passages. Omit to search across all "
            "indexed documents, returning up to two relevant passages per source document."
        ),
    )


class SearchRegulatoryDocumentsTool(BaseTool):
    """Searches official Indian energy and electrical standards (BIS, CEA, BEE, DISCOMs)."""

    name: str = "search_regulatory_documents"
    description: str = (
        "Search the indexed official documents for evidence-backed answers about Indian electricity "
        "regulations, electrical safety, BIS/IS standards, CEA rules, BEE schedules, or DISCOM "
        "orders. Use for a technical/topic question that needs relevant passages or citations. "
        "Provide the user's subject and, when known, publisher/document_identifier. Returns "
        "retrieved excerpts and citations; do not use this for numeric household telemetry."
    )
    args_schema: Type[BaseModel] = SearchRegulatoryDocumentsInput
    retriever: Any = None

    def __init__(self, retriever: HybridDocumentRetriever, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.retriever = retriever

    def _run(
        self,
        query: str,
        publisher: Optional[str] = None,
        document_identifier: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> str:
        if not self.retriever:
            return json.dumps({"error": "Retriever not configured on SearchRegulatoryDocumentsTool."})

        results: List[RetrievedChunk] = self.retriever.search(
            query=query,
            top_k=top_k,
            publisher=publisher,
            document_identifier=document_identifier,
        )

        if not results:
            return json.dumps({
                "message": f"No official regulatory excerpts found matching query: '{query}'",
                "results": [],
            })

        output_items = []
        for r in results:
            output_items.append({
                "source_id": r.source_id,
                "document_identifier": r.document_identifier,
                "publisher": r.publisher,
                "heading": r.heading,
                "clause_id": r.clause_id,
                "page": r.page_number,
                "content": r.content,
                "score": r.score,
                "category": r.category,
                "parent_heading": r.parent_heading,
                "parent_context": r.parent_context,
                "tags": r.tags,
                "citation": r.to_citation(),
            })

        return json.dumps({"query": query, "total_found": len(output_items), "excerpts": output_items}, indent=2)


class GetDocumentClauseInput(BaseModel):
    """Input for retrieving a specific regulatory clause by identifier."""

    document_identifier: str = Field(
        ...,
        description="Exact known standard or document identifier, e.g. 'IS 732'.",
    )
    clause_id: str = Field(
        ...,
        description="Exact known clause/section number; use search_regulatory_documents if unknown.",
    )


class GetDocumentClauseTool(BaseTool):
    """Retrieves an exact verified clause from an official standard or gazette."""

    name: str = "get_document_clause"
    description: str = (
        "Retrieve the indexed text of one exact clause from a known official standard. Use only "
        "when both the document identifier and clause number are known or stated by the user. "
        "If the relevant clause is not known, use search_regulatory_documents to discover it. "
        "Returns source details and a citation; never invent clause text."
    )
    args_schema: Type[BaseModel] = GetDocumentClauseInput
    retriever: Any = None

    def __init__(self, retriever: HybridDocumentRetriever, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.retriever = retriever

    def _run(self, document_identifier: str, clause_id: str) -> str:
        if not self.retriever:
            return json.dumps({"error": "Retriever not configured."})

        results = self.retriever.search(
            query=f"{document_identifier} {clause_id}",
            top_k=5,
            document_identifier=document_identifier,
        )
        matching = [r for r in results if r.clause_id and clause_id.lower() in r.clause_id.lower()]
        target = matching[0] if matching else (results[0] if results else None)

        if not target:
            return json.dumps({"error": f"Clause '{clause_id}' in document '{document_identifier}' was not found."})

        return json.dumps({
            "document_identifier": target.document_identifier,
            "publisher": target.publisher,
            "clause_id": target.clause_id,
            "heading": target.heading,
            "page": target.page_number,
            "content": target.content,
            "citation": target.to_citation(),
        }, indent=2)
