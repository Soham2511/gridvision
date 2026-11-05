"""Tests for end-to-end automated anomaly reporting and notification workflow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from app import create_app
from app.ai.application_store import AIApplicationStore
from app.ai.storage import PrivateFileStore
from app.config import TestingConfig
from app.schemas.rectification_schema import (
    EventCoordinates,
    EventDetails,
    GuidanceCitation,
    RectificationReportPayload,
    SeverityInfo,
)
from app.services.anomaly_workflow_service import AnomalyWorkflowService
from app.services.rectification_agent import RectificationAgent
from report_generator.services.consumption_analytics import is_anomaly_report
from report_generator.services.pdf_renderer import PDFReportRenderer


SAMPLE_EVENT = {
    "event_id": "EVT_TEST_001",
    "event_scope": "SINGLE_CUSTOMER",
    "event_start": "2019-01-01T04:00:00",
    "event_end": "2019-01-01T05:00:00",
    "event_duration": 3600.0,
    "affected_customer_count": 1,
    "customer_ids": [546503],
    "dominant_anomaly_type": "spike",
    "anomaly_types": ["spike"],
    "mean_anomaly_score": 0.71,
    "max_anomaly_score": 0.75,
    "latitude_center": 33.9317,
    "longitude_center": -118.1649,
}


def test_rectification_schema_and_agent():
    payload = RectificationAgent.generate_rectification_payload(
        event=SAMPLE_EVENT,
        run={"run_id": "RUN_TEST_1"},
        persona="household",
        entity_id=546503,
        customer_email="kanak.nagar64@gmail.com",
    )
    assert isinstance(payload, RectificationReportPayload)
    assert payload.event_id == "EVT_TEST_001"
    assert payload.severity.level == "CRITICAL"
    assert payload.severity.score == 0.75
    assert len(payload.probable_causes) >= 1
    assert len(payload.corrective_actions) >= 1
    assert len(payload.preventive_recommendations) >= 1
    assert str(payload.customer_id) == "546503"
    assert is_anomaly_report(payload.model_dump()) is True


def test_pdf_renderer_render_anomaly_report():
    renderer = PDFReportRenderer()
    payload = RectificationAgent.generate_rectification_payload(
        event=SAMPLE_EVENT,
        run={"run_id": "RUN_TEST_1"},
        persona="household",
    )
    pdf_bytes = renderer.render_anomaly_report(payload.model_dump())
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000


def test_application_store_workflow_executions(tmp_path: Path):
    store = AIApplicationStore(tmp_path / "test_app.sqlite")
    store.initialize()

    # Record execution
    rec = store.record_workflow_execution(
        event_id="EVT_EXEC_01",
        run_id="RUN_001",
        persona="household",
        customer_id="546503",
        overall_status="PENDING",
    )
    assert rec["event_id"] == "EVT_EXEC_01"
    assert rec["overall_status"] == "PENDING"
    assert rec["json_status"] == "PENDING"

    # Update execution
    updated = store.update_workflow_execution(
        "EVT_EXEC_01",
        json_status="SUCCESS",
        report_status="SUCCESS",
        overall_status="IN_PROGRESS",
        report_id="REP_001",
    )
    assert updated is not None
    assert updated["json_status"] == "SUCCESS"
    assert updated["report_status"] == "SUCCESS"
    assert updated["report_id"] == "REP_001"

    # Get execution
    fetched = store.get_workflow_execution("EVT_EXEC_01")
    assert fetched is not None
    assert fetched["report_id"] == "REP_001"

    # List executions
    items = store.list_workflow_executions(run_id="RUN_001")
    assert len(items) == 1
    assert items[0]["event_id"] == "EVT_EXEC_01"


def test_workflow_service_end_to_end(tmp_path: Path):
    store = AIApplicationStore(tmp_path / "app.sqlite")
    store.initialize()
    priv = PrivateFileStore(tmp_path / "private")
    priv.initialize()

    config = {
        "REPORT_EMAIL_SMTP_HOST": "smtp.gmail.com",
        "REPORT_EMAIL_DEFAULT_RECIPIENT": "kanak.nagar64@gmail.com",
    }

    sent_emails = []

    def fake_send_report_email(**kwargs):
        sent_emails.append(kwargs)

    with patch("app.services.anomaly_workflow_service.send_report_email", side_effect=fake_send_report_email):
        service = AnomalyWorkflowService(store, priv, config)
        result = service.process_event(
            event=SAMPLE_EVENT,
            run={"run_id": "RUN_ABC"},
            persona="household",
            entity_id=546503,
        )

        assert result["overall_status"] == "COMPLETED"
        assert result["json_status"] == "SUCCESS"
        assert result["report_status"] == "SUCCESS"
        assert result["email_status"] == "SUCCESS"
        assert result["notification_status"] == "SUCCESS"
        assert result["report_id"] is not None
        assert result["pdf_artifact_id"] is not None

        # Verify email was sent with PDF
        assert len(sent_emails) == 1
        assert sent_emails[0]["recipient"] == "kanak.nagar64@gmail.com"
        assert sent_emails[0]["attachment_bytes"].startswith(b"%PDF-")

        # Verify website notification was persisted
        notifs = store.list_notifications("demo:household:entity:546503")
        assert len(notifs) == 1
        assert "Action plan" in notifs[0]["body"]
        assert result["report_id"] in notifs[0]["event_key"]

        # Verify deduplication
        dedup_result = service.process_event(
            event=SAMPLE_EVENT,
            run={"run_id": "RUN_ABC"},
            persona="household",
            entity_id=546503,
        )
        assert dedup_result["execution_id"] == result["execution_id"]
        assert len(sent_emails) == 1  # No duplicate email sent


def test_workflow_service_skips_empty_run_events(tmp_path: Path):
    store = AIApplicationStore(tmp_path / "app.sqlite")
    store.initialize()
    priv = PrivateFileStore(tmp_path / "private")
    priv.initialize()

    service = AnomalyWorkflowService(store, priv, {})
    res = service.process_run_events(run_id="RUN_EMPTY", events=[])
    assert res == []


def test_api_workflow_trigger_and_download(tmp_path: Path):
    class Config(TestingConfig):
        AI_DATABASE_PATH = str(tmp_path / "api_ai.sqlite")
        AI_PRIVATE_STORAGE_ROOT = str(tmp_path / "api_private")
        REPORT_EMAIL_SMTP_HOST = ""  # skip email sending in api test

    app = create_app(Config)
    client = app.test_client()

    # Trigger workflow via API
    trigger_resp = client.post(
        "/api/v1/ai/anomaly-workflow/trigger",
        json={
            "event": SAMPLE_EVENT,
            "run_id": "RUN_API_TEST",
            "persona": "household",
            "entity_id": "546503",
        },
    )
    assert trigger_resp.status_code == 200, trigger_resp.get_json()
    exec_data = trigger_resp.get_json()["data"]
    assert exec_data["overall_status"] == "COMPLETED"
    report_id = exec_data["report_id"]

    # Query executions list
    list_resp = client.get("/api/v1/ai/anomaly-workflow/executions")
    assert list_resp.status_code == 200
    items = list_resp.get_json()["data"]["items"]
    assert len(items) >= 1
    assert any(i["event_id"] == SAMPLE_EVENT["event_id"] for i in items)

    # Query specific execution
    detail_resp = client.get(f"/api/v1/ai/anomaly-workflow/executions/{SAMPLE_EVENT['event_id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.get_json()["data"]["event_id"] == SAMPLE_EVENT["event_id"]

    # Download PDF report via report API
    download_resp = client.get(
        f"/api/v1/ai/reports/{report_id}/download/pdf?persona=household&entity_id=546503"
    )
    assert download_resp.status_code == 200
    assert download_resp.data.startswith(b"%PDF-")
