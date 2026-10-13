"""Residential month-end prediction endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_model
from app.api.v1.schemas import PredictionRequest, PredictionResponse
from app.services.prediction_service import PredictionInputError, predict_one

router = APIRouter()


@router.post("/predict", response_model=PredictionResponse)
def predict_residential(
    payload: PredictionRequest, request: Request
) -> PredictionResponse:
    """Predict remaining calendar-month consumption and estimate its bill."""
    bundle = get_model(request, "residential")
    try:
        predicted_remaining = predict_one(bundle, payload.features)
    except PredictionInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    actual = payload.actual_kwh_so_far
    tariff = (
        float(bundle.metadata["tariff_inr_per_kwh"]) if actual is not None else None
    )
    prediction_is_valid = predicted_remaining >= 0
    total_kwh = (
        actual + predicted_remaining
        if actual is not None and prediction_is_valid
        else None
    )
    coverage = payload.features.get("coverage_today")
    quality = (
        "unknown"
        if coverage is None
        else (
            "meets_minimum"
            if float(coverage) >= float(bundle.metadata["minimum_daily_coverage_ratio"])
            else "below_minimum"
        )
    )
    caveats = [
        "The supplied model has not been independently approved for production use."
    ]
    if payload.context == "retrospective_gold_replay":
        caveats.append(
            "This is a replay from the supplied historical Gold dataset, not a "
            "current live forecast."
        )
    if tariff is not None:
        caveats.append(
            "The bill amount uses the prototype flat tariff; it is not a utility bill."
        )
    if not prediction_is_valid:
        caveats.append(
            "The model returned negative remaining energy. The raw output is shown "
            "for diagnosis; no month-end usage or bill estimate is provided."
        )
    return PredictionResponse(
        entity_id=payload.entity_id,
        forecast_timestamp=payload.forecast_timestamp,
        prediction=predicted_remaining,
        target_name=bundle.metadata["target_name"],
        target_unit=bundle.metadata["target_units"],
        model_name=bundle.name,
        model_version=bundle.version,
        evaluation_status=bundle.metadata["evaluation_status"],
        context=payload.context,
        prediction_status=(
            "valid" if prediction_is_valid else "invalid_negative_energy"
        ),
        actual_kwh_so_far=actual,
        estimated_month_end_kwh=total_kwh,
        estimated_month_end_bill_inr=(
            total_kwh * tariff if total_kwh is not None and tariff is not None else None
        ),
        tariff_inr_per_kwh=tariff,
        data_quality_status=quality,
        caveats=caveats,
    )
