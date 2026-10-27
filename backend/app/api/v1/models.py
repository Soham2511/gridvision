"""Model catalog and customer bill inference routes."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, request

from app.api.error_handlers import AppError, ResourceNotFoundError
from app.models.customer_bill_prediction import (
    CustomerBillPredictionError,
    CustomerBillPredictionService,
)
from app.utils.responses import success_response

bp = Blueprint("models", __name__)


def _service() -> CustomerBillPredictionService:
    return current_app.extensions["customer_bill_prediction_service"]


def _positive_int(value: str | None, name: str, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AppError(
            f"{name} must be a positive integer.",
            code="INVALID_INPUT",
            status_code=422,
        ) from exc
    if parsed < 0:
        raise AppError(
            f"{name} must be a positive integer.",
            code="INVALID_INPUT",
            status_code=422,
        )
    return parsed


@bp.route("/models", methods=["GET"])
def get_model_catalog():
    """Return real model metadata and data readiness for the model workbench."""
    try:
        return success_response({"models": _service().get_model_catalog()})
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="MODEL_UNAVAILABLE", status_code=503
        ) from exc


@bp.route("/models/customer-bill-prediction/records", methods=["GET"])
def get_customer_records():
    """List the latest gold-dataset record for each customer entity."""
    limit = _positive_int(request.args.get("limit"), "limit", 50)
    offset = _positive_int(request.args.get("offset"), "offset", 0)
    if limit < 1 or limit > 200:
        raise AppError(
            "limit must be between 1 and 200.",
            code="INVALID_INPUT",
            status_code=422,
        )
    entity_id_value = request.args.get("entity_id")
    entity_id = (
        _positive_int(entity_id_value, "entity_id", 0)
        if entity_id_value is not None
        else None
    )
    if entity_id is not None and entity_id < 1:
        raise AppError(
            "entity_id must be a positive integer.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        result = _service().get_entity_records(limit, offset, entity_id)
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="DATA_UNAVAILABLE", status_code=503
        ) from exc
    if entity_id is not None and not result["items"]:
        raise ResourceNotFoundError(
            f"Customer entity '{entity_id}' was not found in the gold dataset."
        )
    return success_response(result)


@bp.route("/models/customer-bill-prediction/records/<int:entity_id>", methods=["GET"])
def get_customer_months(entity_id: int):
    """Return all gold-dataset months for one customer entity."""
    try:
        records = _service().get_entity_months(entity_id)
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="DATA_UNAVAILABLE", status_code=503
        ) from exc
    if not records:
        raise ResourceNotFoundError(
            f"Customer entity '{entity_id}' was not found in the gold dataset."
        )
    return success_response(records)


@bp.route("/models/customer-bill-prediction/history", methods=["GET"])
def get_customer_historical_insights():
    """Return residential historical trends from the customer gold dataset."""
    time_range = request.args.get("time_range", "ALL")
    if time_range not in {"3M", "6M", "1Y", "ALL"}:
        raise AppError(
            "time_range must be one of 3M, 6M, 1Y, or ALL.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        result = _service().get_historical_gold_insights(time_range)
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="DATA_UNAVAILABLE", status_code=503
        ) from exc
    return success_response(result)


@bp.route("/models/customer-bill-prediction/predict", methods=["POST"])
def predict_customer_bill():
    """Run a retrospective customer bill prediction for a gold record."""
    payload = request.get_json(force=True, silent=False) or {}
    if not isinstance(payload, dict):
        raise AppError(
            "Request body must be a JSON object.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        entity_id = int(payload.get("entity_id", ""))
    except (TypeError, ValueError) as exc:
        raise AppError(
            "entity_id must be a positive integer.",
            code="INVALID_INPUT",
            status_code=422,
        ) from exc
    if entity_id < 1:
        raise AppError(
            "entity_id must be a positive integer.",
            code="INVALID_INPUT",
            status_code=422,
        )
    month_start = payload.get("month_start")
    if not isinstance(month_start, str):
        raise AppError(
            "month_start must use YYYY-MM-DD format.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        date.fromisoformat(month_start)
    except ValueError as exc:
        raise AppError(
            "month_start must use YYYY-MM-DD format.",
            code="INVALID_INPUT",
            status_code=422,
        ) from exc
    if len(month_start) != 10:
        raise AppError(
            "month_start must use YYYY-MM-DD format.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        cutoff_day = int(payload.get("cutoff_day", ""))
    except (TypeError, ValueError) as exc:
        raise AppError(
            "cutoff_day must be an integer between 1 and 31.",
            code="INVALID_INPUT",
            status_code=422,
        ) from exc
    if not 1 <= cutoff_day <= 31:
        raise AppError(
            "cutoff_day must be an integer between 1 and 31.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        result = _service().predict(entity_id, month_start, cutoff_day)
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="MODEL_UNAVAILABLE", status_code=503
        ) from exc
    if not result:
        raise ResourceNotFoundError(
            f"No gold-dataset record exists for entity '{entity_id}' in {month_start} "
            f"at cutoff day {cutoff_day}."
        )
    return success_response(result)
