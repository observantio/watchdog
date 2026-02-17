"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Database configuration and session management.

Optimizations added:
- idempotent initialization and env-driven pool tuning
- per-request `sessionmaker` sessions for async-safe request isolation
- `session.begin()` for clear transaction boundaries
- connection_test() for health/readiness probes
- dispose_database() for graceful shutdown
"""
import logging
import os
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    from db_models import Base
except ImportError:
    Base = declarative_base()

_engine: Optional[object] = None
_SessionLocal: Optional[sessionmaker] = None


def init_database(database_url: str, echo: bool = False, pool_size: Optional[int] = None) -> None:
    """Initialize database engine and session factory (idempotent).

    Pool and other parameters may be tuned via environment variables:
      - DB_POOL_SIZE
      - DB_MAX_OVERFLOW
      - DB_POOL_TIMEOUT
      - DB_POOL_RECYCLE
    """
    global _engine, _SessionLocal

    if _engine is not None:
        logger.debug("Database already initialized; skipping re-init.")
        return

    pool_size = pool_size or int(os.getenv("DB_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    _engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=echo,
        future=True,
    )

    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=_engine,
        future=True,
    )


@contextmanager
def get_db_session() -> Session:
    """Context-managed DB session.

    This yields a plain Session and mirrors the original commit/rollback
    semantics so existing callers that `db.commit()` manually continue to
    work without change.

    Usage:
        with get_db_session() as db:
            ...
    Commits on successful exit, rolls back on exception.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency that yields a transactional session.

    Maintains the same commit/rollback behavior as `get_db_session` so
    route handlers don't need to be modified.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db: Session = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def connection_test(timeout_seconds: int = 5) -> bool:
    """Quick DB connectivity check for health/readiness probes."""
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc: 
        logger.debug("DB connection test failed: %s", exc)
        return False


def dispose_database() -> None:
    """Dispose engine and clear session factory (call on application shutdown)."""
    global _engine, _SessionLocal
    if _SessionLocal is not None:
        try:
            _SessionLocal = None
        except Exception:
            logger.debug("Session factory cleanup raised during dispose", exc_info=True)

    if _engine is not None:
        try:
            _engine.dispose()
        finally:
            _engine = None


def init_db() -> None:
    """Create database tables from SQLAlchemy models (idempotent)."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    from config import config
    if not config.DB_AUTO_CREATE_SCHEMA:
        logger.info("Skipping Base.metadata.create_all because DB_AUTO_CREATE_SCHEMA=false")
        return

    from db_models import Base  

    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=_engine)
    logger.info("Database tables created successfully")


