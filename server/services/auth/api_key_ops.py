"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

API-key-related operations for DatabaseAuthService.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from database import get_db_session
from db_models import User, UserApiKey
from models.access.api_key_models import ApiKeyCreate, ApiKeyUpdate, ApiKey


def list_api_keys(service, user_id: str) -> List[ApiKey]:
    service._lazy_init()
    with get_db_session() as db:
        keys = db.query(UserApiKey).filter_by(user_id=user_id).order_by(UserApiKey.created_at.asc()).all()
        return [service._to_api_key_schema(k) for k in keys]


def create_api_key(service, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            raise ValueError("User not found")

        key_value = key_create.key or str(uuid.uuid4())
        db.query(UserApiKey).filter(
            UserApiKey.user_id == user_id,
            UserApiKey.is_enabled.is_(True)
        ).update({"is_enabled": False, "updated_at": datetime.now(timezone.utc)})

        api_key = UserApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=key_create.name,
            key=key_value,
            otlp_token=service._generate_otlp_token(),
            is_default=False,
            is_enabled=True
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        return service._to_api_key_schema(api_key)


def update_api_key(service, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=user_id).first()
        if not api_key:
            raise ValueError("API key not found")

        if key_update.name is not None:
            api_key.name = key_update.name

        if key_update.is_default is not None and key_update.is_default:
            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.id != key_id,
                UserApiKey.is_default.is_(True)
            ).update({"is_default": False, "updated_at": datetime.now(timezone.utc)})

            api_key.is_default = True
            api_key.is_enabled = True

            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.id != key_id,
                UserApiKey.is_enabled.is_(True)
            ).update({"is_enabled": False, "updated_at": datetime.now(timezone.utc)})

            user = db.query(User).filter_by(id=user_id).first()
            if user:
                user.org_id = api_key.key
                user.updated_at = datetime.now(timezone.utc)
            db.flush()

        if key_update.is_enabled is not None:
            if api_key.is_default and not key_update.is_enabled:
                raise ValueError("Default key cannot be disabled")
            if not key_update.is_enabled:
                raise ValueError("At least one API key must be enabled")
            api_key.is_enabled = True
            db.flush()
            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.id != key_id,
                UserApiKey.is_enabled.is_(True)
            ).update({"is_enabled": False, "updated_at": datetime.now(timezone.utc)})

        api_key.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(api_key)
        return service._to_api_key_schema(api_key)


def delete_api_key(service, user_id: str, key_id: str) -> bool:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=user_id).first()
        if not api_key:
            return False
        if api_key.is_default:
            raise ValueError("Default key cannot be deleted")

        db.delete(api_key)
        db.flush()

        enabled_count = db.query(UserApiKey).filter_by(user_id=user_id, is_enabled=True).count()
        if enabled_count == 0:
            default_key = db.query(UserApiKey).filter_by(user_id=user_id, is_default=True).first()
            if default_key:
                default_key.is_enabled = True
        db.commit()
        return True


def backfill_otlp_tokens(service):
    with get_db_session() as db:
        keys_without_token = db.query(UserApiKey).filter(
            UserApiKey.otlp_token.is_(None)
        ).all()
        for key in keys_without_token:
            key.otlp_token = service._generate_otlp_token()
            key.updated_at = datetime.now(timezone.utc)
        if keys_without_token:
            db.commit()
            service.logger.info("Backfilled otlp_token for %d API keys", len(keys_without_token))
