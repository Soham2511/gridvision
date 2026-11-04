"""Centralized Authentication & Session Management Service for GridVision.

Handles:
- Bcrypt password hashing & verification.
- Signed JWT access token creation & verification.
- Cryptographically secure refresh token rotation & revocation via user_sessions.
- Case-insensitive username/email registration & login with brute-force rate-limiting.
- Centralized initial residential user seeding mapped to BaseConfig.INITIAL_RESIDENTIAL_OBJECTID.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.config import BaseConfig
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models.user import Meter, User, UserSession, user_meters
from app.services.assistant.auth import AuthenticationError, AuthorizationError

logger = logging.getLogger("gridvision.services.auth")

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")


class AuthenticationService:
    """Centralized service for user authentication, password hashing, and session lifecycle."""

    def __init__(
        self,
        secret_key: Optional[str] = None,
        access_token_expires_seconds: Optional[int] = None,
        refresh_token_expires_days: Optional[int] = None,
    ) -> None:
        self.secret_key = secret_key or BaseConfig.JWT_SECRET_KEY
        self.access_token_expires_seconds = (
            access_token_expires_seconds or BaseConfig.JWT_ACCESS_TOKEN_EXPIRES_SECONDS
        )
        self.refresh_token_expires_days = (
            refresh_token_expires_days or BaseConfig.JWT_REFRESH_TOKEN_EXPIRES_DAYS
        )

    # -------------------------------------------------------------------------
    # Password Hashing & Verification
    # -------------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt with standard salt rounds."""
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify plain password against stored bcrypt hash."""
        if not plain_password or not hashed_password:
            return False
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except Exception as e:
            logger.warning("Bcrypt verification failed with error: %s", e)
            return False

    # -------------------------------------------------------------------------
    # JWT Access Token Management
    # -------------------------------------------------------------------------

    def create_access_token(self, user: User) -> str:
        """Create signed JWT access token carrying trusted claims."""
        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=self.access_token_expires_seconds)

        meters = [m.id for m in user.meters] if user.meters else []

        payload = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "persona": user.persona,
            "role": user.role,
            "meters": meters,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "iss": "gridvision-auth",
        }

        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_access_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate claims of a JWT access token."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                issuer="gridvision-auth",
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Access token has expired.")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid access token: {e}")

    # -------------------------------------------------------------------------
    # Refresh Token & Session Lifecycle (Database-backed)
    # -------------------------------------------------------------------------

    def create_session(
        self,
        session: Session,
        user_id: int,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[str, UserSession]:
        """Generate cryptographically secure refresh token and persist its SHA-256 hash."""
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.utcnow() + timedelta(days=self.refresh_token_expires_days)

        user_session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_revoked=False,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        session.add(user_session)
        session.flush()

        return raw_token, user_session

    def rotate_session(
        self,
        session: Session,
        raw_refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[str, User, UserSession]:
        """Validate existing refresh token, revoke it, and issue a fresh session."""
        if not raw_refresh_token:
            raise AuthenticationError("Refresh token required.")

        token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()
        user_session = (
            session.query(UserSession)
            .filter_by(token_hash=token_hash)
            .first()
        )

        if not user_session:
            raise AuthenticationError("Invalid refresh session.")

        if user_session.is_revoked:
            logger.warning("Revoked session reuse attempt for user_id=%s", user_session.user_id)
            raise AuthenticationError("Session has been revoked.")

        if user_session.expires_at < datetime.utcnow():
            user_session.is_revoked = True
            session.flush()
            raise AuthenticationError("Refresh session has expired.")

        # Revoke existing session (rotation)
        user_session.is_revoked = True
        user_session.last_used_at = datetime.utcnow()

        user = session.query(User).filter_by(id=user_session.user_id).first()
        if not user or not user.is_active:
            raise AuthenticationError("User account is inactive or disabled.")

        # Create new rotated session
        new_token, new_session = self.create_session(
            session=session,
            user_id=user.id,
            user_agent=user_agent or user_session.user_agent,
            ip_address=ip_address or user_session.ip_address,
        )

        return new_token, user, new_session

    def revoke_session(self, session: Session, raw_refresh_token: str) -> None:
        """Revoke a refresh session on logout."""
        if not raw_refresh_token:
            return
        token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()
        user_session = (
            session.query(UserSession)
            .filter_by(token_hash=token_hash)
            .first()
        )
        if user_session:
            user_session.is_revoked = True
            user_session.last_used_at = datetime.utcnow()
            session.flush()

    # -------------------------------------------------------------------------
    # User Registration
    # -------------------------------------------------------------------------

    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        confirm_password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """Register a new residential customer account with strict validation."""
        clean_username = (username or "").strip()
        clean_email = (email or "").strip().lower()

        # 1. Field presence validation
        if not clean_username:
            raise ValueError("Username is mandatory.")
        if not clean_email:
            raise ValueError("Email address is mandatory.")
        if not password:
            raise ValueError("Password is mandatory.")
        if not confirm_password:
            raise ValueError("Password confirmation is mandatory.")

        # 2. Format validation
        if not USERNAME_REGEX.match(clean_username):
            raise ValueError(
                "Username must be 3-50 characters containing only letters, numbers, hyphens, or underscores."
            )
        if not EMAIL_REGEX.match(clean_email):
            raise ValueError("Please provide a valid email address.")

        # 3. Password matching & complexity
        if password != confirm_password:
            raise ValueError("Password and confirm password do not match.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not any(c.isdigit() or not c.isalnum() for c in password):
            raise ValueError("Password must include at least one number or special character.")

        with get_session() as session:
            # 4. Case-insensitive uniqueness validation
            existing_user = (
                session.query(User)
                .filter(
                    (User.username.ilike(clean_username))
                    | (User.email.ilike(clean_email))
                )
                .first()
            )
            if existing_user:
                if existing_user.username.lower() == clean_username.lower():
                    raise ValueError(f"Username '{clean_username}' is already registered.")
                raise ValueError(f"Email '{clean_email}' is already registered.")

            # 5. Create user record and provision initial residential smart meter
            pwd_hash = self.hash_password(password)
            user = User(
                username=clean_username,
                email=clean_email,
                password_hash=pwd_hash,
                persona="RESIDENTIAL",
                role="RESIDENTIAL_USER",
                is_active=True,
            )
            initial_objectid = BaseConfig.INITIAL_RESIDENTIAL_OBJECTID
            meter = session.query(Meter).filter_by(id=initial_objectid).first()
            if not meter:
                meter = Meter(id=initial_objectid)
                session.add(meter)
                session.flush()
            user.meters.append(meter)
            session.add(user)
            session.flush()

            # 6. Issue access token and initial session
            access_token = self.create_access_token(user)
            raw_refresh_token, _ = self.create_session(
                session=session,
                user_id=user.id,
                user_agent=user_agent,
                ip_address=ip_address,
            )

            # Detach user attributes for caller
            user_data = User(
                id=user.id,
                username=user.username,
                email=user.email,
                persona=user.persona,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
            )
            user_data.meters = [Meter(id=m.id) for m in user.meters]
            return user_data, access_token, raw_refresh_token

    # -------------------------------------------------------------------------
    # User Login
    # -------------------------------------------------------------------------

    def login_user(
        self,
        identifier: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """Authenticate user by username or email with rate-limit protection."""
        clean_id = (identifier or "").strip()
        if not clean_id or not password:
            raise AuthenticationError("Username/email and password are required.")

        with get_session() as session:
            # Case-insensitive lookup by username or email
            user = (
                session.query(User)
                .filter(
                    (User.username.ilike(clean_id)) | (User.email.ilike(clean_id))
                )
                .first()
            )

            if not user:
                raise AuthenticationError("Invalid username, email, or password.")

            # Check brute-force lockout
            if user.locked_until and user.locked_until > datetime.utcnow():
                minutes_left = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() / 60))
                raise AuthenticationError(
                    f"Account is temporarily locked due to repeated failed login attempts. Try again in {minutes_left} minutes."
                )

            if not user.is_active:
                raise AuthenticationError("Account has been disabled. Please contact support.")

            # Verify password
            if not self.verify_password(password, user.password_hash):
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                    logger.warning("Account locked for user_id=%s after 5 failed attempts.", user.id)
                session.commit()
                raise AuthenticationError("Invalid username, email, or password.")

            # Reset failed attempts and update last login
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = datetime.utcnow()

            # Ensure residential user has smart meter provisioned
            if user.persona == "RESIDENTIAL" and not user.meters:
                initial_objectid = BaseConfig.INITIAL_RESIDENTIAL_OBJECTID
                meter = session.query(Meter).filter_by(id=initial_objectid).first()
                if not meter:
                    meter = Meter(id=initial_objectid)
                    session.add(meter)
                    session.flush()
                user.meters.append(meter)
                session.flush()

            access_token = self.create_access_token(user)
            raw_refresh_token, _ = self.create_session(
                session=session,
                user_id=user.id,
                user_agent=user_agent,
                ip_address=ip_address,
            )

            # Build detached copy with meters loaded
            meter_list = [Meter(id=m.id) for m in user.meters]
            user_data = User(
                id=user.id,
                username=user.username,
                email=user.email,
                persona=user.persona,
                role=user.role,
                is_active=user.is_active,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
            )
            user_data.meters = meter_list

            return user_data, access_token, raw_refresh_token

    # -------------------------------------------------------------------------
    # Initial Verified Residential Account Seeding (Requirement 8.1)
    # -------------------------------------------------------------------------

    def seed_initial_residential_user(
        self,
        username: str = "resident",
        email: str = "resident@gridvision.local",
        password: str = "GridVision@2026",
    ) -> User:
        """Seed the verified residential user linked to BaseConfig.INITIAL_RESIDENTIAL_OBJECTID."""
        clean_username = username.strip()
        clean_email = email.strip().lower()
        initial_objectid = BaseConfig.INITIAL_RESIDENTIAL_OBJECTID

        with get_session() as session:
            existing = (
                session.query(User)
                .filter(
                    (User.username.ilike(clean_username))
                    | (User.email.ilike(clean_email))
                )
                .first()
            )
            if existing:
                # Ensure meter is linked
                has_meter = any(m.id == initial_objectid for m in existing.meters)
                if not has_meter:
                    meter = session.query(Meter).filter_by(id=initial_objectid).first()
                    if not meter:
                        meter = Meter(id=initial_objectid)
                        session.add(meter)
                        session.flush()
                    existing.meters.append(meter)
                    session.flush()
                return existing

            # Create initial meter if missing
            meter = session.query(Meter).filter_by(id=initial_objectid).first()
            if not meter:
                meter = Meter(id=initial_objectid)
                session.add(meter)
                session.flush()

            pwd_hash = self.hash_password(password)
            user = User(
                username=clean_username,
                email=clean_email,
                password_hash=pwd_hash,
                persona="RESIDENTIAL",
                role="RESIDENTIAL_USER",
                is_active=True,
            )
            user.meters.append(meter)
            session.add(user)
            session.flush()
            logger.info(
                "Provisioned initial residential user '%s' linked to OBJECTID %s",
                clean_username,
                initial_objectid,
            )
            return user


# Singleton instance
auth_service = AuthenticationService()

