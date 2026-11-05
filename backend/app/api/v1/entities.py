"""Entity catalog routes for commercial, residential, and regional sites."""

from __future__ import annotations

from flask import Blueprint, current_app
from app.api.error_handlers import AppError, ResourceNotFoundError
from app.providers.source_approval import require_approved_source
from app.utils.responses import success_response

bp = Blueprint("entities", __name__)


@bp.route("/entities/commercial", methods=["GET"])
def get_commercial_buildings():
    """Returns list of commercial buildings."""
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
        return success_response(items, meta={"sourceProvenance": provenance})
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_commercial_buildings())


@bp.route("/entities/commercial/<building_id>", methods=["GET"])
def get_commercial_building(building_id: str):
    """Returns details for a single commercial building."""
    if not current_app.testing:
        require_approved_source("commercial_gold", "Commercial Gold dataset")
        provider = current_app.extensions["commercial_history_provider"]
        try:
            if hasattr(provider, "get_commercial_building"):
                bldg = provider.get_commercial_building(building_id)
            else:
                bldg = next(
                    (
                        item
                        for item in provider.get_commercial_buildings()
                        if item["buildingId"] == building_id
                    ),
                    None,
                )
            provenance = provider.get_commercial_source_metadata()
        except Exception as exc:
            raise AppError(
                "Commercial Gold building data is unavailable.",
                code="DATA_SOURCE_UNAVAILABLE",
                status_code=503,
                details={"availability": "unavailable", "source": "commercial_gold"},
            ) from exc
        if not bldg:
            raise ResourceNotFoundError(f"Commercial building '{building_id}' not found.")
        provenance["recordType"] = "commercial_building_profile"
        return success_response(bldg, meta={"sourceProvenance": provenance})
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
        return success_response(items, meta={"sourceProvenance": provenance})
    service = current_app.extensions["forecast_service"]
    return success_response(service.get_regional_sites())


@bp.route("/entities/government/<site_id>", methods=["GET"])
def get_regional_site(site_id: str):
    """Returns details for a single regional site."""
    if not current_app.testing:
        require_approved_source("government_2018", "Government 2018 dataset")
        provider = current_app.extensions["commercial_history_provider"]
        try:
            site = next(
                (item for item in provider.get_regional_sites() if item["siteId"] == site_id),
                None,
            )
            provenance = provider.get_government_source_metadata()
        except Exception as exc:
            raise AppError(
                "Government 2018 grid data is unavailable.",
                code="DATA_SOURCE_UNAVAILABLE",
                status_code=503,
                details={"availability": "unavailable", "source": "government_2018"},
            ) from exc
        if not site:
            raise ResourceNotFoundError(f"Government grid '{site_id}' not found.")
        provenance["recordType"] = "government_grid_profile"
        return success_response(site, meta={"sourceProvenance": provenance})
    service = current_app.extensions["forecast_service"]
    site = service.get_regional_site(site_id)
    if not site:
        raise ResourceNotFoundError(f"Regional site '{site_id}' not found.")
    return success_response(site)
