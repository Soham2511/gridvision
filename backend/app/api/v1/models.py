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
from app.models.registry import MODEL_REGISTRY
from app.services.segmentation_service import SegmentationUnavailableError
from app.providers.source_approval import require_approved_source, source_is_approved
from app.ai.anomaly_assistant import build_anomaly_report
from app.ai.application_store import ApplicationStoreError
from app.ai.report_service import ReportService
from app.ai.report_service import ReportRenderError
from app.ai.storage import PrivateStorageError
from app.utils.responses import success_response

bp = Blueprint("models", __name__)


def _raw_service() -> CustomerBillPredictionService:
    return current_app.extensions["customer_bill_prediction_service"]


def _service() -> CustomerBillPredictionService:
    require_approved_source("customer_gold", "Customer Gold dataset")
    return _raw_service()


def _customer_source_meta(record_type: str) -> dict:
    try:
        return {"sourceProvenance": _service().get_source_metadata(record_type)}
    except CustomerBillPredictionError as exc:
        raise AppError(str(exc), code="DATA_UNAVAILABLE", status_code=503) from exc


def _anomaly_service() -> AnomalyPredictionService:
    return current_app.extensions["anomaly_prediction_service"]


def _anomaly_summary() -> dict:
    require_approved_source("anomaly_synthetic_2019", "Synthetic anomaly dataset")
    configured_path = Path(current_app.config.get("ANOMALY_DATASET_PATH")).expanduser()
    expected_path = (
        Path(current_app.config["PROJECT_ROOT"])
        / "data"
        / "anomaly_prediction"
        / "synthetic_2019_normal.parquet"
    )
    synthetic = configured_path.resolve() == expected_path.resolve()
    if not current_app.testing and not synthetic:
        raise AppError(
            "Runtime anomaly inference is restricted to the approved synthetic 2019 dataset.",
            code="DATA_SOURCE_UNAVAILABLE",
            status_code=503,
            details={
                "availability": "provenance_unverified",
                "source": "anomaly_synthetic_2019",
                "live_telemetry": "not_configured",
            },
        )
    summary = _anomaly_service().get_summary()
    summary["sourceProvenance"] = "synthetic" if synthetic else "unverified"
    summary["isLiveTelemetry"] = False
    summary["sourceNotice"] = (
        "The configured anomaly dataset is synthetic 2019 data."
        if synthetic
        else "The configured anomaly dataset provenance has not been verified."
    )
    summary["sourceMetadata"] = {
        "sourceId": "anomaly_synthetic_2019",
        "dataset": configured_path.name,
        "datasetVersion": "untracked",
        "period": {"start": "2019-01-01", "end": "2019-12-31"},
        "recordType": "synthetic_model_output",
        "isLiveTelemetry": False,
        "verifiedFaultEvidence": False,
    }
    return summary


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
    if source_is_approved("customer_gold"):
        try:
            models = _service().get_model_catalog()
        except CustomerBillPredictionError as exc:
            raise AppError(
                str(exc), code="MODEL_UNAVAILABLE", status_code=503
            ) from exc
    else:
        try:
            # Catalog metadata is not a prediction or consumption record. Keep
            # the existing UI shape while explicitly marking the source unverified.
            models = _raw_service().get_model_catalog()
        except CustomerBillPredictionError:
            models = [{**MODEL_REGISTRY["customer-bill-prediction"].as_dict()}]
        for model in models:
            source_by_id = {
                "customer-bill-prediction": "customer_gold",
                "commercial-building-forecast": "commercial_gold",
                "government-load-forecast": "government_2018",
            }
            source_id = source_by_id.get(model.get("modelId"))
            if source_id and not source_is_approved(source_id):
                model["status"] = "provenance_unverified"
                model["provenanceStatus"] = "unverified"
                model["availability"] = "unavailable"
                model["reason"] = f"Source provenance for {source_id} has not been approved."
    segmentation_service = current_app.extensions[
        "government_segmentation_service"
    ]
    if source_is_approved("segmentation_2018"):
        try:
            metadata = segmentation_service.get_model_metadata()
            models.append(
                {
                    **MODEL_REGISTRY["government-customer-segmentation"].as_dict(),
                    "status": "configured",
                    "provider": "published_artifacts",
                    "modelVersion": metadata.get("model_version", "unknown"),
                    "selectedModel": metadata.get("model_version", "unknown"),
                    "healthSummary": (
                        f"{metadata.get('assignment_count', 0):,} buildings assigned "
                        f"across {len(metadata.get('trained_models', []))} model groups."
                    ),
                    "assignmentCount": metadata.get("assignment_count", 0),
                    "trainedModelCount": len(metadata.get("trained_models", [])),
                    "observationStart": metadata.get("observation_start"),
                    "observationEndExclusive": metadata.get(
                        "observation_end_exclusive"
                    ),
                    "features": sorted(
                        {
                            feature
                            for trained_model in metadata.get("trained_models", [])
                            for feature in trained_model.get(
                                "transformed_feature_columns", []
                            )
                        }
                    ),
                }
            )
        except SegmentationUnavailableError as exc:
            models.append(
                {
                    **MODEL_REGISTRY["government-customer-segmentation"].as_dict(),
                    "status": "unavailable",
                    "provider": "published_artifacts",
                    "modelVersion": "not_deployed",
                    "selectedModel": "not_deployed",
                    "healthSummary": str(exc),
                    "error": str(exc),
                }
            )
    else:
        models.append(
            {
                **MODEL_REGISTRY["government-customer-segmentation"].as_dict(),
                "status": "provenance_unverified",
                "provider": "approval_gate",
                "modelVersion": "not_approved",
                "selectedModel": "not_approved",
                "healthSummary": "Segmentation source provenance has not been approved.",
                "availability": "unavailable",
            }
        )
    models.append(_anomaly_summary())
    return success_response({"models": models})


@bp.route("/models/anomaly-prediction", methods=["GET"])
def get_anomaly_model():
    """Return anomaly model status without coupling it to other model datasets."""
    return success_response(_anomaly_summary())


@bp.route("/models/<model_id>/entities", methods=["GET"])
def get_forecast_model_entities(model_id: str):
    """List entity inputs supported by a commercial, government, or anomaly model."""
    service = current_app.extensions["forecast_service"]
    if model_id == "commercial-building-forecast":
        if not current_app.testing:
            require_approved_source("commercial_gold", "Commercial Gold dataset")
            provider = current_app.extensions["commercial_history_provider"]
            try:
                items = provider.get_commercial_buildings()
                provenance = provider.get_commercial_source_metadata()
            except AppError:
                raise
            except Exception as exc:
                raise AppError(
                    "Commercial Gold building data is unavailable.",
                    code="DATA_SOURCE_UNAVAILABLE",
                    status_code=503,
                    details={"availability": "unavailable", "source": "commercial_gold"},
                ) from exc
            provenance["recordType"] = "commercial_building_catalog"
            return success_response(
                {"items": items}, meta={"sourceProvenance": provenance}
            )
        items = service.get_commercial_buildings()
        return success_response({"items": items})
    if model_id == "government-load-forecast":
        if not current_app.testing:
            require_approved_source("government_2018", "Government 2018 dataset")
            provider = current_app.extensions["commercial_history_provider"]
            try:
                items = provider.get_regional_sites()
                provenance = provider.get_government_source_metadata()
            except AppError:
                raise
            except Exception as exc:
                raise AppError(
                    "Government 2018 grid data is unavailable.",
                    code="DATA_SOURCE_UNAVAILABLE",
                    status_code=503,
                    details={"availability": "unavailable", "source": "government_2018"},
                ) from exc
            provenance["recordType"] = "government_grid_catalog"
            return success_response(
                {"items": items}, meta={"sourceProvenance": provenance}
            )
        items = service.get_regional_sites()
        return success_response({"items": items})
    if model_id == "anomaly-prediction":
        anomaly_source = _anomaly_summary()
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
            result = _anomaly_service().get_entities(
                query=query, offset=offset, limit=limit
            )
            result.update(
                {
                    "sourceProvenance": anomaly_source["sourceProvenance"],
                    "sourceMetadata": anomaly_source["sourceMetadata"],
                    "isLiveTelemetry": False,
                }
            )
            return success_response(result)
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
        anomaly_source = _anomaly_summary()
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
            if isinstance(result, dict):
                result["sourceProvenance"] = anomaly_source["sourceProvenance"]
                result["sourceMetadata"] = anomaly_source["sourceMetadata"]
                result["isLiveTelemetry"] = False
                events = result.get("events", [])
                selected_entity = (
                    request.args.get("building_id") or request.args.get("entity_id", "")
                ).strip()
                if events and selected_entity:
                    persona = request.args.get("persona", "household").casefold()
                    if persona not in {"household", "commercial", "government"}:
                        raise AppError(
                            "persona must be household, commercial, or government.",
                            code="INVALID_INPUT",
                            status_code=422,
                        )
                    try:
                        selected_customer_id = int(selected_entity)
                    except ValueError:
                        selected_customer_id = None
                    matching_events = (
                        [
                            event for event in events
                            if selected_customer_id is not None
                            and selected_customer_id in {
                                int(value) for value in event.get("customer_ids", [])
                            }
                        ]
                    )
                    try:
                        store = current_app.extensions["ai_application_store"]
                        store.initialize()
                        run_id = str(result.get("analysis_id") or result.get("run_id") or "unknown")
                        for event in matching_events:
                            event_id = str(event.get("event_id") or "unknown")
                            anomaly_type = str(
                                event.get("dominant_anomaly_type") or "anomaly"
                            ).replace("_", " ")
                            period = (
                                f"{event.get('event_start', 'unknown')} to "
                                f"{event.get('event_end', 'unknown')}"
                            )
                            count = event.get("affected_customer_count", 0)
                            store.notify(
                                f"demo:{persona}:entity:{selected_entity}",
                                f"anomaly-detected:{run_id}:{event_id}",
                                "anomaly_detected",
                                "Synthetic anomaly detected",
                                (
                                    f"The synthetic 2019 detector marked {anomaly_type} "
                                    f"during {period}, affecting {count} customer(s). "
                                    "This is not a live alert or confirmed electrical fault."
                                ),
                            )
                    except ApplicationStoreError:
                        current_app.logger.exception(
                            "Could not persist in-app anomaly notifications."
                        )
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
    anomaly_source = _anomaly_summary()
    limit = _positive_int(request.args.get("limit"), "limit", 25)
    if limit < 1 or limit > 100:
        raise AppError("limit must be between 1 and 100.", code="INVALID_INPUT", status_code=422)
    try:
        return success_response(
            {
                "items": _anomaly_service().list_runs(limit),
                "sourceProvenance": anomaly_source["sourceProvenance"],
                "sourceMetadata": anomaly_source["sourceMetadata"],
                "isLiveTelemetry": False,
            }
        )
    except AnomalyPredictionError as exc:
        raise AppError(str(exc), code="MODEL_UNAVAILABLE", status_code=503) from exc


@bp.route("/models/anomaly-prediction/runs/<run_id>", methods=["GET"])
def get_anomaly_run(run_id: str):
    """Return one persisted anomaly analysis run."""
    anomaly_source = _anomaly_summary()
    try:
        run = _anomaly_service().get_run(run_id)
    except ValueError as exc:
        raise ResourceNotFoundError("Anomaly analysis run was not found.") from exc
    if run is None:
        raise ResourceNotFoundError("Anomaly analysis run was not found.")
    run["sourceProvenance"] = anomaly_source["sourceProvenance"]
    run["sourceMetadata"] = anomaly_source["sourceMetadata"]
    run["isLiveTelemetry"] = False
    return success_response(run)


@bp.route(
    "/models/anomaly-prediction/runs/<run_id>/events/<event_id>/assistant",
    methods=["POST"],
)
def create_anomaly_assistance_report(run_id: str, event_id: str):
    """Create a conservative report from an existing synthetic model event."""
    _anomaly_summary()
    try:
        run = _anomaly_service().get_run(run_id)
    except (AnomalyPredictionError, ValueError) as exc:
        raise ResourceNotFoundError("Anomaly analysis run was not found.") from exc
    if run is None:
        raise ResourceNotFoundError("Anomaly analysis run was not found.")
    event = next(
        (item for item in run.get("events", []) if item.get("event_id") == event_id),
        None,
    )
    if event is None:
        raise ResourceNotFoundError("Anomaly event was not found in this run.")
    selected_entity = (
        request.args.get("building_id") or request.args.get("entity_id", "")
    ).strip()
    if selected_entity:
        try:
            customer_id = int(selected_entity)
        except ValueError as exc:
            raise AppError("entity_id must be a numeric customer OBJECTID.", code="INVALID_INPUT", status_code=422) from exc
        if customer_id not in {int(value) for value in event.get("customer_ids", [])}:
            raise ResourceNotFoundError("Anomaly event was not found for the selected customer.")
        report_context = f"demo:household:entity:{customer_id}"
    else:
        customer_id = None
        report_context = "demo:household"
    report = build_anomaly_report(
        run, event, corpus=current_app.extensions["ai_rag_corpus"]
    )
    if customer_id is not None:
        report["entityId"] = customer_id
    store = current_app.extensions["ai_application_store"]
    try:
        private = current_app.extensions["ai_private_storage"]
        private.initialize()
        sources = [{"sourceId": "anomaly_synthetic_2019", "provenance": "synthetic"}]
        html_id = private.store(
            ReportService.render_html("Synthetic anomaly assistance report", report, sources)
        )
        pdf_id = private.store(
            ReportService.render_pdf("Synthetic anomaly assistance report", report, sources)
        )
        store.initialize()
        store.create_report(
            "anomaly_rectification",
            report_context,
            sources,
            {
                "report": report,
                "metadata": {
                    "reportType": "anomaly_rectification",
                    **({"entityId": str(report["entityId"])} if report.get("entityId") is not None else {}),
                },
                "pdfArtifactId": pdf_id,
            },
            artifact_id=html_id,
            idempotency_key=report["reportId"],
        )
        store.notify(
            report_context,
            f"anomaly-report:{report['reportId']}",
            "anomaly_report",
            "Anomaly report is ready",
            "A synthetic-data anomaly report is available for review.",
        )
    except (ApplicationStoreError, PrivateStorageError, ReportRenderError, OSError) as exc:
        raise AppError("AI report storage is unavailable.", code="AI_STORAGE_UNAVAILABLE", status_code=503) from exc
    return success_response(report)


@bp.route(
    "/models/anomaly-prediction/runs/<run_id>/download/<filename>",
    methods=["GET"],
)
def download_anomaly_run_file(run_id: str, filename: str):
    """Download an allow-listed artifact from a completed anomaly run."""
    anomaly_source = _anomaly_summary()
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
    response = send_file(
        path, as_attachment=True, download_name=filename, mimetype=media_type
    )
    source = anomaly_source["sourceMetadata"]
    response.headers["X-GridVision-Source-Provenance"] = anomaly_source[
        "sourceProvenance"
    ]
    response.headers["X-GridVision-Source-Id"] = source["sourceId"]
    response.headers["X-GridVision-Source-Version"] = source["datasetVersion"]
    response.headers["X-GridVision-Verified-Fault-Evidence"] = str(
        source["verifiedFaultEvidence"]
    ).lower()
    return response


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
    return success_response(
        result, meta=_customer_source_meta("historical_consumption_aggregate")
    )


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
    return success_response(
        records, meta=_customer_source_meta("historical_consumption_records")
    )


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
    return success_response(
        profile, meta=_customer_source_meta("historical_customer_profile")
    )


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
    return success_response(
        result, meta=_customer_source_meta("historical_consumption_aggregate")
    )


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
    return success_response(
        result,
        meta=_customer_source_meta("model_prediction_with_historical_actual"),
    )
