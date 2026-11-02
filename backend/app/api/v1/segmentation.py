"""Read-only endpoints for Government building-behaviour segmentation."""

from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.error_handlers import AppError
from app.utils.responses import success_response

bp = Blueprint("government_segmentation", __name__, url_prefix="/government/segmentation")


def _service():
    return current_app.extensions["government_segmentation_service"]


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
    return success_response(_service().get_overview())


@bp.get("/profiles")
def get_profiles():
    return success_response(
        {"items": _service().get_profiles(request.args.get("category"))}
    )


@bp.get("/profiles/<segment_id>/time-series")
def get_profile_time_series(segment_id: str):
    period = request.args.get("period", "hourly")
    return success_response(
        {
            "segment_id": segment_id,
            "period": period,
            "items": _service().get_time_series(
                segment_id, period, request.args.get("category")
            ),
        }
    )


@bp.get("/distribution")
def get_distribution():
    return success_response(
        {"items": _service().get_distribution(request.args.get("category"))}
    )


@bp.get("/regions")
def get_regions():
    page, page_size = _pagination()
    items, meta = _service().get_regions(
        level=request.args.get("level", "coarse"),
        category=request.args.get("category"),
        segment_id=request.args.get("segment_id"),
        region_id=request.args.get("region_id"),
        page=page,
        page_size=page_size,
    )
    return success_response({"items": items, **meta}, meta=meta)


@bp.get("/regions/<level>/<region_id>")
def get_region_detail(level: str, region_id: str):
    return success_response(
        _service().get_region_detail(level, region_id, request.args.get("category"))
    )


@bp.get("/assignments")
def get_assignments():
    page, page_size = _pagination()
    items, meta = _service().get_assignments(
        category=request.args.get("category"),
        segment_id=request.args.get("segment_id"),
        region_level=request.args.get("region_level", "coarse"),
        region_id=request.args.get("region_id"),
        page=page,
        page_size=page_size,
    )
    return success_response({"items": items, **meta}, meta=meta)


@bp.get("/priorities")
def get_priorities():
    page, page_size = _pagination()
    items, meta = _service().get_priorities(
        category=request.args.get("category"), page=page, page_size=page_size
    )
    return success_response({"items": items, **meta}, meta=meta)


@bp.get("/model")
def get_model_metadata():
    return success_response(_service().get_model_metadata())
