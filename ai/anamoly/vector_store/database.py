"""Single shared Chroma persistent client for assistant and ingestion."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from ai.anamoly.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> Any:
    """Create the configured persistent Chroma client lazily."""
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("Vector retrieval requires the chromadb dependency.") from exc
    path = get_settings().vector_db_path
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_collection(name: str | None = None) -> Any:
    """Get or create a collection without clearing existing data."""
    settings = get_settings()
    return get_client().get_or_create_collection(
        name=name or settings.vector_collection,
        metadata={"hnsw:space": "cosine"},
    )


def reset_client_cache() -> None:
    """Close no data; allow tests to re-open with a different configured path."""
    get_client.cache_clear()


def ensure_path(path: Path) -> Path:
    """Create a persistent vector directory and return its resolved path."""
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()

