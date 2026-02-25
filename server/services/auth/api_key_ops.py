"""
Api key management operations for creating, updating, deleting, and sharing API keys, as well as backfilling missing OTLP tokens for existing keys.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, cast

from sqlalchemy.orm import joinedload
from fastapi import HTTPException, status

from database import get_db_session
from db_models import User, UserApiKey, ApiKeyShare, Group
from models.access.api_key_models import ApiKeyCreate, ApiKeyUpdate, ApiKey, ApiKeyShareUser

_BACKFILL_BATCH_SIZE = 500


def _api_key_to_schema(
    service,
    api_key: UserApiKey,
    viewer: User,
    *,
    is_shared: bool,
    can_use: bool,
    viewer_enabled: bool,
) -> ApiKey:
    shared_with = []
    if not is_shared:
        for share in (getattr(api_key, "shares", None) or []):
            shared_user = getattr(share, "shared_user", None)
            shared_with.append(ApiKeyShareUser(
                user_id=str(getattr(share, 'shared_user_id', '')),
                username=getattr(shared_user, "username", None),
                email=getattr(shared_user, "email", None),
                can_use=bool(getattr(share, "can_use", True)),
                created_at=cast(datetime, getattr(share, 'created_at')),
            ))
    owner_username = getattr(getattr(api_key, "user", None), "username", None)
    payload = {
        "id": getattr(api_key, "id", None),
        "name": getattr(api_key, "name", None),
        "key": getattr(api_key, "key", None),
        "otlp_token": (None if is_shared else getattr(api_key, "otlp_token", None)),
        "owner_user_id": getattr(api_key, "user_id", None),
        "owner_username": owner_username,
        "is_shared": is_shared,
        "can_use": can_use,
        "shared_with": [s.model_dump() if hasattr(s, 'model_dump') else s for s in shared_with],
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
            .options(joinedload(UserApiKey.shares).joinedload(ApiKeyShare.shared_user))
            .filter(UserApiKey.user_id == user_id)
            .order_by(UserApiKey.created_at.asc())
            .all()
        )

        shared_links = (
            db.query(ApiKeyShare)
            .options(
                joinedload(ApiKeyShare.api_key)
                .joinedload(UserApiKey.shares)
                .joinedload(ApiKeyShare.shared_user)
            )
            .filter(ApiKeyShare.shared_user_id == user_id)
            .all()
        )

        output: List[ApiKey] = []
        seen_ids = set()

        for key in own_keys:
            output.append(_api_key_to_schema(
                service, key, viewer,
                is_shared=False,
                can_use=True,
                viewer_enabled=bool(key.is_enabled),
            ))
            seen_ids.add(key.id)

        for link in shared_links:
            key = link.api_key
            if not key or key.id in seen_ids:
                continue
            output.append(_api_key_to_schema(
                service, key, viewer,
                is_shared=True,
                can_use=bool(link.can_use),
                viewer_enabled=(str(viewer.org_id or "") == str(key.key or "")),
            ))
            seen_ids.add(key.id)

        output.sort(key=lambda item: item.created_at)
        return output


def create_api_key(service, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            raise ValueError("User not found")

        key_value = key_create.key or str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        db.query(UserApiKey).filter(
            UserApiKey.user_id == user_id,
            UserApiKey.is_enabled.is_(True),
        ).update({"is_enabled": False, "updated_at": now})

        api_key = UserApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=key_create.name,
            key=key_value,
            otlp_token=service._generate_otlp_token(),
            is_default=False,
            is_enabled=True,
        )
        db.add(api_key)
        db.flush()

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
        return _api_key_to_schema(service, api_key, user, is_shared=False, can_use=True, viewer_enabled=True)


def update_api_key(service, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
    service._lazy_init()
    with get_db_session() as db:
        viewer = db.query(User).filter_by(id=user_id).first()
        if not viewer:
            raise ValueError("User not found")

        api_key = db.query(UserApiKey).filter_by(id=key_id).first()
        if not api_key:
            raise ValueError("API key not found")

        is_owner = api_key.user_id == user_id

        if not is_owner:
            share_link = db.query(ApiKeyShare).filter_by(
                api_key_id=key_id, shared_user_id=user_id, can_use=True
            ).first()
            if not share_link:
                raise ValueError("API key not found")

            requested_fields = key_update.model_dump(exclude_unset=True)
            if set(requested_fields.keys()) - {"is_enabled"}:
                raise ValueError("Shared API keys can only be selected as active")
            if key_update.is_enabled is not True:
                raise ValueError("Shared API key selection requires is_enabled=true")

            now = datetime.now(timezone.utc)
            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.is_enabled.is_(True),
            ).update({"is_enabled": False, "updated_at": now})

            if str(viewer.org_id or "") != str(api_key.key or ""):
                viewer.org_id = api_key.key
                viewer.updated_at = now

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
            return _api_key_to_schema(service, api_key, viewer, is_shared=True, can_use=True, viewer_enabled=True)

        now = datetime.now(timezone.utc)

        if key_update.name is not None:
            api_key.name = key_update.name

        if key_update.is_default is not None and key_update.is_default:
            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.id != key_id,
                UserApiKey.is_default.is_(True),
            ).update({"is_default": False, "updated_at": now})

            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.id != key_id,
                UserApiKey.is_enabled.is_(True),
            ).update({"is_enabled": False, "updated_at": now})

            api_key.is_default = True
            api_key.is_enabled = True

            user = db.query(User).filter_by(id=user_id).first()
            if user:
                user.org_id = api_key.key
                user.updated_at = now
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
                UserApiKey.is_enabled.is_(True),
            ).update({"is_enabled": False, "updated_at": now})

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
        return _api_key_to_schema(service, api_key, viewer, is_shared=False, can_use=True, viewer_enabled=bool(api_key.is_enabled))


def delete_api_key(service, user_id: str, key_id: str) -> bool:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id).first()
        if not api_key:
            return False

        if api_key.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete API key")

        if api_key.is_default:
            raise ValueError("Default key cannot be deleted")

        db.delete(api_key)
        db.flush()

        enabled_count = db.query(UserApiKey).filter_by(user_id=user_id, is_enabled=True).count()
        if enabled_count == 0:
            default_key = db.query(UserApiKey).filter_by(user_id=user_id, is_default=True).first()
            if default_key:
                default_key.is_enabled = True

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
            .filter_by(api_key_id=key_id)
            .all()
        )
        return [
            ApiKeyShareUser(
                user_id=str(getattr(share, 'shared_user_id', '')),
                username=getattr(share.shared_user, "username", None),
                email=getattr(share.shared_user, "email", None),
                can_use=bool(share.can_use),
                created_at=cast(datetime, getattr(share, 'created_at')),
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

        normalized_ids = list(dict.fromkeys(
            uid.strip() for uid in (user_ids or [])
            if uid and uid.strip() and uid.strip() != owner_user_id
        ))

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
                str(g.id) for g in groups
                if any(str(getattr(m, 'id', '')) == owner_user_id for m in (g.members or []))
            }
            unauthorized = sorted(found_group_ids - owner_group_ids)
            if unauthorized:
                raise ValueError("You can only share with groups you are in: " + ", ".join(unauthorized))

            for group in groups:
                for member in (group.members or []):
                    if str(getattr(member, 'id', '')) != owner_user_id and getattr(member, 'is_active', False) and getattr(member, 'tenant_id', None) == tenant_id:
                        member_user_ids_from_groups.append(str(getattr(member, 'id', '')))

        combined_user_ids = list(dict.fromkeys([*normalized_ids, *member_user_ids_from_groups]))

        if combined_user_ids:
            allowed_users = db.query(User).filter(
                User.tenant_id == tenant_id,
                User.id.in_(combined_user_ids),
                User.is_active.is_(True),
            ).all()
            allowed_user_ids = {str(u.id) for u in allowed_users}
            missing = sorted(set(combined_user_ids) - allowed_user_ids)
            if missing:
                raise ValueError("Invalid share users: " + ", ".join(missing))

        db.query(ApiKeyShare).filter_by(api_key_id=key_id).delete(synchronize_session=False)
        now = datetime.now(timezone.utc)
        for shared_user_id in combined_user_ids:
            db.add(ApiKeyShare(
                tenant_id=tenant_id,
                api_key_id=key_id,
                owner_user_id=owner_user_id,
                shared_user_id=shared_user_id,
                can_use=True,
                created_at=now,
            ))

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


def delete_api_key_share(
    service, owner_user_id: str, tenant_id: str, key_id: str, shared_user_id: str
) -> bool:
    service._lazy_init()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        share = db.query(ApiKeyShare).filter_by(api_key_id=key_id, shared_user_id=shared_user_id).first()
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


def backfill_otlp_tokens(service):
    with get_db_session() as db:
        offset = 0
        total = 0
        while True:
            batch = (
                db.query(UserApiKey)
                .filter(UserApiKey.otlp_token.is_(None))
                .limit(_BACKFILL_BATCH_SIZE)
                .offset(offset)
                .all()
            )
            if not batch:
                break
            now = datetime.now(timezone.utc)
            for key in batch:
                key.otlp_token = service._generate_otlp_token()
                key.updated_at = now
            db.commit()
            total += len(batch)
            offset += len(batch)
        if total:
            service.logger.info("Backfilled otlp_token for %d API keys", total)
