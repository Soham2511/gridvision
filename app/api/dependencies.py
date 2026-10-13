"""Dependencies shared by FastAPI routes."""

from __future__ import annotations

from fastapi import Request

from app.models.registry import ModelBundle, ModelRegistry


def get_registry(request: Request) -> ModelRegistry:
    """Return the registry initialized during application startup."""
    registry = getattr(request.app.state, "model_registry", None)
    if registry is None:
        raise RuntimeError("Model registry is not initialized.")
    return registry


def get_model(request: Request, name: str) -> ModelBundle:
    """Return a verified, startup-loaded model bundle."""
    models = getattr(request.app.state, "models", None)
    if not isinstance(models, dict) or name not in models:
        raise RuntimeError(f"Model {name!r} is not ready.")
    return models[name]
