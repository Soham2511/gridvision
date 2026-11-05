"""Permission-aware registry for all assistant-callable functions."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("gridvision.anomaly.tools")

Persona = str
ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Any]


class ToolRegistryError(RuntimeError):
    """Base error for tool discovery and execution."""


class ToolPermissionError(ToolRegistryError):
    """Raised when a persona is not allowed to use a tool."""


class ToolConfirmationRequired(ToolRegistryError):
    """Raised when an operation requires explicit user confirmation."""


class ToolInputError(ToolRegistryError):
    """Raised when tool input violates its declared schema."""


class ToolExecutionError(ToolRegistryError):
    """Raised when a registered tool handler fails."""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    allowed_personas: frozenset[Persona]
    side_effects: bool = False
    user_confirmation_required: bool = False
    enabled: bool = True
    requires_authenticated_principal: bool = False


class ToolRegistry:
    """Register, discover, validate, authorize, and execute assistant tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError(f"Tool name is empty or already registered: {tool.name}")
        self._tools[tool.name] = tool

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "input_schema": item.input_schema,
                "allowed_personas": sorted(item.allowed_personas),
                "side_effects": item.side_effects,
                "user_confirmation_required": item.user_confirmation_required,
                "requires_authenticated_principal": item.requires_authenticated_principal,
                "available": item.enabled,
            }
            for item in self._tools.values()
        ]

    def _validate_input(self, tool: ToolDefinition, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolInputError(f"Input for '{tool.name}' must be an object.")
        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [key for key in required if key not in arguments]
        unknown = set(arguments).difference(properties)
        if missing:
            raise ToolInputError(
                f"Tool '{tool.name}' is missing required fields: {', '.join(missing)}."
            )
        if unknown:
            raise ToolInputError(
                f"Tool '{tool.name}' received unsupported fields: "
                f"{', '.join(sorted(unknown))}."
            )
        for key, value in arguments.items():
            spec = properties[key]
            expected = spec.get("type")
            valid = {
                "string": lambda current: isinstance(current, str),
                "integer": lambda current: isinstance(current, int) and not isinstance(current, bool),
                "number": lambda current: isinstance(current, (int, float)) and not isinstance(current, bool),
                "boolean": lambda current: isinstance(current, bool),
                "array": lambda current: isinstance(current, list),
                "object": lambda current: isinstance(current, dict),
            }.get(expected)
            if valid is not None and not valid(value):
                raise ToolInputError(
                    f"Field '{key}' for '{tool.name}' must be {expected}."
                )
            if "enum" in spec and value not in spec["enum"]:
                raise ToolInputError(
                    f"Field '{key}' for '{tool.name}' must be one of "
                    f"{', '.join(map(str, spec['enum']))}."
                )

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        persona: Persona,
        context: dict[str, Any] | None = None,
        confirmed: bool = False,
    ) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolRegistryError(f"Tool '{name}' is not registered.")
        if not tool.enabled:
            raise ToolRegistryError(f"Tool '{name}' is currently unavailable.")
        if persona not in tool.allowed_personas:
            raise ToolPermissionError(
                f"Persona '{persona}' is not permitted to use '{name}'."
            )
        execution_context = context or {}
        if tool.requires_authenticated_principal:
            if not execution_context.get("principal"):
                raise ToolPermissionError(
                    f"Tool '{name}' requires an authenticated user."
                )
            if execution_context.get("authenticated_persona") != persona:
                raise ToolPermissionError(
                    f"Persona '{persona}' is not verified for this user."
                )
        self._validate_input(tool, arguments)
        if tool.user_confirmation_required and not confirmed:
            raise ToolConfirmationRequired(
                f"Tool '{name}' requires explicit user confirmation."
            )
        started = time.perf_counter()
        try:
            result = tool.handler(arguments, execution_context)
        except Exception as exc:
            logger.exception(
                "Assistant tool failed",
                extra={
                    "tool_name": name,
                    "persona": persona,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            )
            raise ToolExecutionError(f"Tool '{name}' failed: {exc}") from exc
        logger.info(
            "Assistant tool completed",
            extra={
                "tool_name": name,
                "persona": persona,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return result
