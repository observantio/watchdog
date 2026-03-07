"""
Datasource operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import re
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from config import config
from db_models import ApiKeyShare, GrafanaDatasource, Group, User, UserApiKey
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from services.grafana.grafana_service import GrafanaAPIError

DS_PROXY_ID_RE = re.compile(r"/api/datasources/proxy/(\d+)")


def _cap(limit: Optional[int], offset: int) -> tuple[int, int]:
    mx = int(config.MAX_QUERY_LIMIT)
    req = int(limit) if limit is not None else int(config.DEFAULT_QUERY_LIMIT)
    return max(1, min(req, mx)), max(0, int(offset))


def _group_id_strs(group_ids: List[str]) -> List[str]:
    return [str(g) for g in (group_ids or [])]


def _sanitize_datasource_payload(payload: Dict[str, Any], *, is_owner: bool) -> Dict[str, Any]:
    if is_owner:
        return payload
    sanitized = dict(payload)
    for key in ("password", "basicAuthPassword", "secureJsonData"):
        if key in sanitized:
            sanitized[key] = None
    return sanitized


def _is_safe_system_datasource(datasource: Any) -> bool:
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


def _db_datasource_by_uid(db: Session, tenant_id: str, uid: str) -> Optional[GrafanaDatasource]:
    return (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.grafana_uid == uid, GrafanaDatasource.tenant_id == tenant_id)
        .first()
    )


def _enrich_datasource_payload(
    payload: Dict[str, Any],
    *,
    db_ds: Optional[GrafanaDatasource],
    user_id: str,
    is_unregistered_safe_system: bool = False,
) -> Dict[str, Any]:
    is_owner = bool(db_ds and db_ds.created_by == user_id)
    if db_ds and db_ds.name:
        payload["name"] = db_ds.name
    payload = _sanitize_datasource_payload(payload, is_owner=is_owner)
    payload["created_by"] = db_ds.created_by if db_ds else None
    payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
    payload["is_owned"] = is_owner
    payload["visibility"] = (
        db_ds.visibility if db_ds else ("system" if is_unregistered_safe_system else "private")
    )
    sgids = [g.id for g in (db_ds.shared_groups or [])] if db_ds else []
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    return payload


def _load_allowed_scope_org_ids(db: Session, *, user_id: str, tenant_id: str) -> tuple[str, Set[str]]:
    user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
    if not user or not getattr(user, "is_active", False):
        raise HTTPException(status_code=403, detail="User is not active in tenant scope")

    default_scope = str(getattr(user, "org_id", "") or config.DEFAULT_ORG_ID)
    allowed: Set[str] = {default_scope, str(config.DEFAULT_ORG_ID)}
    
    own_rows = (
        db.query(UserApiKey.key)
        .filter(
            UserApiKey.user_id == user_id,
            UserApiKey.tenant_id == tenant_id,
        )
        .all()
    )
    allowed.update(str(r[0]) for r in own_rows if r and r[0])

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
    allowed.update(str(r[0]) for r in shared_rows if r and r[0])
    return default_scope, {v for v in allowed if v}


def _scope_conflicts_with_other_tenants(db: Session, *, org_id: str, tenant_id: str) -> bool:
    return (
        db.query(UserApiKey.id)
        .filter(UserApiKey.key == org_id, UserApiKey.tenant_id != tenant_id)
        .first()
        is not None
    )


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
    db_entries = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    db_map = {d.grafana_uid: d for d in db_entries}
    all_registered_uids = set(db_map.keys())
    accessible_uids, allow_system = get_accessible_datasource_uids(service, db, user_id, tenant_id, group_ids)
    accessible = set(accessible_uids)

    for datasource in all_datasources:
        uid = str(getattr(datasource, "uid", "") or "")
        if not uid:
            continue
        if exclude_uid and uid == str(exclude_uid):
            continue
        is_unregistered_safe = allow_system and uid not in all_registered_uids and _is_safe_system_datasource(datasource)
        if uid not in accessible and not is_unregistered_safe:
            continue
        db_ds = db_map.get(uid)
        if db_ds and user_id in (db_ds.hidden_by or []):
            continue
        visible_name = db_ds.name if (db_ds and db_ds.name) else getattr(datasource, "name", "")
        if _normalize_name(visible_name) == target:
            return True

    return False


def check_datasource_access(
    db: Session,
    datasource_uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDatasource]:
    datasource = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.grafana_uid == datasource_uid, GrafanaDatasource.tenant_id == tenant_id)
        .first()
    )
    if not datasource:
        return None
    if datasource.created_by == user_id:
        return datasource
    if require_write:
        return None
    if datasource.visibility == "tenant":
        return datasource
    if datasource.visibility == "group":
        allowed = set(_group_id_strs(group_ids))
        shared = {str(g.id) for g in (datasource.shared_groups or [])}
        return datasource if allowed.intersection(shared) else None
    return None


def check_datasource_access_by_id(
    db: Session,
    datasource_id: int,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDatasource]:
    datasource = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.grafana_id == datasource_id, GrafanaDatasource.tenant_id == tenant_id)
        .first()
    )
    if not datasource:
        return None
    if datasource.created_by == user_id:
        return datasource
    if require_write:
        return None
    if datasource.visibility == "tenant":
        return datasource
    if datasource.visibility == "group":
        allowed = set(_group_id_strs(group_ids))
        shared = {str(g.id) for g in (datasource.shared_groups or [])}
        return datasource if allowed.intersection(shared) else None
    return None


def get_accessible_datasource_uids(
    service,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> tuple[List[str], bool]:
    conditions = [GrafanaDatasource.created_by == user_id, GrafanaDatasource.visibility == "tenant"]
    if group_ids:
        conditions.append(
            and_(
                GrafanaDatasource.visibility == "group",
                GrafanaDatasource.shared_groups.any(Group.id.in_(group_ids)),
            )
        )
    rows = (
        db.query(GrafanaDatasource.grafana_uid)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .filter(or_(*conditions))
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return [uid for (uid,) in rows], True


def build_datasource_list_context(
    service,
    db: Session,
    *,
    tenant_id: str,
    uid: Optional[str] = None,
) -> Dict[str, Any]:
    if uid:
        return {"uid_db_datasource": _db_datasource_by_uid(db, tenant_id, uid)}
    rows = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    db_entries = {d.grafana_uid: d for d in rows}
    return {"db_entries": db_entries, "all_registered_uids": set(db_entries.keys())}


def collect_datasource_refs_from_query_payload(payload: Any) -> Set[str]:
    refs: Set[str] = set()

    def walk(value: Any):
        if isinstance(value, dict):
            uid = value.get("datasourceUid")
            if isinstance(uid, str) and uid:
                refs.add(uid)
            ds_obj = value.get("datasource")
            if isinstance(ds_obj, dict):
                uid_val = ds_obj.get("uid")
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
    if not (path.startswith("/api/ds/query") or "/api/datasources/proxy/" in path):
        return

    referenced_uids = collect_datasource_refs_from_query_payload(body)

    id_match = DS_PROXY_ID_RE.search(path)
    if id_match:
        ds_id = int(id_match.group(1))
        ds = check_datasource_access_by_id(db, ds_id, user_id, tenant_id, group_ids)
        if not ds:
            maybe = (
                db.query(GrafanaDatasource)
                .filter(GrafanaDatasource.grafana_id == ds_id, GrafanaDatasource.tenant_id == tenant_id)
                .first()
            )
            if maybe is not None:
                raise HTTPException(status_code=403, detail="Datasource access denied")

    for datasource_uid in referenced_uids:
        ds = check_datasource_access(db, datasource_uid, user_id, tenant_id, group_ids)
        if ds:
            continue
        maybe = (
            db.query(GrafanaDatasource)
            .filter(GrafanaDatasource.grafana_uid == datasource_uid, GrafanaDatasource.tenant_id == tenant_id)
            .first()
        )
        if maybe is not None:
            raise HTTPException(status_code=403, detail="Datasource access denied")
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
    limit: Optional[int] = None,
    offset: int = 0,
    datasource_context: Optional[Dict[str, Any]] = None,
) -> List[Datasource]:
    capped_limit, capped_offset = _cap(limit, offset)

    if uid:
        datasource = await service.grafana_service.get_datasource(uid)
        if not datasource:
            return []
        effective_context = datasource_context or build_datasource_list_context(service, db, tenant_id=tenant_id, uid=uid)
        db_ds = effective_context.get("uid_db_datasource")
        if db_ds:
            if check_datasource_access(db, uid, user_id, tenant_id, group_ids) is None:
                return []
            if not show_hidden and user_id in (db_ds.hidden_by or []):
                return []
        elif not _is_safe_system_datasource(datasource):
            return []
        payload = _enrich_datasource_payload(datasource.model_dump(), db_ds=db_ds, user_id=user_id)
        return [Datasource(**payload)]

    all_datasources = await service.grafana_service.get_datasources()
    accessible_uids, allow_system = get_accessible_datasource_uids(service, db, user_id, tenant_id, group_ids)
    accessible = set(accessible_uids)

    effective_context = datasource_context or build_datasource_list_context(service, db, tenant_id=tenant_id)
    all_registered_uids = set(effective_context.get("all_registered_uids") or set())
    db_entries = effective_context.get("db_entries") or {}

    out: List[Datasource] = []
    for d in all_datasources:
        uid_val = str(getattr(d, "uid", "") or "")
        if not uid_val:
            continue
        is_unregistered_safe = allow_system and uid_val not in all_registered_uids and _is_safe_system_datasource(d)
        if uid_val not in accessible and not is_unregistered_safe:
            continue
        db_ds = db_entries.get(uid_val)
        if db_ds and not show_hidden and user_id in (db_ds.hidden_by or []):
            continue
        if team_id is not None:
            if not db_ds:
                continue
            if str(team_id) not in {str(g.id) for g in (db_ds.shared_groups or [])}:
                continue
        payload = _enrich_datasource_payload(d.model_dump(), db_ds=db_ds, user_id=user_id, is_unregistered_safe_system=is_unregistered_safe)
        out.append(Datasource(**payload))

    return out[capped_offset: capped_offset + capped_limit]


async def get_datasource(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> Optional[Datasource]:
    db_ds = _db_datasource_by_uid(db, tenant_id, uid)
    ds = await service.grafana_service.get_datasource(uid)
    if not ds:
        return None
    if db_ds:
        if check_datasource_access(db, uid, user_id, tenant_id, group_ids) is None:
            return None
    elif not _is_safe_system_datasource(ds):
        return None
    payload = _enrich_datasource_payload(ds.model_dump(), db_ds=db_ds, user_id=user_id)
    return Datasource(**payload)


async def get_datasource_by_name(
    service,
    db: Session,
    name: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> Optional[Datasource]:
    ds = await service.grafana_service.get_datasource_by_name(name)
    if not ds:
        return None
    uid = str(getattr(ds, "uid", "") or "")
    db_ds = _db_datasource_by_uid(db, tenant_id, uid) if uid else None
    if db_ds:
        if check_datasource_access(db, uid, user_id, tenant_id, group_ids) is None:
            return None
    elif not _is_safe_system_datasource(ds):
        return None
    payload = _enrich_datasource_payload(ds.model_dump(), db_ds=db_ds, user_id=user_id)
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
    if requested_name and await _has_accessible_name_conflict(
        service, db, tenant_id=tenant_id, user_id=user_id, group_ids=group_ids, name=requested_name,
    ):
        raise HTTPException(status_code=409, detail="Datasource name already exists in your visible scope")

    if datasource_create.type in {"prometheus", "loki", "tempo"}:
        org_id = _resolve_datasource_org_scope(
            db, requested_org_id=getattr(datasource_create, "org_id", None),
            user_id=user_id, tenant_id=tenant_id,
        )
        json_data = dict(getattr(datasource_create, "json_data", None) or {})
        secure_json_data = dict(getattr(datasource_create, "secure_json_data", None) or {})
        json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
        secure_json_data.setdefault("httpHeaderValue1", org_id)
        datasource_create = datasource_create.model_copy(
            update={"org_id": org_id, "json_data": json_data, "secure_json_data": secure_json_data}
        )

    groups = []
    if visibility == "group":
        groups = service._validate_group_visibility(
            db, user_id=user_id, tenant_id=tenant_id, group_ids=group_ids,
            shared_group_ids=shared_group_ids, is_admin=is_admin,
        )

    try:
        result = await service.grafana_service.create_datasource(datasource_create)
    except Exception as exc:
        if isinstance(exc, GrafanaAPIError) and exc.status in {409, 412}:
            internal_name = _build_internal_name(requested_name or datasource_create.name, user_id)
            try:
                result = await service.grafana_service.create_datasource(
                    datasource_create.model_copy(update={"name": internal_name})
                )
            except Exception as retry_exc:
                service._raise_http_from_grafana_error(retry_exc)
                return None
        else:
            service._raise_http_from_grafana_error(exc)
            return None

    if not result:
        return None

    db_ds = GrafanaDatasource(
        tenant_id=tenant_id,
        created_by=user_id,
        grafana_uid=result.uid,
        grafana_id=result.id,
        name=requested_name or result.name,
        type=result.type,
        visibility=visibility,
    )
    if visibility == "group" and shared_group_ids:
        db_ds.shared_groups.extend(groups)

    try:
        db.add(db_ds)
        db.commit()
    except Exception:
        db.rollback()
        raise

    payload = result.model_dump()
    payload["name"] = db_ds.name
    payload = _sanitize_datasource_payload(payload, is_owner=True)
    payload["created_by"] = db_ds.created_by
    payload["is_hidden"] = False
    payload["is_owned"] = True
    payload["visibility"] = db_ds.visibility or "private"
    sgids = [g.id for g in (db_ds.shared_groups or [])]
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
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
    db_ds = check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_ds:
        return None

    existing = await service.grafana_service.get_datasource(uid)
    if existing and _is_safe_system_datasource(existing):
        raise HTTPException(status_code=403, detail="Default/read-only datasources cannot be modified")

    if db_ds.type in {"prometheus", "loki", "tempo"}:
        org_id = getattr(datasource_update, "org_id", None)
        if org_id is not None:
            validated_org_id = _resolve_datasource_org_scope(
                db, requested_org_id=org_id, user_id=user_id, tenant_id=tenant_id,
            )
            json_data = dict(getattr(datasource_update, "json_data", None) or {})
            secure_json_data = dict(getattr(datasource_update, "secure_json_data", None) or {})
            json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
            secure_json_data["httpHeaderValue1"] = validated_org_id
            datasource_update = datasource_update.model_copy(
                update={"org_id": validated_org_id, "json_data": json_data, "secure_json_data": secure_json_data}
            )

    requested_name: Optional[str] = None
    if getattr(datasource_update, "name", None) is not None:
        requested_name = str(datasource_update.name or "").strip()
        if requested_name and await _has_accessible_name_conflict(
            service, db, tenant_id=tenant_id, user_id=user_id, group_ids=group_ids,
            name=requested_name, exclude_uid=uid,
        ):
            raise HTTPException(status_code=409, detail="Datasource name already exists in your visible scope")

    try:
        result = await service.grafana_service.update_datasource(uid, datasource_update)
    except Exception as exc:
        if isinstance(exc, GrafanaAPIError) and exc.status in {409, 412} and requested_name:
            internal_name = _build_internal_name(requested_name, user_id)
            try:
                result = await service.grafana_service.update_datasource(
                    uid, datasource_update.model_copy(update={"name": internal_name})
                )
            except Exception as retry_exc:
                service._raise_http_from_grafana_error(retry_exc)
                return None
        else:
            service._raise_http_from_grafana_error(exc)
            return None

    if not result:
        return None

    db_ds.name = requested_name or db_ds.name or result.name
    db_ds.type = result.type

    if visibility:
        db_ds.visibility = visibility
        if visibility == "group" and shared_group_ids is not None:
            groups = service._validate_group_visibility(
                db, user_id=user_id, tenant_id=tenant_id, group_ids=group_ids,
                shared_group_ids=shared_group_ids, is_admin=is_admin,
            )
            db_ds.shared_groups.clear()
            db_ds.shared_groups.extend(groups)
        elif visibility != "group":
            db_ds.shared_groups.clear()

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    payload = result.model_dump()
    payload["name"] = db_ds.name
    payload = _sanitize_datasource_payload(payload, is_owner=bool(db_ds.created_by == user_id))
    payload["created_by"] = db_ds.created_by
    payload["is_hidden"] = bool(user_id in (db_ds.hidden_by or []))
    payload["is_owned"] = bool(db_ds.created_by == user_id)
    payload["visibility"] = db_ds.visibility or "private"
    sgids = [g.id for g in (db_ds.shared_groups or [])]
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    return Datasource(**payload)


async def delete_datasource(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> bool:
    db_ds = check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_ds:
        return False
    existing = await service.grafana_service.get_datasource(uid)
    if existing and _is_safe_system_datasource(existing):
        raise HTTPException(status_code=403, detail="Default/read-only datasources cannot be deleted")
    ok = await service.grafana_service.delete_datasource(uid)
    if not ok:
        return False
    try:
        db.delete(db_ds)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


async def query_datasource(service, payload: Dict[str, Any]) -> Dict[str, Any]:
    return await service.grafana_service.query_datasource(payload)


def toggle_datasource_hidden(db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
    db_ds = _db_datasource_by_uid(db, tenant_id, uid)
    if not db_ds:
        return False
    hidden_list = list(db_ds.hidden_by or [])
    if hidden:
        if user_id not in hidden_list:
            hidden_list.append(user_id)
    else:
        if user_id in hidden_list:
            hidden_list.remove(user_id)
    db_ds.hidden_by = hidden_list
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def get_datasource_metadata(db: Session, tenant_id: str) -> Dict[str, Any]:
    rows = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    team_ids = sorted({str(g.id) for ds in rows for g in (ds.shared_groups or [])})
    return {"team_ids": team_ids}
