"""Model catalog and customer bill inference routes."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, request, send_file

from app.api.error_handlers import AppError, ResourceNotFoundError
from app.models.anomaly_prediction import (
    AnomalyPredictionError,
    AnomalyPredictionService,
)
from app.models.customer_bill_prediction import (
    CustomerBillPredictionError,
    CustomerBillPredictionService,
)
from app.utils.responses import success_response

bp = Blueprint("models", __name__)


def _service() -> CustomerBillPredictionService:
    return current_app.extensions["customer_bill_prediction_service"]


def _anomaly_service() -> AnomalyPredictionService:
    return current_app.extensions["anomaly_prediction_service"]


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
        catalog = _service().get_model_catalog()
        catalog.append(_anomaly_service().get_summary())
        return success_response({"models": catalog})
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="MODEL_UNAVAILABLE", status_code=503
        ) from exc


@bp.route("/models/anomaly-prediction", methods=["GET"])
def get_anomaly_model():
    """Return anomaly model status without coupling it to other model datasets."""
    return success_response(_anomaly_service().get_summary())


@bp.route("/models/<model_id>/entities", methods=["GET"])
def get_forecast_model_entities(model_id: str):
    """List entity inputs supported by a commercial, government, or anomaly model."""
    service = current_app.extensions["forecast_service"]
    if model_id == "commercial-building-forecast":
        items = service.get_commercial_buildings()
        return success_response({"items": items})
    if model_id == "government-load-forecast":
        items = service.get_regional_sites()
        return success_response({"items": items})
    if model_id == "anomaly-prediction":
        try:
            offset = _positive_int(request.args.get("offset"), "offset", 0)
            limit = _positive_int(request.args.get("limit"), "limit", 100)
            if limit < 1 or limit > 10_000:
                raise AppError(
                    "limit must be between 1 and 10000.",
                    code="INVALID_INPUT",
                    status_code=422,
                )
            query = request.args.get("query", "")
            if len(query) > 100:
                raise AppError(
                    "query must be no longer than 100 characters.",
                    code="INVALID_INPUT",
                    status_code=422,
                )
            return success_response(
                _anomaly_service().get_entities(
                    query=query, offset=offset, limit=limit
                )
            )
        except AnomalyPredictionError as exc:
            raise AppError(str(exc), code="MODEL_UNAVAILABLE", status_code=503) from exc
    raise ResourceNotFoundError(f"Forecast model '{model_id}' was not found.")


@bp.route("/models/<model_id>/predict", methods=["POST"])
def predict_forecast_model(model_id: str):
    """Run a verified chronological holdout replay through the registered model."""
    provider = current_app.extensions["model_provider"]
    service = current_app.extensions["forecast_service"]
    payload = request.get_json(force=True, silent=False) or {}
    if model_id == "commercial-building-forecast":
        entity_id = str(payload.get("entity_id", ""))
        if not entity_id.isdigit() or int(entity_id) < 1:
            raise AppError("entity_id must be a positive integer.", code="INVALID_INPUT", status_code=422)
        sector = "commercial"
    elif model_id == "government-load-forecast":
        entity_id = str(payload.get("entity_id", ""))
        if not entity_id.isdigit() or int(entity_id) < 1:
            raise AppError("entity_id must be a positive integer.", code="INVALID_INPUT", status_code=422)
        sector = "government"
    elif model_id == "anomaly-prediction":
        if not isinstance(payload, dict):
            raise AppError("Request body must be a JSON object.", code="INVALID_INPUT", status_code=422)
        if "start_date" not in payload or "end_date" not in payload:
            raise AppError("start_date and end_date are required for anomaly analysis.", code="INVALID_INPUT", status_code=422)
        if payload.get("customer_ids") is not None and (
            not isinstance(payload["customer_ids"], list)
            or any(
                isinstance(customer_id, bool) or not isinstance(customer_id, int)
                for customer_id in payload["customer_ids"]
            )
        ):
            raise AppError("customer_ids must be a list of integer IDs.", code="INVALID_INPUT", status_code=422)
        if not isinstance(payload["start_date"], str) or not isinstance(payload["end_date"], str):
            raise AppError("start_date and end_date must be ISO dates.", code="INVALID_INPUT", status_code=422)
        try:
            result = _anomaly_service().run_analysis(payload)
            return success_response(result)
        except AnomalyPredictionError as exc:
            raise AppError(str(exc), code="MODEL_UNAVAILABLE", status_code=503) from exc
        except (TypeError, ValueError) as exc:
            raise AppError(str(exc), code="INVALID_INPUT", status_code=422) from exc
    else:
        raise ResourceNotFoundError(f"Forecast model '{model_id}' was not found.")
    horizon = payload.get("horizon_hours", 24)
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 24:
        raise AppError("horizon_hours must be an integer from 1 to 24.", code="INVALID_INPUT", status_code=422)
    status = provider.get_forecast_model_info(sector)
    if status.get("is_demo"):
        raise AppError("The registered champion model is unavailable.", code="MODEL_UNAVAILABLE", status_code=503)
    return success_response({
        "model": status,
        "entity_id": entity_id,
        "horizon": provider.predict_horizon(sector, entity_id, horizon),
    })


@bp.route("/models/anomaly-prediction/runs", methods=["GET"])
def get_anomaly_runs():
    """List persisted anomaly analysis runs."""
    limit = _positive_int(request.args.get("limit"), "limit", 25)
    if limit < 1 or limit > 100:
        raise AppError("limit must be between 1 and 100.", code="INVALID_INPUT", status_code=422)
    try:
        return success_response({"items": _anomaly_service().list_runs(limit)})
    except AnomalyPredictionError as exc:
        raise AppError(str(exc), code="MODEL_UNAVAILABLE", status_code=503) from exc


@bp.route("/models/anomaly-prediction/runs/<run_id>", methods=["GET"])
def get_anomaly_run(run_id: str):
    """Return one persisted anomaly analysis run."""
    try:
        run = _anomaly_service().get_run(run_id)
    except ValueError as exc:
        raise ResourceNotFoundError("Anomaly analysis run was not found.") from exc
    if run is None:
        raise ResourceNotFoundError("Anomaly analysis run was not found.")
    return success_response(run)


@bp.route(
    "/models/anomaly-prediction/runs/<run_id>/download/<filename>",
    methods=["GET"],
)
def download_anomaly_run_file(run_id: str, filename: str):
    """Download an allow-listed artifact from a completed anomaly run."""
    try:
        run = _anomaly_service().get_run(run_id)
        path = _anomaly_service().get_run_file(run_id, filename)
    except ValueError as exc:
        raise ResourceNotFoundError("Anomaly analysis run was not found.") from exc
    if run is None or path is None or run.get("status") != "completed":
        raise ResourceNotFoundError("Anomaly run artifact was not found.")
    media_type = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".geojson": "application/geo+json",
    }.get(Path(filename).suffix, "application/octet-stream")
    return send_file(path, as_attachment=True, download_name=filename, mimetype=media_type)


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


@bp.route("/models/customer-bill-prediction/profile/<int:entity_id>", methods=["GET"])
def get_customer_entity_profile(entity_id: int):
    """Return identity and location metadata for one residential entity."""
    try:
        profile = _service().get_entity_profile(entity_id)
    except CustomerBillPredictionError as exc:
        raise AppError(
            str(exc), code="DATA_UNAVAILABLE", status_code=503
        ) from exc
    if profile is None:
        raise ResourceNotFoundError(
            f"Customer entity '{entity_id}' was not found in the gold dataset."
        )
    return success_response(profile)


@bp.route("/models/customer-bill-prediction/history", methods=["GET"])
def get_customer_historical_insights():
    """Return residential historical trends from the customer gold dataset."""
    time_range = request.args.get("time_range", "ALL")
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
    if time_range not in {"3M", "6M", "1Y", "ALL"}:
        raise AppError(
            "time_range must be one of 3M, 6M, 1Y, or ALL.",
            code="INVALID_INPUT",
            status_code=422,
        )
    try:
        service = _service()
        if entity_id is not None and not service.get_entity_months(entity_id):
            raise ResourceNotFoundError(
                f"Customer entity '{entity_id}' was not found in the gold dataset."
            )
        result = service.get_historical_gold_insights(time_range, entity_id)
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
