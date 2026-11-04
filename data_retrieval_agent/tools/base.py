"""Strict registry and runtime authorization checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Type

from pydantic import BaseModel, ValidationError

from ..context import AuthenticatedRequestContext

logger = logging.getLogger("gridvision.data_retrieval_agent.tools")


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ToolOutput(BaseModel):
    tool_name: str
    status: str = "ok"
    data: dict[str, Any]
    source: dict[str, Any]


class ConsumerProfileOutput(ToolOutput):
    tool_name: Literal["get_consumer_profile"]


class HistoryOutput(ToolOutput):
    tool_name: Literal["get_historical_consumption"]


class CustomerSilverHistoryOutput(ToolOutput):
    tool_name: Literal["get_household_silver_history"]


class LatestCustomerSilverMonthOutput(ToolOutput):
    tool_name: Literal["get_latest_household_silver_month"]


class LatestCommercialSilverMonthOutput(ToolOutput):
    tool_name: Literal["get_latest_commercial_silver_month"]


class BuildingOutput(ToolOutput):
    tool_name: Literal["get_building_details"]


class RegionalOutput(ToolOutput):
    tool_name: Literal["get_regional_information"]


class ForecastOutput(ToolOutput):
    tool_name: Literal["get_energy_forecast"]


class AnomalyOutput(ToolOutput):
    tool_name: Literal["get_anomaly_predictions"]


class SegmentationOutput(ToolOutput):
    tool_name: Literal["get_segmentation_results"]


class ModelMetadataOutput(ToolOutput):
    tool_name: Literal["get_model_metadata"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    required_permission: str
    required_source: str | None
    handler: Callable[[BaseModel, AuthenticatedRequestContext], Any]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def _source_available(self, name: str, context: AuthenticatedRequestContext, sources: set[str], arguments: dict | None = None) -> bool:
        if name == "get_historical_consumption":
            return {"residential": "customer_gold", "commercial": "commercial_gold", "government": "government_2018"}[context.persona.value] in sources
        if name == "get_energy_forecast":
            return f"forecast_{context.persona.value}" in sources
        if name == "get_model_metadata" and arguments:
            model = arguments.get("model_id")
            required = {
                "customer-bill-prediction": "customer_gold",
                "commercial-building-forecast": "commercial_gold",
                "government-load-forecast": "government_2018",
                "anomaly-prediction": "anomaly_synthetic_2019",
                "government-customer-segmentation": "segmentation_2018",
            }.get(model)
            return required in sources
        if name == "get_model_metadata":
            return bool(sources.intersection({"customer_gold", "commercial_gold", "government_2018", "segmentation_2018", "anomaly_synthetic_2019"}))
        tool = self._tools.get(name)
        return bool(tool and (tool.required_source is None or tool.required_source in sources))

    def available_tools(self, context: AuthenticatedRequestContext, available_sources: set[str]) -> list[ToolDefinition]:
        return [
            tool for tool in self._tools.values()
            if context.allows_tool(tool.required_permission)
            and self._scope_available(tool.name, context)
            and self._source_available(tool.name, context, available_sources)
        ]

    @staticmethod
    def _scope_available(name: str, context: AuthenticatedRequestContext) -> bool:
        scopes = context.entity_scopes
        if name in {"get_consumer_profile", "get_anomaly_predictions"}:
            return bool(scopes.get("consumer"))
        if name == "get_historical_consumption":
            if context.persona.value == "residential":
                return bool(scopes.get("consumer") or "*" in scopes.get("customer_cohort", frozenset()))
            if context.persona.value == "commercial":
                return bool(scopes.get("building") or "*" in scopes.get("commercial_cohort", frozenset()))
            return bool(scopes.get("region") or "*" in scopes.get("region", frozenset()) or "system" in scopes.get("region", frozenset()))
        if name == "get_latest_commercial_silver_month":
            return context.persona.value == "commercial" and bool(
                scopes.get("building") or "*" in scopes.get("commercial_cohort", frozenset())
            )
        if name == "get_building_details":
            return bool(scopes.get("building"))
        if name == "get_regional_information":
            return context.persona.value == "government" and bool(scopes.get("region"))
        if name == "get_energy_forecast":
            kind = {"residential": "consumer", "commercial": "building", "government": "region"}[context.persona.value]
            return bool(scopes.get(kind))
        if name == "get_segmentation_results":
            return (context.persona.value == "residential" and bool(scopes.get("consumer"))) or (context.persona.value == "government" and bool(scopes.get("region")))
        return True

    def execute(self, name: str, arguments: dict[str, Any], *, context: AuthenticatedRequestContext, available_sources: set[str]) -> ToolOutput:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError("UNKNOWN_TOOL", "The requested tool is not registered.")
        if not context.allows_tool(tool.required_permission):
            raise ToolError("FORBIDDEN", "The user is not permitted to use this tool.")
        if not self._scope_available(name, context):
            raise ToolError("FORBIDDEN_ENTITY", "The user has no authorized entity scope for this tool.")
        if not self._source_available(name, context, available_sources, arguments):
            raise ToolError("SOURCE_UNAVAILABLE", "The required data source is unavailable.", True)
        try:
            parsed = tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError("INVALID_TOOL_INPUT", "Tool arguments failed validation.") from exc
        try:
            result = tool.handler(parsed, context)
            if isinstance(result, BaseModel):
                result = result.model_dump()
            output = tool.output_schema.model_validate(result)
            logger.info(
                "retrieval_tool_completed",
                extra={"event": {"tool": name, "request_id": context.request_id, "source_id": output.source.get("source_id"), "status": output.status}},
            )
            return output
        except LookupError as exc:
            raise ToolError("NOT_FOUND", "The requested source entity has no matching records.") from exc
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("retrieval_tool_failed", extra={"event": {"tool": name, "request_id": context.request_id}})
            raise ToolError("TOOL_FAILED", "The data retrieval tool failed.", True) from exc
