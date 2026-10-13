"""Compose the versioned public API routes."""

from fastapi import APIRouter

from app.api.v1 import commercial, government, health, residential

router = APIRouter(prefix="/api/v1")
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(residential.router, prefix="/residential", tags=["residential"])
router.include_router(commercial.router, prefix="/commercial", tags=["commercial"])
router.include_router(government.router, prefix="/government", tags=["government"])
