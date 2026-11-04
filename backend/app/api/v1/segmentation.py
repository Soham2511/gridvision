"""Read-only endpoints for Government building-behaviour segmentation."""

from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.error_handlers import AppError
from app.utils.responses import success_response
from app.providers.source_approval import require_approved_source

bp = Blueprint("government_segmentation", __name__, url_prefix="/government/segmentation")


def _service():
    require_approved_source("segmentation_2018", "Government segmentation outputs")
    return current_app.extensions["government_segmentation_service"]


def _success(service, data, record_type: str, units: str | None = None, extra_meta=None):
    provenance = {
        **service.get_source_metadata(),
        "recordType": record_type,
    }
    if units:
        provenance["units"] = units
    response_meta = dict(extra_meta or {})
    response_meta["sourceProvenance"] = provenance
    return success_response(data, meta=response_meta)


def _page_value(name: str, default: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise AppError(
            f"{name} must be an integer.", code="INVALID_INPUT", status_code=422
        ) from exc


def _pagination() -> tuple[int, int]:
    return _page_value("page", 1), _page_value("page_size", 50)


@bp.get("/overview")
def get_overview():
    service = _service()
    return _success(service, service.get_overview(), "segmentation_overview", "kWh")


@bp.get("/profiles")
def get_profiles():
    service = _service()
    return _success(
        service,
        {"items": service.get_profiles(request.args.get("category"))},
        "segment_profiles",
        "kWh",
    )


@bp.get("/profiles/<segment_id>/time-series")
def get_profile_time_series(segment_id: str):
    period = request.args.get("period", "hourly")
    service = _service()
    return _success(
        service,
        {
            "segment_id": segment_id,
            "period": period,
            "items": service.get_time_series(
                segment_id, period, request.args.get("category")
            ),
        },
        "segment_time_series",
        "kWh",
    )


@bp.get("/distribution")
def get_distribution():
    service = _service()
    return _success(
        service,
        {"items": service.get_distribution(request.args.get("category"))},
        "segment_distribution",
    )


@bp.get("/regions")
def get_regions():
    page, page_size = _pagination()
    service = _service()
    items, meta = service.get_regions(
        level=request.args.get("level", "coarse"),
        category=request.args.get("category"),
        segment_id=request.args.get("segment_id"),
        region_id=request.args.get("region_id"),
        page=page,
        page_size=page_size,
    )
    return _success(
        service, {"items": items, **meta}, "regional_segment_summary", "kWh", meta
    )


@bp.get("/regions/<level>/<region_id>")
def get_region_detail(level: str, region_id: str):
    service = _service()
    return _success(
        service,
        service.get_region_detail(level, region_id, request.args.get("category")),
        "regional_segment_detail",
        "kWh",
    )


@bp.get("/assignments")
def get_assignments():
    page, page_size = _pagination()
    service = _service()
    items, meta = service.get_assignments(
        category=request.args.get("category"),
        segment_id=request.args.get("segment_id"),
        region_level=request.args.get("region_level", "coarse"),
        region_id=request.args.get("region_id"),
        page=page,
        page_size=page_size,
    )
    return _success(service, {"items": items, **meta}, "building_segment_assignments", extra_meta=meta)


@bp.get("/priorities")
def get_priorities():
    page, page_size = _pagination()
    service = _service()
    items, meta = service.get_priorities(
        category=request.args.get("category"), page=page, page_size=page_size
    )
    return _success(service, {"items": items, **meta}, "regional_survey_priorities", extra_meta=meta)


@bp.get("/model")
def get_model_metadata():
    service = _service()
    return _success(service, service.get_model_metadata(), "segmentation_model_metadata")
