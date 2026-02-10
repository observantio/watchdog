"""Database configuration and session management."""
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    from db_models import Base
except ImportError:
    Base = declarative_base()

_engine = None
_SessionLocal = None


def init_database(database_url: str, echo: bool = False):
    """Initialize database engine and session factory."""
    global _engine, _SessionLocal
    
    _engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=echo
    )
    
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=_engine)


@contextmanager
def get_db_session() -> Session:
    """Get database session with automatic cleanup."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency for database sessions.

    Mirrors the commit / rollback semantics of ``get_db_session`` so that
    callers don't need to manually commit.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    from db_models import Base
    
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=_engine)
    logger.info("Database tables created successfully")
