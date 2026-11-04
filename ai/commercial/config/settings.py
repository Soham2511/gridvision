"""Validated execution limits for the Commercial workflow."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class CommercialSettings(BaseModel):
    """Bounds applied to every graph execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_provider: Literal["mock", "ollama"] = "mock"
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        min_length=1,
        max_length=500,
    )
    ollama_primary_model: str = Field(default="qwen3:8b", min_length=1)
    ollama_fallback_model: str = Field(default="gemma3:4b", min_length=1)
    ollama_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    tavily_api_key_file: Path = PROJECT_ROOT / "key_vault" / "tavily" / "api.key"
    tavily_timeout_seconds: float = Field(default=12.0, gt=0, le=30)
    commercial_forecast_api_base_url: str = Field(
        default="http://127.0.0.1:5000/api/v1",
        min_length=1,
        max_length=500,
    )
    commercial_forecast_api_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=30,
    )
    rag_documents: tuple[Path, ...] = (
        PROJECT_ROOT
        / "docs"
        / "ai_commercial"
        / "GridVision_Commercial_Energy_Knowledge_RAG.pdf",
        PROJECT_ROOT
        / "docs"
        / "ai_commercial"
        / "GridVision_Commercial_Operations_OCR_Input.pdf",
        PROJECT_ROOT
        / "docs"
        / "ai_commercial"
        / "GridVision_Automotive_Parts_Demo.md",
    )
    rag_allowed_root: Path = (
        PROJECT_ROOT / "docs" / "ai_commercial"
    )
    rag_index_path: Path = (
        PROJECT_ROOT / "data" / "commercial" / "rag" / "index.sqlite3"
    )
    rag_uploads_root: Path = (
        PROJECT_ROOT / "data" / "commercial" / "rag" / "uploads"
    )
    rag_max_document_bytes: int = Field(default=50_000_000, ge=1024)
    rag_max_pdf_pages: int = Field(default=1000, ge=1, le=5000)
    rag_max_ocr_pages: int = Field(default=20, ge=1, le=1000)
    rag_max_extracted_characters: int = Field(
        default=10_000_000,
        ge=1000,
        le=100_000_000,
    )
    rag_conversion_timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=600,
    )
    rag_ocr_enabled: bool = True
    rag_ocr_timeout_seconds: int = Field(default=30, ge=1, le=120)
    rag_ocr_render_scale: float = Field(default=3.0, ge=0.5, le=3.0)
    rag_tesseract_cmd: Path | None = None
    rag_embedding_provider: Literal["hash", "fastembed"] = "hash"
    rag_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        min_length=1,
        max_length=200,
    )
    rag_max_results: int = Field(default=4, ge=1, le=10)
    rag_min_score: float = Field(default=0.25, ge=0, le=1)
    rag_graph_backend: Literal["sqlite", "neo4j"] = "sqlite"
    rag_neo4j_uri: str = "bolt://localhost:7687"
    rag_neo4j_username: str = "neo4j"
    rag_neo4j_password: SecretStr = SecretStr("")
    rag_neo4j_database: str = "neo4j"
    max_graph_steps: int = Field(default=32, ge=8, le=128)
    max_tool_calls: int = Field(default=8, ge=1, le=64)
    max_rework_attempts: int = Field(default=1, ge=0, le=3)

    @classmethod
    def from_env(cls) -> CommercialSettings:
        """Load validated execution limits from Commercial-specific variables."""
        llm_provider = os.getenv(
            "COMMERCIAL_LLM_PROVIDER", "ollama"
        ).lower()
        if llm_provider in {"auto", "groq"}:
            llm_provider = "ollama"
        return cls(
            llm_provider=llm_provider,
            ollama_base_url=os.getenv(
                "COMMERCIAL_OLLAMA_BASE_URL",
                "http://127.0.0.1:11434",
            ),
            ollama_primary_model=os.getenv(
                "COMMERCIAL_OLLAMA_PRIMARY_MODEL", "qwen3:8b"
            ),
            ollama_fallback_model=os.getenv(
                "COMMERCIAL_OLLAMA_FALLBACK_MODEL", "gemma3:4b"
            ),
            ollama_timeout_seconds=float(
                os.getenv("COMMERCIAL_OLLAMA_TIMEOUT_SECONDS", "180")
            ),
            tavily_api_key_file=Path(
                os.getenv(
                    "TAVILY_API_KEY_FILE",
                    str(PROJECT_ROOT / "key_vault" / "tavily" / "api.key"),
                )
            ).expanduser(),
            tavily_timeout_seconds=float(
                os.getenv("TAVILY_TIMEOUT_SECONDS", "12")
            ),
            commercial_forecast_api_base_url=os.getenv(
                "COMMERCIAL_FORECAST_API_BASE_URL",
                "http://127.0.0.1:5000/api/v1",
            ),
            commercial_forecast_api_timeout_seconds=float(
                os.getenv("COMMERCIAL_FORECAST_API_TIMEOUT_SECONDS", "5")
            ),
            rag_documents=tuple(
                Path(path).expanduser()
                for path in os.getenv(
                    "COMMERCIAL_RAG_DOCUMENTS",
                    os.pathsep.join(
                        str(path)
                        for path in (
                            PROJECT_ROOT
                            / "docs"
                            / "ai_commercial"
                            / "GridVision_Commercial_Energy_Knowledge_RAG.pdf",
                            PROJECT_ROOT
                            / "docs"
                            / "ai_commercial"
                            / "GridVision_Commercial_Operations_OCR_Input.pdf",
                            PROJECT_ROOT
                            / "docs"
                            / "ai_commercial"
                            / "GridVision_Automotive_Parts_Demo.md",
                        )
                    ),
                ).split(os.pathsep)
                if path.strip()
            ),
            rag_allowed_root=Path(
                os.getenv(
                    "COMMERCIAL_RAG_ALLOWED_ROOT",
                    str(PROJECT_ROOT / "docs" / "ai_commercial"),
                )
            ).expanduser(),
            rag_index_path=Path(
                os.getenv(
                    "COMMERCIAL_RAG_INDEX_PATH",
                    str(PROJECT_ROOT / "data" / "commercial" / "rag" / "index.sqlite3"),
                )
            ).expanduser(),
            rag_uploads_root=Path(
                os.getenv(
                    "COMMERCIAL_RAG_UPLOAD_ROOT",
                    str(PROJECT_ROOT / "data" / "commercial" / "rag" / "uploads"),
                )
            ).expanduser(),
            rag_max_document_bytes=int(
                os.getenv("COMMERCIAL_RAG_MAX_DOCUMENT_BYTES", "50000000")
            ),
            rag_max_pdf_pages=int(
                os.getenv("COMMERCIAL_RAG_MAX_PDF_PAGES", "1000")
            ),
            rag_max_ocr_pages=int(
                os.getenv("COMMERCIAL_RAG_MAX_OCR_PAGES", "20")
            ),
            rag_max_extracted_characters=int(
                os.getenv(
                    "COMMERCIAL_RAG_MAX_EXTRACTED_CHARACTERS",
                    "10000000",
                )
            ),
            rag_conversion_timeout_seconds=int(
                os.getenv("COMMERCIAL_RAG_CONVERSION_TIMEOUT_SECONDS", "120")
            ),
            rag_ocr_enabled=os.getenv(
                "COMMERCIAL_RAG_OCR_ENABLED", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            rag_ocr_timeout_seconds=int(
                os.getenv("COMMERCIAL_RAG_OCR_TIMEOUT_SECONDS", "30")
            ),
            rag_ocr_render_scale=float(
                os.getenv("COMMERCIAL_RAG_OCR_RENDER_SCALE", "3.0")
            ),
            rag_tesseract_cmd=(
                Path(os.environ["COMMERCIAL_TESSERACT_CMD"]).expanduser()
                if os.getenv("COMMERCIAL_TESSERACT_CMD", "").strip()
                else None
            ),
            rag_embedding_provider=os.getenv(
                "COMMERCIAL_RAG_EMBEDDING_PROVIDER", "hash"
            ).lower(),
            rag_embedding_model=os.getenv(
                "COMMERCIAL_RAG_EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            ),
            rag_max_results=int(os.getenv("COMMERCIAL_RAG_MAX_RESULTS", "4")),
            rag_min_score=float(os.getenv("COMMERCIAL_RAG_MIN_SCORE", "0.25")),
            rag_graph_backend=os.getenv(
                "COMMERCIAL_RAG_GRAPH_BACKEND", "sqlite"
            ).lower(),
            rag_neo4j_uri=os.getenv(
                "COMMERCIAL_NEO4J_URI", "bolt://localhost:7687"
            ),
            rag_neo4j_username=os.getenv(
                "COMMERCIAL_NEO4J_USERNAME", "neo4j"
            ),
            rag_neo4j_password=SecretStr(
                os.getenv("COMMERCIAL_NEO4J_PASSWORD", "")
            ),
            rag_neo4j_database=os.getenv(
                "COMMERCIAL_NEO4J_DATABASE", "neo4j"
            ),
            max_graph_steps=int(os.getenv("COMMERCIAL_MAX_GRAPH_STEPS", "32")),
            max_tool_calls=int(os.getenv("COMMERCIAL_MAX_TOOL_CALLS", "8")),
            max_rework_attempts=int(
                os.getenv("COMMERCIAL_MAX_REWORK_ATTEMPTS", "1")
            ),
        )
