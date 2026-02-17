"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Datasource-focused operations for GrafanaProxyService."""

import re
from typing import List, Optional, Dict, Any, Set

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db_models import GrafanaDatasource, Group
from models.grafana.grafana_datasource_models import DatasourceCreate, DatasourceUpdate, Datasource
from config import config


def _sanitize_datasource_payload(payload: Dict[str, Any], *, is_owner: bool) -> Dict[str, Any]:
    if is_owner:
        return payload
    sanitized = dict(payload)
    for key in ("password", "basicAuthPassword", "secureJsonData"):
        if key in sanitized:
            sanitized[key] = None
    return sanitized


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

    return [uid for (uid,) in capped], True


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
        if grafana_ds and (
            bool(getattr(grafana_ds, "is_default", False))
            or bool(getattr(grafana_ds, "isDefault", False))
            or bool(getattr(grafana_ds, "read_only", False))
            or bool(getattr(grafana_ds, "readOnly", False))
        ):
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
) -> List[Datasource]:
    requested_limit = int(limit) if limit is not None else int(config.DEFAULT_QUERY_LIMIT)
    max_limit = int(config.MAX_QUERY_LIMIT)
    capped_limit = max(1, min(requested_limit, max_limit))
    capped_offset = max(0, int(offset))

    if uid:
        datasource = await service.grafana_service.get_datasource(uid)
        if not datasource:
            return []
        db_ds = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
        if db_ds:
            if check_datasource_access(service, db, uid, user_id, tenant_id, group_ids) is None:
                return []
            if not show_hidden and user_id in (db_ds.hidden_by or []):
                return []
        payload = datasource.model_dump()
        payload = _sanitize_datasource_payload(payload, is_owner=bool(db_ds and db_ds.created_by == user_id))
        payload["created_by"] = db_ds.created_by if db_ds else None
        payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
        payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
        payload["visibility"] = db_ds.visibility if db_ds else 'private'
        payload["shared_group_ids"] = [g.id for g in db_ds.shared_groups] if db_ds else []
        payload["sharedGroupIds"] = payload["shared_group_ids"]
        return [Datasource(**payload)]

    all_datasources = await service.grafana_service.get_datasources()

    if is_admin:
        # For admin responses merge Grafana fields with local DB metadata when present
        db_entries = {
            d.grafana_uid: d
            for d in db.query(GrafanaDatasource)
            .filter(GrafanaDatasource.tenant_id == tenant_id)
            .limit(int(config.MAX_QUERY_LIMIT))
            .all()
        }
        processed = []
        for d in all_datasources:
            payload = d.model_dump()
            db_ds = db_entries.get(d.uid)
            payload = _sanitize_datasource_payload(payload, is_owner=bool(db_ds and db_ds.created_by == user_id))
            payload["created_by"] = db_ds.created_by if db_ds else None
            payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
            payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
            payload["visibility"] = db_ds.visibility if db_ds else (payload.get("visibility") or 'private')
            payload["shared_group_ids"] = [g.id for g in db_ds.shared_groups] if db_ds else (payload.get("shared_group_ids") or [])
            payload["sharedGroupIds"] = payload["shared_group_ids"]
            processed.append(Datasource(**payload))
        return processed[capped_offset:capped_offset + capped_limit]

    accessible_uids, allow_system = get_accessible_datasource_uids(service, db, user_id, tenant_id, group_ids)
    accessible_uids = set(accessible_uids)

    all_registered_uids = {
        uid
        for (uid,) in db.query(GrafanaDatasource.grafana_uid)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    }

    filtered = []
    for d in all_datasources:
        if d.uid not in accessible_uids and not (allow_system and d.uid not in all_registered_uids):
            continue

        db_ds = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == d.uid,
            GrafanaDatasource.tenant_id == tenant_id,
        ).first()
        if db_ds and not show_hidden and user_id in (db_ds.hidden_by or []):
            continue
        if team_id:
            if not db_ds:
                continue
            shared_ids = [group.id for group in db_ds.shared_groups]
            if team_id not in shared_ids:
                continue

        payload = d.model_dump()
        payload = _sanitize_datasource_payload(payload, is_owner=bool(db_ds and db_ds.created_by == user_id))
        payload["created_by"] = db_ds.created_by if db_ds else None
        payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
        payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
        payload["visibility"] = db_ds.visibility if db_ds else 'private'
        payload["shared_group_ids"] = [g.id for g in db_ds.shared_groups] if db_ds else []
        payload["sharedGroupIds"] = payload["shared_group_ids"]
        filtered.append(Datasource(**payload))

    return filtered[capped_offset:capped_offset + capped_limit]


async def get_datasource(service, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> Optional[Datasource]:
    db_datasource = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
    if db_datasource and check_datasource_access(service, db, uid, user_id, tenant_id, group_ids) is None:
        return None
    ds = await service.grafana_service.get_datasource(uid)
    if not ds:
        return None
    payload = ds.model_dump()
    payload = _sanitize_datasource_payload(payload, is_owner=bool(db_datasource and db_datasource.created_by == user_id))
    payload["created_by"] = db_datasource.created_by if db_datasource else None
    payload["is_hidden"] = bool(db_datasource and user_id in (db_datasource.hidden_by or []))
    payload["is_owned"] = bool(db_datasource and db_datasource.created_by == user_id)
    payload["visibility"] = db_datasource.visibility if db_datasource else 'private'
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
    shared_group_ids: List[str] = None,
    is_admin: bool = False,
) -> Optional[Datasource]:
    if datasource_create.type in {"prometheus", "loki", "tempo"}:
        org_id = getattr(datasource_create, "org_id", None) or config.DEFAULT_ORG_ID
        json_data = dict(datasource_create.json_data or {})
        secure_json_data = dict(datasource_create.secure_json_data or {})
        json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
        secure_json_data.setdefault("httpHeaderValue1", org_id)
        datasource_create = datasource_create.model_copy(update={"json_data": json_data, "secure_json_data": secure_json_data})

    groups: List[Group] = []
    if visibility == "group":
        groups = service._validate_group_visibility(
            db,
            tenant_id=tenant_id,
            group_ids=group_ids,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
        )

    try:
        result = await service.grafana_service.create_datasource(datasource_create)
    except Exception as gae:
        service._raise_http_from_grafana_error(gae)
    if not result:
        return None

    db_datasource = GrafanaDatasource(
        tenant_id=tenant_id, created_by=user_id,
        grafana_uid=result.uid,
        grafana_id=result.id,
        name=result.name,
        type=result.type,
        visibility=visibility,
    )

    if visibility == "group" and shared_group_ids:
        db_datasource.shared_groups.extend(groups)

    db.add(db_datasource)
    db.commit()

    # Merge Grafana datasource result with local DB metadata so caller gets visibility/shared groups
    payload = result.model_dump()
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
            json_data = dict(datasource_update.json_data or {})
            secure_json_data = dict(datasource_update.secure_json_data or {})
            json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
            secure_json_data["httpHeaderValue1"] = org_id
            datasource_update = datasource_update.model_copy(update={"json_data": json_data, "secure_json_data": secure_json_data})

    try:
        result = await service.grafana_service.update_datasource(uid, datasource_update)
    except Exception as gae:
        service._raise_http_from_grafana_error(gae)
    if not result:
        return None

    db_datasource.name = result.name
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
