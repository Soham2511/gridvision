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
    top_k: int = Field(
        default=3,
        ge=1,
        le=8,
        description="Maximum number of relevant document passages to return",
    )


class SearchRegulatoryDocumentsTool(BaseTool):
    """Searches official Indian energy and electrical standards (BIS, CEA, BEE, DISCOMs)."""

    name: str = "search_regulatory_documents"
    description: str = (
        "Search authoritative official energy regulations, electrical codes, and government standards "
        "(e.g., National Electrical Code IS 732, BEE Star Rating Schedules, CEA Grid Emission Database, "
        "and State DISCOM retail supply orders). Returns verified excerpts with section citations."
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
        top_k: int = 3,
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
                "citation": r.to_citation(),
            })

        return json.dumps({"query": query, "total_found": len(output_items), "excerpts": output_items}, indent=2)


class GetDocumentClauseInput(BaseModel):
    """Input for retrieving a specific regulatory clause by identifier."""

    document_identifier: str = Field(..., description="Document identifier, e.g. 'IS 732 / NEC India'")
    clause_id: str = Field(..., description="Specific clause number, e.g. 'clause_4.1', 'clause_5.1'")


class GetDocumentClauseTool(BaseTool):
    """Retrieves an exact verified clause from an official standard or gazette."""

    name: str = "get_document_clause"
    description: str = "Look up the exact text and specifications of a specific clause in an official standard."
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

