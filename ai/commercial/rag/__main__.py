"""Command-line entry point for the local Commercial RAG pipeline."""

from __future__ import annotations

import argparse
import json

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.rag.document_retriever import PDFDocumentRetriever


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or query the local Commercial document RAG index."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Ingest configured local documents.")
    index.add_argument(
        "--force",
        action="store_true",
        help="Re-extract and rebuild even when the source hash is unchanged.",
    )
    commands.add_parser("status", help="Show local index counts and sources.")
    query = commands.add_parser("query", help="Run hybrid retrieval.")
    query.add_argument("question", help="Question to retrieve evidence for.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = CommercialSettings.from_env()
    retriever = PDFDocumentRetriever(
        settings.rag_documents,
        max_results=settings.rag_max_results,
        min_score=settings.rag_min_score,
        allowed_root=settings.rag_allowed_root,
        index_path=settings.rag_index_path,
        max_document_bytes=settings.rag_max_document_bytes,
        max_pdf_pages=settings.rag_max_pdf_pages,
        max_ocr_pages=settings.rag_max_ocr_pages,
        max_extracted_characters=settings.rag_max_extracted_characters,
        conversion_timeout_seconds=settings.rag_conversion_timeout_seconds,
        ocr_enabled=settings.rag_ocr_enabled,
        ocr_timeout_seconds=settings.rag_ocr_timeout_seconds,
        ocr_render_scale=settings.rag_ocr_render_scale,
        tesseract_cmd=settings.rag_tesseract_cmd,
        embedding_provider=settings.rag_embedding_provider,
        embedding_model=settings.rag_embedding_model,
        embedding_cache_dir=str(settings.rag_index_path.parent / "models"),
        graph_backend=settings.rag_graph_backend,
        neo4j_uri=settings.rag_neo4j_uri,
        neo4j_username=settings.rag_neo4j_username,
        neo4j_password=settings.rag_neo4j_password.get_secret_value(),
        neo4j_database=settings.rag_neo4j_database,
    )

    if args.command == "index":
        result = retriever.index_documents(force=args.force)
    elif args.command == "status":
        result = {
            "index_path": str(settings.rag_index_path),
            "graph_backend": settings.rag_graph_backend,
            "counts": retriever.index.index_counts(),
            "documents": retriever.index.indexed_documents(),
        }
    else:
        result = retriever.retrieve(args.question).model_dump(mode="json")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
