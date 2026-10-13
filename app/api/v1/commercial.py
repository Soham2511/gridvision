"""Commercial building hourly-demand prediction endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_model
from app.api.v1.schemas import PredictionRequest, PredictionResponse
from app.services.prediction_service import PredictionInputError, predict_one

router = APIRouter()


@router.post("/predict", response_model=PredictionResponse)
def predict_commercial(
    payload: PredictionRequest, request: Request
) -> PredictionResponse:
    """Predict the target for one hourly commercial feature record."""
    bundle = get_model(request, "commercial")
    try:
        prediction = predict_one(bundle, payload.features)
    except PredictionInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    caveats = [
        "The supplied model has not been independently approved for production use."
    ]
    if payload.context == "retrospective_gold_replay":
        caveats.append(
            "This is a replay from the supplied historical Gold dataset, not a "
            "current live forecast."
        )
    return PredictionResponse(
        entity_id=payload.entity_id,
        forecast_timestamp=payload.forecast_timestamp,
        prediction=prediction,
        target_name=bundle.metadata["target_name"],
        target_unit=bundle.metadata["target_units"],
        model_name=bundle.name,
        model_version=bundle.version,
        evaluation_status=bundle.metadata["evaluation_status"],
        context=payload.context,
        prediction_status=("valid" if prediction >= 0 else "invalid_negative_energy"),
        data_quality_status="feature_values_validated",
        caveats=caveats,
    )
