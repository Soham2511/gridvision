"""Centralized error handlers for Flask application."""

from __future__ import annotations

import logging
from flask import Flask, Request
from pydantic import ValidationError

from app.utils.responses import error_response

logger = logging.getLogger("gridvision.errors")


class AppError(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = 400,
        details: object = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class ResourceNotFoundError(AppError):
    """Resource does not exist."""

    def __init__(self, message: str = "Requested resource not found") -> None:
        super().__init__(message=message, code="NOT_FOUND", status_code=404)


class InvalidInputError(AppError):
    """Input parameters failed validation."""

    def __init__(self, message: str, details: object = None) -> None:
        super().__init__(
            message=message,
            code="INVALID_INPUT",
            status_code=422,
            details=details,
        )


class RegionMappingNotFoundError(AppError):
    """Commercial building has no verified coarse-grid mapping."""

    def __init__(self, message: str = "No coarse-grid mapping exists for this building.") -> None:
        super().__init__(message=message, code="REGION_MAPPING_NOT_FOUND", status_code=409)


class ModelUnavailableError(AppError):
    """One or both required forecast models are unavailable."""

    def __init__(self, message: str = "A required forecast model is unavailable.") -> None:
        super().__init__(message=message, code="MODEL_UNAVAILABLE", status_code=503)


class InvalidModelOutputError(AppError):
    """Forecast provider returned data outside the forecast response contract."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="INVALID_MODEL_OUTPUT", status_code=502)


def register_error_handlers(app: Flask) -> None:
    """Register application-wide error handlers."""

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        logger.warning("Application error: %s (%s)", error.message, error.code)
        return error_response(
            message=error.message,
            code=error.code,
            details=error.details,
            status_code=error.status_code,
        )

    @app.errorhandler(ValidationError)
    def handle_pydantic_error(error: ValidationError):
        logger.warning("Pydantic validation error: %s", error)
        return error_response(
            message="Request body failed contract validation.",
            code="VALIDATION_ERROR",
            details=error.errors(),
            status_code=422,
        )

    @app.errorhandler(400)
    def handle_400(error):
        return error_response(
            message="Bad request syntax or invalid parameters.",
            code="BAD_REQUEST",
            status_code=400,
        )

    @app.errorhandler(404)
    def handle_404(error):
        return error_response(
            message="The requested endpoint or resource does not exist.",
            code="NOT_FOUND",
            status_code=404,
        )

    @app.errorhandler(405)
    def handle_405(error):
        return error_response(
            message="HTTP method not allowed for this endpoint.",
            code="METHOD_NOT_ALLOWED",
            status_code=405,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("Unhandled server exception: %s", error)
        return error_response(
            message="An unexpected internal server error occurred.",
            code="INTERNAL_ERROR",
            status_code=500,
        )
