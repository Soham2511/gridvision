from __future__ import annotations

import asyncio
import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import create_app
from app.ai.contracts import (
    AIOutput,
    Citation,
    EvidenceEnvelope,
    EvidenceFact,
    GenerationAuditEvent,
    GenerationRequest,
    GroundedClaim,
    SourceReference,
)
from app.ai.application_store import AIApplicationStore
from app.ai.persistence import SQLiteAuditRepository
from app.ai.policy import AIPolicyError, validate_grounded_output
from app.ai.rag import ApprovedCorpus, CorpusError, CorpusSource
from app.ai.providers import RetryableAIProviderError
from app.ai.redaction import redact_sensitive_text
from app.ai.report_service import ReportService
from app.ai.service import AIOutputRejectedError, AIService, AIUnavailableError
from app.ai.storage import PrivateFileStore, PrivateStorageError
from app.ai.workflow import END, WorkflowDependencyUnavailable, build_workflow
from app.config import TestingConfig


def evidence() -> EvidenceEnvelope:
    return EvidenceEnvelope(
        snapshot_id="snapshot-1",
        created_at="2026-01-01T00:00:00Z",
        persona="household",
        entity_ref="customer-123",
        sources=[
            SourceReference(
                source_id="gold-v1",
                dataset="customer_gold",
                dataset_version="v1",
                provenance="project_historical",
                period_start="2025-01-01",
                period_end="2025-01-31",
                units="kWh",
            )
        ],
        facts=[
            EvidenceFact(
                fact_id="consumption-jan",
                source_id="gold-v1",
                name="monthly_consumption",
                value=120.0,
                units="kWh",
                value_kind="observation",
            )
        ],
    )


def valid_output() -> dict:
    return {
        "narrative": "Recorded use was 120 kWh for the supplied period.",
        "claims": [
            {
                "text": "Recorded use was 120 kWh.",
                "kind": "observation",
                "evidence_fact_ids": ["consumption-jan"],
            }
        ],
        "citations": [
            {"source_id": "gold-v1", "fact_ids": ["consumption-jan"]}
        ],
    }


def request() -> GenerationRequest:
    return GenerationRequest(
        request_id="request-1",
        prompt_key="grounded_explanation",
        evidence=evidence(),
    )


class FakeProvider:
    provider_id = "fake-test"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, prompt, *, timeout_seconds, max_output_chars):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return await response()
        return response


def test_app_ai_core_is_disabled_without_initializing_storage(tmp_path):
    class Config(TestingConfig):
        AI_ENABLED = False
        AI_DATABASE_PATH = str(tmp_path / "must-not-exist.sqlite")
        AI_PRIVATE_STORAGE_ROOT = str(tmp_path / "must-not-exist-private")

    app = create_app(Config)
    service = app.extensions["ai_service"]
    assert service.status() == {
        "enabled": False,
        "generation_provider": "unconfigured",
        "embedding_provider": "unconfigured",
        "external_calls_enabled": False,
    }
    assert not Path(Config.AI_DATABASE_PATH).exists()
    assert not Path(Config.AI_PRIVATE_STORAGE_ROOT).exists()
    with pytest.raises(AIUnavailableError):
        asyncio.run(service.generate(request()))


def test_fake_provider_generates_only_validated_grounded_output(caplog):
    service = AIService(enabled=True, generation_provider=FakeProvider([valid_output()]))
    output = asyncio.run(service.generate(request()))
    assert output.narrative == valid_output()["narrative"]
    assert "customer-123" not in caplog.text
    assert "120.0" not in caplog.text


def test_retry_is_bounded_and_timeout_is_reported():
    provider = FakeProvider([RetryableAIProviderError("temporary"), valid_output()])
    service = AIService(enabled=True, generation_provider=provider, max_retries=1)
    assert asyncio.run(service.generate(request())).narrative
    assert provider.calls == 2

    async def hang():
        await asyncio.sleep(1)

    timed = AIService(
        enabled=True,
        generation_provider=FakeProvider([hang]),
        timeout_seconds=1,
        max_retries=0,
    )
    # asyncio.wait_for's outer limit must still enforce the configured timeout.
    timed.timeout_seconds = 1
    with pytest.raises(AIUnavailableError, match="timed out"):
        asyncio.run(timed.generate(request()))


def test_malformed_and_ungrounded_outputs_are_rejected():
    malformed = AIService(enabled=True, generation_provider=FakeProvider([{"unexpected": True}]))
    with pytest.raises(AIOutputRejectedError):
        asyncio.run(malformed.generate(request()))
    unsupported = valid_output()
    unsupported["narrative"] = "Recorded use was 999 kWh."
    policy = AIService(enabled=True, generation_provider=FakeProvider([unsupported]))
    with pytest.raises(AIOutputRejectedError):
        asyncio.run(policy.generate(request()))


def test_contract_rejects_lineage_errors_and_confirmed_faults():
    with pytest.raises(ValidationError):
        EvidenceEnvelope(
            snapshot_id="s",
            created_at="2026-01-01T00:00:00Z",
            persona="system",
            sources=[],
            facts=[
                {
                    "fact_id": "f",
                    "source_id": "missing",
                    "name": "x",
                    "value": 1,
                    "value_kind": "observation",
                }
            ],
        )
    with pytest.raises(ValidationError):
        AIOutput(narrative="fault confirmed", claims=[], citations=[], confirmed_fault=True)


def test_redaction_masks_common_credentials_and_identifiers():
    redacted = redact_sensitive_text(
        "Contact user@example.com or +1 (555) 123-4567; "
        "Bearer abc.def and api_key=secret-value"
    )
    assert "user@example.com" not in redacted
    assert "123-4567" not in redacted
    assert "abc.def" not in redacted
    assert "secret-value" not in redacted


def test_sqlite_audit_is_separate_minimal_and_idempotent(tmp_path):
    db = tmp_path / "private" / "audit.sqlite"
    repository = SQLiteAuditRepository(db, forbidden_paths=(tmp_path / "gold",))
    repository.initialize()
    event = GenerationAuditEvent(
        request_id="audit-1",
        idempotency_key="idem-1",
        workflow="grounded_explanation",
        prompt_key="grounded_explanation",
        prompt_version="1.0.0",
        provider="fake-test",
        outcome="succeeded",
        source_ids=["gold-v1"],
        duration_ms=3.5,
        output_chars=40,
    )
    first = repository.record(event)
    second = repository.record(event.model_copy(update={"request_id": "audit-2"}))
    assert first["request_id"] == second["request_id"] == "audit-1"
    with sqlite3.connect(db) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_audit_events)")}
    assert not {"prompt", "evidence", "narrative", "entity_ref"}.intersection(columns)
    if os.name == "posix":
        assert db.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        SQLiteAuditRepository(tmp_path / "gold" / "leak.sqlite", forbidden_paths=(tmp_path / "gold",))


def test_private_storage_is_opaque_bounded_and_rejects_traversal(tmp_path):
    store = PrivateFileStore(tmp_path / "private", max_bytes=5)
    store.initialize()
    artifact_id = store.store(b"hello")
    assert store.read(artifact_id) == b"hello"
    with pytest.raises(PrivateStorageError):
        store.read("../secret")
    with pytest.raises(PrivateStorageError):
        store.store(b"too large")


def test_typed_workflow_executes_compiled_langgraph():
    if not importlib.util.find_spec("langgraph"):
        with pytest.raises(WorkflowDependencyUnavailable):
            build_workflow({"step": lambda state: {}}, [("step", END)], entry_point="step")
        return
    graph = build_workflow(
        {"step": lambda state: {"request_id": state["request_id"]}},
        [("step", END)],
        entry_point="step",
    )
    assert graph.invoke({"request_id": "workflow-1"})["request_id"] == "workflow-1"


def test_claim_citations_must_resolve_to_source_facts():
    bad = AIOutput(
        narrative="All values came from source A.",
        claims=[GroundedClaim(text="Observed.", kind="observation", evidence_fact_ids=["consumption-jan"])],
        citations=[Citation(source_id="other", fact_ids=["consumption-jan"])],
    )
    with pytest.raises(AIPolicyError):
        validate_grounded_output(bad, evidence())


def test_rag_filters_by_jurisdiction_and_carries_citations():
    source = CorpusSource(
        source_id="approved-guide-v1",
        title="Meter reporting guide",
        publisher="GridVision test fixture",
        url="https://guidance.example.org/meter",
        jurisdiction="IN",
        version="v1",
        reviewed_on="2026-01-01",
        license_status="approved",
        approved_for_ai=True,
        content="If a meter reading seems inconsistent, compare the display and bill reading.",
    )
    corpus = ApprovedCorpus([source], allowed_domains={"example.org"}, today=__import__("datetime").date(2026, 2, 1))
    result = corpus.retrieve("meter reading bill", jurisdiction="IN")
    assert result.status == "available"
    assert result.passages[0].source_id == "approved-guide-v1"
    assert result.passages[0].url == source.url
    assert corpus.retrieve("meter reading bill", jurisdiction="US").status == "no_answer"
    assert "untrusted" in result.instructions


def test_rag_rejects_unapproved_sources_and_drops_stale_content():
    source = CorpusSource(
        source_id="pending",
        title="Pending guide",
        publisher="Example",
        url="https://example.org/guide",
        jurisdiction="all",
        version="v1",
        reviewed_on="2025-01-01",
        license_status="pending",
        content="consumer guidance",
    )
    with pytest.raises(CorpusError, match="approval"):
        ApprovedCorpus([source], allowed_domains={"example.org"})

    approved = source.model_copy(
        update={
            "license_status": "approved",
            "approved_for_ai": True,
            "expires_on": __import__("datetime").date(2025, 12, 31),
        }
    )
    stale = ApprovedCorpus([approved], allowed_domains={"example.org"}, today=__import__("datetime").date(2026, 1, 1))
    assert stale.retrieve("consumer guidance").status == "no_answer"


def test_application_store_notification_deduplication(tmp_path):
    store = AIApplicationStore(tmp_path / "app.sqlite")
    store.initialize()
    first = store.notify("demo:household", "event-1", "case_status", "Case updated", "Review the case.")
    second = store.notify("demo:household", "event-1", "case_status", "Duplicate", "Duplicate")
    assert first["notification_id"] == second["notification_id"]


def test_report_rendering_escapes_content_and_exports_pdf():
    html_content = ReportService.render_html(
        "<script>alert(1)</script>", {"label": "<img src=x onerror=alert(1)>"}, []
    ).decode()
    assert "<script>" not in html_content
    assert "<img src=x" not in html_content
    pdf_content = ReportService.render_pdf("GridVision report", {"value": 5}, [])
    assert pdf_content.startswith(b"%PDF-")


def test_monthly_report_is_public_cohort_report_with_persona_scoped_downloads(tmp_path, monkeypatch):
    class Config(TestingConfig):
        AI_DATABASE_PATH = str(tmp_path / "ai.sqlite")
        AI_PRIVATE_STORAGE_ROOT = str(tmp_path / "private")

    app = create_app(Config)
    from datetime import date, timedelta
    from app.ai.storage import PrivateFileStore

    last_month = date(2018, 12, 1)
    month_end = date(2018, 12, 31)
    source = {
        "persona": "household",
        "period": {"start": last_month.isoformat(), "end": month_end.isoformat()},
        "daysReturned": 1,
        "totalConsumptionKwh": 88.5,
        "scope": "household_cohort",
    }
    class RetrievalAgent:
        def available_sources(self):
            return {"customer_silver"}
        class Registry:
            def execute(self, name, arguments, *, context, available_sources):
                assert name == "get_latest_household_silver_month"
                assert arguments == {}
                assert context.principal_id == "public-monthly-report-demo"
                assert context.allows_entity("customer_cohort", "*") and "customer_silver" in available_sources
                from types import SimpleNamespace
                return SimpleNamespace(data=source, source={"source_id": "customer_silver", "record_type": "monthly_household_cohort_consumption"})
        registry = Registry()

    class GeneratorRepository:
        def get(self, report_id, owner_key):
            assert report_id == "agent-report-id" and owner_key
            return {"html_artifact_id": html_id, "pdf_artifact_id": pdf_id}

    class Generator:
        repository = GeneratorRepository()
        def generate(self, request, *, owner_key):
            assert owner_key
            assert request.data["period"]["start"] == last_month.isoformat()
            assert request.data["totalConsumptionKwh"] == 88.5
            return {"report_id": "agent-report-id", "title": "Agent monthly summary", "status": "complete"}

    private = PrivateFileStore(tmp_path / "private")
    private.initialize()
    html_id = private.store(b"<html>agent report</html>")
    pdf_id = private.store(b"%PDF-fake-agent")
    app.extensions["data_retrieval_agent"] = RetrievalAgent()
    app.extensions["ai_private_storage"] = private
    app.extensions["report_generator"] = Generator()
    client = app.test_client()
    response = client.post(
        "/api/v1/ai/reports",
        json={"report_type": "monthly_consumption", "persona": "household", "time_range": "1Y"},
    )
    assert response.status_code == 201, response.get_json()
    report = response.get_json()["data"]
    assert report["report_type"] == "monthly_consumption"
    assert report["payload"]["generatorReportId"] == "agent-report-id"
    assert report["payload"]["metadata"]["period"]["start"] == last_month.isoformat()
    html_download = client.get(f"/api/v1/ai/reports/{report['report_id']}/download/html?persona=household")
    pdf_download = client.get(f"/api/v1/ai/reports/{report['report_id']}/download/pdf?persona=household")
    assert html_download.status_code == 200
    assert pdf_download.status_code == 200
    assert pdf_download.data.startswith(b"%PDF-")
    assert client.get(f"/api/v1/ai/reports/{report['report_id']}/download/html?persona=commercial").status_code == 404

    unavailable = client.post(f"/api/v1/ai/reports/{report['report_id']}/email?persona=household", json={})
    assert unavailable.status_code == 503
    assert unavailable.get_json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"

    app.config.update({"REPORT_EMAIL_SMTP_HOST": "smtp.example.test", "REPORT_EMAIL_FROM_ADDRESS": "reports@example.test"})
    sent = {}
    def fake_send_report_email(**kwargs):
        sent.update(kwargs)
    monkeypatch.setattr("app.api.v1.ai_layer.send_report_email", fake_send_report_email)
    emailed = client.post(f"/api/v1/ai/reports/{report['report_id']}/email?persona=household", json={})
    assert emailed.status_code == 202
    assert emailed.get_json()["data"]["recipient"] == "kanak.nagar64@gmail.com"
    assert emailed.get_json()["data"]["format"] == "pdf"
    assert sent["attachment_bytes"].startswith(b"%PDF-")
