"""Local stdio MCP server exposing permissioned Commercial tools."""

from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.tools.document_rag_tools import DocumentRAGCommercialTools
from ai.commercial.tools.protocol import CommercialTools
from ai.commercial.tools.registry import (
    ToolRegistry,
    build_commercial_tool_registry,
)

MCP_PRINCIPAL = "mcp:stdio"


def create_commercial_mcp_server(
    tools: CommercialTools | None = None,
    settings: CommercialSettings | None = None,
) -> FastMCP:
    """Create an MCP server with only the registered read-oriented tool surface."""
    resolved_settings = settings or CommercialSettings.from_env()
    resolved_tools = tools or DocumentRAGCommercialTools(
        resolved_settings.rag_documents,
        settings=resolved_settings,
    )
    registry = build_commercial_tool_registry(resolved_tools)
    _validate_mcp_registry(registry)
    server = FastMCP("GridVision Commercial")

    @server.tool()
    def operational_context_read(goal: str) -> dict[str, Any]:
        """Search configured Commercial documents and return cited passages."""
        return registry.invoke(
            "operational_context_read",
            {"goal": goal},
            principal=MCP_PRINCIPAL,
        ).model_dump(mode="json")

    @server.tool()
    def peak_forecast(
        building_id: str,
        goal: str,
    ) -> dict[str, Any]:
        """Get a trained Commercial building forecast by its explicit ID."""
        return registry.invoke(
            "peak_forecast",
            {"building_id": building_id, "goal": goal},
            principal=MCP_PRINCIPAL,
        ).model_dump(mode="json")

    @server.tool()
    def commercial_buildings_list(limit: int = 20) -> dict[str, Any]:
        """List buildings available to the trained Commercial forecast model."""
        return registry.invoke(
            "commercial_buildings_list",
            {"limit": limit},
            principal=MCP_PRINCIPAL,
        ).model_dump(mode="json")

    @server.tool()
    def renewable_scenario_read(
        goal: str,
        factory_id: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve renewable scenario evidence when a provider is configured."""
        return registry.invoke(
            "renewable_scenario_read",
            {"factory_id": factory_id, "goal": goal},
            principal=MCP_PRINCIPAL,
        ).model_dump(mode="json")

    @server.tool()
    def cost_optimizer(
        inputs: dict[str, Any],
        factory_id: str | None = None,
    ) -> dict[str, Any]:
        """Request cost optimization with validated structured inputs."""
        return registry.invoke(
            "cost_optimizer",
            {"factory_id": factory_id, "inputs": inputs},
            principal=MCP_PRINCIPAL,
        ).model_dump(mode="json")

    return server


def _validate_mcp_registry(registry: ToolRegistry) -> None:
    registered = {
        definition.name
        for definition in registry.list_tools(MCP_PRINCIPAL, mcp_only=True)
    }
    expected = {
        "operational_context_read",
        "peak_forecast",
        "commercial_buildings_list",
        "renewable_scenario_read",
        "cost_optimizer",
    }
    if registered != expected:
        raise RuntimeError(
            "The Commercial MCP tool registrations do not match the exposed "
            "server handlers."
        )


def main() -> None:
    """Run the local server over stdio; no network listener is opened."""
    print(
        "GridVision Commercial MCP server ready; waiting for a stdio client.",
        file=sys.stderr,
        flush=True,
    )
    create_commercial_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
