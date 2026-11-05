"""Tool registry authorization, input validation, and output validation tests."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from data_retrieval_agent.context import AuthenticatedRequestContext, Persona
from data_retrieval_agent.tools.base import ToolDefinition, ToolError, ToolOutput, ToolRegistry
from data_retrieval_agent.tools.registered import build_tool_registry


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(min_length=1)


def _context(permissions=frozenset(), scopes=None):
    return AuthenticatedRequestContext(
        principal_id="user-1",
        persona=Persona.RESIDENTIAL,
        permissions=frozenset(permissions),
        entity_scopes=scopes or {},
        request_id="req-1",
    )


def _registry():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="read_profile",
            description="Read a profile",
            input_schema=EchoInput,
            output_schema=ToolOutput,
            required_permission="read_profile",
            required_source="customer_gold",
            handler=lambda args, ctx: ToolOutput(
                tool_name="read_profile", data={"id": args.entity_id}, source={"source_id": "customer_gold"}
            ),
        )
    )
    return registry


def test_registry_filters_tools_by_permission_and_source():
    registry = _registry()
    allowed = _context({"read_profile"})
    assert registry.available_tools(allowed, {"customer_gold"})
    assert not registry.available_tools(allowed, set())
    assert not registry.available_tools(_context(), {"customer_gold"})


def test_tool_execution_rechecks_permission_and_source():
    registry = _registry()
    with pytest.raises(ToolError, match="not permitted"):
        registry.execute("read_profile", {"entity_id": "1"}, context=_context(), available_sources={"customer_gold"})
    with pytest.raises(ToolError, match="unavailable"):
        registry.execute("read_profile", {"entity_id": "1"}, context=_context({"read_profile"}), available_sources=set())


def test_tool_input_rejects_extra_fields():
    registry = _registry()
    with pytest.raises(ToolError, match="failed validation"):
        registry.execute(
            "read_profile",
            {"entity_id": "1", "principal_id": "attacker"},
            context=_context({"read_profile"}),
            available_sources={"customer_gold"},
        )


def test_tool_output_is_validated():
    registry = _registry()
    bad = ToolRegistry()
    bad.register(ToolDefinition("bad", "bad output", EchoInput, ToolOutput, "bad", None,
                                lambda args, ctx: {"tool_name": "bad", "data": []}))
    with pytest.raises(ToolError, match="failed"):
        bad.execute("bad", {"entity_id": "1"}, context=_context({"bad"}), available_sources=set())


def test_gridvision_adapter_reads_profile_through_existing_service():
    class CustomerService:
        def __init__(self):
            self.requested_id = None

        def get_entity_profile(self, entity_id):
            self.requested_id = entity_id
            return {"entityId": str(entity_id), "buildingType": "Residential"}

        def get_source_metadata(self, record_type):
            return {"sourceId": "customer_gold", "recordType": record_type, "units": "kWh"}

    customer = CustomerService()
    registry = build_tool_registry({"customer_bill_prediction_service": customer}, {"customer_gold"})
    context = AuthenticatedRequestContext(
        principal_id="resident", persona=Persona.RESIDENTIAL,
        permissions=frozenset({"get_consumer_profile"}),
        entity_scopes={"consumer": frozenset({"101"})}, request_id="req-profile",
    )
    result = registry.execute("get_consumer_profile", {"consumer_id": 101}, context=context, available_sources={"customer_gold"})
    assert customer.requested_id == 101
    assert result.data["buildingType"] == "Residential"
    assert result.source["data_class"] == "historical"


def test_public_report_context_can_only_read_customer_cohort_history():
    class SilverService:
        def get_cohort_history(self, start_date, end_date):
            return {"period": {"start": start_date.isoformat(), "end": end_date.isoformat()}, "daysReturned": 1}

        def get_source_metadata(self):
            return {"sourceId": "customer_silver", "units": "kWh"}

    registry = build_tool_registry({"customer_silver_history_service": SilverService()}, {"customer_silver"})
    public_context = AuthenticatedRequestContext(
        principal_id="public-monthly-report-demo", persona=Persona.RESIDENTIAL,
        permissions={"get_household_silver_history"}, entity_scopes={"customer_cohort": {"*"}},
        request_id="public-report-request",
    )
    result = registry.execute(
            "get_household_silver_history",
            {"start_date": "2026-10-01", "end_date": "2026-10-31"},
        context=public_context,
        available_sources={"customer_silver"},
    )
    assert result.data["daysReturned"] == 1
    assert result.source["source_id"] == "customer_silver"


def test_public_report_context_cannot_read_individual_consumer_history():
    registry = build_tool_registry({}, {"customer_silver"})
    public_context = AuthenticatedRequestContext(
        principal_id="public-monthly-report-demo", persona=Persona.RESIDENTIAL,
        permissions={"get_household_silver_history"}, entity_scopes={"customer_cohort": {"*"}},
        request_id="public-report-request",
    )
    with pytest.raises(ToolError, match="failed validation"):
        registry.execute(
            "get_household_silver_history",
            {"start_date": "2026-10-01", "end_date": "2026-10-31", "entity_id": "123"},
            context=public_context,
            available_sources={"customer_silver"},
        )


def test_gridvision_adapter_denies_wrong_persona_and_entity():
    class CustomerService:
        def get_entity_profile(self, entity_id):
            raise AssertionError("must not read unauthorized entity")

    registry = build_tool_registry({"customer_bill_prediction_service": CustomerService()}, {"customer_gold"})
    context = AuthenticatedRequestContext(
        principal_id="user", persona=Persona.COMMERCIAL,
        permissions=frozenset({"get_consumer_profile"}), entity_scopes={"consumer": frozenset({"101"})}, request_id="req-deny",
    )
    with pytest.raises(ToolError, match="persona"):
        registry.execute("get_consumer_profile", {"consumer_id": 101}, context=context, available_sources={"customer_gold"})


def test_gridvision_adapter_denies_out_of_scope_consumer_id():
    class CustomerService:
        def get_entity_profile(self, entity_id):
            raise AssertionError("unauthorized records must not be read")

    registry = build_tool_registry({"customer_bill_prediction_service": CustomerService()}, {"customer_gold"})
    context = AuthenticatedRequestContext(
        principal_id="resident", persona=Persona.RESIDENTIAL,
        permissions=frozenset({"get_consumer_profile"}), entity_scopes={"consumer": frozenset({"101"})}, request_id="req-scope",
    )
    with pytest.raises(ToolError, match="outside the user's authorized scope"):
        registry.execute("get_consumer_profile", {"consumer_id": 202}, context=context, available_sources={"customer_gold"})


def test_registered_tools_are_hidden_without_entity_scope():
    registry = build_tool_registry({}, {"customer_gold", "commercial_gold", "government_2018"})
    context = AuthenticatedRequestContext(
        principal_id="resident", persona=Persona.RESIDENTIAL,
        permissions=frozenset({"get_consumer_profile", "get_historical_consumption"}),
        entity_scopes={}, request_id="req-no-scope",
    )
    assert registry.available_tools(context, {"customer_gold"}) == []


def test_authenticated_context_scopes_are_deeply_immutable():
    context = AuthenticatedRequestContext(
        principal_id="resident", persona=Persona.RESIDENTIAL,
        permissions={"get_consumer_profile"}, entity_scopes={"consumer": {"101"}}, request_id="req-immutable",
    )
    with pytest.raises(TypeError):
        context.entity_scopes["consumer"] = frozenset({"202"})
    with pytest.raises(AttributeError):
        context.entity_scopes["consumer"].add("202")
