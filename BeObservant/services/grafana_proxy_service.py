"""
Grafana Proxy Service for forwarding requests to Grafana API with authentication, error handling, and audit logging.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db_models import Group
from models.access.auth_models import TokenData
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from services.grafana import proxy_auth_ops as _proxy_auth_ops
from services.grafana.grafana_service import GrafanaService
from services.grafana.dashboard_ops import (
    build_dashboard_search_context,
    create_dashboard,
    delete_dashboard,
    get_dashboard,
    get_dashboard_metadata,
    search_dashboards,
    toggle_dashboard_hidden,
    update_dashboard,
)
from services.grafana.datasource_ops import (
    build_datasource_list_context,
    create_datasource,
    delete_datasource,
    enforce_datasource_query_access,
    get_datasource,
    get_datasource_by_name,
    get_datasource_metadata,
    get_datasources,
    query_datasource,
    toggle_datasource_hidden,
    update_datasource,
)
from services.grafana.folder_ops import (
    create_folder,
    delete_folder,
    get_folders,
)

logger = logging.getLogger(__name__)

is_admin_user = _proxy_auth_ops.is_admin_user
is_resource_accessible = _proxy_auth_ops.is_resource_accessible
extract_dashboard_uid = _proxy_auth_ops.extract_dashboard_uid
extract_datasource_uid = _proxy_auth_ops.extract_datasource_uid
extract_datasource_id = _proxy_auth_ops.extract_datasource_id
extract_proxy_token = _proxy_auth_ops.extract_proxy_token
authorize_proxy_request = _proxy_auth_ops.authorize_proxy_request
clear_proxy_auth_cache = getattr(_proxy_auth_ops, "clear_proxy_auth_cache", lambda: None)


class GrafanaProxyService:
    def __init__(self):
        self.logger = logger
        self.grafana_service = GrafanaService()

    @staticmethod
    def _raise_http_from_grafana_error(exc: Exception) -> None:
        from services.grafana.grafana_service import GrafanaAPIError
        if not isinstance(exc, GrafanaAPIError):
            raise exc
        body = exc.body
        message = (
            (isinstance(body, dict) and (body.get("message") or body.get("error") or body.get("detail")))
            or (isinstance(body, str) and body)
            or "Grafana API error"
        )
        raise HTTPException(status_code=exc.status if 400 <= exc.status < 600 else 500, detail=message)

    def _validate_group_visibility(
        self,
        db: Session,
        *,
        tenant_id: str,
        group_ids: Optional[List[str]],
        shared_group_ids: Optional[List[str]],
        is_admin: bool,
    ) -> List[Group]:
        if not shared_group_ids:
            raise HTTPException(status_code=400, detail="No groups provided for group visibility")
        groups = db.query(Group).filter(Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id).all()
        if len(groups) != len(shared_group_ids):
            raise HTTPException(status_code=400, detail="One or more group ids are invalid")
        if not is_admin:
            user_groups = set(group_ids or [])
            not_member = [gid for gid in shared_group_ids if gid not in user_groups]
            if not_member:
                raise HTTPException(status_code=403, detail="User is not a member of one or more specified groups")
        return groups

    def _is_admin_user(self, token_data: TokenData) -> bool:
        return is_admin_user(token_data)

    def _is_resource_accessible(self, resource, token_data: TokenData) -> bool:
        return is_resource_accessible(resource, token_data)

    def _extract_dashboard_uid(self, path: str) -> Optional[str]:
        return extract_dashboard_uid(path)

    def _extract_datasource_uid(self, path: str) -> Optional[str]:
        return extract_datasource_uid(path)

    def _extract_datasource_id(self, path: str) -> Optional[int]:
        return extract_datasource_id(path)

    def _extract_proxy_token(self, request, token: Optional[str] = None) -> Optional[str]:
        return extract_proxy_token(request, token)

    async def authorize_proxy_request(
        self,
        request,
        auth_service,
        token: Optional[str] = None,
        orig: Optional[str] = None,
    ) -> Dict[str, str]:
        return await authorize_proxy_request(self, request, auth_service, token, orig)

    def clear_proxy_auth_cache(self) -> None:
        clear_proxy_auth_cache()

    def build_dashboard_search_context(
        self, db: Session, *, tenant_id: str, uid: Optional[str] = None,
    ) -> Dict[str, Any]:
        return build_dashboard_search_context(db, tenant_id=tenant_id, uid=uid)

    def build_datasource_list_context(
        self, db: Session, *, tenant_id: str, uid: Optional[str] = None,
    ) -> Dict[str, Any]:
        return build_datasource_list_context(self, db, tenant_id=tenant_id, uid=uid)

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
        team_id: Optional[str] = None,
        show_hidden: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
        search_context: Optional[Dict[str, Any]] = None,
    ) -> List[DashboardSearchResult]:
        return await search_dashboards(
            self, db, user_id, tenant_id, group_ids,
            query=query, tag=tag, starred=starred, uid=uid, team_id=team_id,
            show_hidden=show_hidden, limit=limit, offset=offset, search_context=search_context,
        )

    async def get_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        return await get_dashboard(self, db, uid, user_id, tenant_id, group_ids)

    async def create_dashboard(
        self,
        db: Session,
        dashboard_create: DashboardCreate,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        visibility: str = "private",
        shared_group_ids: Optional[List[str]] = None,
        is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return await create_dashboard(
            self, db, dashboard_create, user_id, tenant_id, group_ids,
            visibility, shared_group_ids, is_admin,
        )

    async def update_dashboard(
        self,
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
        return await update_dashboard(
            self, db, uid, dashboard_update, user_id, tenant_id, group_ids,
            visibility, shared_group_ids, is_admin,
        )

    async def delete_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> bool:
        return await delete_dashboard(self, db, uid, user_id, tenant_id, group_ids)

    def toggle_dashboard_hidden(
        self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool,
    ) -> bool:
        return toggle_dashboard_hidden(db, uid, user_id, tenant_id, hidden)

    def get_dashboard_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        return get_dashboard_metadata(db, tenant_id)

    async def get_datasources(
        self,
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
        return await get_datasources(
            self, db, user_id, tenant_id, group_ids,
            uid, team_id, show_hidden, limit, offset, datasource_context,
        )

    async def get_datasource(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> Optional[Datasource]:
        return await get_datasource(self, db, uid, user_id, tenant_id, group_ids)

    async def get_datasource_by_name(
        self, db: Session, name: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> Optional[Datasource]:
        return await get_datasource_by_name(self, db, name, user_id, tenant_id, group_ids)

    async def create_datasource(
        self,
        db: Session,
        datasource_create: DatasourceCreate,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        visibility: str = "private",
        shared_group_ids: Optional[List[str]] = None,
        is_admin: bool = False,
    ) -> Optional[Datasource]:
        return await create_datasource(
            self, db, datasource_create, user_id, tenant_id, group_ids,
            visibility, shared_group_ids, is_admin,
        )

    async def update_datasource(
        self,
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
        return await update_datasource(
            self, db, uid, datasource_update, user_id, tenant_id, group_ids,
            visibility, shared_group_ids, is_admin,
        )

    async def delete_datasource(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> bool:
        return await delete_datasource(self, db, uid, user_id, tenant_id, group_ids)

    def toggle_datasource_hidden(
        self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool,
    ) -> bool:
        return toggle_datasource_hidden(db, uid, user_id, tenant_id, hidden)

    def get_datasource_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        return get_datasource_metadata(db, tenant_id)

    async def query_datasource(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await query_datasource(self, payload)

    async def enforce_datasource_query_access(
        self,
        db: Session,
        payload: Dict[str, Any],
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
    ) -> None:
        await enforce_datasource_query_access(
            self, db, user_id, tenant_id, group_ids, "/api/ds/query", "POST", payload,
        )

    async def get_folders(self) -> List[Folder]:
        return await get_folders(self)

    async def create_folder(self, title: str) -> Optional[Folder]:
        return await create_folder(self, title)

    async def delete_folder(self, uid: str) -> bool:
        return await delete_folder(self, uid)