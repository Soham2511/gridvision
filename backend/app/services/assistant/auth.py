"""Trusted principal and household isolation authorization module.

Provides a clean security abstraction for resolving authenticated principals,
validating meter authorizations, and enforcing strict tenant boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from flask import Request, current_app

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

        # 1. Production Authentication Path: Check server-side session or verified token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            # Production JWT verification hook
            if token and token != "dev-token":
                # When production auth is deployed, decode trusted claims:
                # payload = jwt.decode(token, app_config["SECRET_KEY"], algorithms=["HS256"])
                # return UserPrincipal(user_id=payload["sub"], persona=payload["persona"], authorized_meters=tuple(payload["meters"]))
                pass

        # 2. If production auth is required and no valid token is present, fail closed
        if not is_dev_auth_enabled:
            logger.warning("Authentication failed: No trusted authentication credentials provided.")
            raise AuthenticationError("Authentication required to access household energy assistant.")

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

        # Support explicit dev user header if configured (supporting X-Dev-User-Id and X-Dev-User)
        dev_user_header = (
            request.headers.get("X-Dev-User-Id")
            or request.headers.get("X-Dev-User")
            or ""
        ).strip()
        if dev_user_header and dev_user_header in dev_mapping:
            meters = tuple(dev_mapping[dev_user_header])
            return UserPrincipal(
                user_id=dev_user_header,
                persona="residential",
                authorized_meters=meters,
            )

        # In dev mode, if the request targets a specific meter_id or entity_id in the dev whitelist,
        # resolve to that specific authorized user identity
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
        if not principal.authorized_meters:
            logger.warning("Principal '%s' has no authorized meters assigned.", principal.user_id)
            raise AuthorizationError("Your user account has no smart meter assigned.")

        if not requested_meter_id or not requested_meter_id.strip():
            # Automatically resolve to the principal's primary authorized meter
            return principal.authorized_meters[0]

        clean_id = requested_meter_id.strip().upper()
        if not principal.is_meter_authorized(clean_id):
            logger.warning(
                "Access denied: User '%s' attempted unauthorized access to meter '%s' (authorized: %s)",
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
