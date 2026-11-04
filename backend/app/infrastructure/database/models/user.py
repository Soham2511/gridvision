"""User model for GridVision authentication.

This file introduces a persistent user table required for the new
centralized authentication layer.  It purposefully contains only the
fields needed for the current residential persona and does **not**
alter any existing business‑logic tables.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Table, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from . import Base  # Assuming Base is exported from infrastructure/database/models/__init__.py

# Association table linking users to authorized meters/OBJECTIDs
user_meters = Table(
    "user_meters",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("meter_id", String, ForeignKey("meters.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    """Persistent user entity.

    * `username` – case‑insensitive unique identifier used for login.
    * `email` – unique, stored normalized to lower‑case.
    * `password_hash` – secure password hash (never plain text).
    * `persona` – currently fixed to ``RESIDENTIAL`` for all new users.
    * `role` – authorization role (default ``RESIDENTIAL_USER``).
    * `is_active` – flag for account status.
    * timestamps – for audit and last‑login tracking.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(150), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    persona = Column(String(50), nullable=False, default="RESIDENTIAL")
    role = Column(String(50), nullable=False, default="RESIDENTIAL_USER")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)

    # Relationship to authorized meters (OBJECTIDs)
    meters = relationship(
        "Meter",
        secondary=user_meters,
        back_populates="users",
        cascade="all, delete",
    )

    # Relationship to active sessions
    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class UserSession(Base):
    """Persistent user session / refresh token record for token rotation and revocation."""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(100), nullable=True)

    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id} revoked={self.is_revoked}>"

class Meter(Base):
    """Simple representation of a household OBJECTID / meter.

    The table may already exist elsewhere; if not, this model creates a
    lightweight catalogue that can be populated with existing OBJECTIDs.
    """

    __tablename__ = "meters"

    id = Column(String, primary_key=True)  # e.g. "2254213" or "METER-2254213"
    # Additional metadata can be added later without affecting current logic.

    users = relationship(
        "User",
        secondary=user_meters,
        back_populates="meters",
    )

    def __repr__(self) -> str:
        return f"<Meter id={self.id}>"

