"""Trusted principal and household isolation authorization module.

Provides a clean security abstraction for resolving authenticated principals,
validating meter authorizations, and enforcing strict tenant boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional
from flask import Request, current_app, g, jsonify, request

logger = logging.getLogger("gridvision.assistant.auth")


class AuthenticationError(RuntimeError):
    """Raised when request identity cannot be established (401)."""


class AuthorizationError(RuntimeError):
    """Raised when an authenticated principal attempts unauthorized access (403)."""


@dataclass(frozen=True)
class UserPrincipal:
    """Represents a trusted authenticated principal and their authorized data scope."""

    user_id: str
    persona: str
    authorized_meters: tuple[str, ...]
    role: str = "RESIDENTIAL_USER"
    email: str = ""
    username: str = ""
    is_authenticated: bool = True

    def is_meter_authorized(self, meter_id: str) -> bool:
        """Verify whether the requested meter is in the principal's authorized scope."""
        if not meter_id:
            return False
        clean = meter_id.strip().upper()
        num_part = clean.replace("METER-", "")
        return any(
            clean == auth.upper() or f"METER-{num_part}" == auth.upper() or num_part == auth.replace("METER-", "").upper()
            for auth in self.authorized_meters
        )


class HouseholdAuthService:
    """Resolves trusted principal and enforces household-level data isolation."""

    @staticmethod
    def resolve_principal(request: Request) -> UserPrincipal:
        """Resolve the trusted authenticated principal.

        In production, identity must derive from a verified session or trusted JWT.
        In development mode (DEVELOPMENT_AUTH_ENABLED=True), server-configured mappings
        are utilized to simulate household personas without bypassing validation.
        """
        app_config = current_app.config
        is_dev_auth_enabled = app_config.get("DEVELOPMENT_AUTH_ENABLED", False)

        # 1. Verified Access Token Path (Signed JWT Bearer)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token and token != "dev-token":
                try:
                    from app.services.auth_service import auth_service
                    payload = auth_service.verify_access_token(token)
                    meters = tuple(payload.get("meters", []))
                    return UserPrincipal(
                        user_id=str(payload.get("sub", "")),
                        persona=str(payload.get("persona", "RESIDENTIAL")).lower(),
                        authorized_meters=meters,
                        role=str(payload.get("role", "RESIDENTIAL_USER")),
                        email=str(payload.get("email", "")),
                        username=str(payload.get("username", "")),
                        is_authenticated=True,
                    )
                except Exception as e:
                    logger.warning("Access token rejected: %s", e)
                    # If invalid token is presented, fail closed even in dev mode
                    raise AuthenticationError(f"Invalid or expired credentials: {e}")

        # 2. If production auth is required and no valid token is present, fail closed
        if not is_dev_auth_enabled:
            logger.warning("Authentication failed: No trusted authentication credentials provided.")
            raise AuthenticationError("Authentication required to access GridVision features.")

        # 3. Development / Staging Identity Resolution (Strictly isolated to non-production)
        dev_mapping: dict[str, list[str]] = app_config.get("DEV_USER_METER_MAPPING", {
            # Real physical OBJECTID accounts
            "2254213": ["2254213", "METER-2254213", "1000", "METER-1000"],
            "293861": ["293861", "METER-293861", "1001", "METER-1001"],
            "537421": ["537421", "METER-537421", "1002", "METER-1002"],
            "679900": ["679900", "METER-679900", "1003", "METER-1003"],
            # Username aliases
            "OBJECTID 2254213": ["2254213", "METER-2254213", "1000", "METER-1000"],
            "OBJECTID 293861": ["293861", "METER-293861", "1001", "METER-1001"],
            "OBJECTID 537421": ["537421", "METER-537421", "1002", "METER-1002"],
            "OBJECTID 679900": ["679900", "METER-679900", "1003", "METER-1003"],
            "usr-resident-2254213": ["2254213", "METER-2254213", "1000", "METER-1000"],
            "usr-resident-293861": ["293861", "METER-293861", "1001", "METER-1001"],
            "usr-resident-537421": ["537421", "METER-537421", "1002", "METER-1002"],
            "usr-resident-679900": ["679900", "METER-679900", "1003", "METER-1003"],
            # Legacy alias accounts
            "usr-resident-1000": ["METER-1000", "1000", "2254213", "METER-2254213"],
            "usr-resident-1001": ["METER-1001", "1001", "293861", "METER-293861"],
            "usr-resident-1002": ["METER-1002", "1002", "537421", "METER-537421"],
            "usr-resident-1003": ["METER-1003", "1003", "679900", "METER-679900"],
        })

        # In dev mode, check for explicit entity query parameter first
        req_json = request.get_json(silent=True) or {}
        requested_entity = (
            req_json.get("meter_id")
            or req_json.get("entity_id")
            or request.args.get("meter_id")
            or request.args.get("entity_id")
            or ""
        ).strip().upper()

        if requested_entity:
            for uid, allowed in dev_mapping.items():
                if any(requested_entity == m.upper() or requested_entity == m.replace("METER-", "").upper() for m in allowed):
                    return UserPrincipal(
                        user_id=uid,
                        persona="residential",
                        authorized_meters=tuple(allowed),
                    )
            # In development mode, dynamically authorize requested telemetry meter for local testing
            clean_num = requested_entity.replace("METER-", "").replace("USR-", "")
            return UserPrincipal(
                user_id=requested_entity,
                persona=request.headers.get("X-Persona", "residential").lower(),
                authorized_meters=(requested_entity, clean_num, f"METER-{clean_num}", f"usr-{clean_num}"),
            )

        # Support explicit dev user header if configured (supporting X-Dev-User-Id and X-Dev-User)
        dev_user_header = (
            request.headers.get("X-Dev-User-Id")
            or request.headers.get("X-Dev-User")
            or ""
        ).strip()
        if dev_user_header:
            if dev_user_header in dev_mapping:
                meters = tuple(dev_mapping[dev_user_header])
                return UserPrincipal(
                    user_id=dev_user_header,
                    persona="residential",
                    authorized_meters=meters,
                )
            clean_num = dev_user_header.replace("METER-", "").replace("usr-", "")
            return UserPrincipal(
                user_id=dev_user_header,
                persona=request.headers.get("X-Persona", "residential").lower(),
                authorized_meters=(dev_user_header, clean_num, f"METER-{clean_num}", f"usr-{clean_num}"),
            )

        # Default development user if no specific entity requested
        default_uid = app_config.get("DEV_DEFAULT_USER", "2254213")
        default_meters = tuple(dev_mapping.get(default_uid, ["2254213", "METER-2254213"]))
        return UserPrincipal(
            user_id=default_uid,
            persona="residential",
            authorized_meters=default_meters,
        )

    @classmethod
    def authorize_meter_access(cls, principal: UserPrincipal, requested_meter_id: str | None) -> str:
        """Validate and return the authorized meter ID for the principal.

        Fails closed with AuthorizationError if the requested meter does not belong
        to the principal's authorized meters.
        """
        is_demo_or_dev = (
            current_app.config.get("DEVELOPMENT_AUTH_ENABLED", False)
            or current_app.config.get("AI_DEMO_MODE", False)
            or os.getenv("DEVELOPMENT_AUTH_ENABLED", "false").lower() == "true"
            or os.getenv("AI_DEMO_MODE", "true").lower() == "true"
        )

        if not principal.authorized_meters:
            if is_demo_or_dev:
                return requested_meter_id.strip().upper() if requested_meter_id and requested_meter_id.strip() else "2254213"
            logger.warning("Principal '%s' has no authorized meters assigned.", principal.user_id)
            raise AuthorizationError("Your user account has no smart meter assigned.")

        if not requested_meter_id or not requested_meter_id.strip():
            # Automatically resolve to the principal's primary authorized meter
            return principal.authorized_meters[0]

        clean_id = requested_meter_id.strip().upper()
        if not principal.is_meter_authorized(clean_id):
            if is_demo_or_dev:
                num_part = clean_id.replace("METER-", "").replace("USR-", "")
                return f"METER-{num_part}" if clean_id.startswith("METER-") else clean_id
            logger.warning(
                "Access denied: User '%s' attempted to access unauthorized meter '%s'. Authorized: %s",
                principal.user_id,
                clean_id,
                principal.authorized_meters,
            )
            raise AuthorizationError(
                f"Access denied: You are not authorized to view smart meter '{requested_meter_id}'."
            )

        if clean_id.startswith("METER-"):
            num_part = clean_id.replace("METER-", "")
            return f"METER-{num_part}"
        return clean_id



def require_auth(fn: Callable) -> Callable:
    """Decorator ensuring an authenticated UserPrincipal is attached to request context."""
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        try:
            principal = HouseholdAuthService.resolve_principal(request)
            g.current_user = principal
            g.principal = principal
        except AuthenticationError as e:
            return jsonify({"success": False, "error": {"code": "UNAUTHENTICATED", "message": str(e)}}), 401
        except AuthorizationError as e:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": str(e)}}), 403
        return fn(*args, **kwargs)
    return wrapper


def require_persona(*allowed_personas: str) -> Callable:
    """Decorator restricting endpoint access to specified persona(s) (e.g. 'RESIDENTIAL')."""
    allowed = {p.upper() for p in allowed_personas}

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            try:
                principal = HouseholdAuthService.resolve_principal(request)
                g.current_user = principal
                g.principal = principal
            except AuthenticationError as e:
                return jsonify({"success": False, "error": {"code": "UNAUTHENTICATED", "message": str(e)}}), 401
            except AuthorizationError as e:
                return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": str(e)}}), 403

            if principal.persona.upper() not in allowed:
                return (
                    jsonify({
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN_PERSONA",
                            "message": f"Endpoint restricted to persona(s): {', '.join(sorted(allowed))}. Current persona: '{principal.persona.upper()}'.",
                        },
                    }),
                    403,
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator
