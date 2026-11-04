"""Versioned Flask endpoints for JSON report generation and retrieval."""

from __future__ import annotations

import hashlib
import hmac
import io
import re
from typing import Any

from flask import Blueprint, current_app, request, send_file

from app.api.error_handlers import AppError
from app.utils.responses import success_response
from report_generator.schemas.input_schema import InputError, parse_request_bytes
from report_generator.services.report_generator import JSONReportGenerator, ReportGenerationError
from report_generator.storage.report_storage import ReportStorageError

bp = Blueprint("report_generator", __name__)
_REPORT_ID = re.compile(r"^[a-f0-9]{32}$")


def _service() -> JSONReportGenerator:
    return current_app.extensions["report_generator"]


def resolve_report_owner_key() -> str:
    resolver = current_app.extensions.get("report_generator_identity_resolver")
    if not callable(resolver):
        raise AppError(
            "Report access requires a configured trusted identity provider.",
            code="AUTHENTICATION_REQUIRED",
            status_code=401,
        )
    try:
        identity = resolver(request)
    except Exception as exc:
        raise AppError(
            "Report access requires a valid authenticated identity.",
            code="AUTHENTICATION_REQUIRED",
            status_code=401,
        ) from exc
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 512:
        raise AppError(
            "Report access requires a valid authenticated identity.",
            code="AUTHENTICATION_REQUIRED",
            status_code=401,
        )
    secret = str(current_app.config.get("SECRET_KEY", "")).encode("utf-8")
    if not secret:
        raise AppError("Report authorization is unavailable.", code="AUTHORIZATION_UNAVAILABLE", status_code=503)
    return hmac.new(secret, identity.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def _record(report_id: str) -> tuple[str, dict[str, Any]]:
    if not _REPORT_ID.fullmatch(report_id):
        raise AppError("Report not found.", code="NOT_FOUND", status_code=404)
    owner = resolve_report_owner_key()
    try:
        report = _service().repository.get(report_id, owner)
    except ReportStorageError as exc:
        raise AppError("Report storage is unavailable.", code="REPORT_STORAGE_UNAVAILABLE", status_code=503) from exc
    if report is None:
        raise AppError("Report not found.", code="NOT_FOUND", status_code=404)
    return owner, report


@bp.get("/health")
def health():
    result = _service().health()
    result["identity_resolver_configured"] = callable(
        current_app.extensions.get("report_generator_identity_resolver")
    )
    return success_response(result)


@bp.post("/generate")
def generate():
    owner = resolve_report_owner_key()
    settings = _service().settings
    if request.content_length is not None and request.content_length > settings.max_request_bytes:
        raise AppError("Request exceeds the configured size limit.", code="REQUEST_TOO_LARGE", status_code=413)
    if request.mimetype != "application/json":
        raise AppError("Content-Type must be application/json.", code="UNSUPPORTED_MEDIA_TYPE", status_code=415)
    raw = request.stream.read(settings.max_request_bytes + 1)
    try:
        body = parse_request_bytes(
            raw,
            max_bytes=settings.max_request_bytes,
            max_depth=settings.max_json_depth,
            max_nodes=settings.max_json_nodes,
            max_string_chars=settings.max_string_chars,
            max_instruction_chars=settings.max_instruction_chars,
        )
    except InputError as exc:
        status = 413 if "size limit" in str(exc) or "too many values" in str(exc) else 422
        raise AppError(
            "Report request is invalid or exceeds configured limits.",
            code="INVALID_REPORT_INPUT",
            status_code=status,
        ) from exc
    try:
        result = _service().generate(body, owner_key=owner)
    except ReportGenerationError as exc:
        details = {"status": "failed"}
        if exc.report_id:
            details["report_id"] = exc.report_id
        raise AppError(str(exc), code=exc.code, status_code=exc.status_code, details=details) from exc
    return success_response(result, status_code=201)


@bp.get("/reports/<report_id>")
def metadata(report_id: str):
    _owner, report = _record(report_id)
    result = {
        key: report[key]
        for key in ("report_id", "title", "status", "generated_at", "error_code", "limitations")
    }
    result["html_url"] = f"/api/v1/report-generator/reports/{report_id}/html" if report["html_artifact_id"] else None
    result["pdf_url"] = f"/api/v1/report-generator/reports/{report_id}/pdf" if report["pdf_artifact_id"] else None
    return success_response(result)


def _artifact(report_id: str, artifact_key: str, mimetype: str):
    _owner, report = _record(report_id)
    artifact_id = report[artifact_key]
    if not artifact_id:
        raise AppError("Report artifact not found.", code="NOT_FOUND", status_code=404)
    storage = current_app.extensions["ai_private_storage"]
    try:
        content = storage.read(artifact_id)
    except Exception as exc:
        raise AppError("Report artifact is unavailable.", code="REPORT_ARTIFACT_UNAVAILABLE", status_code=503) from exc
    response = send_file(
        io.BytesIO(content),
        mimetype=mimetype,
        as_attachment=False,
        download_name=f"gridvision-report-{report_id}.{artifact_key.removesuffix('_artifact_id')}",
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if artifact_key == "html_artifact_id":
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    return response


@bp.get("/reports/<report_id>/html")
def html_report(report_id: str):
    return _artifact(report_id, "html_artifact_id", "text/html; charset=utf-8")


@bp.get("/reports/<report_id>/pdf")
def pdf_report(report_id: str):
    return _artifact(report_id, "pdf_artifact_id", "application/pdf")
