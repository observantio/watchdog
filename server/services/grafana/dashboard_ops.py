"""Dashboard-focused operations for GrafanaProxyService."""

from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db_models import GrafanaDashboard, Group
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate, DashboardSearchResult


def check_dashboard_access(
    service,
    db: Session,
    dashboard_uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDashboard]:
    dashboard = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.grafana_uid == dashboard_uid,
        GrafanaDashboard.tenant_id == tenant_id
    ).first()

    if not dashboard:
        return None

    if dashboard.created_by == user_id:
        return dashboard

    if require_write:
        return None

    if dashboard.visibility == "tenant":
        return dashboard
    if dashboard.visibility == "group":
        shared_group_ids = [g.id for g in dashboard.shared_groups]
        if any(gid in shared_group_ids for gid in group_ids):
            return dashboard

    return None


def get_accessible_dashboard_uids(service, db: Session, user_id: str, tenant_id: str, group_ids: List[str]) -> tuple[List[str], bool]:
    query = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.tenant_id == tenant_id
    )

    conditions = [
        GrafanaDashboard.created_by == user_id,
        GrafanaDashboard.visibility == "tenant"
    ]

    if group_ids:
        conditions.append(
            and_(
                GrafanaDashboard.visibility == "group",
                GrafanaDashboard.shared_groups.any(Group.id.in_(group_ids))
            )
        )

    query = query.filter(or_(*conditions))
    dashboards = query.all()

    return [d.grafana_uid for d in dashboards], True


async def search_dashboards(
    service,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    query: Optional[str] = None,
    tag: Optional[str] = None,
    starred: Optional[bool] = None,
    uid: Optional[str] = None,
    team_id: Optional[str] = None,
    show_hidden: bool = False,
    is_admin: bool = False,
) -> List[DashboardSearchResult]:
    if uid:
        dashboard = await service.grafana_service.get_dashboard(uid)
        if not dashboard:
            return []
        db_dash = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == uid
        ).first()
        if db_dash:
            if check_dashboard_access(service, db, uid, user_id, tenant_id, group_ids) is None:
                return []
            if not show_hidden and user_id in (db_dash.hidden_by or []):
                return []
        dash_data = dashboard.get("dashboard", {})
        meta = dashboard.get("meta", {})

        created_by = db_dash.created_by if db_dash else None
        is_hidden = bool(db_dash and user_id in (db_dash.hidden_by or []))
        is_owned = bool(db_dash and db_dash.created_by == user_id)

        return [DashboardSearchResult(
            id=dash_data.get("id", 0),
            uid=uid,
            title=dash_data.get("title", ""),
            uri=f"db/{meta.get('slug', '')}",
            url=meta.get("url", f"/d/{uid}"),
            slug=meta.get("slug", ""),
            type="dash-db",
            tags=dash_data.get("tags", []),
            is_starred=meta.get("isStarred", False),
            folder_id=meta.get("folderId"),
            folder_uid=meta.get("folderUid"),
            folder_title=meta.get("folderTitle"),
            created_by=created_by,
            is_hidden=is_hidden,
            is_owned=is_owned,
            visibility=db_dash.visibility if db_dash else 'private',
            shared_group_ids=[g.id for g in db_dash.shared_groups] if db_dash else [],
            sharedGroupIds=[g.id for g in db_dash.shared_groups] if db_dash else [],
        )]

    all_dashboards = await service.grafana_service.search_dashboards(
        query=query, tag=tag, starred=starred
    )

    if is_admin:
        accessible_uids = {d.uid for d in all_dashboards}
        allow_system = True
    else:
        accessible_uids, allow_system = get_accessible_dashboard_uids(
            service, db, user_id, tenant_id, group_ids
        )
        accessible_uids = set(accessible_uids)

    all_registered_uids = {
        d.grafana_uid
        for d in db.query(GrafanaDashboard).filter(GrafanaDashboard.tenant_id == tenant_id).all()
    }

    db_dashboards = {
        d.grafana_uid: d
        for d in db.query(GrafanaDashboard).filter(
            GrafanaDashboard.tenant_id == tenant_id
        ).all()
    }

    filtered = []
    for d in all_dashboards:
        if d.uid not in accessible_uids and not (allow_system and d.uid not in all_registered_uids):
            continue

        db_dash = db_dashboards.get(d.uid)

        if db_dash and not show_hidden and user_id in (db_dash.hidden_by or []):
            continue

        if team_id:
            if not db_dash:
                continue
            shared_ids = [g.id for g in db_dash.shared_groups]
            if team_id not in shared_ids:
                continue

        payload = d.model_dump()
        payload["created_by"] = db_dash.created_by if db_dash else None
        payload["is_hidden"] = bool(db_dash and user_id in (db_dash.hidden_by or []))
        payload["is_owned"] = bool(db_dash and db_dash.created_by == user_id)
        payload["visibility"] = db_dash.visibility if db_dash else 'private'
        payload["shared_group_ids"] = [g.id for g in db_dash.shared_groups] if db_dash else []
        payload["sharedGroupIds"] = payload["shared_group_ids"]

        filtered.append(DashboardSearchResult(**payload))

    return filtered


async def get_dashboard(service, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> Optional[Dict[str, Any]]:
    db_dashboard = db.query(GrafanaDashboard).filter(GrafanaDashboard.grafana_uid == uid).first()
    if db_dashboard and check_dashboard_access(service, db, uid, user_id, tenant_id, group_ids) is None:
        return None
    return await service.grafana_service.get_dashboard(uid)


async def create_dashboard(
    service,
    db: Session,
    dashboard_create: DashboardCreate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: str = "private",
    shared_group_ids: List[str] = None,
    is_admin: bool = False,
) -> Optional[Dict[str, Any]]:
    try:
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
            result = await service.grafana_service.create_dashboard(dashboard_create)
        except Exception as gae:
            service._raise_http_from_grafana_error(gae)
        if not result:
            return None

        dashboard_data = result.get("dashboard", {})
        uid = result.get("uid") or dashboard_data.get("uid")
        if not uid:
            return result

        folder_uid = result.get("folderUid") or dashboard_data.get("folderUid")
        if not folder_uid:
            folder_id = getattr(dashboard_create, "folder_id", None)
            try:
                if folder_id:
                    folders = await service.grafana_service.get_folders()
                    for f in folders:
                        if f.id == folder_id:
                            folder_uid = f.uid
                            break
            except Exception as exc:
                service.logger.debug("Unable to resolve folder uid for created dashboard: %s", exc)

        db_dashboard = GrafanaDashboard(
            tenant_id=tenant_id, created_by=user_id, grafana_uid=uid,
            grafana_id=result.get("id"),
            title=dashboard_data.get("title", "Untitled"),
            folder_uid=folder_uid, visibility=visibility,
            tags=dashboard_data.get("tags", []),
            hidden_by=[],
        )

        if visibility == "group" and shared_group_ids:
            db_dashboard.shared_groups.extend(groups)

        db.add(db_dashboard)
        db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        service.logger.error("Error creating dashboard: %s", exc, exc_info=True)
        db.rollback()
        return None


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
    db_dashboard = check_dashboard_access(service, db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_dashboard:
        return None

    try:
        result = await service.grafana_service.update_dashboard(uid, dashboard_update)
    except Exception as gae:
        service._raise_http_from_grafana_error(gae)
    if not result:
        return None

    dashboard_data = result.get("dashboard", {})
    db_dashboard.title = dashboard_data.get("title", db_dashboard.title)
    db_dashboard.tags = dashboard_data.get("tags", [])

    if visibility:
        db_dashboard.visibility = visibility
        if visibility == "group" and shared_group_ids is not None:
            groups = service._validate_group_visibility(
                db,
                tenant_id=tenant_id,
                group_ids=group_ids,
                shared_group_ids=shared_group_ids,
                is_admin=is_admin,
            )
            db_dashboard.shared_groups.clear()
            db_dashboard.shared_groups.extend(groups)
        elif visibility != "group":
            db_dashboard.shared_groups.clear()

    db.commit()
    return result


async def delete_dashboard(service, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> bool:
    db_dashboard = check_dashboard_access(service, db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_dashboard:
        return False
    success = await service.grafana_service.delete_dashboard(uid)
    if success:
        db.delete(db_dashboard)
        db.commit()
    return success


def toggle_dashboard_hidden(service, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
    db_dash = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.grafana_uid == uid, GrafanaDashboard.tenant_id == tenant_id
    ).first()
    if not db_dash:
        return False
    hidden_list = list(db_dash.hidden_by or [])
    if hidden and user_id not in hidden_list:
        hidden_list.append(user_id)
    elif not hidden and user_id in hidden_list:
        hidden_list.remove(user_id)
    db_dash.hidden_by = hidden_list
    db.commit()
    return True


def get_dashboard_metadata(service, db: Session, tenant_id: str) -> Dict[str, Any]:
    dashboards = db.query(GrafanaDashboard).filter(GrafanaDashboard.tenant_id == tenant_id).all()
    all_teams = set()
    for dash in dashboards:
        for group in dash.shared_groups:
            all_teams.add(group.id)
    return {"team_ids": sorted(all_teams)}
