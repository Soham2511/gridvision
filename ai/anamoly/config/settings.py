"""Environment-backed settings for the anomaly intelligence assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ANOMALY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ANOMALY_ROOT.parents[1]


def _secret(name: str, filename: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value.strip()
    secret_root = Path(
        os.getenv("GRIDVISION_ANOMALY_SECRETS_DIR", ANOMALY_ROOT / "Key")
    )
    secret_path = secret_root / filename / "api.key"
    if not secret_path.is_file():
        return None
    content = secret_path.read_text(encoding="utf-8").strip()
    return content or None


@dataclass(frozen=True)
class AnomalyAssistantSettings:
    ollama_base_url: str
    chat_model: str
    embedding_model: str
    vector_db_path: Path
    vector_collection: str
    knowledge_base_path: Path
    raw_knowledge_base_path: Path
    secrets_dir: Path
    ollama_api_key: str | None
    tavily_api_key: str | None
    langsmith_api_key: str | None
    langsmith_tracing: bool
    request_timeout_seconds: int


def get_settings() -> AnomalyAssistantSettings:
    """Build settings without logging or exposing secret values."""
    default_vector_path = (
        ANOMALY_ROOT / "vector_store" / "storage" / "chroma" / "persistent_db"
    )
    return AnomalyAssistantSettings(
        ollama_base_url=os.getenv(
            "GRIDVISION_ANOMALY_OLLAMA_BASE_URL",
            os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ).rstrip("/"),
        chat_model=os.getenv("GRIDVISION_ANOMALY_CHAT_MODEL", "qwen3:8b"),
        embedding_model=os.getenv(
            "GRIDVISION_ANOMALY_EMBEDDING_MODEL", "qwen3-embedding:0.6b"
        ),
        vector_db_path=Path(
            os.getenv("GRIDVISION_ANOMALY_VECTOR_DB_PATH", default_vector_path)
        ).expanduser(),
        vector_collection=os.getenv(
            "GRIDVISION_ANOMALY_VECTOR_COLLECTION", "gridvision_anomaly_knowledge"
        ),
        knowledge_base_path=Path(
            os.getenv("GRIDVISION_ANOMALY_KNOWLEDGE_BASE_PATH", ANOMALY_ROOT / "knowledge_base")
        ).expanduser(),
        raw_knowledge_base_path=Path(
            os.getenv("GRIDVISION_ANOMALY_RAW_KNOWLEDGE_BASE_PATH", ANOMALY_ROOT / "raw_knowledge_base")
        ).expanduser(),
        secrets_dir=Path(
            os.getenv("GRIDVISION_ANOMALY_SECRETS_DIR", ANOMALY_ROOT / "Key")
        ).expanduser(),
        ollama_api_key=_secret("OLLAMA_API_KEY", "ollama"),
        tavily_api_key=_secret("TAVILY_API_KEY", "tavily"),
        langsmith_api_key=_secret("LANGSMITH_API_KEY", "langsmith"),
        langsmith_tracing=os.getenv(
            "GRIDVISION_ANOMALY_LANGSMITH_TRACING", "false"
        ).lower() in {"1", "true", "yes"},
        request_timeout_seconds=int(
            os.getenv("GRIDVISION_ANOMALY_REQUEST_TIMEOUT_SECONDS", "120")
        ),
    )
