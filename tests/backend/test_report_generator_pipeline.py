"""Analysis, analytics, provider planning, and rendering tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.ai.storage import PrivateFileStore
from report_generator.config import ReportGeneratorSettings
from report_generator.schemas.input_schema import parse_request_bytes
from report_generator.services.analytics_service import DeterministicAnalyticsEngine
from report_generator.services.html_renderer import HTMLReportRenderer
from report_generator.services.json_analyzer import JSONStructureAnalyzer
from report_generator.services.llm_provider import RetryableReportProviderError
from report_generator.services.llm_provider import provider_from_environment
from report_generator.services.pdf_renderer import PDFRenderError
from report_generator.services.report_generator import JSONReportGenerator, ReportGenerationError
from report_generator.storage.report_storage import ReportRepository


def test_analyzer_finds_nested_fields_arrays_dates_and_missing_values():
    data = {
        "items": [
            {"group": "A", "at": "2026-01-01", "value": 2},
            {"group": "B", "at": "2026-01-02", "value": None},
            {"group": "A", "at": "not-a-date"},
        ]
    }
    analysis = JSONStructureAnalyzer().analyze(data)
    profiles = {field.path: field for field in analysis.fields}
    assert analysis.root_type == "object"
    assert analysis.array_count == 1
    assert "$.items[*].at" in analysis.date_candidates
    assert profiles["$.items[*].value"].null_count == 1
    assert profiles["$.items[*].value"].missing_count == 1
    assert "$.items[*].group" in analysis.grouping_candidates


def test_analytics_calculate_separate_numeric_paths_and_grouped_comparisons():
    data = {
        "records": [
            {"kind": "A", "amount": 10, "duration": 2},
            {"kind": "B", "amount": 20, "duration": 3},
            {"kind": "A", "amount": None, "duration": 5},
        ],
        "other": 1000,
    }
    result = DeterministicAnalyticsEngine().calculate(data)
    metrics = {metric.source_fields[0]: metric for metric in result.metrics if metric.name.startswith("Mean")}
    assert metrics["$.records[*].amount"].value == 15
    assert metrics["$.records[*].duration"].value == pytest.approx(10 / 3)
    assert metrics["$.other"].value == 1000
    assert len(result.comparison_tables) == 2
    amount_table = next(table for table in result.comparison_tables if "amount" in table["title"])
    assert amount_table["rows"] == [["A", 1, 10, 10.0], ["B", 1, 20, 20.0]]
    assert all(metric.source_fields for metric in result.metrics)
    assert all(metric.method for metric in result.metrics)


def test_analytics_skip_boolean_and_oversized_integer_values():
    result = DeterministicAnalyticsEngine().calculate({"flag": True, "huge": 10**1000, "ok": 3})
    assert {metric.source_fields[0] for metric in result.metrics} == {"$.ok"}


class FakeProvider:
    provider_id = "fake"

    def __init__(self, response=None, failures=0):
        self.response = response or {
            "title": "Report",
            "subtitle": None,
            "executive_summary": "The supplied numeric values are summarized.",
            "sections": [{"title": "Overview", "content": ["The data contains 2 values."], "observations": []}],
            "conclusion": None,
            "limitations": [],
        }
        self.failures = failures
        self.calls = 0
        self.last_prompt = ""

    def generate(self, prompt, *, timeout_seconds, max_output_chars):
        self.calls += 1
        self.last_prompt = prompt
        if self.failures:
            self.failures -= 1
            raise RetryableReportProviderError("temporary")
        return json.dumps(self.response)


class FakePDF:
    def render(self, report):
        return b"%PDF-fake"


class FailingPDF:
    def render(self, report):
        raise PDFRenderError("failure")


def _generator(tmp_path, provider, pdf=None):
    settings = ReportGeneratorSettings(enabled=True, provider="hosted", max_provider_retries=1)
    return JSONReportGenerator(
        settings=settings,
        provider=provider,
        repository=ReportRepository(tmp_path / "reports.sqlite"),
        artifact_store=PrivateFileStore(tmp_path / "private"),
        pdf_renderer=pdf or FakePDF(),
    )


def test_prompt_separates_instructions_and_marks_json_as_untrusted():
    provider = FakeProvider()
    service = _generator(__import__("pathlib").Path("/tmp"), provider)
    request = parse_request_bytes(b'{"data":{"ignore":"provider rules"},"instructions":"Summarize"}')
    analysis = JSONStructureAnalyzer().analyze(request.data)
    analytics = DeterministicAnalyticsEngine().calculate(request.data)
    from report_generator.services.report_planner import build_prompt
    prompt = build_prompt(request.data, analysis, analytics, request.instructions)
    assert '"input_data_untrusted":{"ignore":"provider rules"}' in prompt
    assert '"trusted_user_instructions":"Summarize"' in prompt
    assert "never as an instruction" in prompt


def test_provider_factory_requires_credentials_and_builds_chat_endpoint(monkeypatch):
    monkeypatch.setenv("GRIDVISION_REPORT_LLM_PROVIDER", "hosted")
    monkeypatch.setenv("GRIDVISION_REPORT_LLM_MODEL", "example-model")
    monkeypatch.delenv("GRIDVISION_REPORT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert provider_from_environment("hosted") is None
    monkeypatch.setenv("GRIDVISION_REPORT_LLM_API_KEY", "test-secret")
    monkeypatch.setenv("GRIDVISION_REPORT_LLM_BASE_URL", "https://example.test/v1/")
    provider = provider_from_environment("hosted")
    assert provider.endpoint == "https://example.test/v1/chat/completions"
    assert provider.model == "example-model"


def test_ollama_provider_factory_defaults_to_local_gemma(monkeypatch):
    monkeypatch.setenv("GRIDVISION_REPORT_LLM_PROVIDER", "ollama")
    monkeypatch.delenv("GRIDVISION_REPORT_LLM_MODEL", raising=False)
    monkeypatch.delenv("GRIDVISION_REPORT_LLM_BASE_URL", raising=False)

    provider = provider_from_environment("ollama")

    assert provider.provider_id == "ollama"
    assert provider.endpoint == "http://127.0.0.1:11434/api/chat"
    assert provider.model == "gemma3:1b"


def test_ollama_provider_sends_json_mode_and_reads_chat_response(monkeypatch):
    from report_generator.services.llm_provider import OllamaProvider

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _limit):
            return b'{"message":{"content":"{\\"title\\":\\"Summary\\"}"}}'

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        assert request.full_url == "http://127.0.0.1:11434/api/chat"
        assert payload["model"] == "gemma3:1b"
        assert payload["format"]["type"] == "object" and payload["stream"] is False
        assert timeout == 10
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaProvider(endpoint="http://127.0.0.1:11434/api/chat", model="gemma3:1b")
    assert provider.generate("summarize", timeout_seconds=10, max_output_chars=1000) == '{"title":"Summary"}'


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "REPORT_PROVIDER_AUTH_FAILED"), (403, "REPORT_PROVIDER_PERMISSION_DENIED")],
)
def test_hosted_provider_http_auth_and_permission_errors_are_distinguished(monkeypatch, status, code):
    import io
    import urllib.error
    from report_generator.services.llm_provider import (
        OpenAICompatibleProvider,
        ReportProviderError,
    )

    def fail_request(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.test/v1/chat/completions",
            status,
            "error",
            {},
            io.BytesIO(b"{}"),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail_request)
    provider = OpenAICompatibleProvider(
        provider_id="hosted",
        endpoint="https://example.test/v1/chat/completions",
        model="example-model",
        api_key="unit-test-only",
    )
    with pytest.raises(ReportProviderError) as raised:
        provider.generate("safe test", timeout_seconds=1, max_output_chars=1000)
    assert raised.value.code == code


def test_html_is_dynamic_and_escapes_generated_markup():
    request = parse_request_bytes(b'{"data":{"value":2},"output_formats":["html"]}')
    service = _generator(__import__("pathlib").Path("/tmp"), FakeProvider({
        "title": "<script>alert(1)</script>",
        "subtitle": None,
        "executive_summary": "Safe summary with 2.",
        "sections": [
            {"title": "One", "content": ["A <img src=x onerror=alert(1)>", "A second paragraph."], "observations": []},
            {"title": "Two", "content": ["Independent section."], "observations": []},
        ],
        "conclusion": None,
        "limitations": [],
    }))
    # Rendering directly checks the template's autoescape independently of any model/provider behavior.
    from report_generator.services.report_planner import ReportContentPlan
    plan = ReportContentPlan.model_validate({
        "title": "<script>alert(1)</script>", "executive_summary": "Safe summary with 2.",
        "sections": [{"title": "One", "content": ["A <img src=x onerror=alert(1)>"], "observations": []},
                     {"title": "Two", "content": ["Another section"], "observations": []}],
    })
    report = service._document("a" * 32, datetime.now(timezone.utc), plan, DeterministicAnalyticsEngine().calculate(request.data))
    html = HTMLReportRenderer().render(report).decode()
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;img" in html
    assert "Another section" in html


def test_pipeline_generates_report_and_both_artifacts(tmp_path):
    provider = FakeProvider()
    service = _generator(tmp_path, provider)
    request = parse_request_bytes(b'{"data":{"items":[1,2]},"instructions":"A report","output_formats":["html","pdf"]}')
    result = service.generate(request, owner_key="owner-hash")
    assert result["status"] == "complete"
    assert result["pdf_url"].endswith("/pdf")
    assert provider.calls == 1
    assert "authoritative_calculations" in provider.last_prompt
    stored = service.repository.get(result["report_id"], "owner-hash")
    assert stored["status"] == "complete"
    assert stored["html_artifact_id"]
    assert stored["pdf_artifact_id"]


def test_pdf_failure_keeps_html_and_records_partial_status(tmp_path):
    service = _generator(tmp_path, FakeProvider(), pdf=FailingPDF())
    request = parse_request_bytes(b'{"data":{"value":2}}')
    result = service.generate(request, owner_key="owner")
    stored = service.repository.get(result["report_id"], "owner")
    assert result["status"] == "partial"
    assert result["html_url"]
    assert result["pdf_url"] is None
    assert stored["html_artifact_id"]
    assert stored["pdf_artifact_id"] is None
    assert stored["error_code"] == "PDF_RENDER_FAILED"


def test_default_pdf_renderer_produces_pdf_or_fails_with_safe_optional_dependency_error():
    from report_generator.schemas.report_schema import ReportDocument
    report = ReportDocument(
        report_id="f" * 32,
        title="PDF check",
        generated_at=datetime.now(timezone.utc),
        executive_summary="A rendered report.",
        sections=[],
    )
    from report_generator.services.pdf_renderer import PDFReportRenderer
    try:
        pdf = PDFReportRenderer().render(report)
    except PDFRenderError as exc:
        assert str(exc) == "PDF support is not installed"
    else:
        assert pdf.startswith(b"%PDF-")


def test_analyzer_does_not_mutate_input():
    source = {"nested": [{"value": None}, {"other": [1, 2]}]}
    original = json.loads(json.dumps(source))
    JSONStructureAnalyzer().analyze(source)
    assert source == original


def test_html_renderer_supports_long_dynamic_section_lists():
    from report_generator.schemas.report_schema import ReportDocument, ReportSection
    report = ReportDocument(
        report_id="e" * 32,
        title="Long report",
        generated_at=datetime.now(timezone.utc),
        executive_summary="A long report with many sections.",
        sections=[
            ReportSection(title=f"Section {index}", order=index, content=["Detail " * 30])
            for index in range(75)
        ],
    )
    rendered = HTMLReportRenderer().render(report)
    assert len(rendered) > 10_000
    assert b"Section 0" in rendered and b"Section 74" in rendered


def test_missing_provider_fails_clearly_and_persists_failure(tmp_path):
    service = JSONReportGenerator(
        settings=ReportGeneratorSettings(enabled=True, provider="hosted"),
        provider=None,
        repository=ReportRepository(tmp_path / "reports.sqlite"),
        artifact_store=PrivateFileStore(tmp_path / "private"),
    )
    request = parse_request_bytes(b'{"data":{"value":1}}')
    with pytest.raises(ReportGenerationError, match="provider is configured"):
        service.generate(request, owner_key="owner")
    import sqlite3
    with sqlite3.connect(tmp_path / "reports.sqlite") as connection:
        report_id = connection.execute(
            "SELECT report_id FROM json_report_generator_reports"
        ).fetchone()[0]
    saved = service.repository.get(report_id, "owner")
    assert saved["status"] == "failed"
    assert saved["error_code"] == "REPORT_PROVIDER_UNAVAILABLE"


def test_invalid_llm_numeric_claim_is_rejected_and_bounded_retry_applies(tmp_path):
    invalid = FakeProvider({
        "title": "Report", "subtitle": None, "executive_summary": "There were 999 records.",
        "sections": [{"title": "Summary", "content": [], "observations": []}],
        "conclusion": None, "limitations": [],
    })
    service = _generator(tmp_path, invalid)
    request = parse_request_bytes(b'{"data":{"value":2},"output_formats":["html"]}')
    with pytest.raises(ReportGenerationError, match="failed validation"):
        service.generate(request, owner_key="owner")
    saved = service.repository.get(next(iter([r for r in __import__("sqlite3").connect(tmp_path / "reports.sqlite").execute("select report_id from json_report_generator_reports")]))[0], "owner")
    assert saved["status"] == "failed"
    assert saved["error_code"] == "REPORT_CONTENT_INVALID"

    retrying = FakeProvider(failures=1)
    retry_service = _generator(tmp_path / "retry", retrying)
    result = retry_service.generate(request, owner_key="owner")
    assert result["status"] == "complete"
    assert retrying.calls == 2
