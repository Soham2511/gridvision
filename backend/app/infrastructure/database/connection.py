"""SQLAlchemy 2.0 database connection and session management.

Supports dialect-agnostic configuration for SQLite (in-memory or file) and PostgreSQL,
enforcing foreign key constraints for SQLite and strict session lifecycle boundaries.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _get_default_db_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    # Default to sqlite in data directory
    root_dir = Path(__file__).resolve().parents[4]
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "reference.db"
    return f"sqlite:///{db_path.as_posix()}"


def create_db_engine(db_url: Optional[str] = None) -> Engine:
    """Create a configured SQLAlchemy 2.0 Engine."""
    url = db_url or _get_default_db_url()
    is_sqlite = url.startswith("sqlite")
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}

    if is_sqlite:
        connect_args["check_same_thread"] = False
        if ":memory:" in url:
            engine_kwargs["poolclass"] = StaticPool
        # If file-based SQLite, ensure directory exists
        if url.startswith("sqlite:///") and ":memory:" not in url:
            file_part = url.replace("sqlite:///", "")
            file_path = Path(file_part)
            file_path.parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(url, connect_args=connect_args, **engine_kwargs)

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        engine = create_engine(url, pool_pre_ping=True)

    return engine


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def get_engine(db_url: Optional[str] = None) -> Engine:
    """Return the singleton Engine or a new Engine for an explicit db_url."""
    global _engine
    if db_url is not None:
        return create_db_engine(db_url)
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory(target_engine: Optional[Engine] = None) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the given or default engine."""
    global _session_factory
    eng = target_engine or get_engine()
    if target_engine is not None:
        return sessionmaker(autocommit=False, autoflush=False, bind=eng)
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return _session_factory


@contextmanager
def get_session(session_factory: Optional[sessionmaker[Session]] = None) -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit/rollback."""
    factory = session_factory or get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """Dependency provider yielding a Session for web/test integration."""
    with get_session() as session:
        yield session


def init_db(target_engine: Optional[Engine] = None) -> None:
    """Initialize database tables using Declarative Base metadata."""
    from app.infrastructure.database.models.reference import Base

    eng = target_engine or get_engine()
    Base.metadata.create_all(bind=eng)


# Global instances for contract_helper and module consumers
engine: Engine = get_engine()
SessionLocal: sessionmaker[Session] = get_session_factory(engine)
