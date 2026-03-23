"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, Permission, Tenant, User
from services.database_auth import bootstrap as mod


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_ensure_permissions_is_idempotent():
    db = _session()
    mod.ensure_permissions(db)
    first_count = db.query(Permission).count()
    assert first_count > 0
    mod.ensure_permissions(db)
    second_count = db.query(Permission).count()
    assert second_count == first_count


def test_ensure_default_setup_creates_tenant_and_admin_when_missing(monkeypatch):
    db = _session()
    logs = []
    service = SimpleNamespace(
        hash_password=lambda text: f"hashed:{text}",
        logger=SimpleNamespace(info=lambda *args, **kwargs: logs.append(args), warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
    )

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(mod, "get_db_session", fake_session)
    monkeypatch.setattr(mod, "_pg_advisory_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_pg_advisory_unlock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_user_security_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_grafana_folder_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_api_key_constraints", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_backfill_password_changed_at", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "ensure_default_api_key", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED", True, raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_TENANT", "Default Tenant", raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_USERNAME", "admin", raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com", raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_PASSWORD", "supersecurepassword1!", raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ORG_ID", "org-default", raising=False)

    mod.ensure_default_setup(service)

    assert db.query(Tenant).filter_by(name="Default Tenant").first() is not None
    admin = db.query(User).filter_by(username="admin").first()
    assert admin is not None
    assert str(getattr(admin, "hashed_password", "")).startswith("hashed:")
