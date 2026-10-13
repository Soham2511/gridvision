"""Load approved model artifacts from the project-local registry."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ModelBundle:
    """A verified model and the metadata needed to serve it."""

    name: str
    estimator: Any
    metadata: dict[str, Any]
    features: tuple[str, ...]
    artifact_path: Path
    version: str


class ModelRegistry:
    """Resolve and verify only the models declared in model_registry.yaml."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.config_path = self.project_root / "configs" / "model_registry.yaml"
        with self.config_path.open(encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        entries = config.get("models") if isinstance(config, dict) else None
        if not isinstance(entries, dict) or not entries:
            raise ValueError(f"No models configured in {self.config_path}")
        self.entries: dict[str, dict[str, Any]] = entries
        self._bundles: dict[str, ModelBundle] = {}

    def names(self) -> tuple[str, ...]:
        """Return configured model identifiers."""
        return tuple(sorted(self.entries))

    def get(self, name: str) -> ModelBundle:
        """Load an allow-listed artifact once and verify its metadata contract."""
        if name not in self.entries:
            raise KeyError(f"Unknown model name: {name}")
        if name in self._bundles:
            return self._bundles[name]

        entry = self.entries[name]
        artifact_path = self._project_path(entry["artifact_path"])
        metadata_path = self._project_path(entry["metadata_path"])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metrics_path = metadata_path.parent / metadata["metrics_report"]
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        metadata["evaluation_status"] = metrics.get("status", "unknown")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")
        if artifact_path.stat().st_size != metadata.get("artifact_size_bytes"):
            raise ValueError(f"Artifact size mismatch for {name}.")
        digest = self._sha256(artifact_path)
        expected_digest = metadata.get("sha256")
        if digest != expected_digest:
            raise ValueError(
                f"SHA-256 mismatch for {name} artifact: expected "
                f"{expected_digest}, got {digest}"
            )

        # Artifacts are loaded only from this project after checksum validation.
        with artifact_path.open("rb") as stream:
            payload = pickle.load(stream)
        if name == "residential":
            if not isinstance(payload, dict) or "model" not in payload:
                raise TypeError("Residential artifact must contain a 'model' pipeline.")
            estimator = payload["model"]
            artifact_features = tuple(payload.get("feature_columns", ()))
        else:
            estimator = payload
            artifact_features = tuple(estimator.booster_.feature_name())
        metadata_features = tuple(metadata.get("features", ()))
        configured_target = entry.get("target_name")
        if metadata.get("target_name") != configured_target:
            raise ValueError(f"Target contract mismatch for configured model {name}.")
        if metadata.get("feature_schema_version") != entry.get(
            "feature_schema_version"
        ):
            raise ValueError(f"Feature schema version mismatch for model {name}.")
        if metadata.get("target_units") != entry.get("target_unit"):
            raise ValueError(f"Target unit mismatch for configured model {name}.")
        if artifact_features != metadata_features:
            raise ValueError(
                f"Feature contract mismatch for {name}: artifact has "
                f"{len(artifact_features)} features, metadata has "
                f"{len(metadata_features)}."
            )
        if len(set(metadata_features)) != len(metadata_features):
            raise ValueError(f"Duplicate feature names in {name} metadata.")
        version = (
            f"{metadata.get('model_version', 'unversioned')} (sha256:{digest[:12]})"
        )
        bundle = ModelBundle(
            name=name,
            estimator=estimator,
            metadata=metadata,
            features=metadata_features,
            artifact_path=artifact_path,
            version=version,
        )
        self._bundles[name] = bundle
        return bundle

    def load_all(self) -> dict[str, ModelBundle]:
        """Load every configured artifact, failing explicitly on contract errors."""
        return {name: self.get(name) for name in self.names()}

    def _project_path(self, relative_path: str) -> Path:
        path = (self.project_root / relative_path).resolve()
        if not path.is_relative_to(self.project_root):
            raise ValueError(f"Configured path escapes project root: {relative_path}")
        return path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
