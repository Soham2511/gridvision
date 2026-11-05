"""Centralized Authentication & Session Management Endpoints."""

from __future__ import annotations

import logging
from datetime import timedelta
from flask import Blueprint, current_app, make_response, request, g

from app.config import BaseConfig
from app.infrastructure.database.connection import get_session
from app.services.assistant.auth import (
    AuthenticationError,
    AuthorizationError,
    HouseholdAuthService,
    require_auth,
)
from app.services.auth_service import auth_service
from app.services.assistant.historical.snapshot_repository import (
    HistoricalSnapshotRepository,
)
from app.utils.responses import error_response, success_response

logger = logging.getLogger("gridvision.api.v1.auth")

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _set_refresh_cookie(response, refresh_token: str) -> None:
    """Attach secure HttpOnly cookie containing the refresh token."""
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "gridvision_refresh_token")
    secure = current_app.config.get("AUTH_COOKIE_SECURE", False)
    samesite = current_app.config.get("AUTH_COOKIE_SAMESITE", "Lax")
    days = current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 7)
    max_age = int(timedelta(days=days).total_seconds())

    response.set_cookie(
        key=cookie_name,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )


def _clear_refresh_cookie(response) -> None:
    """Clear refresh token cookie."""
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "gridvision_refresh_token")
    response.delete_cookie(key=cookie_name, path="/")


@bp.route("/register", methods=["POST"])
def register():
    """Register a new residential customer account."""
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "")
    email = payload.get("email", "")
    password = payload.get("password", "")
    confirm_password = payload.get("confirm_password", "")

    user_agent = request.headers.get("User-Agent")
    ip_address = request.remote_addr

    try:
        user, access_token, refresh_token = auth_service.register_user(
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except ValueError as e:
        return error_response(str(e), code="VALIDATION_ERROR", status_code=400)
    except Exception as e:
        logger.error("Registration error: %s", e, exc_info=True)
        return error_response("Failed to register account.", code="INTERNAL_ERROR", status_code=500)

    user_payload = {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "persona": user.persona,
        "role": user.role,
        "meters": [m.id for m in user.meters] if user.meters else [],
    }

    res_body, status_code = success_response(
        {
            "user": user_payload,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": auth_service.access_token_expires_seconds,
        },
        status_code=201,
    )
    resp = make_response(res_body, status_code)
    _set_refresh_cookie(resp, refresh_token)
    return resp


@bp.route("/login", methods=["POST"])
def login():
    """Authenticate with username or email + password."""
    payload = request.get_json(silent=True) or {}
    identifier = payload.get("identifier") or payload.get("username") or payload.get("email") or ""
    password = payload.get("password", "")

    user_agent = request.headers.get("User-Agent")
    ip_address = request.remote_addr

    try:
        user, access_token, refresh_token = auth_service.login_user(
            identifier=identifier,
            password=password,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except AuthenticationError as e:
        return error_response(str(e), code="AUTHENTICATION_FAILED", status_code=401)
    except Exception as e:
        logger.error("Login failure: %s", e, exc_info=True)
        return error_response("An unexpected authentication error occurred.", code="INTERNAL_ERROR", status_code=500)

    try:
        snapshot_repository = HistoricalSnapshotRepository()
    except Exception as exc:
        logger.warning(
            "Could not initialize historical snapshot repository after login: %s",
            exc,
            exc_info=True,
        )
    else:
        for meter in user.meters:
            try:
                snapshot_repository.generate_snapshot_if_missing(meter.id)
            except Exception as exc:
                logger.warning(
                    "Could not generate historical snapshot for authenticated meter '%s': %s",
                    meter.id,
                    exc,
                    exc_info=True,
                )

    user_payload = {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "persona": user.persona,
        "role": user.role,
        "meters": [m.id for m in user.meters] if user.meters else [],
    }

    res_body, status_code = success_response(
        {
            "user": user_payload,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": auth_service.access_token_expires_seconds,
        },
        status_code=200,
    )
    resp = make_response(res_body, status_code)
    _set_refresh_cookie(resp, refresh_token)
    return resp


@bp.route("/refresh", methods=["POST"])
def refresh():
    """Rotate refresh token and issue a fresh JWT access token."""
    payload = request.get_json(silent=True) or {}
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "gridvision_refresh_token")
    raw_refresh = payload.get("refresh_token") or request.cookies.get(cookie_name)

    if not raw_refresh:
        return error_response("Refresh token required.", code="MISSING_REFRESH_TOKEN", status_code=401)

    user_agent = request.headers.get("User-Agent")
    ip_address = request.remote_addr

    try:
        with get_session() as db_session:
            new_refresh, user, _ = auth_service.rotate_session(
                session=db_session,
                raw_refresh_token=raw_refresh,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            new_access_token = auth_service.create_access_token(user)
    except AuthenticationError as e:
        resp, status = error_response(str(e), code="INVALID_REFRESH_TOKEN", status_code=401)
        response = make_response(resp, status)
        _clear_refresh_cookie(response)
        return response
    except Exception as e:
        logger.error("Session refresh error: %s", e, exc_info=True)
        return error_response("Failed to refresh session.", code="INTERNAL_ERROR", status_code=500)

    res_body, status_code = success_response(
        {
            "access_token": new_access_token,
            "refresh_token": new_refresh,
            "token_type": "Bearer",
            "expires_in": auth_service.access_token_expires_seconds,
        },
        status_code=200,
    )
    resp = make_response(res_body, status_code)
    _set_refresh_cookie(resp, new_refresh)
    return resp


@bp.route("/logout", methods=["POST"])
def logout():
    """Revoke active refresh token session and clear auth cookie."""
    payload = request.get_json(silent=True) or {}
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "gridvision_refresh_token")
    raw_refresh = payload.get("refresh_token") or request.cookies.get(cookie_name)

    if raw_refresh:
        try:
            with get_session() as db_session:
                auth_service.revoke_session(session=db_session, raw_refresh_token=raw_refresh)
        except Exception as e:
            logger.warning("Error revoking session on logout: %s", e)

    res_body, status_code = success_response(
        {"message": "Logged out successfully."},
        status_code=200,
    )
    resp = make_response(res_body, status_code)
    _clear_refresh_cookie(resp)
    return resp


@bp.route("/me", methods=["GET"])
@require_auth
def get_current_user():
    """Return identity and authorized meter scope for current authenticated principal."""
    principal = g.current_user
    return success_response(
        {
            "id": principal.user_id,
            "username": principal.username,
            "email": principal.email,
            "persona": principal.persona.upper(),
            "role": principal.role,
            "meters": list(principal.authorized_meters),
        }
    )
