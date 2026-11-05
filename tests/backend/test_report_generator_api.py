"""Flask API authorization, validation, and artifact access checks."""

from __future__ import annotations

import pytest
from flask import request

from app.ai.storage import PrivateFileStore
from report_generator.config import ReportGeneratorSettings
from report_generator.services.report_generator import JSONReportGenerator
from report_generator.storage.report_storage import ReportRepository


class APIProvider:
    provider_id = "test"

    def generate(self, prompt, *, timeout_seconds, max_output_chars):
        return '{"title":"Test report","subtitle":null,"executive_summary":"One value is included: 5.","sections":[{"title":"Summary","content":["The source contains 5."],"observations":[]}],"conclusion":null,"limitations":[]}'


class APIPDF:
    def render(self, report):
        return b"%PDF-fake"


@pytest.fixture
def report_api(app, tmp_path):
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.extensions["report_generator_identity_resolver"] = lambda req: req.headers.get("X-Test-User")
    app.extensions["ai_private_storage"] = PrivateFileStore(tmp_path / "private")
    app.extensions["report_generator"] = JSONReportGenerator(
        settings=ReportGeneratorSettings(enabled=True, provider="hosted"),
        provider=APIProvider(),
        repository=ReportRepository(tmp_path / "reports.sqlite"),
        artifact_store=app.extensions["ai_private_storage"],
        pdf_renderer=APIPDF(),
    )
    return app.test_client()


def test_generation_requires_trusted_identity(app):
    client = app.test_client()
    response = client.post(
        "/api/v1/report-generator/generate",
        json={"data": {"value": 5}},
    )
    assert response.status_code == 401
    assert response.json["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_provider_failure_returns_id_for_owner_scoped_status_lookup(report_api):
    from report_generator.config import ReportGeneratorSettings
    from report_generator.services.report_generator import JSONReportGenerator
    existing = report_api.application.extensions["report_generator"]
    report_api.application.extensions["report_generator"] = JSONReportGenerator(
        settings=ReportGeneratorSettings(enabled=True, provider="hosted"),
        provider=None,
        repository=existing.repository,
        artifact_store=report_api.application.extensions["ai_private_storage"],
    )
    response = report_api.post(
        "/api/v1/report-generator/generate",
        json={"data": {"value": 5}},
        headers={"X-Test-User": "alice"},
    )
    assert response.status_code == 503
    error = response.json["error"]
    assert error["code"] == "REPORT_PROVIDER_UNAVAILABLE"
    report_id = error["details"]["report_id"]
    status = report_api.get(
        f"/api/v1/report-generator/reports/{report_id}",
        headers={"X-Test-User": "alice"},
    )
    assert status.json["data"]["status"] == "failed"


def test_generation_and_owner_scoped_report_retrieval(report_api):
    response = report_api.post(
        "/api/v1/report-generator/generate",
        json={"data": {"value": 5}, "output_formats": ["html", "pdf"]},
        headers={"X-Test-User": "alice"},
    )
    assert response.status_code == 201
    result = response.json["data"]
    report_id = result["report_id"]
    assert result["status"] == "complete"

    metadata = report_api.get(
        f"/api/v1/report-generator/reports/{report_id}",
        headers={"X-Test-User": "alice"},
    )
    assert metadata.status_code == 200
    assert metadata.json["data"]["title"] == "Test report"

    html = report_api.get(
        f"/api/v1/report-generator/reports/{report_id}/html",
        headers={"X-Test-User": "alice"},
    )
    assert html.status_code == 200
    assert html.mimetype == "text/html"
    assert html.headers["Cache-Control"] == "private, no-store"
    assert b"Test report" in html.data

    pdf = report_api.get(
        f"/api/v1/report-generator/reports/{report_id}/pdf",
        headers={"X-Test-User": "alice"},
    )
    assert pdf.status_code == 200
    assert pdf.data == b"%PDF-fake"

    cross_owner = report_api.get(
        f"/api/v1/report-generator/reports/{report_id}",
        headers={"X-Test-User": "bob"},
    )
    assert cross_owner.status_code == 404


@pytest.mark.parametrize(
    ("headers", "body", "expected"),
    [
        ({"X-Test-User": "alice", "Content-Type": "text/plain"}, b"{}", 415),
        ({"X-Test-User": "alice", "Content-Type": "application/json"}, b"{broken", 422),
        ({"X-Test-User": "alice", "Content-Type": "application/json"}, b'{"data":1,"unknown":2}', 422),
    ],
)
def test_invalid_api_requests_are_rejected(report_api, headers, body, expected):
    response = report_api.post(
        "/api/v1/report-generator/generate", data=body, headers=headers
    )
    assert response.status_code == expected


def test_missing_and_invalid_report_ids_are_not_disclosed(report_api):
    response = report_api.get(
        "/api/v1/report-generator/reports/../html",
        headers={"X-Test-User": "alice"},
    )
    assert response.status_code in {404, 308}
    not_found = report_api.get(
        "/api/v1/report-generator/reports/0123456789abcdef0123456789abcdef",
        headers={"X-Test-User": "alice"},
    )
    assert not_found.status_code == 404


def test_health_reports_readiness_without_secret_values(report_api):
    response = report_api.get("/api/v1/report-generator/health")
    assert response.status_code == 200
    assert response.json["data"]["enabled"] is True
    assert response.json["data"]["identity_resolver_configured"] is True
    assert "api_key" not in str(response.json).lower()
