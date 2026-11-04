"""Historical demand analysis route."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.api.error_handlers import AppError
from app.providers.source_approval import require_approved_source
from app.utils.responses import success_response

bp = Blueprint("historical", __name__)


@bp.route("/historical", methods=["GET"])
def get_historical_analysis():
    """Historical telemetry curves and dynamic KPI rollups."""
    persona = request.args.get("persona", "household")
    time_range = request.args.get("time_range", "30D")
    entity_id = request.args.get("entity_id")

    if persona.casefold() == "commercial" and not current_app.testing:
        require_approved_source("commercial_gold", "Commercial Gold dataset")
        provider = current_app.extensions["commercial_history_provider"]
        try:
            data = provider.get_commercial_historical_insights(
                time_range=time_range, entity_id=entity_id
            )
            provenance = provider.get_commercial_source_metadata()
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "Commercial Gold historical data is unavailable.",
                code="DATA_SOURCE_UNAVAILABLE",
                status_code=503,
                details={"availability": "unavailable", "source": "commercial_gold"},
            ) from exc
        curve = data.get("historyCurve", [])
        provenance.update(
            {
                "recordType": "historical_consumption_aggregate",
                "period": {
                    "start": curve[0]["fullDate"] if curve else None,
                    "end": curve[-1]["fullDate"] if curve else None,
                },
            }
        )
        return success_response(data, meta={"sourceProvenance": provenance})

    if persona.casefold() == "government" and not current_app.testing:
        require_approved_source("government_2018", "Government 2018 dataset")
        provider = current_app.extensions["commercial_history_provider"]
        try:
            data = provider.get_government_historical_insights(
                time_range=time_range, entity_id=entity_id
            )
            provenance = provider.get_government_source_metadata()
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "Government 2018 historical data is unavailable.",
                code="DATA_SOURCE_UNAVAILABLE",
                status_code=503,
                details={"availability": "unavailable", "source": "government_2018"},
            ) from exc
        provenance.update(
            {
                "recordType": "government_historical_consumption_aggregate",
                "displayUnits": data.get("unit"),
                "scope": data.get("scope"),
            }
        )
        return success_response(data, meta={"sourceProvenance": provenance})

    service = current_app.extensions["dashboard_service"]
    data = service.get_historical_insights(
        persona=persona,
        time_range=time_range,
        entity_id=entity_id,
    )
    return success_response(data)
