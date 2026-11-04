"""Permission-aware registry for typed Commercial agent tools."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai.commercial.schemas.communication import ToolObservation
from ai.commercial.tools.protocol import CommercialTools
from ai.commercial.schemas.optimization import ScheduleInput

MAX_TOOL_INPUT_BYTES = 16_384
MAX_TOOL_OUTPUT_BYTES = 262_144
logger = logging.getLogger("gridvision.commercial.tools")


class ToolRegistryError(ValueError):
    """A tool call failed registry lookup, authorization, or input validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OperationsInput(_ToolInput):
    goal: str = Field(min_length=1, max_length=2000)


class FactoryGoalInput(_ToolInput):
    factory_id: str | None = Field(default=None, min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=2000)


class PeakForecastInput(_ToolInput):
    building_id: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]{0,15}$",
        strict=True,
    )
    goal: str = Field(min_length=1, max_length=2000)


class CommercialBuildingsInput(_ToolInput):
    limit: int = Field(default=20, strict=True, ge=1, le=50)


class OptimizationInput(_ToolInput):
    factory_id: str | None = Field(default=None, min_length=1, max_length=128)
    inputs: ScheduleInput


ToolHandler = Callable[..., ToolObservation]


@dataclass(frozen=True)
class ToolDefinition:
    """A typed tool capability and the principals allowed to invoke it."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    allowed_principals: frozenset[str]
    mcp_exposed: bool = True


class ToolRegistry:
    """Validate and authorize calls before dispatching to an injected provider."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool is already registered: {definition.name}")
        if not definition.name or len(definition.name) > 128:
            raise ValueError("Tool name must contain 1 to 128 characters.")
        if not definition.allowed_principals:
            raise ValueError("A tool must have at least one allowed principal.")
        self._definitions[definition.name] = definition

    def list_tools(
        self,
        principal: str,
        *,
        mcp_only: bool = False,
    ) -> tuple[ToolDefinition, ...]:
        """Return only capabilities authorized for the trusted caller."""
        return tuple(
            definition
            for definition in self._definitions.values()
            if principal in definition.allowed_principals
            and (not mcp_only or definition.mcp_exposed)
        )

    def invoke(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        principal: str,
    ) -> ToolObservation:
        definition = self._definitions.get(name)
        if definition is None:
            raise ToolRegistryError("TOOL_NOT_FOUND", "The requested tool is not registered.")
        if principal not in definition.allowed_principals:
            raise ToolRegistryError(
                "TOOL_NOT_AUTHORIZED",
                "The caller is not authorized to invoke this tool.",
            )
        try:
            encoded_arguments = json.dumps(
                arguments,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ToolRegistryError(
                "TOOL_INPUT_INVALID",
                "Tool arguments must be JSON-compatible values.",
            ) from exc
        if len(encoded_arguments) > MAX_TOOL_INPUT_BYTES:
            raise ToolRegistryError(
                "TOOL_INPUT_TOO_LARGE",
                f"Tool arguments exceed {MAX_TOOL_INPUT_BYTES} bytes.",
            )
        try:
            validated_input = definition.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolRegistryError(
                "TOOL_INPUT_INVALID",
                "Tool arguments do not match the registered input schema.",
            ) from exc

        call_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            observation = ToolObservation.model_validate(
                definition.handler(**validated_input.model_dump())
            )
        except Exception as exc:
            logger.error(
                "commercial_tool_failed",
                extra={
                    "event": {
                        "tool_call_id": call_id,
                        "tool_name": name,
                        "principal": principal,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise
        serialized_output = observation.model_dump_json().encode("utf-8")
        if len(serialized_output) > MAX_TOOL_OUTPUT_BYTES:
            raise ToolRegistryError(
                "TOOL_OUTPUT_TOO_LARGE",
                f"Tool output exceeds {MAX_TOOL_OUTPUT_BYTES} bytes.",
            )
        logger.info(
            "commercial_tool_completed",
            extra={
                "event": {
                    "tool_call_id": call_id,
                    "tool_name": name,
                    "principal": principal,
                    "status": observation.status,
                    "output_bytes": len(serialized_output),
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                }
            },
        )
        return observation


def build_commercial_tool_registry(tools: CommercialTools) -> ToolRegistry:
    """Register current Commercial tool interfaces with explicit permissions."""
    def operations_handler(goal: str) -> ToolObservation:
        return tools.retrieve_operational_context(None, goal)

    def peak_handler(
        building_id: str | None,
        goal: str,
    ) -> ToolObservation:
        return tools.get_peak_forecast(None, goal, building_id)

    def buildings_handler(limit: int) -> ToolObservation:
        return tools.get_commercial_buildings(limit)
    def renewable_handler(
        factory_id: str | None,
        goal: str,
    ) -> ToolObservation:
        return tools.get_renewable_scenarios(factory_id, goal)

    def optimizer_handler(
        factory_id: str | None,
        inputs: ScheduleInput | dict[str, Any],
    ) -> ToolObservation:
        schedule = ScheduleInput.model_validate(inputs)
        return tools.optimize(
            factory_id,
            schedule.model_dump(mode="python"),
        )

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="operational_context_read",
            description=(
                "Search configured Commercial documents for cited operational "
                "context. Does not accept document paths or perform writes."
            ),
            input_model=OperationsInput,
            handler=operations_handler,
            allowed_principals=frozenset({"agent:operations", "mcp:stdio"}),
        )
    )
    registry.register(
        ToolDefinition(
            name="peak_forecast",
            description=(
                "Retrieve a trained Commercial building peak forecast from the "
                "configured local backend; requires a building ID."
            ),
            input_model=PeakForecastInput,
            handler=peak_handler,
            allowed_principals=frozenset({"agent:peak_prediction", "mcp:stdio"}),
        )
    )
    registry.register(
        ToolDefinition(
            name="commercial_buildings_list",
            description=(
                "List a bounded number of buildings available in the trained "
                "Commercial forecast dataset."
            ),
            input_model=CommercialBuildingsInput,
            handler=buildings_handler,
            allowed_principals=frozenset(
                {"agent:peak_prediction", "mcp:stdio"}
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="renewable_scenario_read",
            description="Retrieve renewable scenario evidence when configured.",
            input_model=FactoryGoalInput,
            handler=renewable_handler,
            allowed_principals=frozenset({"agent:renewable", "mcp:stdio"}),
        )
    )
    registry.register(
        ToolDefinition(
            name="cost_optimizer",
            description=(
                "Request a deterministic cost optimization when a configured "
                "solver and validated inputs are available."
            ),
            input_model=OptimizationInput,
            handler=optimizer_handler,
            allowed_principals=frozenset(
                {"agent:cost_optimization", "mcp:stdio"}
            ),
        )
    )
    return registry


class RegistryCommercialTools:
    """Adapt registry calls back to the interface used by agent nodes."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def get_peak_forecast(
        self,
        factory_id: str | None,
        goal: str,
        building_id: str | None = None,
    ) -> ToolObservation:
        del factory_id
        return self._registry.invoke(
            "peak_forecast",
            {"building_id": building_id, "goal": goal},
            principal="agent:peak_prediction",
        )

    def get_commercial_buildings(self, limit: int = 20) -> ToolObservation:
        return self._registry.invoke(
            "commercial_buildings_list",
            {"limit": limit},
            principal="agent:peak_prediction",
        )

    def retrieve_operational_context(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        del factory_id
        return self._registry.invoke(
            "operational_context_read",
            {"goal": goal},
            principal="agent:operations",
        )

    def get_renewable_scenarios(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        return self._registry.invoke(
            "renewable_scenario_read",
            {"factory_id": factory_id, "goal": goal},
            principal="agent:renewable",
        )

    def optimize(
        self, factory_id: str | None, inputs: dict[str, Any]
    ) -> ToolObservation:
        return self._registry.invoke(
            "cost_optimizer",
            {"factory_id": factory_id, "inputs": inputs},
            principal="agent:cost_optimization",
        )
