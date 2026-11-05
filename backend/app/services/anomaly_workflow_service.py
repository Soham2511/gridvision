"""End-to-end automated anomaly reporting and notification workflow."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.ai.application_store import AIApplicationStore, ApplicationStoreError
from app.ai.email_delivery import EmailDeliveryError, send_report_email
from app.ai.report_service import ReportService
from app.ai.storage import PrivateFileStore
from app.schemas.rectification_schema import RectificationReportPayload
from app.services.rectification_agent import RectificationAgent
from report_generator.services.pdf_renderer import PDFReportRenderer

logger = logging.getLogger("gridvision.anomaly.workflow")


class AnomalyWorkflowError(RuntimeError):
    """Raised when an anomaly workflow execution fails fatally."""


class AnomalyWorkflowService:
    """Orchestrates JSON diagnosis, PDF generation, email alerts, and persistent notifications."""

    def __init__(
        self,
        store: AIApplicationStore,
        private_store: PrivateFileStore,
        config: dict[str, Any] | Any,
        pdf_renderer: PDFReportRenderer | None = None,
        max_email_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.store = store
        self.private_store = private_store
        self.config = config
        self.pdf_renderer = pdf_renderer or PDFReportRenderer()
        self.max_email_retries = max(1, max_email_retries)
        self.retry_delay_seconds = max(0.1, retry_delay_seconds)

    def _get_config_value(self, key: str, default: Any = None) -> Any:
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        return getattr(self.config, key, default)

    def process_event(
        self,
        event: dict[str, Any],
        run: dict[str, Any] | None = None,
        *,
        persona: str = "household",
        entity_id: str | int | None = None,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """Execute the complete reporting and notification workflow for a single anomaly event."""
        event_id = str(event.get("event_id") or event.get("id") or "")
        if not event_id:
            raise ValueError("Anomaly event data must contain an 'event_id'.")

        run_data = run or {}
        run_id = str(
            event.get("run_id")
            or run_data.get("analysis_id")
            or run_data.get("run_id")
            or "RUN_UNKNOWN"
        )

        customer_ids = event.get("customer_ids") or []
        resolved_customer = entity_id or (customer_ids[0] if customer_ids else None)

        self.store.initialize()
        self.private_store.initialize()

        # Step 0: Deduplication Check
        existing = self.store.get_workflow_execution(event_id)
        if existing and existing.get("overall_status") == "COMPLETED":
            logger.info(
                "anomaly_workflow_deduplicated",
                extra={
                    "event": {
                        "event_id": event_id,
                        "status": "COMPLETED",
                        "message": "Event already processed; returning cached execution.",
                    }
                },
            )
            return existing

        retry_count = (existing.get("retry_count") or 0) + 1 if existing else 0
        if existing:
            self.store.update_workflow_execution(
                event_id,
                overall_status="IN_PROGRESS",
                retry_count=retry_count,
            )
        else:
            self.store.record_workflow_execution(
                event_id=event_id,
                run_id=run_id,
                persona=persona,
                customer_id=str(resolved_customer) if resolved_customer else None,
                overall_status="IN_PROGRESS",
                json_status="PENDING",
                report_status="PENDING",
                email_status="PENDING",
                notification_status="PENDING",
            )

        logger.info(
            "anomaly_workflow_started",
            extra={"event": {"event_id": event_id, "run_id": run_id, "retry_count": retry_count}},
        )

        # -------------------------------------------------------------
        # Step 1: Rectification JSON Diagnosis Generation
        # -------------------------------------------------------------
        try:
            self.store.update_workflow_execution(event_id, json_status="IN_PROGRESS")
            payload_model = RectificationAgent.generate_rectification_payload(
                event=event,
                run=run,
                persona=persona,
                entity_id=resolved_customer,
                customer_email=customer_email,
            )
            payload_dict = payload_model.model_dump()
            self.store.update_workflow_execution(event_id, json_status="SUCCESS")
            logger.info(
                "anomaly_workflow_json_success",
                extra={
                    "event": {
                        "event_id": event_id,
                        "dominant_anomaly_type": payload_model.dominant_anomaly_type,
                        "severity": payload_model.severity.level,
                    }
                },
            )
        except Exception as exc:
            err_msg = f"Rectification JSON generation failed: {exc}"
            logger.error("anomaly_workflow_json_failed", extra={"event": {"event_id": event_id, "error": str(exc)}})
            self.store.update_workflow_execution(
                event_id,
                json_status="FAILED",
                overall_status="FAILED",
                error_message=err_msg,
            )
            raise AnomalyWorkflowError(err_msg) from exc

        # -------------------------------------------------------------
        # Step 2: Report Agent PDF and HTML Generation
        # -------------------------------------------------------------
        try:
            self.store.update_workflow_execution(event_id, report_status="IN_PROGRESS")
            pdf_bytes = self.pdf_renderer.render_anomaly_report(payload_dict)
            pdf_artifact_id = self.private_store.store(pdf_bytes)

            title = f"Anomaly Incident & Rectification Report: {event_id}"
            sources = [
                {
                    "dataset": "anomaly_inference_engine",
                    "datasetVersion": "1.0",
                    "provenance": f"model_run:{run_id}",
                }
            ]
            html_bytes = ReportService.render_html(title, payload_dict, sources)
            html_artifact_id = self.private_store.store(html_bytes)

            # Store in ai_reports table
            base_context = f"demo:{persona}"
            target_context = (
                f"{base_context}:entity:{resolved_customer}"
                if resolved_customer and persona in {"household", "commercial"}
                else base_context
            )

            report_record = self.store.create_report(
                report_type="anomaly_rectification",
                context=target_context,
                source_refs=sources,
                payload={
                    "metadata": {
                        "eventId": event_id,
                        "runId": run_id,
                        "persona": persona,
                        "entityId": str(resolved_customer) if resolved_customer else None,
                        "anomalyType": payload_model.dominant_anomaly_type,
                        "severity": payload_model.severity.level,
                    },
                    "pdfArtifactId": pdf_artifact_id,
                    "generationStatus": "complete",
                    "rectification": payload_dict,
                },
                artifact_id=html_artifact_id,
                idempotency_key=f"anomaly_report:{event_id}",
            )
            report_id = report_record["report_id"]

            self.store.update_workflow_execution(
                event_id,
                report_status="SUCCESS",
                report_id=report_id,
                pdf_artifact_id=pdf_artifact_id,
            )
            logger.info(
                "anomaly_workflow_report_success",
                extra={"event": {"event_id": event_id, "report_id": report_id, "pdf_artifact_id": pdf_artifact_id}},
            )
        except Exception as exc:
            err_msg = f"Report generation failed: {exc}"
            logger.error("anomaly_workflow_report_failed", extra={"event": {"event_id": event_id, "error": str(exc)}})
            self.store.update_workflow_execution(
                event_id,
                report_status="FAILED",
                overall_status="FAILED",
                error_message=err_msg,
            )
            raise AnomalyWorkflowError(err_msg) from exc

        # -------------------------------------------------------------
        # Step 3: Customer Email Delivery
        # -------------------------------------------------------------
        email_status = "SKIPPED"
        recipient = (
            customer_email
            or str(self._get_config_value("REPORT_EMAIL_DEFAULT_RECIPIENT", "")).strip()
        )
        smtp_host = str(self._get_config_value("REPORT_EMAIL_SMTP_HOST", "")).strip()

        if recipient and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient) and smtp_host:
            self.store.update_workflow_execution(event_id, email_status="IN_PROGRESS", email_recipient=recipient)
            delivered = False
            last_email_err: Exception | None = None
            for attempt in range(1, self.max_email_retries + 1):
                try:
                    logger.info(
                        "anomaly_workflow_email_attempt",
                        extra={"event": {"event_id": event_id, "attempt": attempt, "recipient": recipient}},
                    )
                    send_report_email(
                        config=self.config,
                        recipient=recipient,
                        subject=f"GridVision Alert: {payload_model.dominant_anomaly_type} [{payload_model.severity.level}] - Event {event_id}",
                        body=(
                            f"A power grid anomaly ({payload_model.dominant_anomaly_type}) "
                            f"with severity {payload_model.severity.level} was detected.\n\n"
                            f"Customer / Meter: {resolved_customer or 'Grid Substation'}\n"
                            f"Duration: {payload_model.event_details.duration_hours:.2f} hours\n\n"
                            "Attached is your complete Anomaly Rectification & Corrective Action PDF Report."
                        ),
                        attachment_name=f"gridvision-anomaly-{event_id}.pdf",
                        attachment_bytes=pdf_bytes,
                        attachment_mime="application/pdf",
                    )
                    delivered = True
                    email_status = "SUCCESS"
                    self.store.update_workflow_execution(event_id, email_status="SUCCESS")
                    logger.info(
                        "anomaly_workflow_email_success",
                        extra={"event": {"event_id": event_id, "recipient": recipient, "attempt": attempt}},
                    )
                    break
                except EmailDeliveryError as exc:
                    last_email_err = exc
                    logger.warning(
                        "anomaly_workflow_email_retry",
                        extra={"event": {"event_id": event_id, "attempt": attempt, "error": str(exc)}},
                    )
                    if attempt < self.max_email_retries:
                        time.sleep(self.retry_delay_seconds * attempt)

            if not delivered:
                email_status = "FAILED"
                logger.error(
                    "anomaly_workflow_email_exhausted",
                    extra={"event": {"event_id": event_id, "recipient": recipient, "error": str(last_email_err)}},
                )
                self.store.update_workflow_execution(
                    event_id,
                    email_status="FAILED",
                    error_message=f"Email delivery failed after {self.max_email_retries} attempts: {last_email_err}",
                )
        else:
            logger.info(
                "anomaly_workflow_email_skipped",
                extra={"event": {"event_id": event_id, "reason": "No valid recipient or SMTP unconfigured"}},
            )
            self.store.update_workflow_execution(event_id, email_status="SKIPPED")

        # -------------------------------------------------------------
        # Step 4: Persistent Website Notification
        # -------------------------------------------------------------
        try:
            self.store.update_workflow_execution(event_id, notification_status="IN_PROGRESS")
            notif_title = f"Anomaly Alert: {payload_model.dominant_anomaly_type} ({payload_model.severity.level})"
            meter_info = f"Meter #{resolved_customer}" if resolved_customer else "Grid Sensor"
            notif_body = (
                f"{payload_model.severity.level} severity event detected on {meter_info}. "
                f"Duration: {payload_model.event_details.duration_hours:.1f} hrs. "
                "Action plan and engineering rectification report are available."
            )

            notif = self.store.notify(
                recipient_context=target_context,
                event_key=f"anomaly-event:{event_id}:report:{report_id}",
                notification_type="anomaly_alert",
                title=notif_title,
                body=notif_body,
            )
            self.store.update_workflow_execution(
                event_id,
                notification_status="SUCCESS",
                notification_id=notif["notification_id"],
            )
            logger.info(
                "anomaly_workflow_notification_success",
                extra={"event": {"event_id": event_id, "notification_id": notif["notification_id"]}},
            )
        except ApplicationStoreError as exc:
            err_msg = f"Notification persistence failed: {exc}"
            logger.error("anomaly_workflow_notification_failed", extra={"event": {"event_id": event_id, "error": str(exc)}})
            self.store.update_workflow_execution(
                event_id,
                notification_status="FAILED",
                overall_status="FAILED",
                error_message=err_msg,
            )
            raise AnomalyWorkflowError(err_msg) from exc

        # -------------------------------------------------------------
        # Overall Status Resolution
        # -------------------------------------------------------------
        if email_status in {"SUCCESS", "SKIPPED"}:
            overall_status = "COMPLETED"
        else:
            overall_status = "PARTIAL"

        final_record = self.store.update_workflow_execution(event_id, overall_status=overall_status)
        logger.info(
            "anomaly_workflow_finished",
            extra={
                "event": {
                    "event_id": event_id,
                    "overall_status": overall_status,
                    "report_id": report_id,
                    "email_status": email_status,
                }
            },
        )
        return final_record or {}

    def process_run_events(
        self,
        run_id: str,
        events: list[dict[str, Any]],
        *,
        persona: str = "household",
        entity_id: str | int | None = None,
        customer_email: str | None = None,
    ) -> list[dict[str, Any]]:
        """Process all events from a model analysis run. Skips if events is empty."""
        if not events:
            logger.info("anomaly_workflow_run_empty_skipped", extra={"event": {"run_id": run_id}})
            return []

        logger.info(
            "anomaly_workflow_run_started",
            extra={"event": {"run_id": run_id, "event_count": len(events)}},
        )
        results: list[dict[str, Any]] = []
        for event in events:
            try:
                res = self.process_event(
                    event=event,
                    run={"analysis_id": run_id, "run_id": run_id},
                    persona=persona,
                    entity_id=entity_id,
                    customer_email=customer_email,
                )
                results.append(res)
            except Exception as exc:
                logger.error(
                    "anomaly_workflow_event_failed",
                    extra={"event": {"run_id": run_id, "event_id": event.get("event_id"), "error": str(exc)}},
                )
                results.append({
                    "event_id": event.get("event_id"),
                    "run_id": run_id,
                    "overall_status": "FAILED",
                    "error_message": str(exc),
                })
        return results

    def get_execution(self, event_id: str) -> dict[str, Any] | None:
        """Fetch tracking record for a given anomaly event."""
        self.store.initialize()
        return self.store.get_workflow_execution(event_id)

    def list_executions(self, run_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List execution records with optional run_id filtering."""
        self.store.initialize()
        return self.store.list_workflow_executions(run_id=run_id, limit=limit)

