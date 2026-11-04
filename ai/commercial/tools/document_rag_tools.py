"""Commercial tool adapter using configured local documents for Operations retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.rag.document_retriever import PDFDocumentRetriever
from ai.commercial.schemas.communication import ToolObservation
from ai.commercial.tools.commercial_forecast_api import (
    CommercialForecastAPITools,
)
from ai.commercial.tools.cost_optimizer import optimize_schedule
from ai.commercial.tools.renewable_energy import RenewableEnergyTools


class DocumentRAGCommercialTools:
    """Provide local Operations RAG, backend forecasts, and explicit unavailable tools."""

    def __init__(
        self,
        document_paths: tuple[Path, ...],
        *,
        settings: CommercialSettings | None = None,
        max_results: int = 4,
        min_score: float = 0.25,
    ) -> None:
        if settings is None:
            self._retriever = PDFDocumentRetriever(
                document_paths,
                max_results=max_results,
                min_score=min_score,
            )
        else:
            self._retriever = PDFDocumentRetriever(
                document_paths,
                max_results=settings.rag_max_results,
                min_score=settings.rag_min_score,
                allowed_root=settings.rag_allowed_root,
                upload_root=settings.rag_uploads_root,
                index_path=settings.rag_index_path,
                max_document_bytes=settings.rag_max_document_bytes,
                max_pdf_pages=settings.rag_max_pdf_pages,
                max_ocr_pages=settings.rag_max_ocr_pages,
                max_extracted_characters=(
                    settings.rag_max_extracted_characters
                ),
                conversion_timeout_seconds=(
                    settings.rag_conversion_timeout_seconds
                ),
                ocr_enabled=settings.rag_ocr_enabled,
                ocr_timeout_seconds=settings.rag_ocr_timeout_seconds,
                ocr_render_scale=settings.rag_ocr_render_scale,
                tesseract_cmd=settings.rag_tesseract_cmd,
                embedding_provider=settings.rag_embedding_provider,
                embedding_model=settings.rag_embedding_model,
                embedding_cache_dir=str(
                    settings.rag_index_path.parent / "models"
                ),
                graph_backend=settings.rag_graph_backend,
                neo4j_uri=settings.rag_neo4j_uri,
                neo4j_username=settings.rag_neo4j_username,
                neo4j_password=(
                    settings.rag_neo4j_password.get_secret_value()
                ),
                neo4j_database=settings.rag_neo4j_database,
            )
        self._forecast = CommercialForecastAPITools(
            base_url=(
                settings.commercial_forecast_api_base_url
                if settings is not None
                else "http://127.0.0.1:5000/api/v1"
            ),
            timeout_seconds=(
                settings.commercial_forecast_api_timeout_seconds
                if settings is not None
                else 5.0
            ),
        )
        self._renewable = RenewableEnergyTools(
            api_key_file=(
                settings.tavily_api_key_file
                if settings is not None
                else Path(__file__).resolve().parents[3]
                / "key_vault"
                / "tavily"
                / "api.key"
            ),
            timeout_seconds=(
                settings.tavily_timeout_seconds if settings is not None else 12.0
            ),
        )

    @property
    def retriever(self) -> PDFDocumentRetriever:
        """Return the shared retriever used by retrieval and upload routes."""
        return self._retriever

    def get_peak_forecast(
        self,
        factory_id: str | None,
        goal: str,
        building_id: str | None = None,
    ) -> ToolObservation:
        return self._forecast.get_peak_forecast(
            factory_id,
            goal,
            building_id,
        )

    def get_commercial_buildings(self, limit: int = 20) -> ToolObservation:
        return self._forecast.get_commercial_buildings(limit)

    def retrieve_operational_context(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        del factory_id
        return self._retriever.retrieve(goal)

    def get_renewable_scenarios(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        return self._renewable.get_renewable_scenarios(factory_id, goal)

    def optimize(
        self, factory_id: str | None, inputs: dict[str, Any]
    ) -> ToolObservation:
        del factory_id
        return optimize_schedule(inputs)
