from __future__ import annotations

import pytest

from ai.anamoly.tools.registry import (
    ToolDefinition,
    ToolInputError,
    ToolPermissionError,
    ToolRegistry,
)


def _tool() -> ToolDefinition:
    return ToolDefinition(
        name="read_test",
        description="A test tool.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler=lambda args, _context: {"value": args["value"]},
        allowed_personas=frozenset({"government"}),
    )


def test_registry_executes_registered_tool_and_logs_metadata(caplog):
    registry = ToolRegistry()
    registry.register(_tool())

    result = registry.execute(
        "read_test",
        {"value": "ok"},
        persona="government",
        context={"principal": "trusted-user", "authenticated_persona": "government"},
    )

    assert result == {"value": "ok"}
    assert registry.describe()[0]["name"] == "read_test"


def test_registry_rejects_unregistered_and_unverified_personas():
    registry = ToolRegistry()
    registry.register(_tool())
    with pytest.raises(ToolPermissionError, match="authenticated user"):
        registry.execute("read_test", {"value": "ok"}, persona="government")
    with pytest.raises(ToolPermissionError, match="not permitted"):
        registry.execute(
            "read_test",
            {"value": "ok"},
            persona="household",
            context={"principal": "trusted-user", "authenticated_persona": "household"},
        )


def test_registry_validates_arguments_before_handler_execution():
    registry = ToolRegistry()
    registry.register(_tool())
    context = {"principal": "trusted-user", "authenticated_persona": "government"}
    with pytest.raises(ToolInputError, match="missing required"):
        registry.execute("read_test", {}, persona="government", context=context)
    with pytest.raises(ToolInputError, match="unsupported fields"):
        registry.execute(
            "read_test",
            {"value": "ok", "python": "not allowed"},
            persona="government",
            context=context,
        )

