"""
Datasource operations for Grafana integration, providing functions to list, retrieve, create, update, and delete Grafana datasources while managing access control based on user permissions and group memberships. This module interacts with both the local database to track datasource metadata and the Grafana API to perform operations on the actual datasources in Grafana, ensuring that users can only access and modify datasources they have permissions for while also enforcing constraints such as unique names within a user's visible scope. The operations include handling of datasource visibility (private, group, tenant), shared group management, and conflict resolution during creation and updates.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import re
import uuid
from typing import List, Optional, Dict, Any, Set

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db_models import ApiKeyShare, GrafanaDatasource, Group, User, UserApiKey
from models.grafana.grafana_datasource_models import DatasourceCreate, DatasourceUpdate, Datasource
from config import config
from services.grafana_service import GrafanaAPIError


def _sanitize_datasource_payload(payload: Dict[str, Any], *, is_owner: bool) -> Dict[str, Any]:
    if is_owner:
        return payload
    sanitized = dict(payload)
    for key in ("password", "basicAuthPassword", "secureJsonData"):
        if key in sanitized:
            sanitized[key] = None
    return sanitized


def _is_safe_system_datasource(datasource: Any) -> bool:
    # Unregistered datasources are visible/queryable only when Grafana marks
    # them as default/read-only system datasources.
    return bool(
        getattr(datasource, "is_default", False)
        or getattr(datasource, "isDefault", False)
        or getattr(datasource, "read_only", False)
        or getattr(datasource, "readOnly", False)
    )


def _normalize_name(name: Optional[str]) -> str:
    return str(name or "").strip().lower()


def _build_internal_name(display_name: str, user_id: str) -> str:
    suffix = uuid.uuid4().hex[:6]
    return f"{display_name}__bo_{str(user_id)[:8]}_{suffix}"


def _load_allowed_scope_org_ids(db: Session, *, user_id: str, tenant_id: str) -> tuple[str, Set[str]]:
    user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
    if not user or not getattr(user, "is_active", False):
        raise HTTPException(status_code=403, detail="User is not active in tenant scope")

    default_scope = str(getattr(user, "org_id", "") or config.DEFAULT_ORG_ID)
    allowed: Set[str] = {default_scope, str(config.DEFAULT_ORG_ID)}

    own_enabled_rows = (
        db.query(UserApiKey.key)
        .filter(
            UserApiKey.user_id == user_id,
            UserApiKey.tenant_id == tenant_id,
            UserApiKey.is_enabled.is_(True),
        )
        .all()
    )
    allowed.update(str(row[0]) for row in own_enabled_rows if row and row[0])

    shared_rows = (
        db.query(UserApiKey.key)
        .join(ApiKeyShare, ApiKeyShare.api_key_id == UserApiKey.id)
        .filter(
            ApiKeyShare.shared_user_id == user_id,
            ApiKeyShare.can_use.is_(True),
            ApiKeyShare.tenant_id == tenant_id,
            UserApiKey.tenant_id == tenant_id,
            UserApiKey.is_enabled.is_(True),
        )
        .all()
    )
    allowed.update(str(row[0]) for row in shared_rows if row and row[0])
    allowed = {v for v in allowed if v}
    return default_scope, allowed


def _scope_conflicts_with_other_tenants(db: Session, *, org_id: str, tenant_id: str) -> bool:
    conflict = (
        db.query(UserApiKey.id)
        .filter(UserApiKey.key == org_id, UserApiKey.tenant_id != tenant_id)
        .first()
    )
    return conflict is not None


def _resolve_datasource_org_scope(
    db: Session,
    *,
    requested_org_id: Optional[str],
    user_id: str,
    tenant_id: str,
) -> str:
    default_scope, allowed_scopes = _load_allowed_scope_org_ids(db, user_id=user_id, tenant_id=tenant_id)
    candidate = str(requested_org_id or "").strip() or default_scope
    if candidate not in allowed_scopes:
        raise HTTPException(status_code=403, detail="Requested datasource org_id is not permitted for this user")
    if _scope_conflicts_with_other_tenants(db, org_id=candidate, tenant_id=tenant_id):
        raise HTTPException(status_code=403, detail="Requested datasource org_id is ambiguous across tenants")
    return candidate


async def _has_accessible_name_conflict(
    service,
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    group_ids: List[str],
    name: str,
    exclude_uid: Optional[str] = None,
) -> bool:
    target = _normalize_name(name)
    if not target:
        return False

    all_datasources = await service.grafana_service.get_datasources()
    db_entries = {
        entry.grafana_uid: entry
        for entry in db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    }

    accessible_uids, allow_system = get_accessible_datasource_uids(service, db, user_id, tenant_id, group_ids)
    accessible_uid_set = set(accessible_uids)
    all_registered_uids = set(db_entries.keys())

    for datasource in all_datasources:
        uid = str(getattr(datasource, "uid", "") or "")
        if exclude_uid and uid == exclude_uid:
            continue
        is_unregistered_safe_system_ds = allow_system and uid not in all_registered_uids and _is_safe_system_datasource(datasource)
        if uid not in accessible_uid_set and not is_unregistered_safe_system_ds:
            continue

        db_ds = db_entries.get(uid)
        if db_ds and user_id in (db_ds.hidden_by or []):
            continue

        visible_name = db_ds.name if db_ds and db_ds.name else datasource.name
        if _normalize_name(visible_name) == target:
            return True

    return False


def check_datasource_access(
    service,
    db: Session,
    datasource_uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDatasource]:
    datasource = db.query(GrafanaDatasource).filter(
        GrafanaDatasource.grafana_uid == datasource_uid,
        GrafanaDatasource.tenant_id == tenant_id
    ).first()

    if not datasource:
        return None

    if datasource.created_by == user_id:
        return datasource

    if require_write:
        return None

    if datasource.visibility == "tenant":
        return datasource
    if datasource.visibility == "group":
        shared_group_ids = [g.id for g in datasource.shared_groups]
        if any(gid in shared_group_ids for gid in group_ids):
            return datasource

    return None


def check_datasource_access_by_id(
    service,
    db: Session,
    datasource_id: int,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDatasource]:
    datasource = db.query(GrafanaDatasource).filter(
        GrafanaDatasource.grafana_id == datasource_id,
        GrafanaDatasource.tenant_id == tenant_id
    ).first()

    if not datasource:
        return None

    if datasource.created_by == user_id:
        return datasource

    if require_write:
        return None

    if datasource.visibility == "tenant":
        return datasource
    if datasource.visibility == "group":
        shared_group_ids = [g.id for g in datasource.shared_groups]
        if any(gid in shared_group_ids for gid in group_ids):
            return datasource

    return None


def get_accessible_datasource_uids(service, db: Session, user_id: str, tenant_id: str, group_ids: List[str]) -> tuple[List[str], bool]:
    query = db.query(GrafanaDatasource).filter(
        GrafanaDatasource.tenant_id == tenant_id
    )

    conditions = [
        GrafanaDatasource.created_by == user_id,
        GrafanaDatasource.visibility == "tenant"
    ]

    if group_ids:
        conditions.append(
            and_(
                GrafanaDatasource.visibility == "group",
                GrafanaDatasource.shared_groups.any(Group.id.in_(group_ids))
            )
        )

    query = query.filter(or_(*conditions))
    capped = query.with_entities(GrafanaDatasource.grafana_uid).limit(int(config.MAX_QUERY_LIMIT)).all()

    # Allow fallback visibility for unregistered default/read-only datasources.
    return [uid for (uid,) in capped], True


def build_datasource_list_context(
    service,
    db: Session,
    *,
    tenant_id: str,
    uid: Optional[str] = None,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    if uid:
        context["uid_db_datasource"] = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == uid,
            GrafanaDatasource.tenant_id == tenant_id,
        ).first()
        return context

    db_entries = {
        datasource.grafana_uid: datasource
        for datasource in db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    }
    context["db_entries"] = db_entries
    context["all_registered_uids"] = set(db_entries.keys())
    return context


def collect_datasource_refs_from_query_payload(service, payload: Any) -> Set[str]:
    refs: Set[str] = set()

    def walk(value: Any):
        if isinstance(value, dict):
            uid = value.get("datasourceUid")
            if isinstance(uid, str) and uid:
                refs.add(uid)

            datasource_obj = value.get("datasource")
            if isinstance(datasource_obj, dict):
                uid_val = datasource_obj.get("uid")
                if isinstance(uid_val, str) and uid_val:
                    refs.add(uid_val)

            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return refs


async def enforce_datasource_query_access(
    service,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    path: str,
    method: str,
    body: Any,
) -> None:
    if method.upper() != "POST":
        return

    is_query_endpoint = path.startswith("/api/ds/query") or "/api/datasources/proxy/" in path
    if not is_query_endpoint:
        return

    referenced_uids = collect_datasource_refs_from_query_payload(service, body)

    id_match = re.search(r"/api/datasources/proxy/(\d+)", path)
    if id_match:
        ds = check_datasource_access_by_id(
            service,
            db,
            int(id_match.group(1)),
            user_id,
            tenant_id,
            group_ids,
            require_write=False,
        )
        if not ds:
            # Keep denying registered-but-inaccessible datasources; allow unknown IDs to pass
            # because legacy/system datasources may be unregistered in Be Observant.
            maybe_registered = db.query(GrafanaDatasource).filter(
                GrafanaDatasource.grafana_id == int(id_match.group(1)),
                GrafanaDatasource.tenant_id == tenant_id,
            ).first()
            if maybe_registered is not None:
                raise HTTPException(status_code=403, detail="Datasource access denied")

    for datasource_uid in referenced_uids:
        ds = check_datasource_access(service, db, datasource_uid, user_id, tenant_id, group_ids)
        if ds:
            continue

        # If datasource is registered in tenant but inaccessible, deny.
        maybe_registered = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == datasource_uid,
            GrafanaDatasource.tenant_id == tenant_id,
        ).first()
        if maybe_registered is not None:
            raise HTTPException(status_code=403, detail="Datasource access denied")

        # Allow safe Grafana system datasources that are unregistered in Be Observant
        # (default/read-only are query-only by design).
        grafana_ds = await service.grafana_service.get_datasource(datasource_uid)
        if grafana_ds and _is_safe_system_datasource(grafana_ds):
            continue

        raise HTTPException(status_code=403, detail="Datasource access denied")


async def get_datasources(
    service,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    uid: Optional[str] = None,
    team_id: Optional[str] = None,
    show_hidden: bool = False,
    is_admin: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
    datasource_context: Optional[Dict[str, Any]] = None,
) -> List[Datasource]:
    requested_limit = int(limit) if limit is not None else int(config.DEFAULT_QUERY_LIMIT)
    max_limit = int(config.MAX_QUERY_LIMIT)
    capped_limit = max(1, min(requested_limit, max_limit))
    capped_offset = max(0, int(offset))

    if uid:
        datasource = await service.grafana_service.get_datasource(uid)
        if not datasource:
            return []
        effective_context = datasource_context or build_datasource_list_context(service, db, tenant_id=tenant_id, uid=uid)
        db_ds = effective_context.get("uid_db_datasource")
        if db_ds:
            if check_datasource_access(service, db, uid, user_id, tenant_id, group_ids) is None:
                return []
            if not show_hidden and user_id in (db_ds.hidden_by or []):
                return []
        elif not _is_safe_system_datasource(datasource):
            return []
        payload = datasource.model_dump()
        if db_ds and db_ds.name:
            payload["name"] = db_ds.name
        payload = _sanitize_datasource_payload(payload, is_owner=bool(db_ds and db_ds.created_by == user_id))
        payload["created_by"] = db_ds.created_by if db_ds else None
        payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
        payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
        payload["visibility"] = db_ds.visibility if db_ds else 'system'
        payload["shared_group_ids"] = [g.id for g in db_ds.shared_groups] if db_ds else []
        payload["sharedGroupIds"] = payload["shared_group_ids"]
        return [Datasource(**payload)]

    all_datasources = await service.grafana_service.get_datasources()

    accessible_uids, allow_system = get_accessible_datasource_uids(service, db, user_id, tenant_id, group_ids)
    accessible_uids = set(accessible_uids)

    effective_context = datasource_context or build_datasource_list_context(service, db, tenant_id=tenant_id)
    all_registered_uids = effective_context.get("all_registered_uids", set())
    db_entries = effective_context.get("db_entries", {})

    filtered = []
    for d in all_datasources:
        is_unregistered_safe_system_ds = allow_system and d.uid not in all_registered_uids and _is_safe_system_datasource(d)
        if d.uid not in accessible_uids and not is_unregistered_safe_system_ds:
            continue

        db_ds = db_entries.get(d.uid)
        if db_ds and not show_hidden and user_id in (db_ds.hidden_by or []):
            continue
        if team_id:
            if not db_ds:
                continue
            shared_ids = [group.id for group in db_ds.shared_groups]
            if team_id not in shared_ids:
                continue

        payload = d.model_dump()
        if db_ds and db_ds.name:
            payload["name"] = db_ds.name
        payload = _sanitize_datasource_payload(payload, is_owner=bool(db_ds and db_ds.created_by == user_id))
        payload["created_by"] = db_ds.created_by if db_ds else None
        payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
        payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
        payload["visibility"] = db_ds.visibility if db_ds else ('system' if is_unregistered_safe_system_ds else 'private')
        payload["shared_group_ids"] = [g.id for g in db_ds.shared_groups] if db_ds else []
        payload["sharedGroupIds"] = payload["shared_group_ids"]
        filtered.append(Datasource(**payload))

    return filtered[capped_offset:capped_offset + capped_limit]


async def get_datasource(service, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> Optional[Datasource]:
    db_datasource = db.query(GrafanaDatasource).filter(
        GrafanaDatasource.grafana_uid == uid,
        GrafanaDatasource.tenant_id == tenant_id,
    ).first()
    ds = await service.grafana_service.get_datasource(uid)
    if not ds:
        return None
    if db_datasource:
        if check_datasource_access(service, db, uid, user_id, tenant_id, group_ids) is None:
            return None
    elif not _is_safe_system_datasource(ds):
        return None
    payload = ds.model_dump()
    payload = _sanitize_datasource_payload(payload, is_owner=bool(db_datasource and db_datasource.created_by == user_id))
    payload["created_by"] = db_datasource.created_by if db_datasource else None
    payload["is_hidden"] = bool(db_datasource and user_id in (db_datasource.hidden_by or []))
    payload["is_owned"] = bool(db_datasource and db_datasource.created_by == user_id)
    payload["visibility"] = db_datasource.visibility if db_datasource else 'system'
    payload["shared_group_ids"] = [g.id for g in db_datasource.shared_groups] if db_datasource else []
    payload["sharedGroupIds"] = payload["shared_group_ids"]
    return Datasource(**payload)


async def create_datasource(
    service,
    db: Session,
    datasource_create: DatasourceCreate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: str = "private",
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
) -> Optional[Datasource]:
    requested_name = str(getattr(datasource_create, "name", "") or "").strip()
    if await _has_accessible_name_conflict(
        service,
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        group_ids=group_ids,
        name=requested_name,
    ):
        raise HTTPException(status_code=409, detail="Datasource name already exists in your visible scope")

    if datasource_create.type in {"prometheus", "loki", "tempo"}:
        org_id = _resolve_datasource_org_scope(
            db,
            requested_org_id=getattr(datasource_create, "org_id", None),
            user_id=user_id,
            tenant_id=tenant_id,
        )
        json_data = dict(datasource_create.json_data or {})
        secure_json_data = dict(datasource_create.secure_json_data or {})
        json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
        secure_json_data.setdefault("httpHeaderValue1", org_id)
        datasource_create = datasource_create.model_copy(
            update={"org_id": org_id, "json_data": json_data, "secure_json_data": secure_json_data}
        )

    groups: List[Group] = []
    if visibility == "group":
        groups = service._validate_group_visibility(
            db,
            tenant_id=tenant_id,
            group_ids=group_ids,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
        )

    result = None
    try:
        result = await service.grafana_service.create_datasource(datasource_create)
    except Exception as gae:
        if isinstance(gae, GrafanaAPIError) and gae.status in {409, 412}:
            internal_name = _build_internal_name(requested_name or datasource_create.name, user_id)
            retry_payload = datasource_create.model_copy(update={"name": internal_name})
            try:
                result = await service.grafana_service.create_datasource(retry_payload)
            except Exception as retry_exc:
                service._raise_http_from_grafana_error(retry_exc)
        else:
            service._raise_http_from_grafana_error(gae)
    if not result:
        return None

    db_datasource = GrafanaDatasource(
        tenant_id=tenant_id, created_by=user_id,
        grafana_uid=result.uid,
        grafana_id=result.id,
        name=requested_name or result.name,
        type=result.type,
        visibility=visibility,
    )

    if visibility == "group" and shared_group_ids:
        db_datasource.shared_groups.extend(groups)

    db.add(db_datasource)
    db.commit()

    # Merge Grafana datasource result with local DB metadata so caller gets visibility/shared groups
    payload = result.model_dump()
    payload["name"] = db_datasource.name
    payload = _sanitize_datasource_payload(payload, is_owner=True)
    payload["created_by"] = db_datasource.created_by
    payload["is_hidden"] = bool(db_datasource and False)
    payload["is_owned"] = True
    payload["visibility"] = db_datasource.visibility or 'private'
    payload["shared_group_ids"] = [g.id for g in db_datasource.shared_groups] if db_datasource else []
    payload["sharedGroupIds"] = payload["shared_group_ids"]

    return Datasource(**payload)


async def update_datasource(
    service,
    db: Session,
    uid: str,
    datasource_update: DatasourceUpdate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: Optional[str] = None,
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
) -> Optional[Datasource]:
    db_datasource = check_datasource_access(service, db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_datasource:
        return None

    existing = await service.grafana_service.get_datasource(uid)
    if existing and (bool(getattr(existing, "is_default", False)) or bool(getattr(existing, "read_only", False))):
        raise HTTPException(status_code=403, detail="Default/read-only datasources cannot be modified")

    if db_datasource.type in {"prometheus", "loki", "tempo"}:
        org_id = getattr(datasource_update, "org_id", None)
        if org_id is not None:
            validated_org_id = _resolve_datasource_org_scope(
                db,
                requested_org_id=org_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            json_data = dict(datasource_update.json_data or {})
            secure_json_data = dict(datasource_update.secure_json_data or {})
            json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
            secure_json_data["httpHeaderValue1"] = validated_org_id
            datasource_update = datasource_update.model_copy(
                update={"org_id": validated_org_id, "json_data": json_data, "secure_json_data": secure_json_data}
            )

    requested_name = None
    if getattr(datasource_update, "name", None) is not None:
        requested_name = datasource_update.name.strip()
        if requested_name and await _has_accessible_name_conflict(
            service,
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            group_ids=group_ids,
            name=requested_name,
            exclude_uid=uid,
        ):
            raise HTTPException(status_code=409, detail="Datasource name already exists in your visible scope")

    update_payload = datasource_update
    try:
        result = await service.grafana_service.update_datasource(uid, update_payload)
    except Exception as gae:
        if isinstance(gae, GrafanaAPIError) and gae.status in {409, 412} and requested_name:
            internal_name = _build_internal_name(requested_name, user_id)
            update_payload = datasource_update.model_copy(update={"name": internal_name})
            try:
                result = await service.grafana_service.update_datasource(uid, update_payload)
            except Exception as retry_exc:
                service._raise_http_from_grafana_error(retry_exc)
        else:
            service._raise_http_from_grafana_error(gae)
    if not result:
        return None

    db_datasource.name = requested_name or db_datasource.name or result.name
    db_datasource.type = result.type

    if visibility:
        db_datasource.visibility = visibility
        if visibility == "group" and shared_group_ids is not None:
            groups = service._validate_group_visibility(
                db,
                tenant_id=tenant_id,
                group_ids=group_ids,
                shared_group_ids=shared_group_ids,
                is_admin=is_admin,
            )
            db_datasource.shared_groups.clear()
            db_datasource.shared_groups.extend(groups)
        elif visibility != "group":
            db_datasource.shared_groups.clear()

    db.commit()

    # Return merged datasource (Grafana fields + DB visibility/shared groups)
    payload = result.model_dump()
    payload["name"] = db_datasource.name
    payload = _sanitize_datasource_payload(payload, is_owner=bool(db_datasource and db_datasource.created_by == user_id))
    payload["created_by"] = db_datasource.created_by
    payload["is_hidden"] = bool(db_datasource and user_id in (db_datasource.hidden_by or []))
    payload["is_owned"] = bool(db_datasource and db_datasource.created_by == user_id)
    payload["visibility"] = db_datasource.visibility or 'private'
    payload["shared_group_ids"] = [g.id for g in db_datasource.shared_groups] if db_datasource else []
    payload["sharedGroupIds"] = payload["shared_group_ids"]

    return Datasource(**payload)


async def delete_datasource(service, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> bool:
    db_datasource = check_datasource_access(service, db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_datasource:
        return False

    existing = await service.grafana_service.get_datasource(uid)
    if existing and (bool(getattr(existing, "is_default", False)) or bool(getattr(existing, "read_only", False))):
        raise HTTPException(status_code=403, detail="Default/read-only datasources cannot be deleted")

    success = await service.grafana_service.delete_datasource(uid)
    if success:
        db.delete(db_datasource)
        db.commit()

    return success


def toggle_datasource_hidden(service, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
    db_ds = db.query(GrafanaDatasource).filter(
        GrafanaDatasource.grafana_uid == uid, GrafanaDatasource.tenant_id == tenant_id
    ).first()
    if not db_ds:
        return False
    hidden_list = list(db_ds.hidden_by or [])
    if hidden and user_id not in hidden_list:
        hidden_list.append(user_id)
    elif not hidden and user_id in hidden_list:
        hidden_list.remove(user_id)
    db_ds.hidden_by = hidden_list
    db.commit()
    return True


def get_datasource_metadata(service, db: Session, tenant_id: str) -> Dict[str, Any]:
    datasources = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    all_teams = set()
    for ds in datasources:
        for group in ds.shared_groups:
            all_teams.add(group.id)
    return {"team_ids": sorted(all_teams)}
