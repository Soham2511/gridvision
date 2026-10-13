"""Liveness and readiness checks for the API process."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

router = APIRouter()


@router.get("/live")
def live() -> dict[str, str]:
    """Report that the API process is responsive."""
    return {"status": "alive"}


@router.get("/ready")
def ready(request: Request, response: Response) -> dict[str, object]:
    """Report whether all configured model artifacts passed startup checks."""
    models = getattr(request.app.state, "models", None)
    expected = getattr(request.app.state, "expected_models", ())
    loaded = sorted(models) if isinstance(models, dict) else []
    is_ready = bool(expected) and set(loaded) == set(expected)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if is_ready else "not_ready",
        "models_loaded": loaded,
        "models_expected": list(expected),
    }
