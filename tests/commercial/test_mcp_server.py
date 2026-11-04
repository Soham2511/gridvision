"""Tests for the permissioned Commercial tool registry and MCP server."""

from __future__ import annotations

import asyncio

from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from ai.commercial.mcp_server import create_commercial_mcp_server
from ai.commercial.tools.mock_tools import (
    MockCommercialTools,
    synthetic_fixture,
)
from ai.commercial.tools.registry import (
    ToolRegistryError,
    build_commercial_tool_registry,
)


def test_registry_validates_arguments_and_enforces_principal_allowlists() -> None:
    tools = MockCommercialTools(
        {
            "operations": synthetic_fixture(
                source_id="fixture:operations",
                finding="Synthetic test fixture: register is available.",
            )
        }
    )
    registry = build_commercial_tool_registry(tools)

    observation = registry.invoke(
        "operational_context_read",
        {"goal": "Find the equipment register."},
        principal="agent:operations",
    )

    assert observation.status == "available"
    assert observation.evidence_refs[0].synthetic

    try:
        registry.invoke(
            "operational_context_read",
            {"goal": "Find the equipment register."},
            principal="agent:renewable",
        )
    except ToolRegistryError as exc:
        assert exc.code == "TOOL_NOT_AUTHORIZED"
    else:
        raise AssertionError("Unauthorized agent unexpectedly invoked a tool.")

    try:
        registry.invoke(
            "operational_context_read",
            {"goal": "valid", "document_path": "D:\\private.pdf"},
            principal="agent:operations",
        )
    except ToolRegistryError as exc:
        assert exc.code == "TOOL_INPUT_INVALID"
    else:
        raise AssertionError("Undeclared tool arguments were accepted.")


def test_registry_reports_unconfigured_providers_as_unavailable() -> None:
    registry = build_commercial_tool_registry(MockCommercialTools())

    observation = registry.invoke(
        "peak_forecast",
        {"building_id": "101", "goal": "Forecast peak demand."},
        principal="mcp:stdio",
    )

    assert observation.status == "unavailable"
    assert observation.error is not None
    assert observation.error.code == "MOCK_DATA_UNAVAILABLE"


def test_mcp_server_exposes_registered_tools_over_memory_transport() -> None:
    tools = MockCommercialTools(
        {
            "operations": synthetic_fixture(
                source_id="fixture:operations",
                finding="Synthetic test fixture: cited operational result.",
            )
        }
    )
    server = create_commercial_mcp_server(tools=tools)

    async def exercise_server() -> None:
        async with create_connected_server_and_client_session(
            server,
            raise_exceptions=True,
        ) as session:
            client: ClientSession = session
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert names == {
                "operational_context_read",
                "peak_forecast",
                "commercial_buildings_list",
                "renewable_scenario_read",
                "cost_optimizer",
            }

            response = await client.call_tool(
                "operational_context_read",
                {"goal": "Find the equipment register."},
            )
            assert response.isError is not True
            assert response.structuredContent["status"] == "available"
            assert response.structuredContent["evidence_refs"][0]["synthetic"]

            unavailable = await client.call_tool(
                "peak_forecast",
                {"building_id": "101", "goal": "Forecast peak demand."},
            )
            assert unavailable.structuredContent["status"] == "unavailable"
            assert (
                unavailable.structuredContent["error"]["code"]
                == "MOCK_DATA_UNAVAILABLE"
            )
            buildings = await client.call_tool(
                "commercial_buildings_list",
                {"limit": 10},
            )
            assert buildings.structuredContent["status"] == "unavailable"

    asyncio.run(exercise_server())


def test_registry_rejects_non_json_arguments() -> None:
    registry = build_commercial_tool_registry(MockCommercialTools())

    try:
        registry.invoke(
            "operational_context_read",
            {"goal": object()},
            principal="agent:operations",
        )
    except ToolRegistryError as exc:
        assert exc.code == "TOOL_INPUT_INVALID"
    else:
        raise AssertionError("Non-JSON tool arguments were accepted.")
