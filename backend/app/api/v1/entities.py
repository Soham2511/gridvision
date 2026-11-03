"""Entity catalog routes for commercial, residential, and regional sites."""

from __future__ import annotations

from flask import Blueprint, current_app
from app.api.error_handlers import ResourceNotFoundError
from app.utils.responses import success_response

bp = Blueprint("entities", __name__)


@bp.route("/entities/commercial", methods=["GET"])
def get_commercial_buildings():
    """Returns list of commercial buildings."""
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_commercial_buildings())


@bp.route("/entities/commercial/<building_id>", methods=["GET"])
def get_commercial_building(building_id: str):
    """Returns details for a single commercial building."""
    service = current_app.extensions["forecast_service"]
    bldg = service.get_commercial_building(building_id)
    if not bldg:
        raise ResourceNotFoundError(f"Commercial building '{building_id}' not found.")
    return success_response(bldg)


@bp.route("/entities/residential", methods=["GET"])
def get_residential_meters():
    """Returns list of residential smart meters."""
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_residential_meters())


@bp.route("/entities/residential/<household_id>", methods=["GET"])
def get_residential_meter(household_id: str):
    """Returns details for a single residential meter."""
    data_provider = current_app.extensions["data_provider"]
    meter = data_provider.get_residential_meter(household_id)
    if not meter:
        raise ResourceNotFoundError(f"Residential meter '{household_id}' not found.")
    return success_response(meter)


@bp.route("/entities/government", methods=["GET"])
def get_regional_sites():
    """Returns list of regional government grid sites."""
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_regional_sites())


@bp.route("/entities/government/<site_id>", methods=["GET"])
def get_regional_site(site_id: str):
    """Returns details for a single regional site."""
    service = current_app.extensions["forecast_service"]
    site = service.get_regional_site(site_id)
    if not site:
        raise ResourceNotFoundError(f"Regional site '{site_id}' not found.")
    return success_response(site)
