"""Additive demo APIs for AI reports and notifications."""

from __future__ import annotations

import io
import hashlib
import hmac
import re
import uuid
from datetime import date, timedelta
from typing import Any

from flask import Blueprint, current_app, request, send_file
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.anomaly_assistant import build_anomaly_report
from app.ai.application_store import ApplicationStoreError
from app.ai.email_delivery import EmailDeliveryError, send_report_email
from app.ai.report_service import ReportRenderError, ReportService
from app.api.error_handlers import AppError, ResourceNotFoundError
from app.providers.source_approval import require_approved_source
from app.utils.responses import success_response
from report_generator.schemas.input_schema import GenerateReportRequest
from report_generator.services.report_generator import ReportGenerationError
from report_generator.storage.report_storage import ReportStorageError
from data_retrieval_agent.context import AuthenticatedRequestContext, Persona
from data_retrieval_agent.tools.base import ToolError

bp = Blueprint("ai_layer", __name__)
_CONTEXTS = {"household", "commercial", "government"}


def _require_demo() -> None:
    if not current_app.config.get("AI_DEMO_MODE", False):
        raise AppError(
            "AI demo workflows are disabled in this environment.",
            code="AI_DEMO_DISABLED",
            status_code=503,
        )


def _store():
    store = current_app.extensions["ai_application_store"]
    store.initialize()
    return store


def _private_store():
    storage = current_app.extensions["ai_private_storage"]
    storage.initialize()
    return storage


def _context(value: str | None, *, default: str | None = None) -> str:
    persona = (value or default or "").casefold()
    if persona not in _CONTEXTS:
        raise AppError("persona must be household, commercial, or government.", code="INVALID_INPUT", status_code=422)
    return f"demo:{persona}"


def _request_building_id() -> str | None:
    """Read the Building Profile key, accepting the older entity_id alias."""
    return request.args.get("building_id") or request.args.get("entity_id")


def _entity_context(persona: str | None, entity_id: str | None, *, default: str | None = None) -> str:
    context = _context(persona, default=default)
    if entity_id is None or not entity_id.strip():
        return context
    normalized = entity_id.strip()
    if len(normalized) > 120 or any(ord(char) < 32 for char in normalized):
        raise AppError("building_id has an invalid format.", code="INVALID_INPUT", status_code=422)
    return f"{context}:entity:{normalized}"


def _report_access_context(
    report: dict[str, Any] | None, persona: str | None, entity_id: str | None
) -> str | None:
    if report is None:
        return None
    base_context = _context(persona, default="household")
    stored_context = report.get("context")
    if stored_context == base_context:
        return base_context if not entity_id else None
    if isinstance(stored_context, str) and stored_context.startswith(f"{base_context}:entity:"):
        requested_context = _entity_context(persona, entity_id, default="household")
        return stored_context if requested_context == stored_context else None
    if report.get("report_type") != "monthly_consumption":
        return None
    metadata = report.get("payload", {}).get("metadata", {})
    report_entity = metadata.get("entityId")
    if report_entity is None:
        return base_context
    requested_context = _entity_context(persona, entity_id, default="household")
    expected_context = _entity_context(persona, str(report_entity), default="household")
    return expected_context if requested_context == expected_context else None


@bp.route("/ai/status", methods=["GET"])
def get_ai_status():
    return success_response(current_app.extensions["ai_service"].status())


def _last_month_consumption(
    persona: str, requested_entity: str | None
) -> tuple[dict[str, Any], list[dict[str, Any]], date, date]:
    """Retrieve authorized JSON through the data agent, then retain last month."""
    today = date.today()
    month_end = today.replace(day=1) - timedelta(days=1)
    month_start = month_end.replace(day=1)
    expected_persona = {"household": Persona.RESIDENTIAL, "commercial": Persona.COMMERCIAL}.get(persona)
    if expected_persona is None:
        raise AppError("Monthly reports support household and commercial personas.", code="INVALID_INPUT", status_code=422)
    normalized_entity: str | None = None
    if requested_entity is not None:
        normalized_entity = str(requested_entity).strip()
        if not normalized_entity or len(normalized_entity) > 120:
            raise AppError("building_id is invalid.", code="INVALID_INPUT", status_code=422)
        if persona == "household":
            try:
                parsed_entity = int(normalized_entity)
            except ValueError as exc:
                raise AppError("Household building_id must be a Silver OBJECTID.", code="INVALID_INPUT", status_code=422) from exc
            if parsed_entity <= 0:
                raise AppError("Household building_id must be a positive Silver OBJECTID.", code="INVALID_INPUT", status_code=422)
            normalized_entity = str(parsed_entity)
        elif persona == "commercial":
            try:
                parsed_entity = int(normalized_entity)
            except ValueError as exc:
                raise AppError("Commercial building_id must be a commercial Silver OBJECTID.", code="INVALID_INPUT", status_code=422) from exc
            if parsed_entity <= 0:
                raise AppError("Commercial building_id must be a positive Silver OBJECTID.", code="INVALID_INPUT", status_code=422)
            normalized_entity = str(parsed_entity)
    context = AuthenticatedRequestContext(
        principal_id="public-monthly-report-demo",
        persona=expected_persona,
        permissions={
            "get_historical_consumption", "get_household_silver_history",
            "get_latest_household_silver_month", "get_latest_commercial_silver_month",
        },
        entity_scopes=(
            {"consumer": {normalized_entity}} if normalized_entity and persona == "household"
            else {"customer_cohort": {"*"}} if persona == "household"
            else {"building": {normalized_entity}} if normalized_entity
            else {"commercial_cohort": {"*"}}
        ),
        request_id=uuid.uuid4().hex,
    )

    agent = current_app.extensions.get("data_retrieval_agent")
    if agent is None:
        raise AppError("The data retrieval agent is unavailable.", code="AGENT_UNAVAILABLE", status_code=503)
    try:
        available_sources = agent.available_sources()
        if persona == "household":
            result = agent.registry.execute(
                "get_latest_household_silver_month",
                ({"entity_id": int(normalized_entity)} if normalized_entity else {}),
                context=context,
                available_sources=available_sources,
            )
            period = result.data.get("period", {})
            try:
                month_start = date.fromisoformat(period["start"])
                month_end = date.fromisoformat(period["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AppError("Silver retrieval returned an invalid reporting period.", code="INVALID_REPORT_DATA", status_code=502) from exc
        else:
            result = agent.registry.execute(
                "get_latest_commercial_silver_month",
                ({"entity_id": normalized_entity} if normalized_entity else {}),
                context=context,
                available_sources=available_sources,
            )
    except ToolError as exc:
        if persona == "commercial" and exc.code == "NOT_FOUND":
            subject = f" for commercial Silver OBJECTID {normalized_entity}" if normalized_entity else ""
            raise AppError(
                f"No commercial Silver consumption data is available{subject}.",
                code="REPORT_PERIOD_UNAVAILABLE", status_code=404,
            ) from exc
        status = 403 if exc.code.startswith("FORBIDDEN") else 404 if exc.code == "NOT_FOUND" else 503 if exc.retryable or exc.code == "SOURCE_UNAVAILABLE" else 422
        raise AppError(str(exc), code=exc.code, status_code=status) from exc
    raw = result.data
    sources = [result.source]

    if persona == "household":
        if not raw.get("daysReturned"):
            coverage_end = raw.get("sourceCoverage", {}).get("end")
            coverage_detail = f" Silver source data ends on {coverage_end}." if coverage_end else ""
            subject = f" for household OBJECTID {normalized_entity}" if normalized_entity else ""
            raise AppError(
                f"No household Silver consumption data is available{subject} for {month_start:%B %Y}.{coverage_detail}",
                code="REPORT_PERIOD_UNAVAILABLE", status_code=404,
            )
        data = raw
    else:
        if not raw.get("daysReturned"):
            subject = f" for commercial building OBJECTID {normalized_entity}" if normalized_entity else ""
            raise AppError(
                f"No commercial Silver consumption data is available{subject} in its latest available month.",
                code="REPORT_PERIOD_UNAVAILABLE", status_code=404,
            )
        data = raw
        try:
            month_start = date.fromisoformat(raw["period"]["start"])
            month_end = date.fromisoformat(raw["period"]["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("Commercial Silver retrieval returned an invalid reporting period.", code="INVALID_REPORT_DATA", status_code=502) from exc
    tariff_val = current_app.config.get("CUSTOMER_TARIFF_INR_PER_KWH", 10.0)
    data["tariffInrPerKwh"] = float(tariff_val) if tariff_val is not None else None
    return data, sources, month_start, month_end


def _generate_agent_monthly_report(data: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
    """Generate the narrative report and return its private artifact IDs."""
    owner_key = _public_report_owner_key()
    generator = current_app.extensions["report_generator"]
    generation_request = GenerateReportRequest(
        data=data,
        instructions=(
            "Create a concise electricity consumption summary for the supplied reporting period. "
            "Keep the report specific to the supplied entity when entityId is present. "
            "Report only source-backed figures, explain coverage and limitations, and do not estimate missing days."
        ),
        output_formats=["html", "pdf"],
    )
    try:
        result = generator.generate(generation_request, owner_key=owner_key)
        record = generator.repository.get(result["report_id"], owner_key)
    except ReportGenerationError as exc:
        details = {"report_id": exc.report_id} if exc.report_id else None
        raise AppError(str(exc), code=exc.code, status_code=exc.status_code, details=details) from exc
    except ReportStorageError as exc:
        raise AppError("Report service is unavailable.", code="REPORT_STORAGE_UNAVAILABLE", status_code=503) from exc
    if not record or not record.get("html_artifact_id"):
        raise AppError("Generated report artifact is unavailable.", code="REPORT_UNAVAILABLE", status_code=503)
    return result, record["html_artifact_id"], record.get("pdf_artifact_id")


def _public_report_owner_key() -> str:
    """Shared owner for explicitly public demo reports."""
    secret = str(current_app.config.get("SECRET_KEY", "")).encode("utf-8")
    if not secret:
        raise AppError("Report authorization is unavailable.", code="AUTHORIZATION_UNAVAILABLE", status_code=503)
    return hmac.new(secret, b"gridvision-public-monthly-report-demo", hashlib.sha256).hexdigest()


def _owns_agent_report(report: dict[str, Any]) -> bool:
    generator_report_id = report.get("payload", {}).get("generatorReportId")
    if not generator_report_id:
        return True
    if report.get("payload", {}).get("publicDemo") is not True:
        return False
    generator = current_app.extensions["report_generator"]
    return generator.repository.get(generator_report_id, _public_report_owner_key()) is not None


@bp.route("/ai/reports", methods=["POST"])
def create_report():
    _require_demo()
    body = request.get_json(force=True, silent=False) or {}
    if not isinstance(body, dict):
        raise AppError("Report request must be a JSON object.", code="INVALID_INPUT", status_code=422)
    report_type = body.get("report_type")
    persona = str(body.get("persona", "household")).casefold()
    time_range = str(body.get("time_range", "1Y" if persona == "household" else "ALL")).upper()
    report_entity_id: str | None = None
    try:
        if report_type == "monthly_consumption":
            requested_entity = body.get("building_id", body.get("entity_id"))
            if requested_entity is not None and (not isinstance(requested_entity, (str, int)) or isinstance(requested_entity, bool)):
                raise AppError("building_id must be a string or integer.", code="INVALID_INPUT", status_code=422)
            data, sources, month_start, month_end = _last_month_consumption(persona, str(requested_entity) if requested_entity is not None else None)
            agent_result, html_id, pdf_id = _generate_agent_monthly_report(data)
            report_entity_id = str(data.get("entityId")) if data.get("entityId") is not None else None
            context = _entity_context(persona, report_entity_id)
            entity_label = f" for {report_entity_id}" if report_entity_id else ""
            title = agent_result.get("title") or f"{persona.title()} monthly consumption report{entity_label}"
        elif report_type == "government_analytics":
            if persona != "government":
                raise AppError("Government persona is required for this report.", code="INVALID_INPUT", status_code=422)
            require_approved_source("government_2018", "Government 2018 dataset")
            require_approved_source("segmentation_2018", "Published segmentation outputs")
            provider = current_app.extensions["commercial_history_provider"]
            data = {
                "historicalConsumption": provider.get_government_historical_insights(time_range, None),
                "segmentation": current_app.extensions["government_segmentation_service"].get_overview(),
            }
            sources = [provider.get_government_source_metadata(), current_app.extensions["government_segmentation_service"].get_source_metadata()]
            context = "demo:government"
            title = "Government regional analytics report"
        else:
            raise AppError("Unsupported report_type.", code="INVALID_INPUT", status_code=422)

        metadata = {
            "reportType": report_type,
            "reportVersion": ReportService.VERSION,
            "createdAt": date.today().isoformat(),
            "period": ({"label": "latest_available_source_month", "start": month_start.isoformat(), "end": month_end.isoformat()} if report_type == "monthly_consumption" else time_range),
            "coverage": data.get("scope", "available source observations"),
            "methodology": ("Latest available calendar-month Silver observations retrieved by the data retrieval agent and summarized by the report agent.") if report_type == "monthly_consumption" else "Deterministic values read from existing GridVision services.",
            "limitations": ["Historical/model data is not live telemetry."],
            "data": data,
        }
        if report_entity_id:
            metadata["entityId"] = report_entity_id
            metadata["subject"] = {"entityId": report_entity_id, "persona": persona}
        generation_status = agent_result.get("status", "complete") if report_type == "monthly_consumption" else "complete"
        if report_type != "monthly_consumption":
            html_bytes = ReportService.render_html(title, metadata, sources)
            private = _private_store()
            html_id = private.store(html_bytes)
            try:
                pdf_bytes = ReportService.render_pdf(title, metadata, sources)
                pdf_id = private.store(pdf_bytes)
            except ReportRenderError:
                # PDF support is optional; preserve a usable HTML report.
                pdf_id = None
                generation_status = "partial"
                metadata["limitations"].append("PDF output is unavailable in this environment.")
        _store().initialize()
        report = _store().create_report(
            report_type, context, sources,
            {
                "metadata": metadata,
                "pdfArtifactId": pdf_id,
                "generationStatus": generation_status,
                **({"generatorReportId": agent_result["report_id"], "publicDemo": True} if report_type == "monthly_consumption" else {}),
            },
            artifact_id=html_id,
        )
        _store().notify(
            context, f"report-ready:{report['report_id']}", "report_ready",
            "Report is ready", f"Your {report_type.replace('_', ' ')} report is ready to download.",
        )
        return success_response(report, status_code=201)
    except AppError:
        raise
    except (ApplicationStoreError, ReportRenderError, OSError) as exc:
        current_app.logger.error(
            "ai_report_service_failed",
            extra={"event": {"report_type": report_type, "error_type": type(exc).__name__}},
        )
        raise AppError("Report service is unavailable.", code="REPORT_UNAVAILABLE", status_code=503) from exc


@bp.route("/ai/reports", methods=["GET"])
def list_reports():
    _require_demo()
    context = _entity_context(
        request.args.get("persona"), _request_building_id(), default="household"
    )
    try:
        _store().initialize()
        items = _store().list_reports(context)
        # Public demo reports are additionally checked against their generator record.
        agent_items = [item for item in items if item.get("payload", {}).get("generatorReportId")]
        if agent_items:
            repository = current_app.extensions["report_generator"].repository
            try:
                public_owner = _public_report_owner_key()
            except AppError:
                public_owner = None
            try:
                from report_generator.api.routes import resolve_report_owner_key
                owner_key = resolve_report_owner_key()
            except AppError:
                owner_key = None
            filtered = []
            for item in items:
                generator_id = item.get("payload", {}).get("generatorReportId")
                if not generator_id:
                    filtered.append(item)
                elif item.get("payload", {}).get("publicDemo") is True:
                    if public_owner and repository.get(generator_id, public_owner):
                        filtered.append(item)
                elif owner_key and repository.get(generator_id, owner_key):
                    filtered.append(item)
            items = filtered
        return success_response({"items": items})
    except ApplicationStoreError as exc:
        raise AppError("Report service is unavailable.", code="REPORT_UNAVAILABLE", status_code=503) from exc


@bp.route("/ai/reports/<report_id>", methods=["GET"])
def get_report(report_id: str):
    _require_demo()
    report = _store().get_report(report_id)
    context = _report_access_context(
        report, request.args.get("persona"), _request_building_id()
    )
    if report is None or report["context"] != context or not _owns_agent_report(report):
        raise ResourceNotFoundError("Report was not found.")
    return success_response(report)


@bp.route("/ai/reports/<report_id>/download/<file_format>", methods=["GET"])
def download_report(report_id: str, file_format: str):
    _require_demo()
    report = _store().get_report(report_id)
    context = _report_access_context(
        report, request.args.get("persona"), _request_building_id()
    )
    if report is None or report["context"] != context or not _owns_agent_report(report):
        raise ResourceNotFoundError("Report was not found.")
    artifact_id = report["artifact_id"] if file_format == "html" else report["payload"].get("pdfArtifactId") if file_format == "pdf" else None
    if not artifact_id:
        raise ResourceNotFoundError("Report format was not found.")
    try:
        content = _private_store().read(artifact_id)
    except Exception as exc:
        raise AppError("Report artifact is unavailable.", code="REPORT_UNAVAILABLE", status_code=503) from exc
    mimetype = "text/html; charset=utf-8" if file_format == "html" else "application/pdf"
    return send_file(io.BytesIO(content), mimetype=mimetype, as_attachment=True, download_name=f"gridvision-report-{report_id}.{file_format}")


@bp.route("/ai/reports/<report_id>/email", methods=["POST"])
def email_report(report_id: str):
    """Email a generated report to the configured fixed recipient on request."""
    _require_demo()
    persona = request.args.get("persona", "household").casefold()
    report = _store().get_report(report_id)
    context = _report_access_context(report, persona, _request_building_id())
    if report is None or report["context"] != context or not _owns_agent_report(report):
        raise ResourceNotFoundError("Report was not found.")

    recipient = str(current_app.config.get("REPORT_EMAIL_DEFAULT_RECIPIENT", "")).strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient):
        raise AppError("The report email recipient is not configured correctly.", code="EMAIL_CONFIGURATION_INVALID", status_code=503)
    payload = report.get("payload", {})
    pdf_id = payload.get("pdfArtifactId")
    if pdf_id:
        artifact_id, file_format, mimetype = pdf_id, "pdf", "application/pdf"
    else:
        artifact_id, file_format, mimetype = report.get("artifact_id"), "html", "text/html"
    if not artifact_id:
        raise ResourceNotFoundError("Report attachment was not found.")
    try:
        attachment = _private_store().read(artifact_id)
    except Exception as exc:
        raise AppError("Report attachment is unavailable.", code="REPORT_UNAVAILABLE", status_code=503) from exc

    metadata = payload.get("metadata", {})
    period = metadata.get("period")
    if isinstance(period, dict):
        period_label = f" ({period.get('start', '')} to {period.get('end', '')})"
    else:
        period_label = ""
    title = str(metadata.get("reportType", report["report_type"])).replace("_", " ").title()
    report_entity = metadata.get("entityId")
    entity_label = f" for Building ID {report_entity}" if report_entity is not None else ""
    try:
        send_report_email(
            config=current_app.config,
            recipient=recipient,
            subject=f"GridVision report: {title}{entity_label}{period_label}",
            body=(
                f"Your requested GridVision report{entity_label} is attached "
                f"as a {file_format.upper()} file."
            ),
            attachment_name=f"gridvision-report-{report_id}.{file_format}",
            attachment_bytes=attachment,
            attachment_mime=mimetype,
        )
    except EmailDeliveryError as exc:
        code = "EMAIL_NOT_CONFIGURED" if "not configured" in str(exc).lower() else "EMAIL_DELIVERY_FAILED"
        raise AppError(str(exc), code=code, status_code=503) from exc
    return success_response({"report_id": report_id, "recipient": recipient, "format": file_format, "status": "sent"}, status_code=202)


@bp.route("/ai/notifications", methods=["GET"])
def list_notifications():
    _require_demo()
    context = _entity_context(
        request.args.get("persona"), _request_building_id(), default="household"
    )
    try:
        _store().initialize()
        items = _store().list_notifications(context)
        return success_response({"items": items, "emailDelivery": "disabled"})
    except ApplicationStoreError as exc:
        raise AppError("Notification storage is unavailable.", code="AI_STORAGE_UNAVAILABLE", status_code=503) from exc


@bp.route("/ai/notifications/<notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id: str):
    _require_demo()
    context = _entity_context(
        request.args.get("persona"), _request_building_id(), default="household"
    )
    try:
        updated = _store().mark_notification_read(context, notification_id)
        if updated is None:
            raise ResourceNotFoundError("Notification was not found.")
        return success_response(updated)
    except ApplicationStoreError as exc:
        raise AppError("Notification storage is unavailable.", code="AI_STORAGE_UNAVAILABLE", status_code=503) from exc
