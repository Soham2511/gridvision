"""Ollama-based entry point for routing questions to GridVision assistants."""

from .router import AssistantRoute, route_query

__all__ = ["AssistantRoute", "route_query"]
