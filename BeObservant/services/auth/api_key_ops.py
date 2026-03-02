"""
Api key management operations for creating, updating, deleting, rotating, and sharing API keys, as well as backfilling missing OTLP tokens for existing keys.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, cast

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from database import get_db_session
from db_models import ApiKeyShare, Group, User, UserApiKey
from models.access.api_key_models import ApiKey, ApiKeyCreate, ApiKeyShareUser, ApiKeyUpdate

BACKFILL_BATCH_SIZE = 500
ORG_SCOPE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_scope_key(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        raise ValueError("API key value cannot be blank")
    if not ORG_SCOPE_KEY_RE.fullmatch(value):
        raise ValueError(
            "API key value must be 3-200 chars and contain only letters, numbers, dot, underscore, hyphen, or colon"
        )
    return value


def _require_user(db, user_id: str) -> User:
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError("User not found")
    return user


def _require_user_in_tenant(db, user_id: str, tenant_id: str) -> User:
    user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
    if not user:
        raise ValueError("User not found")
    return user


def _require_api_key_in_tenant(db, key_id: str, tenant_id: str) -> UserApiKey:
    api_key = db.query(UserApiKey).filter_by(id=key_id, tenant_id=tenant_id).first()
    if not api_key:
        raise ValueError("API key not found")
    return api_key


def _disable_other_enabled_keys(
    db, user_id: str, tenant_id: str, now: datetime, exclude_key_id: Optional[str] = None
) -> None:
    q = db.query(UserApiKey).filter(
        UserApiKey.user_id == user_id,
        UserApiKey.tenant_id == tenant_id,
        UserApiKey.is_enabled.is_(True),
    )
    if exclude_key_id is not None:
        q = q.filter(UserApiKey.id != exclude_key_id)
    q.update({"is_enabled": False, "updated_at": now})


def _set_org_id(user: User, new_org_id: Optional[str], now: datetime) -> None:
    if new_org_id is None:
        return
    if str(user.org_id or "") != str(new_org_id or ""):
        user.org_id = new_org_id
        user.updated_at = now


def _api_key_to_schema(
    api_key: UserApiKey,
    is_shared: bool,
    can_use: bool,
    viewer_enabled: bool,
    revealed_otlp_token: Optional[str] = None,
) -> ApiKey:
    shared_with: List[ApiKeyShareUser] = []
    if not is_shared:
        for share in (getattr(api_key, "shares", None) or []):
            shared_user = getattr(share, "shared_user", None)
            shared_with.append(
                ApiKeyShareUser(
                    user_id=str(getattr(share, "shared_user_id", "")),
                    username=getattr(shared_user, "username", None),
                    email=getattr(shared_user, "email", None),
                    can_use=bool(getattr(share, "can_use", True)),
                    created_at=cast(datetime, getattr(share, "created_at")),
                )
            )

    owner_username = getattr(getattr(api_key, "user", None), "username", None)

    if is_shared:
        otlp_token_value = None
    else:
        otlp_token_value = (
            revealed_otlp_token if revealed_otlp_token is not None else getattr(api_key, "otlp_token", None)
        )

    payload = {
        "id": getattr(api_key, "id", None),
        "name": getattr(api_key, "name", None),
        "key": getattr(api_key, "key", None),
        "otlp_token": otlp_token_value,
        "owner_user_id": getattr(api_key, "user_id", None),
        "owner_username": owner_username,
        "is_shared": is_shared,
        "can_use": can_use,
        "shared_with": [s.model_dump() if hasattr(s, "model_dump") else s for s in shared_with],
        "is_default": bool(getattr(api_key, "is_default", False)),
        "is_enabled": bool(viewer_enabled),
        "created_at": getattr(api_key, "created_at", None),
        "updated_at": getattr(api_key, "updated_at", None),
    }
    return ApiKey.model_validate(payload)


def list_api_keys(service, user_id: str) -> List[ApiKey]:
    service._lazy_init()
    with get_db_session() as db:
        viewer = db.query(User).filter_by(id=user_id).first()
        if not viewer:
            return []

        own_keys = (
            db.query(UserApiKey)
            .options(joinedload(UserApiKey.shares).joinedload(ApiKeyShare.shared_user), joinedload(UserApiKey.user))
            .filter(UserApiKey.user_id == user_id, UserApiKey.tenant_id == viewer.tenant_id)
            .order_by(UserApiKey.created_at.asc())
            .all()
        )

        shared_links = (
            db.query(ApiKeyShare)
            .options(
                joinedload(ApiKeyShare.api_key).joinedload(UserApiKey.shares).joinedload(ApiKeyShare.shared_user),
                joinedload(ApiKeyShare.api_key).joinedload(UserApiKey.user),
            )
            .filter(ApiKeyShare.shared_user_id == user_id, ApiKeyShare.tenant_id == viewer.tenant_id)
            .all()
        )

        output: List[ApiKey] = []
        seen_ids = set()
        has_enabled_owned_key = any(bool(getattr(k, "is_enabled", False)) for k in own_keys)

        for key in own_keys:
            output.append(
                _api_key_to_schema(
                    key,
                    is_shared=False,
                    can_use=True,
                    viewer_enabled=bool(getattr(key, "is_enabled", False)),
                )
            )
            seen_ids.add(getattr(key, "id", None))

        for link in shared_links:
            key = getattr(link, "api_key", None)
            if not key:
                continue
            key_id = getattr(key, "id", None)
            if key_id in seen_ids:
                continue

            can_use = bool(getattr(link, "can_use", True))
            viewer_enabled = bool(
                can_use
                and (not has_enabled_owned_key)
                and (str(viewer.org_id or "") == str(getattr(key, "key", None) or ""))
            )

            output.append(_api_key_to_schema(key, is_shared=True, can_use=can_use, viewer_enabled=viewer_enabled))
            seen_ids.add(key_id)

        output.sort(key=lambda item: item.created_at)
        return output


def create_api_key(service, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        user = _require_user_in_tenant(db, user_id, tenant_id)

        requested_key = _normalize_scope_key(key_create.key)
        if requested_key:
            existing = db.query(UserApiKey).filter(UserApiKey.key == requested_key).first()
            if existing and str(existing.tenant_id) != str(tenant_id):
                raise ValueError("API key value is already assigned to another tenant")
            if existing and str(existing.tenant_id) == str(tenant_id):
                raise ValueError("API key value already exists in this tenant")
            key_value = requested_key
        else:
            while True:
                candidate = str(uuid.uuid4())
                if not db.query(UserApiKey.id).filter(UserApiKey.key == candidate).first():
                    key_value = candidate
                    break

        now = _utcnow()
        _disable_other_enabled_keys(db, user_id=user_id, tenant_id=tenant_id, now=now)

        raw_otlp_token = service._generate_otlp_token()
        api_key = UserApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=key_create.name,
            key=key_value,
            otlp_token=None,
            otlp_token_hash=service._hash_otlp_token(raw_otlp_token),
            is_default=False,
            is_enabled=True,
        )
        db.add(api_key)

        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ValueError("API key value already exists in this tenant")

        user.org_id = api_key.key
        user.updated_at = now

        service._log_audit(
            db,
            tenant_id,
            user_id,
            "api_key.create",
            "api_keys",
            api_key.id,
            {"name": api_key.name},
        )
        db.commit()
        db.refresh(api_key)

        return _api_key_to_schema(
            api_key,
            is_shared=False,
            can_use=True,
            viewer_enabled=True,
            revealed_otlp_token=raw_otlp_token,
        )


def update_api_key(service, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        viewer = _require_user(db, user_id)
        api_key = _require_api_key_in_tenant(db, key_id, viewer.tenant_id)

        is_owner = str(getattr(api_key, "user_id", "")) == str(user_id)

        if not is_owner:
            share_link = (
                db.query(ApiKeyShare)
                .filter_by(
                    api_key_id=key_id,
                    shared_user_id=user_id,
                    can_use=True,
                    tenant_id=viewer.tenant_id,
                )
                .first()
            )
            if not share_link:
                raise ValueError("API key not found")

            requested_fields = key_update.model_dump(exclude_unset=True)
            if set(requested_fields.keys()) - {"is_enabled"}:
                raise ValueError("Shared API keys can only be selected as active")
            if key_update.is_enabled is not True:
                raise ValueError("Shared API key selection requires is_enabled=true")

            now = _utcnow()
            _disable_other_enabled_keys(db, user_id=user_id, tenant_id=viewer.tenant_id, now=now)

            _set_org_id(viewer, getattr(api_key, "key", None), now)
            db.flush()

            service._log_audit(
                db,
                viewer.tenant_id,
                user_id,
                "api_key.use_shared",
                "api_keys",
                api_key.id,
                {"owner_user_id": api_key.user_id, "name": api_key.name},
            )
            db.commit()
            db.refresh(api_key)
            return _api_key_to_schema(api_key, is_shared=True, can_use=True, viewer_enabled=True)

        now = _utcnow()

        if key_update.name is not None:
            api_key.name = key_update.name

        if key_update.is_default is not None and key_update.is_default:
            has_shares = (
                db.query(ApiKeyShare)
                .filter(ApiKeyShare.api_key_id == key_id, ApiKeyShare.tenant_id == viewer.tenant_id)
                .first()
                is not None
            )
            if has_shares:
                raise ValueError("Shared keys cannot be set as default. Remove shares first")

            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.tenant_id == viewer.tenant_id,
                UserApiKey.id != key_id,
                UserApiKey.is_default.is_(True),
            ).update({"is_default": False, "updated_at": now})

            _disable_other_enabled_keys(
                db,
                user_id=user_id,
                tenant_id=viewer.tenant_id,
                now=now,
                exclude_key_id=key_id,
            )

            api_key.is_default = True
            api_key.is_enabled = True

            owner = db.query(User).filter_by(id=user_id).first()
            if owner:
                _set_org_id(owner, getattr(api_key, "key", None), now)
            db.flush()

        if key_update.is_enabled is not None:
            if bool(getattr(api_key, "is_default", False)) and not key_update.is_enabled:
                raise ValueError("Default key cannot be disabled")
            if not key_update.is_enabled:
                raise ValueError("At least one API key must be enabled")

            _disable_other_enabled_keys(
                db,
                user_id=user_id,
                tenant_id=viewer.tenant_id,
                now=now,
                exclude_key_id=key_id,
            )
            api_key.is_enabled = True
            _set_org_id(viewer, getattr(api_key, "key", None), now)

        api_key.updated_at = now

        service._log_audit(
            db,
            api_key.tenant_id,
            user_id,
            "api_key.update",
            "api_keys",
            api_key.id,
            key_update.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(api_key)

        return _api_key_to_schema(api_key, is_shared=False, can_use=True, viewer_enabled=bool(api_key.is_enabled))


def regenerate_api_key_otlp_token(service, user_id: str, key_id: str) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        viewer = _require_user(db, user_id)
        api_key = _require_api_key_in_tenant(db, key_id, viewer.tenant_id)

        if str(getattr(api_key, "user_id", "")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to rotate API key token")
        if bool(getattr(api_key, "is_default", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Default key OTLP token cannot be regenerated",
            )

        now = _utcnow()
        raw_otlp_token = service._generate_otlp_token()
        api_key.otlp_token_hash = service._hash_otlp_token(raw_otlp_token)
        api_key.otlp_token = None
        api_key.updated_at = now

        service._log_audit(
            db,
            api_key.tenant_id,
            user_id,
            "api_key.rotate_otlp_token",
            "api_keys",
            api_key.id,
            {"name": api_key.name},
        )
        db.commit()
        db.refresh(api_key)

        return _api_key_to_schema(
            api_key,
            is_shared=False,
            can_use=True,
            viewer_enabled=bool(api_key.is_enabled),
            revealed_otlp_token=raw_otlp_token,
        )


def delete_api_key(service, user_id: str, key_id: str) -> bool:
    service._lazy_init()
    with get_db_session() as db:
        viewer = db.query(User).filter_by(id=user_id).first()
        if not viewer:
            return False

        api_key = (
            db.query(UserApiKey)
            .filter(UserApiKey.id == key_id, UserApiKey.tenant_id == viewer.tenant_id)
            .first()
        )
        if not api_key:
            return False

        if str(getattr(api_key, "user_id", "")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete API key")
        if bool(getattr(api_key, "is_default", False)):
            raise ValueError("Default key cannot be deleted")

        db.delete(api_key)
        db.flush()

        enabled_count = (
            db.query(UserApiKey)
            .filter(
                UserApiKey.user_id == user_id,
                UserApiKey.tenant_id == api_key.tenant_id,
                UserApiKey.is_enabled.is_(True),
            )
            .count()
        )
        if enabled_count == 0:
            default_key = (
                db.query(UserApiKey)
                .filter(
                    UserApiKey.user_id == user_id,
                    UserApiKey.tenant_id == api_key.tenant_id,
                    UserApiKey.is_default.is_(True),
                )
                .first()
            )
            if default_key:
                default_key.is_enabled = True
                default_key.updated_at = _utcnow()

        service._log_audit(
            db,
            api_key.tenant_id,
            user_id,
            "api_key.delete",
            "api_keys",
            key_id,
            {"name": api_key.name},
        )
        db.commit()
        return True


def list_api_key_shares(service, owner_user_id: str, tenant_id: str, key_id: str) -> List[ApiKeyShareUser]:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        shares = (
            db.query(ApiKeyShare)
            .options(joinedload(ApiKeyShare.shared_user))
            .filter(ApiKeyShare.api_key_id == key_id, ApiKeyShare.tenant_id == tenant_id)
            .all()
        )

        return [
            ApiKeyShareUser(
                user_id=str(getattr(share, "shared_user_id", "")),
                username=getattr(getattr(share, "shared_user", None), "username", None),
                email=getattr(getattr(share, "shared_user", None), "email", None),
                can_use=bool(getattr(share, "can_use", True)),
                created_at=cast(datetime, getattr(share, "created_at")),
            )
            for share in shares
        ]


def replace_api_key_shares(
    service,
    owner_user_id: str,
    tenant_id: str,
    key_id: str,
    user_ids: List[str],
    group_ids: Optional[List[str]] = None,
) -> List[ApiKeyShareUser]:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        normalized_user_ids = list(
            dict.fromkeys(
                uid.strip()
                for uid in (user_ids or [])
                if uid and uid.strip() and uid.strip() != owner_user_id
            )
        )

        normalized_group_ids = [gid.strip() for gid in (group_ids or []) if gid and gid.strip()]
        member_user_ids_from_groups: List[str] = []

        if normalized_group_ids:
            groups = (
                db.query(Group)
                .options(joinedload(Group.members))
                .filter(
                    Group.tenant_id == tenant_id,
                    Group.id.in_(normalized_group_ids),
                    Group.is_active.is_(True),
                )
                .all()
            )
            found_group_ids = {str(g.id) for g in groups}
            missing_groups = sorted(set(normalized_group_ids) - found_group_ids)
            if missing_groups:
                raise ValueError("Invalid share groups: " + ", ".join(missing_groups))

            owner_group_ids = {
                str(g.id)
                for g in groups
                if any(str(getattr(m, "id", "")) == owner_user_id for m in (getattr(g, "members", None) or []))
            }
            unauthorized = sorted(found_group_ids - owner_group_ids)
            if unauthorized:
                raise ValueError("You can only share with groups you are in: " + ", ".join(unauthorized))

            for group in groups:
                for member in (getattr(group, "members", None) or []):
                    if (
                        str(getattr(member, "id", "")) != owner_user_id
                        and bool(getattr(member, "is_active", False))
                        and str(getattr(member, "tenant_id", "")) == str(tenant_id)
                    ):
                        member_user_ids_from_groups.append(str(getattr(member, "id", "")))

        combined_user_ids = list(dict.fromkeys([*normalized_user_ids, *member_user_ids_from_groups]))

        if bool(getattr(api_key, "is_default", False)) and combined_user_ids:
            raise ValueError("Default key cannot be shared")

        if combined_user_ids:
            allowed_users = (
                db.query(User)
                .filter(User.tenant_id == tenant_id, User.id.in_(combined_user_ids), User.is_active.is_(True))
                .all()
            )
            allowed_user_ids = {str(u.id) for u in allowed_users}
            missing = sorted(set(combined_user_ids) - allowed_user_ids)
            if missing:
                raise ValueError("Invalid share users: " + ", ".join(missing))

        db.query(ApiKeyShare).filter(
            ApiKeyShare.api_key_id == key_id, ApiKeyShare.tenant_id == tenant_id
        ).delete(synchronize_session=False)

        now = _utcnow()
        for shared_user_id in combined_user_ids:
            db.add(
                ApiKeyShare(
                    tenant_id=tenant_id,
                    api_key_id=key_id,
                    owner_user_id=owner_user_id,
                    shared_user_id=shared_user_id,
                    can_use=True,
                    created_at=now,
                )
            )

        service._log_audit(
            db,
            tenant_id,
            owner_user_id,
            "api_key.share",
            "api_keys",
            key_id,
            {"shared_user_ids": combined_user_ids, "shared_group_ids": normalized_group_ids},
        )
        db.commit()

    return list_api_key_shares(service, owner_user_id, tenant_id, key_id)


def delete_api_key_share(service, owner_user_id: str, tenant_id: str, key_id: str, shared_user_id: str) -> bool:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        share = (
            db.query(ApiKeyShare)
            .filter(
                ApiKeyShare.api_key_id == key_id,
                ApiKeyShare.shared_user_id == shared_user_id,
                ApiKeyShare.tenant_id == tenant_id,
            )
            .first()
        )
        if not share:
            return False

        db.delete(share)
        service._log_audit(
            db,
            tenant_id,
            owner_user_id,
            "api_key.unshare",
            "api_keys",
            key_id,
            {"shared_user_id": shared_user_id},
        )
        db.commit()
        return True


def backfill_otlp_tokens(service) -> None:
    service._lazy_init()
    with get_db_session() as db:
        total = 0
        while True:
            batch = (
                db.query(UserApiKey)
                .filter(UserApiKey.otlp_token_hash.is_(None))
                .order_by(UserApiKey.id.asc())
                .limit(BACKFILL_BATCH_SIZE)
                .all()
            )
            if not batch:
                break

            now = _utcnow()
            for key in batch:
                source_token = getattr(key, "otlp_token", None) or service._generate_otlp_token()
                key.otlp_token_hash = service._hash_otlp_token(source_token)
                key.otlp_token = None
                key.updated_at = now

            db.commit()
            total += len(batch)

        if total:
            service.logger.info("Backfilled otlp_token_hash for %d API keys", total)