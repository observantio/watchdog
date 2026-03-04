"""
Dashboard operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from config import config
from db_models import GrafanaDashboard, GrafanaFolder, Group
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from services.grafana.grafana_service import GrafanaAPIError
from services.grafana.folder_ops import is_folder_accessible


def _cap(limit: Optional[int], offset: int) -> tuple[int, int]:
    mx = int(config.MAX_QUERY_LIMIT)
    req = int(limit) if limit is not None else int(config.DEFAULT_QUERY_LIMIT)
    return max(1, min(req, mx)), max(0, int(offset))


def _normalize_title(title: Optional[str]) -> str:
    return str(title or "").strip().lower()


def _group_id_strs(group_ids: List[str]) -> List[str]:
    return [str(g) for g in (group_ids or [])]


def _visible_scope_filter(user_id: str, group_ids: List[str]):
    gids = _group_id_strs(group_ids)
    conds = [GrafanaDashboard.created_by == user_id, GrafanaDashboard.visibility == "tenant"]
    if gids:
        conds.append(
            and_(
                GrafanaDashboard.visibility == "group",
                GrafanaDashboard.shared_groups.any(Group.id.in_(gids)),
            )
        )
    return or_(*conds)


def _is_hidden_for(db_dash: Optional[GrafanaDashboard], user_id: str) -> bool:
    return bool(db_dash and user_id in (db_dash.hidden_by or []))


def _shared_group_ids(db_dash: Optional[GrafanaDashboard]) -> List[str]:
    return [str(g.id) for g in (db_dash.shared_groups or [])] if db_dash else []


def _db_dashboard_by_uid(db: Session, tenant_id: str, uid: str) -> Optional[GrafanaDashboard]:
    return (
        db.query(GrafanaDashboard)
        .filter(GrafanaDashboard.grafana_uid == uid, GrafanaDashboard.tenant_id == tenant_id)
        .first()
    )


def _db_dashboards_map(db: Session, tenant_id: str) -> Dict[str, GrafanaDashboard]:
    rows = (
        db.query(GrafanaDashboard)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return {d.grafana_uid: d for d in rows}


def _to_search_result(grafana_obj: Any, *, db_dash: Optional[GrafanaDashboard], user_id: str) -> DashboardSearchResult:
    payload = grafana_obj.model_dump() if hasattr(grafana_obj, "model_dump") else dict(grafana_obj)
    if db_dash and db_dash.title:
        payload["title"] = db_dash.title
    payload["created_by"] = db_dash.created_by if db_dash else None
    payload["is_hidden"] = _is_hidden_for(db_dash, user_id)
    payload["is_owned"] = bool(db_dash and db_dash.created_by == user_id)
    payload["visibility"] = (db_dash.visibility if db_dash else "private") or "private"
    sgids = _shared_group_ids(db_dash)
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    return DashboardSearchResult.model_validate(payload)


async def _has_accessible_title_conflict(
    service,
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    group_ids: List[str],
    title: str,
    exclude_uid: Optional[str] = None,
) -> bool:
    target = _normalize_title(title)
    if not target:
        return False
    all_dashboards = await service.grafana_service.search_dashboards()
    live_uids = {str(d.uid) for d in all_dashboards if getattr(d, "uid", None)}
    if not live_uids:
        return False

    q = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.tenant_id == tenant_id,
        GrafanaDashboard.grafana_uid.in_(live_uids),
    )
    for dash in q.all():
        if exclude_uid and dash.grafana_uid == str(exclude_uid):
            continue
        if _normalize_title(dash.title) != target:
            continue
        if check_dashboard_access(db, dash.grafana_uid, user_id, tenant_id, group_ids) is not None:
            return True
    return False


def _purge_stale_dashboards(
    db: Session,
    *,
    tenant_id: str,
    live_uids: set[str],
) -> None:
    if not live_uids:
        return
    stale_rows = (
        db.query(GrafanaDashboard)
        .filter(
            GrafanaDashboard.tenant_id == tenant_id,
            ~GrafanaDashboard.grafana_uid.in_(live_uids),
        )
        .all()
    )
    if not stale_rows:
        return
    for row in stale_rows:
        db.delete(row)
    db.commit()


def check_dashboard_access(
    db: Session,
    dashboard_uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDashboard]:
    dashboard = _db_dashboard_by_uid(db, tenant_id, dashboard_uid)
    if not dashboard:
        return None
    if dashboard.created_by == user_id:
        return dashboard
    if require_write:
        return None
    if dashboard.visibility == "tenant":
        return dashboard
    if dashboard.visibility == "group":
        allowed = set(_group_id_strs(group_ids))
        shared = {str(g.id) for g in (dashboard.shared_groups or [])}
        return dashboard if allowed.intersection(shared) else None
    return None


def get_accessible_dashboard_uids(
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> tuple[List[str], bool]:
    rows = (
        db.query(GrafanaDashboard.grafana_uid)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .filter(_visible_scope_filter(user_id, group_ids))
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return [uid for (uid,) in rows], False


def build_dashboard_search_context(
    db: Session,
    *,
    tenant_id: str,
    uid: Optional[str] = None,
) -> Dict[str, Any]:
    if uid:
        return {"uid_db_dashboard": _db_dashboard_by_uid(db, tenant_id, uid)}
    uids = (
        db.query(GrafanaDashboard.grafana_uid)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return {
        "all_registered_uids": {u for (u,) in uids},
        "db_dashboards": _db_dashboards_map(db, tenant_id),
    }


def _dashboard_has_datasource(dashboard_obj: Any) -> bool:
    if not dashboard_obj:
        return False
    dash = dashboard_obj.model_dump() if hasattr(dashboard_obj, "model_dump") else dict(dashboard_obj)

    for item in (dash.get("templating") or {}).get("list") or []:
        if isinstance(item, dict) and item.get("type") == "datasource":
            if (item.get("current") or {}).get("value"):
                return True

    saw_query = False
    for panel in dash.get("panels") or []:
        if not isinstance(panel, dict):
            continue
        pds = panel.get("datasource")
        panel_has_ds = bool(
            (isinstance(pds, str) and pds.strip())
            or (isinstance(pds, dict) and pds.get("uid"))
            or panel.get("datasourceUid")
        )
        for t in panel.get("targets") or []:
            if not isinstance(t, dict):
                continue
            requires_ds = bool(t.get("expr") or t.get("query") or t.get("rawQuery") or t.get("metric"))
            if not requires_ds:
                continue
            saw_query = True
            tds = t.get("datasource")
            target_has_ds = bool(
                t.get("datasourceUid")
                or (isinstance(tds, dict) and tds.get("uid"))
                or (isinstance(tds, str) and tds.strip())
            )
            if target_has_ds or panel_has_ds:
                return True

    return not saw_query


def _is_general_folder_id(folder_id: Any) -> bool:
    if folder_id in ("", 0, "0"):
        return True
    if folder_id is None:
        return False
    try:
        return int(folder_id) <= 0
    except (TypeError, ValueError):
        return False


def _is_non_general_folder_id(folder_id: Any) -> bool:
    if folder_id in (None, "", 0, "0"):
        return False
    try:
        return int(folder_id) > 0
    except (TypeError, ValueError):
        return False


async def _resolve_folder_uid_by_id(service, folder_id: Optional[int]) -> Optional[str]:
    if not folder_id:
        return None
    try:
        target_id = int(folder_id)
    except (TypeError, ValueError):
        return None
    folders = await service.grafana_service.get_folders()
    for folder in folders:
        if getattr(folder, "id", None) == target_id:
            return str(getattr(folder, "uid", "") or "") or None
    return None


async def search_dashboards(
    service,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    query: Optional[str] = None,
    tag: Optional[str] = None,
    starred: Optional[bool] = None,
    folder_ids: Optional[List[int]] = None,
    folder_uids: Optional[List[str]] = None,
    dashboard_uids: Optional[List[str]] = None,
    uid: Optional[str] = None,
    team_id: Optional[str] = None,
    show_hidden: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
    search_context: Optional[Dict[str, Any]] = None,
    is_admin: bool = False,
    exclude_foldered_dashboards: bool = False,
) -> List[DashboardSearchResult]:
    capped_limit, capped_offset = _cap(limit, offset)
    gids = _group_id_strs(group_ids)
    team_id_s = str(team_id) if team_id is not None else None
    folder_id_set = {int(fid) for fid in (folder_ids or []) if fid is not None}
    folder_uid_set = {str(fu) for fu in (folder_uids or []) if fu}
    dashboard_uid_set = {str(du) for du in (dashboard_uids or []) if du}

    if uid:
        result = await service.grafana_service.get_dashboard(uid)
        if not result:
            return []
        folder_uid = (result.get("meta") or {}).get("folderUid")
        if folder_uid and not is_folder_accessible(
            db, folder_uid, user_id, tenant_id, gids, require_write=False, is_admin=is_admin,
        ):
            return []
        effective_context = search_context or build_dashboard_search_context(db, tenant_id=tenant_id, uid=uid)
        db_dash = effective_context.get("uid_db_dashboard")
        if db_dash:
            if check_dashboard_access(db, uid, user_id, tenant_id, gids) is None:
                return []
            if not show_hidden and _is_hidden_for(db_dash, user_id):
                return []
        dash_data = result.get("dashboard", {})
        meta = result.get("meta", {})
        grafana_like = {
            "id": dash_data.get("id", 0),
            "uid": uid,
            "title": dash_data.get("title", ""),
            "uri": f"db/{meta.get('slug', '')}",
            "url": meta.get("url", f"/d/{uid}"),
            "slug": meta.get("slug", ""),
            "type": "dash-db",
            "tags": dash_data.get("tags", []),
            "isStarred": meta.get("isStarred", False),
            "folderId": meta.get("folderId"),
            "folderUid": meta.get("folderUid"),
            "folderTitle": meta.get("folderTitle"),
        }
        return [_to_search_result(grafana_like, db_dash=db_dash, user_id=user_id)]

    all_dashboards = await service.grafana_service.search_dashboards(
        query=query, tag=tag, starred=starred,
        folder_ids=list(folder_id_set) or None,
        folder_uids=list(folder_uid_set) or None,
        dashboard_uids=list(dashboard_uid_set) or None,
    )
    # Grafana search can occasionally return duplicated UIDs (e.g. transient folder indexing);
    # keep a single entry per UID and prefer the one that carries folder context.
    deduped: Dict[str, Any] = {}
    for d in all_dashboards:
        uid_val = str(getattr(d, "uid", "") or "")
        if not uid_val:
            continue
        if dashboard_uid_set and uid_val not in dashboard_uid_set:
            continue
        current = deduped.get(uid_val)
        d_has_folder = bool(getattr(d, "folder_uid", None) or getattr(d, "folderUid", None))
        current_has_folder = bool(
            current and (getattr(current, "folder_uid", None) or getattr(current, "folderUid", None))
        )
        if current is None or (d_has_folder and not current_has_folder):
            deduped[uid_val] = d
    all_dashboards = list(deduped.values())
    should_sync_stale = (
        query is None
        and tag is None
        and starred is None
        and not folder_id_set
        and not folder_uid_set
        and not dashboard_uid_set
        and not exclude_foldered_dashboards
    )
    if should_sync_stale:
        _purge_stale_dashboards(
            db,
            tenant_id=tenant_id,
            live_uids={str(d.uid) for d in all_dashboards if getattr(d, "uid", None)},
        )
    accessible_uids, allow_system = get_accessible_dashboard_uids(db, user_id, tenant_id, gids)
    accessible = set(accessible_uids)

    effective_context = search_context or build_dashboard_search_context(db, tenant_id=tenant_id)
    all_registered_uids = set(effective_context.get("all_registered_uids") or [])
    db_dashboards = effective_context.get("db_dashboards") or {}

    out: List[DashboardSearchResult] = []
    folder_updates: List[GrafanaDashboard] = []
    for d in all_dashboards:
        db_dash = db_dashboards.get(d.uid)
        folder_id = getattr(d, "folder_id", None)
        if folder_id is None:
            folder_id = getattr(d, "folderId", None)
        try:
            folder_id_int = int(folder_id) if folder_id is not None else None
        except (TypeError, ValueError):
            folder_id_int = None
        folder_uid = (
            getattr(d, "folder_uid", None)
            or getattr(d, "folderUid", None)
            or (getattr(db_dash, "folder_uid", None) if db_dash else None)
        )
        if _is_general_folder_id(folder_id):
            if db_dash and db_dash.folder_uid:
                # Dashboard moved back to General; clear stale folder mapping.
                db_dash.folder_uid = None
                folder_updates.append(db_dash)
            folder_uid = None
        if folder_uid_set and str(folder_uid or "") not in folder_uid_set:
            continue
        if folder_id_set and folder_id_int not in folder_id_set:
            continue
        if exclude_foldered_dashboards and (folder_uid or _is_non_general_folder_id(folder_id_int)):
            continue
        if not folder_uid and folder_id:
            folder_by_id = (
                db.query(GrafanaFolder)
                .filter(
                    GrafanaFolder.tenant_id == tenant_id,
                    GrafanaFolder.grafana_id == folder_id,
                )
                .first()
            )
            folder_uid = getattr(folder_by_id, "grafana_uid", None)
        # Fail closed: if Grafana says dashboard is in a folder but we cannot map folder scope, do not leak it.
        if not folder_uid and _is_non_general_folder_id(folder_id):
            continue
        if db_dash and folder_uid and db_dash.folder_uid != folder_uid:
            db_dash.folder_uid = str(folder_uid)
            folder_updates.append(db_dash)
        if folder_uid and not is_folder_accessible(
            db, folder_uid, user_id, tenant_id, gids, require_write=False, is_admin=is_admin,
        ):
            continue
        if d.uid not in accessible and not (allow_system and d.uid not in all_registered_uids):
            continue
        if db_dash and not show_hidden and _is_hidden_for(db_dash, user_id):
            continue
        if team_id_s:
            if not db_dash:
                continue
            if team_id_s not in {str(g.id) for g in (db_dash.shared_groups or [])}:
                continue
        out.append(_to_search_result(d, db_dash=db_dash, user_id=user_id))

    if folder_updates:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return out[capped_offset: capped_offset + capped_limit]


async def get_dashboard(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    is_admin: bool = False,
) -> Optional[Dict[str, Any]]:
    gids = _group_id_strs(group_ids)
    db_dashboard = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dashboard:
        return None
    result = await service.grafana_service.get_dashboard(uid)
    if not result:
        try:
            db.delete(db_dashboard)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return None
    meta = result.get("meta") or {}
    folder_uid = meta.get("folderUid") or db_dashboard.folder_uid
    folder_id = meta.get("folderId")
    if _is_general_folder_id(folder_id) and db_dashboard.folder_uid:
        db_dashboard.folder_uid = None
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        folder_uid = None
    if not folder_uid and _is_non_general_folder_id(folder_id):
        folder_by_id = (
            db.query(GrafanaFolder)
            .filter(
                GrafanaFolder.tenant_id == tenant_id,
                GrafanaFolder.grafana_id == folder_id,
            )
            .first()
        )
        folder_uid = getattr(folder_by_id, "grafana_uid", None)
    if not folder_uid and _is_non_general_folder_id(folder_id):
        return None
    if folder_uid and not is_folder_accessible(
        db, folder_uid, user_id, tenant_id, gids, require_write=False, is_admin=is_admin,
    ):
        return None
    if check_dashboard_access(db, uid, user_id, tenant_id, gids) is None:
        return None
    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = bool(db_dashboard.created_by == user_id)
    payload["is_hidden"] = _is_hidden_for(db_dashboard, user_id)
    return payload


async def create_dashboard(
    service,
    db: Session,
    dashboard_create: DashboardCreate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: str = "private",
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
) -> Optional[Dict[str, Any]]:
    requested_title = str(getattr(getattr(dashboard_create, "dashboard", None), "title", "") or "").strip()
    gids = _group_id_strs(group_ids)
    if requested_title and await _has_accessible_title_conflict(
        service, db, tenant_id=tenant_id, user_id=user_id, group_ids=group_ids, title=requested_title,
    ):
        raise HTTPException(status_code=409, detail="Dashboard title already exists in your visible scope")

    folder_id = getattr(dashboard_create, "folder_id", None)
    folder_uid = await _resolve_folder_uid_by_id(service, folder_id)
    if folder_uid and not is_folder_accessible(
        db, folder_uid, user_id, tenant_id, gids, require_write=True, is_admin=is_admin,
    ):
        raise HTTPException(status_code=403, detail="Folder access denied")

    dash_obj = getattr(dashboard_create, "dashboard", None)
    if dash_obj and not _dashboard_has_datasource(dash_obj):
        raise HTTPException(
            status_code=400,
            detail="Dashboard JSON missing datasource references; include a templating datasource (ds_default) or explicit panel/target datasources",
        )

    groups = []
    if visibility == "group":
        groups = service._validate_group_visibility(
            db, tenant_id=tenant_id, group_ids=group_ids,
            shared_group_ids=shared_group_ids, is_admin=is_admin,
        )

    try:
        result = await service.grafana_service.create_dashboard(dashboard_create)
    except Exception as exc:
        if isinstance(exc, GrafanaAPIError) and exc.status in {409, 412} and getattr(dash_obj, "uid", None):
            next_uid = f"{str(dash_obj.uid)}-{uuid.uuid4().hex[:6]}"
            retry_payload = dashboard_create.model_copy(
                update={"dashboard": dash_obj.model_copy(update={"uid": next_uid})}
            )
            try:
                result = await service.grafana_service.create_dashboard(retry_payload)
            except Exception as retry_exc:
                service._raise_http_from_grafana_error(retry_exc)
        else:
            service._raise_http_from_grafana_error(exc)
        return None

    if not result:
        return None

    dashboard_data = result.get("dashboard", {})
    uid = result.get("uid") or dashboard_data.get("uid")
    if not uid:
        return dict(result)

    folder_uid = result.get("folderUid") or dashboard_data.get("folderUid")
    if not folder_uid:
        folder_id = getattr(dashboard_create, "folder_id", None)
        if folder_id:
            try:
                for f in await service.grafana_service.get_folders():
                    if f.id == folder_id:
                        folder_uid = f.uid
                        break
            except Exception as e:
                service.logger.debug("Unable to resolve folder uid for created dashboard: %s", e)

    db_dashboard = GrafanaDashboard(
        tenant_id=tenant_id,
        created_by=user_id,
        grafana_uid=uid,
        grafana_id=result.get("id"),
        title=requested_title or dashboard_data.get("title", "Untitled"),
        folder_uid=folder_uid,
        visibility=visibility,
        tags=dashboard_data.get("tags", []),
        hidden_by=[],
    )
    if visibility == "group" and shared_group_ids:
        db_dashboard.shared_groups.extend(groups)

    try:
        db.add(db_dashboard)
        db.commit()
    except Exception:
        db.rollback()
        raise

    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = True
    payload["is_hidden"] = False
    return payload


async def update_dashboard(
    service,
    db: Session,
    uid: str,
    dashboard_update: DashboardUpdate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: Optional[str] = None,
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
) -> Optional[Dict[str, Any]]:
    gids = _group_id_strs(group_ids)
    db_dashboard = check_dashboard_access(db, uid, user_id, tenant_id, gids, require_write=True)
    if not db_dashboard:
        return None

    requested_title = str(getattr(getattr(dashboard_update, "dashboard", None), "title", "") or "").strip()
    if requested_title and await _has_accessible_title_conflict(
        service, db, tenant_id=tenant_id, user_id=user_id, group_ids=gids,
        title=requested_title, exclude_uid=uid,
    ):
        raise HTTPException(status_code=409, detail="Dashboard title already exists in your visible scope")

    target_folder_id = getattr(dashboard_update, "folder_id", None)
    target_folder_uid = await _resolve_folder_uid_by_id(service, target_folder_id)
    if target_folder_uid and not is_folder_accessible(
        db, target_folder_uid, user_id, tenant_id, gids, require_write=True, is_admin=is_admin,
    ):
        raise HTTPException(status_code=403, detail="Folder access denied")

    dash_obj = getattr(dashboard_update, "dashboard", None)
    if dash_obj and not _dashboard_has_datasource(dash_obj):
        raise HTTPException(
            status_code=400,
            detail="Dashboard JSON missing datasource references; include a templating datasource (ds_default) or explicit panel/target datasources",
        )

    try:
        result = await service.grafana_service.update_dashboard(uid, dashboard_update)
    except Exception as exc:
        service._raise_http_from_grafana_error(exc)
        return None

    if not result:
        return None

    dashboard_data = result.get("dashboard", {})
    db_dashboard.title = requested_title or dashboard_data.get("title", db_dashboard.title)
    db_dashboard.tags = dashboard_data.get("tags", [])
    resolved_folder_uid = result.get("folderUid") or dashboard_data.get("folderUid")
    if not resolved_folder_uid:
        if _is_general_folder_id(target_folder_id):
            resolved_folder_uid = None
        elif target_folder_uid:
            resolved_folder_uid = target_folder_uid
    db_dashboard.folder_uid = str(resolved_folder_uid) if resolved_folder_uid else None

    if visibility:
        db_dashboard.visibility = visibility
        if visibility == "group" and shared_group_ids is not None:
            groups = service._validate_group_visibility(
                db, tenant_id=tenant_id, group_ids=group_ids,
                shared_group_ids=shared_group_ids, is_admin=is_admin,
            )
            db_dashboard.shared_groups.clear()
            db_dashboard.shared_groups.extend(groups)
        elif visibility != "group":
            db_dashboard.shared_groups.clear()

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = bool(db_dashboard.created_by == user_id)
    payload["is_hidden"] = _is_hidden_for(db_dashboard, user_id)
    return payload


async def delete_dashboard(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> bool:
    db_dashboard = check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_dashboard:
        return False
    ok = await service.grafana_service.delete_dashboard(uid)
    if not ok:
        return False
    try:
        db.delete(db_dashboard)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def toggle_dashboard_hidden(db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
    db_dash = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dash:
        return False
    hidden_list = list(db_dash.hidden_by or [])
    if hidden:
        if user_id not in hidden_list:
            hidden_list.append(user_id)
    else:
        if user_id in hidden_list:
            hidden_list.remove(user_id)
    db_dash.hidden_by = hidden_list
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def get_dashboard_metadata(db: Session, tenant_id: str) -> Dict[str, Any]:
    rows = (
        db.query(GrafanaDashboard)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    team_ids = sorted({str(g.id) for d in rows for g in (d.shared_groups or [])})
    return {"team_ids": team_ids}
