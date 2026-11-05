"""Shared, disabled-by-default GridVision AI foundation."""

from app.ai.service import AIService, AIUnavailableError

__all__ = ["AIService", "AIUnavailableError"]
