"""
Service for proxying requests to Grafana, providing functions to handle authentication, authorization, and access control for Grafana resources such as dashboards and datasources. This module includes logic to extract necessary information from incoming requests, to validate access permissions based on user roles and group memberships, and to interact with the Grafana API for operations related to dashboards and datasources. The service ensures that only authorized users can access or modify Grafana resources through the proxy, and it provides utility functions to manage visibility and sharing of these resources within the context of the application.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import logging
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db_models import Group
from models.access.auth_models import TokenData
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate, DashboardSearchResult
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from services.grafana_service import GrafanaService, GrafanaAPIError
from services.grafana.proxy_auth_ops import (
    is_admin_user, is_resource_accessible, extract_dashboard_uid,
    extract_datasource_uid, extract_datasource_id, extract_proxy_token, authorize_proxy_request,
    clear_proxy_auth_cache,
)
from services.grafana.dashboard_ops import (
    check_dashboard_access, get_accessible_dashboard_uids, build_dashboard_search_context,
    search_dashboards, get_dashboard, create_dashboard, update_dashboard,
    delete_dashboard, toggle_dashboard_hidden, get_dashboard_metadata,
)
from services.grafana.datasource_ops import (
    check_datasource_access, check_datasource_access_by_id, get_accessible_datasource_uids,
    build_datasource_list_context, enforce_datasource_query_access,
    get_datasources, get_datasource, create_datasource, update_datasource,
    delete_datasource, toggle_datasource_hidden, get_datasource_metadata,
)

logger = logging.getLogger(__name__)


class GrafanaProxyService:
    def __init__(self):
        self.grafana_service = GrafanaService()

    @staticmethod
    def _raise_http_from_grafana_error(gae: GrafanaAPIError) -> None:
        body = gae.body
        message = (
            (isinstance(body, dict) and (body.get("message") or body.get("error") or body.get("detail")))
            or (isinstance(body, str) and body)
            or "Grafana API error"
        )
        raise HTTPException(status_code=gae.status if 400 <= gae.status < 600 else 500, detail=message)

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
        return is_admin_user(self, token_data)

    def _is_resource_accessible(self, resource, token_data: TokenData) -> bool:
        return is_resource_accessible(self, resource, token_data)

    def _extract_dashboard_uid(self, path: str) -> Optional[str]:
        return extract_dashboard_uid(self, path)

    def _extract_datasource_uid(self, path: str) -> Optional[str]:
        return extract_datasource_uid(self, path)

    def _extract_datasource_id(self, path: str) -> Optional[int]:
        return extract_datasource_id(self, path)

    def _extract_proxy_token(self, request, token: Optional[str] = None) -> Optional[str]:
        return extract_proxy_token(self, request, token)

    async def authorize_proxy_request(
        self,
        request,
        db: Session,
        auth_service,
        token: Optional[str] = None,
        orig: Optional[str] = None,
    ) -> Dict[str, str]:
        return await authorize_proxy_request(self, request, db, auth_service, token, orig)

    def clear_proxy_auth_cache(self) -> None:
        clear_proxy_auth_cache()

    def _check_dashboard_access(
        self, db: Session, dashboard_uid: str, user_id: str, tenant_id: str,
        group_ids: List[str], require_write: bool = False,
    ):
        return check_dashboard_access(self, db, dashboard_uid, user_id, tenant_id, group_ids, require_write)

    def _check_datasource_access(
        self, db: Session, datasource_uid: str, user_id: str, tenant_id: str,
        group_ids: List[str], require_write: bool = False,
    ):
        return check_datasource_access(self, db, datasource_uid, user_id, tenant_id, group_ids, require_write)

    def _check_datasource_access_by_id(
        self, db: Session, datasource_id: int, user_id: str, tenant_id: str,
        group_ids: List[str], require_write: bool = False,
    ):
        return check_datasource_access_by_id(self, db, datasource_id, user_id, tenant_id, group_ids, require_write)

    async def enforce_datasource_query_access(
        self, db: Session, payload: Dict[str, Any], user_id: str,
        tenant_id: str, group_ids: List[str], is_admin: bool = False,
    ) -> None:
        await enforce_datasource_query_access(self, db, user_id, tenant_id, group_ids, "/api/ds/query", "POST", payload)

    def _get_accessible_dashboard_uids(
        self, db: Session, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> tuple[List[str], bool]:
        return get_accessible_dashboard_uids(self, db, user_id, tenant_id, group_ids)

    def _get_accessible_datasource_uids(
        self, db: Session, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> tuple[List[str], bool]:
        return get_accessible_datasource_uids(self, db, user_id, tenant_id, group_ids)

    def build_dashboard_search_context(self, db: Session, *, tenant_id: str, uid: Optional[str] = None) -> Dict[str, Any]:
        return build_dashboard_search_context(self, db, tenant_id=tenant_id, uid=uid)

    def build_datasource_list_context(self, db: Session, *, tenant_id: str, uid: Optional[str] = None) -> Dict[str, Any]:
        return build_datasource_list_context(self, db, tenant_id=tenant_id, uid=uid)

    async def search_dashboards(
        self, db: Session, user_id: str, tenant_id: str, group_ids: List[str],
        query: Optional[str] = None, tag: Optional[str] = None, starred: Optional[bool] = None,
        uid: Optional[str] = None, team_id: Optional[str] = None, show_hidden: bool = False,
        is_admin: bool = False, limit: Optional[int] = None, offset: int = 0,
        search_context: Optional[Dict[str, Any]] = None,
    ) -> List[DashboardSearchResult]:
        return await search_dashboards(
            self, db, user_id, tenant_id, group_ids,
            query=query, tag=tag, starred=starred, uid=uid, team_id=team_id,
            show_hidden=show_hidden, is_admin=is_admin, limit=limit, offset=offset,
            search_context=search_context,
        )

    async def get_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        return await get_dashboard(self, db, uid, user_id, tenant_id, group_ids)

    async def create_dashboard(
        self, db: Session, dashboard_create: DashboardCreate, user_id: str, tenant_id: str,
        group_ids: List[str], visibility: str = "private",
        shared_group_ids: Optional[List[str]] = None, is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return await create_dashboard(self, db, dashboard_create, user_id, tenant_id, group_ids, visibility, shared_group_ids, is_admin)

    async def update_dashboard(
        self, db: Session, uid: str, dashboard_update: DashboardUpdate, user_id: str,
        tenant_id: str, group_ids: List[str], visibility: Optional[str] = None,
        shared_group_ids: Optional[List[str]] = None, is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return await update_dashboard(self, db, uid, dashboard_update, user_id, tenant_id, group_ids, visibility, shared_group_ids, is_admin)

    async def delete_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> bool:
        return await delete_dashboard(self, db, uid, user_id, tenant_id, group_ids)

    def toggle_dashboard_hidden(self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
        return toggle_dashboard_hidden(self, db, uid, user_id, tenant_id, hidden)

    async def get_datasources(
        self, db: Session, user_id: str, tenant_id: str, group_ids: List[str],
        uid: Optional[str] = None, team_id: Optional[str] = None, show_hidden: bool = False,
        is_admin: bool = False, limit: Optional[int] = None, offset: int = 0,
        datasource_context: Optional[Dict[str, Any]] = None,
    ) -> List[Datasource]:
        return await get_datasources(self, db, user_id, tenant_id, group_ids, uid, team_id, show_hidden, is_admin, limit, offset, datasource_context)

    async def get_datasource(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> Optional[Datasource]:
        return await get_datasource(self, db, uid, user_id, tenant_id, group_ids)

    async def create_datasource(
        self, db: Session, datasource_create: DatasourceCreate, user_id: str, tenant_id: str,
        group_ids: List[str], visibility: str = "private",
        shared_group_ids: Optional[List[str]] = None, is_admin: bool = False,
    ) -> Optional[Datasource]:
        return await create_datasource(self, db, datasource_create, user_id, tenant_id, group_ids, visibility, shared_group_ids, is_admin)

    async def update_datasource(
        self, db: Session, uid: str, datasource_update: DatasourceUpdate, user_id: str,
        tenant_id: str, group_ids: List[str], visibility: Optional[str] = None,
        shared_group_ids: Optional[List[str]] = None, is_admin: bool = False,
    ) -> Optional[Datasource]:
        return await update_datasource(self, db, uid, datasource_update, user_id, tenant_id, group_ids, visibility, shared_group_ids, is_admin)

    async def delete_datasource(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str],
    ) -> bool:
        return await delete_datasource(self, db, uid, user_id, tenant_id, group_ids)

    def toggle_datasource_hidden(self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
        return toggle_datasource_hidden(self, db, uid, user_id, tenant_id, hidden)

    def get_dashboard_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        return get_dashboard_metadata(self, db, tenant_id)

    def get_datasource_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        return get_datasource_metadata(self, db, tenant_id)
