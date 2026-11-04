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
    Column("meter_id", String, primary_key=True),
    UniqueConstraint("meter_id", name="uq_user_meter"),
)

class User(Base):
    """Persistent user entity.

    * `username` – case‑insensitive unique identifier used for login.
    * `email` – unique, stored normalized to lower‑case.
    * `password_hash` – Argon2id hash (never plain text).
    * `persona` – currently fixed to ``RESIDENTIAL`` for all new users.
    * `is_active` – flag for account status.
    * timestamps – for audit and last‑login tracking.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(150), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    persona = Column(String(50), nullable=False, default="RESIDENTIAL")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Relationship to authorized meters (OBJECTIDs)
    meters = relationship(
        "Meter",
        secondary=user_meters,
        back_populates="users",
        cascade="all, delete",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"

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

