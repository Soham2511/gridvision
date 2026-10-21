"""Demand forecasting and model inference routes."""

from __future__ import annotations

from flask import Blueprint, current_app, request
from app.utils.responses import success_response
from app.utils.validation import PredictionRequestModel

bp = Blueprint("forecast", __name__)


@bp.route("/forecast/commercial/<building_id>", methods=["GET"])
def commercial_forecast(building_id: str):
    """Multi-horizon demand forecast for a commercial building."""
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_commercial_forecast(building_id))


@bp.route("/forecast/residential/<household_id>", methods=["GET"])
def residential_forecast(household_id: str):
    """Month-end demand forecast for a residential meter."""
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_residential_forecast(household_id))


@bp.route("/forecast/government/<site_id>", methods=["GET"])
def government_forecast(site_id: str):
    """Demand forecast for a regional government grid site."""
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_government_forecast(site_id))


@bp.route("/forecast/predict", methods=["POST"])
def unified_predict():
    """Unified inference endpoint for raw feature records."""
    data = request.get_json(force=True, silent=False) or {}
    validated = PredictionRequestModel.model_validate(data)
    service = current_app.extensions["forecast_service"]

    result = service.predict_one(
        model_name=data.get("model_name", "commercial"),
        entity_id=validated.entity_id,
        features=validated.features,
        actual_kwh_so_far=validated.actual_kwh_so_far,
        context=validated.context,
    )
    return success_response(result.model_dump())


@bp.route("/commercial/predict", methods=["POST"])
def commercial_predict():
    """Commercial inference matching reference FastAPI signature."""
    data = request.get_json(force=True, silent=False) or {}
    validated = PredictionRequestModel.model_validate(data)
    service = current_app.extensions["forecast_service"]

    result = service.predict_one(
        model_name="commercial",
        entity_id=validated.entity_id,
        features=validated.features,
        context=validated.context,
    )
    return success_response(result.model_dump())


@bp.route("/residential/predict", methods=["POST"])
def residential_predict():
    """Residential inference matching reference FastAPI signature."""
    data = request.get_json(force=True, silent=False) or {}
    validated = PredictionRequestModel.model_validate(data)
    service = current_app.extensions["forecast_service"]

    result = service.predict_one(
        model_name="residential",
        entity_id=validated.entity_id,
        features=validated.features,
        actual_kwh_so_far=validated.actual_kwh_so_far,
        context=validated.context,
    )
    return success_response(result.model_dump())


@bp.route("/government/predict", methods=["POST"])
def government_predict():
    """Government inference matching reference FastAPI signature."""
    data = request.get_json(force=True, silent=False) or {}
    validated = PredictionRequestModel.model_validate(data)
    service = current_app.extensions["forecast_service"]

    result = service.predict_one(
        model_name="government",
        entity_id=validated.entity_id,
        features=validated.features,
        context=validated.context,
    )
    return success_response(result.model_dump())
