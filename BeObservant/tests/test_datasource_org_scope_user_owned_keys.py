"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
"""

import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import ApiKeyShare, Base, Tenant, User, UserApiKey
from services.grafana import datasource_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_resolve_datasource_org_scope_allows_user_owned_disabled_key():
    db = _session()
    db.add_all(
        [
            Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
            User(
                id="u1",
                tenant_id="t1",
                username="owner",
                email="owner@example.com",
                hashed_password="x",
                org_id="org-default",
                is_active=True,
            ),
            UserApiKey(
                id="k1",
                tenant_id="t1",
                user_id="u1",
                name="disabled-key",
                key="org-disabled-owned",
                is_default=False,
                is_enabled=False,
            ),
        ]
    )
    db.commit()

    resolved = datasource_ops._resolve_datasource_org_scope(
        db,
        requested_org_id="org-disabled-owned",
        user_id="u1",
        tenant_id="t1",
    )
    assert resolved == "org-disabled-owned"


def test_resolve_datasource_org_scope_rejects_unknown_key():
    db = _session()
    db.add_all(
        [
            Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
            User(
                id="u1",
                tenant_id="t1",
                username="owner",
                email="owner@example.com",
                hashed_password="x",
                org_id="org-default",
                is_active=True,
            ),
        ]
    )
    db.commit()

    with pytest.raises(HTTPException) as exc:
        datasource_ops._resolve_datasource_org_scope(
            db,
            requested_org_id="org-unknown",
            user_id="u1",
            tenant_id="t1",
        )
    assert exc.value.status_code == 403


def test_resolve_datasource_org_scope_allows_shared_key_without_activation():
    db = _session()
    db.add_all(
        [
            Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
            User(
                id="owner",
                tenant_id="t1",
                username="owner",
                email="owner@example.com",
                hashed_password="x",
                org_id="org-owner",
                is_active=True,
            ),
            User(
                id="viewer",
                tenant_id="t1",
                username="viewer",
                email="viewer@example.com",
                hashed_password="x",
                org_id="org-viewer-default",
                is_active=True,
            ),
            UserApiKey(
                id="k-shared",
                tenant_id="t1",
                user_id="owner",
                name="shared-key",
                key="org-shared",
                is_default=False,
                is_enabled=False,
            ),
            ApiKeyShare(
                id="share-1",
                tenant_id="t1",
                api_key_id="k-shared",
                owner_user_id="owner",
                shared_user_id="viewer",
                can_use=True,
            ),
        ]
    )
    db.commit()

    resolved = datasource_ops._resolve_datasource_org_scope(
        db,
        requested_org_id="org-shared",
        user_id="viewer",
        tenant_id="t1",
    )
    assert resolved == "org-shared"
