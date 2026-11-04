"""Local embedding providers for persistent vector retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]*", re.IGNORECASE)


class EmbeddingProvider(Protocol):
    """Encode text into stable, locally searchable vectors."""

    @property
    def model_id(self) -> str:
        """Return a versioned identifier for the embedding implementation."""

    def embed(self, text: str) -> list[float]:
        """Generate one normalized embedding without uploading document text."""


class LocalFeatureHashEmbedder:
    """Small deterministic lexical vectorizer requiring no model downloads."""

    DIMENSIONS = 2048
    model_id = "local-feature-hash-v1:2048"

    def embed(self, text: str) -> list[float]:
        tokens = [token.casefold() for token in TOKEN_PATTERN.findall(text)]
        counts: Counter[int] = Counter()
        for index, token in enumerate(tokens):
            features = [f"w:{token}"]
            if index:
                features.append(f"b:{tokens[index - 1]}_{token}")
            padded = f"^{token}$"
            features.extend(
                f"c:{padded[start:start + size]}"
                for size in (3, 4)
                for start in range(max(0, len(padded) - size + 1))
            )
            for feature in features:
                digest = hashlib.blake2b(
                    feature.encode("utf-8"),
                    digest_size=8,
                    person=b"gridvis",
                ).digest()
                counts[int.from_bytes(digest, "little") % self.DIMENSIONS] += 1

        vector = [0.0] * self.DIMENSIONS
        for index, count in counts.items():
            vector[index] = float(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


class FastEmbedProvider:
    """Locally execute a Hugging Face model through FastEmbed/ONNX."""

    def __init__(
        self,
        model_name: str,
        cache_dir: str,
    ) -> None:
        from fastembed import TextEmbedding

        self._model_name = model_name
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=cache_dir,
            local_files_only=True,
        )

    @property
    def model_id(self) -> str:
        return f"fastembed:{self._model_name}"

    def embed(self, text: str) -> list[float]:
        vector = next(iter(self._model.embed(text)))
        return [float(value) for value in vector]


def create_embedder(
    provider: str,
    model_name: str,
    cache_dir: str,
) -> EmbeddingProvider:
    """Construct the explicitly configured offline embedding provider."""
    if provider == "hash":
        return LocalFeatureHashEmbedder()
    if provider == "fastembed":
        return FastEmbedProvider(model_name, cache_dir)
    raise ValueError(f"Unsupported local RAG embedding provider: {provider!r}")


def pack_vector(vector: Sequence[float]) -> bytes:
    """Serialize a finite vector using a compact fixed-width representation."""
    import array
    import math

    values = array.array("f", vector)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Embedding vector contains a non-finite value.")
    if values.itemsize != 4:
        raise RuntimeError("Platform float serialization is not float32.")
    if not values:
        raise ValueError("Embedding vector must not be empty.")
    return values.tobytes()


def unpack_vector(payload: bytes) -> list[float]:
    """Decode a stored float32 vector."""
    import array

    values = array.array("f")
    values.frombytes(payload)
    if values.itemsize != 4:
        raise RuntimeError("Platform float serialization is not float32.")
    return values.tolist()
