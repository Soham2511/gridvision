"""FastAPI application factory and project-local model startup checks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.router import router
from app.models.registry import ModelRegistry


def create_app(project_root: Path | None = None) -> FastAPI:
    """Create the API and load only configured, checksum-verified artifacts."""
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    registry = ModelRegistry(root)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.model_registry = registry
        application.state.expected_models = registry.names()
        application.state.models = registry.load_all()
        yield

    application = FastAPI(
        title="GridVision Prediction API",
        version="0.1.0",
        description=(
            "Residential, commercial, and government demand inference. "
            "Model metrics and historical replay limitations are reported."
        ),
        lifespan=lifespan,
    )
    application.include_router(router)

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "GridVision Prediction API",
            "health": "/api/v1/health/live",
            "readiness": "/api/v1/health/ready",
            "docs": "/docs",
        }

    return application


app = create_app()
