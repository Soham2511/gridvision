"""Commercial multi-agent analysis endpoint."""

from __future__ import annotations

import hmac
import os
import uuid
from pathlib import Path
from uuid import UUID

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.utils import secure_filename

from ai.commercial.graph import WorkflowExecutionError
from ai.commercial.schemas.communication import AgentResult
from app.utils.responses import error_response, success_response
from app.utils.validation import (
    CommercialWorkflowRequestModel,
    ScheduleApprovalRequestModel,
)

bp = Blueprint("commercial_workflow", __name__)
DEMO_FACTORY_ID = "automotive-parts-demo"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_FILENAME_LENGTH = 120
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".md",
    ".txt",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".csv",
}


@bp.before_request
def authenticate_demo_user():
    """Require the single locally configured demo account for this endpoint."""
    if request.method == "OPTIONS":
        return None

    expected_user = os.getenv("DEMO_USER_ID", "")
    expected_password = os.getenv("DEMO_PASSWORD", "")
    if not expected_user or not expected_password:
        return (
            jsonify(
                {
                    "error": {
                        "code": "DEMO_AUTH_NOT_CONFIGURED",
                        "message": "Configure local demo credentials to use this endpoint.",
                    }
                }
            ),
            503,
        )

    credentials = request.authorization
    supplied_user = credentials.username if credentials else ""
    supplied_password = credentials.password if credentials else ""
    user_matches = hmac.compare_digest(
        supplied_user.encode("utf-8"),
        expected_user.encode("utf-8"),
    )
    password_matches = hmac.compare_digest(
        supplied_password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )
    if not (user_matches and password_matches):
        response = jsonify(
            {
                "error": {
                    "code": "DEMO_AUTH_REQUIRED",
                    "message": "Valid demo credentials are required.",
                }
            }
        )
        response.status_code = 401
        response.headers["WWW-Authenticate"] = (
            'Basic realm="GridVision automotive-parts demo"'
        )
        return response

    g.demo_user_id = expected_user
    return None


@bp.route("/commercial/workflow", methods=["POST"])
def commercial_workflow():
    """Run a bounded read-only Commercial workflow and return its final report."""
    data = request.get_json(force=True, silent=False) or {}
    validated = CommercialWorkflowRequestModel.model_validate(data)
    if validated.factory_id not in (None, DEMO_FACTORY_ID):
        return (
            jsonify(
                {
                    "error": {
                        "code": "DEMO_FACTORY_SCOPE_VIOLATION",
                        "message": (
                            "This demo is limited to the automotive-parts "
                            "demonstration factory."
                        ),
                    }
                }
            ),
            403,
        )
    if validated.building_id is not None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "DEMO_BUILDING_SCOPE_UNAVAILABLE",
                        "message": (
                            "No building forecast is mapped to the synthetic "
                            "automotive-parts demo."
                        ),
                    }
                }
            ),
            403,
        )
    request_id = validated.request_id or g.request_id
    try:
        result = current_app.extensions["commercial_workflow"].invoke(
            {
                "request_id": request_id,
                "factory_id": DEMO_FACTORY_ID,
                "building_id": None,
                "user_goal": validated.user_goal,
                "optimization_inputs": (
                    validated.optimization_inputs.model_dump(mode="python")
                    if validated.optimization_inputs is not None
                    else None
                ),
            }
        )
    except WorkflowExecutionError as exc:
        return error_response(
            str(exc),
            code="WORKFLOW_STEP_FAILED",
            details={
                "request_id": request_id,
                "failed_node": exc.failed_node,
                "error_type": exc.error_type,
                "execution_trace": exc.execution_trace,
            },
            status_code=500,
        )
    response_data = dict(result["final_response"])
    response_data["execution_trace"] = result.get("execution_trace", [])
    response_data["specialist_results"] = {
        agent_result.specialist: agent_result.model_dump(mode="json")
        for agent_result in result.get("specialist_results", {}).values()
        if isinstance(agent_result, AgentResult)
    }
    optimizer_result = result.get("optimization_result")
    if (
        isinstance(optimizer_result, AgentResult)
        and validated.optimization_inputs is not None
        and optimizer_result.status == "completed"
        and optimizer_result.data.get("status") in {"optimal", "feasible"}
        and isinstance(optimizer_result.data.get("schedule"), list)
        and response_data.get("status") == "passed"
    ):
        proposal = {
            "optimization_inputs": validated.optimization_inputs.model_dump(
                mode="json"
            ),
            "optimization_result": optimizer_result.data,
        }
        proposal_info = current_app.extensions[
            "commercial_schedule_approvals"
        ].create_proposal(
            request_id=request_id,
            factory_id=DEMO_FACTORY_ID,
            actor_id=g.demo_user_id,
            proposal=proposal,
        )
        response_data["schedule_proposal"] = {
            **proposal_info,
            "schedule": optimizer_result.data["schedule"],
            "calculated_cost_inr": optimizer_result.data.get(
                "calculated_cost_inr"
            ),
            "calculated_savings_inr": optimizer_result.data.get(
                "calculated_savings_inr"
            ),
            "battery_dispatch": optimizer_result.data.get("battery_dispatch"),
            "approval_required_before_use": True,
            "equipment_controlled": False,
        }
    return success_response(
        response_data,
        meta={
            "request_id": request_id,
            "step_count": result.get("step_count", 0),
            "tool_call_count": result.get("tool_call_count", 0),
            "llm_call_count": result.get("llm_call_count", 0),
        },
    )


@bp.route("/commercial/session", methods=["POST"])
def commercial_session():
    """Validate the configured demo credentials without persisting a session."""
    return success_response(
        {
            "user_id": g.demo_user_id,
            "factory_id": DEMO_FACTORY_ID,
            "scope": "automotive-parts demonstration only",
        }
    )


@bp.route("/commercial/rag/documents", methods=["GET"])
def list_uploaded_documents():
    """Return indexed upload metadata without exposing server filesystem paths."""
    retriever = current_app.extensions["commercial_rag_retriever"]
    upload_root = retriever.upload_root.resolve()
    documents = []
    for item in retriever.index.indexed_documents():
        try:
            path = Path(item["path"]).resolve()
            path.relative_to(upload_root)
        except (OSError, ValueError, KeyError):
            continue
        documents.append(
            {
                "source_id": item["source_id"],
                "size_bytes": item["size_bytes"],
                "page_count": item["page_count"],
            }
        )
    return success_response(
        {
            "documents": documents,
            "index_counts": retriever.index.index_counts(),
        }
    )


@bp.route("/commercial/rag/documents", methods=["POST"])
def upload_rag_document():
    """Store and immediately index a bounded local document for shared RAG."""
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return (
            jsonify(
                {
                    "error": {
                        "code": "UPLOAD_FILE_REQUIRED",
                        "message": "Choose a document file to upload.",
                    }
                }
            ),
            400,
        )

    original_name = secure_filename(uploaded_file.filename)
    extension = Path(original_name).suffix.casefold()
    if not original_name:
        return (
            jsonify(
                {
                    "error": {
                        "code": "UPLOAD_FILENAME_INVALID",
                        "message": "The selected filename is invalid.",
                    }
                }
            ),
            400,
        )
    if len(original_name) > MAX_UPLOAD_FILENAME_LENGTH:
        return (
            jsonify(
                {
                    "error": {
                        "code": "UPLOAD_FILENAME_TOO_LONG",
                        "message": "Document filenames must be 120 characters or fewer.",
                    }
                }
            ),
            400,
        )
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        return (
            jsonify(
                {
                    "error": {
                        "code": "UPLOAD_FORMAT_NOT_SUPPORTED",
                        "message": (
                            "Supported formats are PDF, Markdown, TXT, DOCX, "
                            "PPTX, XLSX, HTML, and CSV."
                        ),
                    }
                }
            ),
            415,
        )
    if request.content_length is not None and request.content_length > (
        MAX_UPLOAD_BYTES + 1024 * 1024
    ):
        return (
            jsonify(
                {
                    "error": {
                        "code": "UPLOAD_TOO_LARGE",
                        "message": "Documents must be 25 MB or smaller.",
                    }
                }
            ),
            413,
        )

    retriever = current_app.extensions["commercial_rag_retriever"]
    upload_root = retriever.upload_root
    upload_root.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    temporary_path = upload_root / f".{upload_id}.upload"
    stored_name = f"{upload_id}_{original_name}"
    stored_path = upload_root / stored_name
    first_bytes = b""
    total_bytes = 0
    too_large = False

    try:
        with temporary_path.open("xb") as destination:
            while True:
                block = uploaded_file.stream.read(1024 * 1024)
                if not block:
                    break
                if not first_bytes:
                    first_bytes = block[:1024]
                total_bytes += len(block)
                if total_bytes > MAX_UPLOAD_BYTES:
                    too_large = True
                    break
                destination.write(block)

        if too_large:
            temporary_path.unlink(missing_ok=True)
            return (
                jsonify(
                    {
                        "error": {
                            "code": "UPLOAD_TOO_LARGE",
                            "message": "Documents must be 25 MB or smaller.",
                        }
                    }
                ),
                413,
            )
        if total_bytes == 0:
            temporary_path.unlink(missing_ok=True)
            return (
                jsonify(
                    {
                        "error": {
                            "code": "UPLOAD_FILE_EMPTY",
                            "message": "The selected document is empty.",
                        }
                    }
                ),
                400,
            )
        if extension == ".pdf" and b"%PDF-" not in first_bytes:
            temporary_path.unlink(missing_ok=True)
            return (
                jsonify(
                    {
                        "error": {
                            "code": "UPLOAD_CONTENT_INVALID",
                            "message": "The selected file is not a valid PDF.",
                        }
                    }
                ),
                422,
            )
        if extension in {".docx", ".pptx", ".xlsx"} and not first_bytes.startswith(
            b"PK\x03\x04"
        ):
            temporary_path.unlink(missing_ok=True)
            return (
                jsonify(
                    {
                        "error": {
                            "code": "UPLOAD_CONTENT_INVALID",
                            "message": "The selected Office file is invalid.",
                        }
                    }
                ),
                422,
            )
        if extension in {".md", ".txt", ".html", ".csv"}:
            try:
                temporary_path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                temporary_path.unlink(missing_ok=True)
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "UPLOAD_CONTENT_INVALID",
                                "message": "Text documents must use UTF-8 encoding.",
                            }
                        }
                    ),
                    422,
                )

        temporary_path.replace(stored_path)
        report = retriever.index_documents()
        source_report = next(
            (
                item
                for item in report["documents"]
                if item.get("source_id") == stored_name
            ),
            None,
        )
        if source_report is None or source_report.get("status") not in {
            "indexed",
            "unchanged",
        }:
            stored_path.unlink(missing_ok=True)
            message = (
                source_report.get("message", "The document could not be indexed.")
                if source_report is not None
                else "The document was stored but no index result was returned."
            )
            return (
                jsonify(
                    {
                        "error": {
                            "code": "RAG_INGESTION_FAILED",
                            "message": message,
                        }
                    }
                ),
                422,
            )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        stored_path.unlink(missing_ok=True)
        raise

    return success_response(
        {
            "source_id": stored_name,
            "size_bytes": total_bytes,
            "page_count": source_report.get("page_count"),
            "chunk_count": source_report.get("chunk_count"),
            "status": source_report["status"],
        },
        status_code=201,
    )


@bp.route(
    "/commercial/schedules/<uuid:proposal_id>/approval",
    methods=["POST"],
)
def decide_schedule_proposal(proposal_id: UUID):
    """Approve or reject an immutable proposal without executing equipment."""
    data = request.get_json(force=True, silent=False) or {}
    validated = ScheduleApprovalRequestModel.model_validate(data)
    decision = current_app.extensions[
        "commercial_schedule_approvals"
    ].decide(
        str(proposal_id),
        actor_id=g.demo_user_id,
        decision=validated.decision,
        note=validated.note,
    )
    if decision is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "SCHEDULE_PROPOSAL_NOT_FOUND",
                        "message": "No matching schedule proposal was found.",
                    }
                }
            ),
            404,
        )
    if decision.get("already_decided") == "true":
        return (
            jsonify(
                {
                    "error": {
                        "code": "SCHEDULE_PROPOSAL_ALREADY_DECIDED",
                        "message": "A decision has already been recorded.",
                    }
                }
            ),
            409,
        )
    return success_response(
        {
            **decision,
            "equipment_controlled": False,
        }
    )
