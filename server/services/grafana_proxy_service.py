"""Grafana proxy service with multi-tenancy, team scoping, and access control."""
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from services.grafana_service import GrafanaService
from services.grafana_user_sync_service import GrafanaUserSyncService
from db_models import GrafanaDashboard, GrafanaDatasource, Group
from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate
)
from config import config

logger = logging.getLogger(__name__)


class GrafanaProxyService:
    """Proxy service for Grafana with multi-tenant access control, team scoping,
    hide/show, labels, and UID search."""

    def __init__(self):
        self.grafana_service = GrafanaService()
        self.grafana_sync = GrafanaUserSyncService()

    # ------------------------------------------------------------------
    # Access check helpers
    # ------------------------------------------------------------------

    def _check_dashboard_access(
        self,
        db: Session,
        dashboard_uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        require_write: bool = False
    ) -> Optional[GrafanaDashboard]:
        """Check if user has access to a dashboard."""
        dashboard = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == dashboard_uid,
            GrafanaDashboard.tenant_id == tenant_id
        ).first()

        if not dashboard:
            return None

        # Owner always has full access
        if dashboard.created_by == user_id:
            return dashboard

        # Non-owners cannot write
        if require_write:
            return None

        # Tenant-wide visibility
        if dashboard.visibility == "tenant":
            return dashboard
        elif dashboard.visibility == "group":
            shared_group_ids = [g.id for g in dashboard.shared_groups]
            if any(gid in shared_group_ids for gid in group_ids):
                return dashboard

        return None

    def _check_datasource_access(
        self,
        db: Session,
        datasource_uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        require_write: bool = False
    ) -> Optional[GrafanaDatasource]:
        """Check if user has access to a datasource."""
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
        elif datasource.visibility == "group":
            shared_group_ids = [g.id for g in datasource.shared_groups]
            if any(gid in shared_group_ids for gid in group_ids):
                return datasource

        return None

    def _get_accessible_dashboard_uids(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> tuple[List[str], bool]:
        """Get list of dashboard UIDs accessible to user."""
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

    def _get_accessible_datasource_uids(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> tuple[List[str], bool]:
        """Get list of datasource UIDs accessible to user."""
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
        datasources = query.all()

        return [d.grafana_uid for d in datasources], True

    # ------------------------------------------------------------------
    # Dashboard CRUD with hide/show, labels, UID search
    # ------------------------------------------------------------------

    async def search_dashboards(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        query: Optional[str] = None,
        tag: Optional[str] = None,
        starred: Optional[bool] = None,
        uid: Optional[str] = None,
        label_key: Optional[str] = None,
        label_value: Optional[str] = None,
        team_id: Optional[str] = None,
        show_hidden: bool = False,
    ) -> List[DashboardSearchResult]:
        """Search dashboards with multi-tenant filtering, UID search, labels, teams."""

        # If searching by UID directly, skip the broad Grafana search
        if uid:
            dashboard = await self.grafana_service.get_dashboard(uid)
            if not dashboard:
                return []
            db_dash = db.query(GrafanaDashboard).filter(
                GrafanaDashboard.grafana_uid == uid
            ).first()
            if db_dash:
                if not self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids):
                    return []
                if not show_hidden and user_id in (db_dash.hidden_by or []):
                    return []
            dash_data = dashboard.get("dashboard", {})
            meta = dashboard.get("meta", {})

            created_by = db_dash.created_by if db_dash else None
            is_hidden = bool(db_dash and user_id in (db_dash.hidden_by or []))
            is_owned = bool(db_dash and db_dash.created_by == user_id)
            labels = db_dash.labels or {}

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
                labels=labels,
            )]

        all_dashboards = await self.grafana_service.search_dashboards(
            query=query, tag=tag, starred=starred
        )

        accessible_uids, allow_system = self._get_accessible_dashboard_uids(
            db, user_id, tenant_id, group_ids
        )

        all_registered_uids = {d.grafana_uid for d in db.query(GrafanaDashboard).all()}

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

            if label_key:
                if not db_dash:
                    continue
                dash_labels = db_dash.labels or {}
                if label_key not in dash_labels:
                    continue
                if label_value and dash_labels.get(label_key) != label_value:
                    continue

            if team_id:
                if not db_dash:
                    continue
                shared_ids = [g.id for g in db_dash.shared_groups]
                if team_id not in shared_ids:
                    continue

            # Enhance result with proxy-specific metadata
            payload = d.model_dump()
            payload["created_by"] = db_dash.created_by if db_dash else None
            payload["is_hidden"] = bool(db_dash and user_id in (db_dash.hidden_by or []))
            payload["is_owned"] = bool(db_dash and db_dash.created_by == user_id)
            payload["labels"] = db_dash.labels or {}

            filtered.append(DashboardSearchResult(**payload))

        logger.info("User %s has access to %d/%d dashboards", user_id, len(filtered), len(all_dashboards))
        return filtered

    async def get_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Get a dashboard with access control."""
        db_dashboard = db.query(GrafanaDashboard).filter(GrafanaDashboard.grafana_uid == uid).first()
        if db_dashboard:
            if not self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids):
                return None
        return await self.grafana_service.get_dashboard(uid)

    async def create_dashboard(
        self, db: Session, dashboard_create: DashboardCreate, user_id: str, tenant_id: str,
        group_ids: List[str], visibility: str = "private",
        shared_group_ids: List[str] = None, labels: Optional[Dict[str, str]] = None,
        is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Create a dashboard with ownership tracking, labels, and Grafana permissions."""
        try:
            # Validate group visibility settings
            if visibility == "group":
                if not shared_group_ids:
                    raise ValueError("No groups provided for group visibility")
                groups = db.query(Group).filter(Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id).all()
                missing = set(shared_group_ids) - {g.id for g in groups}
                if missing:
                    raise ValueError(f"Invalid group ids: {missing}")
                # Admins can share to any group without being a member
                if not is_admin:
                    not_member = [gid for gid in shared_group_ids if gid not in (group_ids or [])]
                    if not_member:
                        raise ValueError(f"User not member of groups: {not_member}")
            
            result = await self.grafana_service.create_dashboard(dashboard_create)
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
                        folders = await self.grafana_service.get_folders()
                        for f in folders:
                            if f.id == folder_id:
                                folder_uid = f.uid
                                break
                except Exception:
                    pass

            db_dashboard = GrafanaDashboard(
                tenant_id=tenant_id, created_by=user_id, grafana_uid=uid,
                grafana_id=result.get("id"),
                title=dashboard_data.get("title", "Untitled"),
                folder_uid=folder_uid, visibility=visibility,
                tags=dashboard_data.get("tags", []),
                labels=labels or {}, hidden_by=[],
            )

            if visibility == "group" and shared_group_ids:
                groups = db.query(Group).filter(
                    Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id
                ).all()
                db_dashboard.shared_groups.extend(groups)
                await self._sync_dashboard_grafana_permissions(db, uid, user_id, groups)

            db.add(db_dashboard)
            db.commit()
            logger.info("Created dashboard %s for user %s (visibility=%s)", uid, user_id, visibility)
            return result
        except Exception as e:
            logger.error("Error creating dashboard: %s", e, exc_info=True)
            db.rollback()
            return None

    async def update_dashboard(
        self, db: Session, uid: str, dashboard_update: DashboardUpdate,
        user_id: str, tenant_id: str, group_ids: List[str],
        visibility: Optional[str] = None, shared_group_ids: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a dashboard with access control and label support."""
        db_dashboard = self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_dashboard:
            return None

        result = await self.grafana_service.update_dashboard(uid, dashboard_update)
        if not result:
            return None

        dashboard_data = result.get("dashboard", {})
        db_dashboard.title = dashboard_data.get("title", db_dashboard.title)
        db_dashboard.tags = dashboard_data.get("tags", [])

        if labels is not None:
            db_dashboard.labels = labels

        if visibility:
            db_dashboard.visibility = visibility
            if visibility == "group" and shared_group_ids is not None:
                db_dashboard.shared_groups.clear()
                if shared_group_ids:
                    groups = db.query(Group).filter(
                        Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id
                    ).all()
                    db_dashboard.shared_groups.extend(groups)
                    await self._sync_dashboard_grafana_permissions(db, uid, user_id, groups)
            elif visibility != "group":
                db_dashboard.shared_groups.clear()

        db.commit()
        return result

    async def delete_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]
    ) -> bool:
        """Delete a dashboard with access control."""
        db_dashboard = self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_dashboard:
            return False
        success = await self.grafana_service.delete_dashboard(uid)
        if success:
            db.delete(db_dashboard)
            db.commit()
        return success

    # ------------------------------------------------------------------
    # Dashboard hide/show & labels
    # ------------------------------------------------------------------

    def toggle_dashboard_hidden(self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
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

    def update_dashboard_labels(self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str], labels: Dict[str, str]) -> bool:
        db_dash = self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_dash:
            return False
        db_dash.labels = labels
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Datasource CRUD with hide/show, labels, UID search
    # ------------------------------------------------------------------

    async def get_datasources(
        self, db: Session, user_id: str, tenant_id: str, group_ids: List[str],
        uid: Optional[str] = None, label_key: Optional[str] = None,
        label_value: Optional[str] = None, team_id: Optional[str] = None,
        show_hidden: bool = False,
    ) -> List[Datasource]:
        """Get datasources with filtering."""
        if uid:
            ds = await self.grafana_service.get_datasource(uid)
            if not ds:
                return []
            db_ds = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
            if db_ds:
                if not self._check_datasource_access(db, uid, user_id, tenant_id, group_ids):
                    return []
                if not show_hidden and user_id in (db_ds.hidden_by or []):
                    return []
            payload = ds.model_dump()
            payload["created_by"] = db_ds.created_by if db_ds else None
            payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
            payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
            payload["labels"] = db_ds.labels or {} if db_ds else {}
            return [Datasource(**payload)]

        all_datasources = await self.grafana_service.get_datasources()
        accessible_uids, allow_system = self._get_accessible_datasource_uids(db, user_id, tenant_id, group_ids)
        all_registered_uids = {ds.grafana_uid for ds in db.query(GrafanaDatasource).all()}
        db_datasources = {d.grafana_uid: d for d in db.query(GrafanaDatasource).filter(GrafanaDatasource.tenant_id == tenant_id).all()}

        filtered = []
        for ds in all_datasources:
            if ds.uid not in accessible_uids and not (allow_system and ds.uid not in all_registered_uids):
                continue
            db_ds = db_datasources.get(ds.uid)
            if db_ds and not show_hidden and user_id in (db_ds.hidden_by or []):
                continue
            if label_key:
                if not db_ds:
                    continue
                ds_labels = db_ds.labels or {}
                if label_key not in ds_labels:
                    continue
                if label_value and ds_labels.get(label_key) != label_value:
                    continue
            if team_id:
                if not db_ds:
                    continue
                shared_ids = [g.id for g in db_ds.shared_groups]
                if team_id not in shared_ids:
                    continue

            payload = ds.model_dump()
            payload["created_by"] = db_ds.created_by if db_ds else None
            payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
            payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
            payload["labels"] = db_ds.labels or {} if db_ds else {}

            filtered.append(Datasource(**payload))

        return filtered

    async def get_datasource(self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> Optional[Datasource]:
        db_datasource = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
        if db_datasource:
            if not self._check_datasource_access(db, uid, user_id, tenant_id, group_ids):
                return None
        return await self.grafana_service.get_datasource(uid)

    async def create_datasource(
        self, db: Session, datasource_create: DatasourceCreate, user_id: str, tenant_id: str,
        group_ids: List[str], visibility: str = "private",
        shared_group_ids: List[str] = None, labels: Optional[Dict[str, str]] = None,
        is_admin: bool = False,
    ) -> Optional[Datasource]:
        try:
            if datasource_create.type in {"prometheus", "loki", "tempo"}:
                org_id = getattr(datasource_create, 'org_id', None) or config.DEFAULT_ORG_ID
                json_data = dict(datasource_create.json_data or {})
                secure_json_data = dict(datasource_create.secure_json_data or {})
                json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
                secure_json_data.setdefault("httpHeaderValue1", org_id)
                datasource_create = datasource_create.model_copy(update={"json_data": json_data, "secure_json_data": secure_json_data})

            if visibility == "group":
                if not shared_group_ids:
                    raise ValueError("No groups provided for group visibility")
                groups = db.query(Group).filter(Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id).all()
                missing = set(shared_group_ids) - {g.id for g in groups}
                if missing:
                    raise ValueError(f"Invalid group ids: {missing}")
                # Admins can share to any group without being a member
                if not is_admin:
                    not_member = [gid for gid in shared_group_ids if gid not in (group_ids or [])]
                    if not_member:
                        raise ValueError(f"User not member of groups: {not_member}")

            datasource = await self.grafana_service.create_datasource(datasource_create)
            if not datasource:
                return None

            db_datasource = GrafanaDatasource(
                tenant_id=tenant_id, created_by=user_id,
                grafana_uid=datasource.uid, grafana_id=datasource.id,
                name=datasource.name, type=datasource.type,
                visibility=visibility, labels=labels or {}, hidden_by=[],
            )
            if visibility == "group" and shared_group_ids:
                groups = db.query(Group).filter(Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id).all()
                db_datasource.shared_groups.extend(groups)
            db.add(db_datasource)
            db.commit()
            return datasource
        except Exception as e:
            logger.error("Error creating datasource: %s", e, exc_info=True)
            db.rollback()
            return None

    async def update_datasource(
        self, db: Session, uid: str, datasource_update: DatasourceUpdate,
        user_id: str, tenant_id: str, group_ids: List[str],
        visibility: Optional[str] = None, shared_group_ids: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Optional[Datasource]:
        db_datasource = self._check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_datasource:
            return None

        if db_datasource.type in {"prometheus", "loki", "tempo"}:
            org_id = getattr(datasource_update, "org_id", None)
            if org_id is not None:
                json_data = dict(datasource_update.json_data or {})
                secure_json_data = dict(datasource_update.secure_json_data or {})
                json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
                secure_json_data["httpHeaderValue1"] = org_id
                datasource_update = datasource_update.model_copy(update={"json_data": json_data, "secure_json_data": secure_json_data})

        datasource = await self.grafana_service.update_datasource(uid, datasource_update)
        if not datasource:
            return None

        db_datasource.name = datasource.name
        db_datasource.type = datasource.type
        if labels is not None:
            db_datasource.labels = labels

        if visibility:
            if visibility == "group" and shared_group_ids is not None:
                if not shared_group_ids:
                    return None
                groups = db.query(Group).filter(Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id).all()
                if set(shared_group_ids) - {g.id for g in groups}:
                    return None
                db_datasource.visibility = visibility
                db_datasource.shared_groups.clear()
                db_datasource.shared_groups.extend(groups)
            else:
                db_datasource.visibility = visibility
                if visibility != "group":
                    db_datasource.shared_groups.clear()

        db.commit()
        return datasource

    async def delete_datasource(self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> bool:
        db_datasource = self._check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_datasource:
            return False
        success = await self.grafana_service.delete_datasource(uid)
        if success:
            db.delete(db_datasource)
            db.commit()
        return success

    # ------------------------------------------------------------------
    # Datasource hide/show & labels
    # ------------------------------------------------------------------

    def toggle_datasource_hidden(self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
        db_ds = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid, GrafanaDatasource.tenant_id == tenant_id).first()
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

    def update_datasource_labels(self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str], labels: Dict[str, str]) -> bool:
        db_ds = self._check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_ds:
            return False
        db_ds.labels = labels
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Metadata for filtering UI
    # ------------------------------------------------------------------

    def get_dashboard_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        dashboards = db.query(GrafanaDashboard).filter(GrafanaDashboard.tenant_id == tenant_id).all()
        all_labels: Dict[str, set] = {}
        all_teams = set()
        for d in dashboards:
            for k, v in (d.labels or {}).items():
                all_labels.setdefault(k, set()).add(v)
            for g in d.shared_groups:
                all_teams.add(g.id)
        return {
            "label_keys": sorted(list(all_labels.keys())),
            "label_values": {k: sorted(v) for k, v in all_labels.items()},
            "team_ids": sorted(all_teams),
        }

    def get_datasource_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        datasources = db.query(GrafanaDatasource).filter(GrafanaDatasource.tenant_id == tenant_id).all()
        all_labels: Dict[str, set] = {}
        all_teams = set()
        for ds in datasources:
            for k, v in (ds.labels or {}).items():
                all_labels.setdefault(k, set()).add(v)
            for g in ds.shared_groups:
                all_teams.add(g.id)
        return {
            "label_keys": sorted(list(all_labels.keys())),
            "label_values": {k: sorted(v) for k, v in all_labels.items()},
            "team_ids": sorted(all_teams),
        }

    # ------------------------------------------------------------------
    # Grafana-native permission sync
    # ------------------------------------------------------------------

    async def _sync_dashboard_grafana_permissions(self, db: Session, dashboard_uid: str, owner_user_id: str, shared_groups: List) -> None:
        try:
            from db_models import User as UserModel
            owner = db.query(UserModel).filter(UserModel.id == owner_user_id).first()
            perms = []
            if owner and owner.grafana_user_id:
                perms.append({"userId": owner.grafana_user_id, "permission": 4})
            for group in shared_groups:
                if group.grafana_team_id:
                    perms.append({"teamId": group.grafana_team_id, "permission": 2})
            if perms:
                await self.grafana_sync.set_dashboard_permissions(dashboard_uid, perms)
        except Exception as e:
            logger.warning("Failed to sync Grafana permissions for dashboard %s: %s", dashboard_uid, e)
