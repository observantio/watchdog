"""
Database initialization and session management using SQLAlchemy with connection pooling and environment variable configuration for pool settings.

Alerting/incident/rules/channel persistence was moved to BeNotified.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import logging
import os
import threading
from contextlib import contextmanager
from types import TracebackType
from typing import Any, Callable, Generator, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from db_models import Base

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_session_local: Optional[Callable[[], Session]] = None
_init_lock = threading.Lock()


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, v, default)
        return default


def init_database(
    database_url: str,
    echo: bool = False,
    pool_size: Optional[int] = None,
) -> None:
    global _engine, _session_local

    if _engine is not None and _session_local is not None:
        return

    with _init_lock:
        if _engine is not None and _session_local is not None:
            return

        resolved_pool_size = pool_size or _env_int("DB_POOL_SIZE", 10)
        resolved_max_overflow = _env_int("DB_MAX_OVERFLOW", 20)
        resolved_pool_timeout = _env_int("DB_POOL_TIMEOUT", 30)
        resolved_pool_recycle = _env_int("DB_POOL_RECYCLE", 1800)
        engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "echo": echo,
            "future": True,
        }
        if make_url(database_url).get_backend_name() != "sqlite":
            engine_kwargs.update(
                {
                    "pool_size": resolved_pool_size,
                    "max_overflow": resolved_max_overflow,
                    "pool_timeout": resolved_pool_timeout,
                    "pool_recycle": resolved_pool_recycle,
                }
            )

        _engine = create_engine(
            database_url,
            **engine_kwargs,
        )

        _session_local = sessionmaker(
            bind=_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )


def _require_session_factory() -> Callable[[], Session]:
    if _session_local is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _session_local


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = _require_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class _SessionContext:
    def __init__(self) -> None:
        self._session: Optional[Session] = None

    def __enter__(self) -> Session:
        self._session = _require_session_factory()()
        return self._session

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        del exc_val, exc_tb
        if self._session is None:
            return
        try:
            if exc_type is None:
                try:
                    self._session.commit()
                except Exception:
                    self._session.rollback()
                    raise
            else:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None


def get_db_session() -> _SessionContext:
    return _SessionContext()


def get_db() -> Generator[Session, None, None]:
    with get_db_session() as session:
        yield session


def connection_test() -> bool:
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.debug("DB connection test failed: %s", exc, exc_info=True)
        return False


def dispose_database() -> None:
    global _engine, _session_local
    with _init_lock:
        _session_local = None
        if _engine is not None:
            try:
                _engine.dispose()
            finally:
                _engine = None


def init_db() -> None:
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    Base.metadata.create_all(bind=_engine)
