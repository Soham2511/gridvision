"""Ollama-backed embeddings for the anomaly knowledge base."""

from __future__ import annotations

import json
import urllib.parse
import urllib.error
import urllib.request
from collections.abc import Sequence

from ai.anamoly.config import get_settings


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot return embeddings."""


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Generate embeddings in one Ollama API request."""
    if not texts:
        return []
    settings = get_settings()
    body = json.dumps(
        {"model": settings.embedding_model, "input": list(texts)}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.ollama_api_key and urllib.parse.urlparse(settings.ollama_base_url).scheme == "https":
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    request = urllib.request.Request(
        f"{settings.ollama_base_url}/api/embed",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.request_timeout_seconds
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise EmbeddingError(
            f"Ollama embedding request failed for model "
            f"'{settings.embedding_model}': {exc}"
        ) from exc
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise EmbeddingError("Ollama returned an unexpected embedding response.")
    if any(not isinstance(vector, list) or not vector for vector in embeddings):
        raise EmbeddingError("Ollama returned an empty or malformed embedding vector.")
    return embeddings
