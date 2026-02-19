"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from ipaddress import ip_network, ip_address
import os

from sqlalchemy import Boolean, Column, ForeignKey, String, create_engine, text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://beobservant:changeme123@localhost:5432/beobservant",
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)
    is_active = Column(Boolean, nullable=False, default=True)


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    otlp_token = Column(String, nullable=True, unique=True, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True)

    user = relationship("User")


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def _validate_schema_compatibility(db: Session) -> None:
    """Raise RuntimeError when required DB schema is missing.

    Kept from the original `main.py` to preserve early startup checks.
    """
    required = [
        ("users", "id"),
        ("users", "is_active"),
        ("users", "tenant_id"),
        ("tenants", "id"),
        ("tenants", "is_active"),
        ("user_api_keys", "otlp_token"),
        ("user_api_keys", "key"),
        ("user_api_keys", "is_enabled"),
        ("user_api_keys", "user_id"),
    ]

    for table, column in required:
        exists_stmt = text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        )
        row = db.execute(exists_stmt, {"table_name": table, "column_name": column}).scalar()
        if not row:
            raise RuntimeError(f"Missing required DB schema: {table}.{column}")
