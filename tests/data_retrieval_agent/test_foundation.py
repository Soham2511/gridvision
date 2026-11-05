"""Contract tests for the independent agent foundation."""

import pytest
from pydantic import ValidationError

from data_retrieval_agent.config import AgentSettings
from data_retrieval_agent.context import AuthenticatedRequestContext, Persona
from data_retrieval_agent.schemas import MessageRequest, SourceReference


def test_settings_are_disabled_without_trusted_identity_adapter(monkeypatch):
    monkeypatch.setenv("GRIDVISION_RETRIEVAL_ENABLED", "true")
    settings = AgentSettings.from_env()
    assert settings.enabled is True
    assert settings.llm_provider == "none"


def test_request_schema_rejects_identity_or_persona_claims():
    with pytest.raises(ValidationError):
        MessageRequest.model_validate(
            {"message": "show my usage", "persona": "government", "principal_id": "x"}
        )


def test_request_context_denies_entity_without_explicit_scope():
    context = AuthenticatedRequestContext(
        principal_id="verified-user",
        persona=Persona.RESIDENTIAL,
        permissions=frozenset({"get_consumer_profile"}),
        entity_scopes={"consumer": frozenset({"1001"})},
        request_id="request-1",
    )
    assert context.allows_tool("get_consumer_profile")
    assert context.allows_entity("consumer", "1001")
    assert not context.allows_entity("consumer", "1002")
    assert not context.allows_entity("building", "1001")


def test_source_reference_requires_data_class():
    source = SourceReference(
        source_id="customer_gold",
        record_type="monthly_history",
        period_start="2018-01",
        units="kWh",
        data_class="historical",
    )
    assert source.data_class == "historical"
