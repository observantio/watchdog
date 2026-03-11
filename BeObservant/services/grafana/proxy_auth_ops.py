"""
NginX proxy authentication operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set, TYPE_CHECKING, TypedDict

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import joinedload

from config import config
from database import get_db_session
from db_models import GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, User
from models.access.auth_models import Permission, Role, TokenData
from custom_types.json import JSONDict
from services.auth.delegation import role_to_text as _role_to_text

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService
    from services.grafana_proxy_service import GrafanaProxyService

class ProxyAuthCacheEntry(TypedDict):
    expires: float
    headers: Dict[str, str]


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


PROXY_AUTH_CACHE: Dict[str, ProxyAuthCacheEntry] = {}
PROXY_AUTH_CACHE_TTL = int(getattr(config, "GRAFANA_PROXY_CACHE_TTL", 60))
PROXY_AUTH_CACHE_LOCK = threading.Lock()
PROXY_AUTH_CACHE_GC_EVERY = 500
proxy_auth_cache_ops = 0

HEADER_SAFE_RE = re.compile(r"[\r\n\x00]")
STATIC_PREFIXES = ("/grafana/public/", "/grafana/public/build/")
BLOCKED_GRAFANA_PROXY_PREFIXES = (
    "/grafana/public-dashboards/",
    "/grafana/dashboard/snapshot/",
    "/grafana/api/public/dashboards/",
    "/grafana/api/snapshots",
)
ALLOWED_GRAFANA_PROXY_PERMISSIONS = {
    Permission.READ_DASHBOARDS.value,
    Permission.CREATE_DASHBOARDS.value,
    Permission.UPDATE_DASHBOARDS.value,
    Permission.DELETE_DASHBOARDS.value,
    Permission.READ_DATASOURCES.value,
    Permission.CREATE_DATASOURCES.value,
    Permission.UPDATE_DATASOURCES.value,
    Permission.DELETE_DATASOURCES.value,
    Permission.QUERY_DATASOURCES.value,
    Permission.READ_FOLDERS.value,
    Permission.CREATE_FOLDERS.value,
    Permission.DELETE_FOLDERS.value,
    Permission.WRITE_DASHBOARDS.value,
}


@dataclass(slots=True)
class ProxyAuthorizationContext:
    org_id: str
    permissions: list[str]
    group_ids: list[str]
    dashboard: GrafanaDashboard | None
    datasource_by_uid: GrafanaDatasource | None
    datasource_by_id: GrafanaDatasource | None
    folder: GrafanaFolder | None


def _normalize_cache_path(path: str) -> str:
    p = (path or "").strip().lower()
    if not p:
        return "/"
    if "?" in p:
        p = p.split("?", 1)[0]
    if not p.startswith("/"):
        p = f"/{p}"
    return p


def _cache_key(token: str, method: str, path: str, tenant_id: str) -> str:
    raw = "|".join([
        hashlib.sha256(token.encode("utf-8")).hexdigest(),
        (method or "GET").upper(),
        _normalize_cache_path(path),
        str(tenant_id or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sanitize_header_value(value: str) -> str:
    return HEADER_SAFE_RE.sub("", value or "")


def _is_static_path(path: str) -> bool:
    p = (path or "").lower()
    return any(p.startswith(pref) for pref in STATIC_PREFIXES)


def _cache_get(token: str, method: str, path: str, tenant_id: str) -> Optional[Dict[str, str]]:
    key = _cache_key(token, method, path, tenant_id)
    now = time.monotonic()
    with PROXY_AUTH_CACHE_LOCK:
        entry = PROXY_AUTH_CACHE.get(key)
        if entry and entry["expires"] > now:
            return entry["headers"]
        if entry:
            PROXY_AUTH_CACHE.pop(key, None)
    return None


def _cache_set(token: str, method: str, path: str, tenant_id: str, headers: Dict[str, str]) -> None:
    global proxy_auth_cache_ops
    key = _cache_key(token, method, path, tenant_id)
    now = time.monotonic()
    with PROXY_AUTH_CACHE_LOCK:
        proxy_auth_cache_ops += 1
        if proxy_auth_cache_ops % PROXY_AUTH_CACHE_GC_EVERY == 0:
            expired = [k for k, v in PROXY_AUTH_CACHE.items() if v["expires"] <= now]
            for k in expired:
                PROXY_AUTH_CACHE.pop(k, None)
        PROXY_AUTH_CACHE[key] = {"expires": now + PROXY_AUTH_CACHE_TTL, "headers": headers}


def clear_proxy_auth_cache() -> None:
    with PROXY_AUTH_CACHE_LOCK:
        PROXY_AUTH_CACHE.clear()


def _has_any_permission(token_data: TokenData, required: Set[str]) -> bool:
    if not required:
        return True
    if getattr(token_data, "is_superuser", False):
        return True
    return bool(set(token_data.permissions or []).intersection(required))


def _required_permissions_for_path(path: str, method: str) -> Set[str]:
    p = (path or "").lower()
    m = (method or "GET").upper()

    if p.startswith("/grafana/d/") or p.startswith("/grafana/d-solo/"):
        return {Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/connections/datasources/edit/"):
        return {Permission.UPDATE_DATASOURCES.value, Permission.CREATE_DATASOURCES.value}
    if p.startswith("/grafana/api/search"):
        return {Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/api/ds/query"):
        return {Permission.QUERY_DATASOURCES.value}
    if p.startswith("/grafana/api/query-history"):
        if m in {"POST", "PUT", "PATCH", "DELETE"}:
            return {Permission.QUERY_DATASOURCES.value}
        return {Permission.QUERY_DATASOURCES.value, Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/api/datasources/proxy/"):
        return {Permission.QUERY_DATASOURCES.value}
    if p.startswith("/grafana/api/dashboards/db") and m == "POST":
        return {
            Permission.CREATE_DASHBOARDS.value,
            Permission.UPDATE_DASHBOARDS.value,
            Permission.WRITE_DASHBOARDS.value,
        }
    if p.startswith("/grafana/api/dashboards/uid/"):
        if m == "GET":
            return {Permission.READ_DASHBOARDS.value}
        if m == "DELETE":
            return {Permission.DELETE_DASHBOARDS.value}
    if p.startswith("/grafana/api/datasources/uid/"):
        if "/resources/" in p or "/health" in p or p.endswith("/resources"):
            if m in {"GET", "HEAD", "OPTIONS"}:
                return {Permission.READ_DATASOURCES.value}
            return {Permission.QUERY_DATASOURCES.value}
        if m == "GET":
            return {Permission.READ_DATASOURCES.value}
        if m == "PUT":
            return {Permission.UPDATE_DATASOURCES.value}
        if m == "DELETE":
            return {Permission.DELETE_DATASOURCES.value}
    if p.startswith("/grafana/api/datasources/proxy/uid/"):
        if m in {"GET", "HEAD", "OPTIONS"}:
            return {Permission.READ_DATASOURCES.value}
        return {Permission.QUERY_DATASOURCES.value}
    if p.startswith("/grafana/api/datasources"):
        if m == "GET":
            return {Permission.READ_DATASOURCES.value}
        if m == "POST":
            return {Permission.CREATE_DATASOURCES.value}
    if p.startswith("/grafana/api/folders"):
        if m == "GET":
            return {Permission.READ_FOLDERS.value}
        if m == "POST":
            return {Permission.CREATE_FOLDERS.value}
        if m == "DELETE":
            return {Permission.DELETE_FOLDERS.value}
    if p.startswith("/grafana/api/live"):
        return {Permission.READ_DASHBOARDS.value}
    if m in {"GET", "HEAD", "OPTIONS"}:
        return {
            Permission.READ_DASHBOARDS.value,
            Permission.READ_DATASOURCES.value,
            Permission.READ_FOLDERS.value,
        }
    return set()


def _is_blocked_proxy_path(path: str) -> bool:
    p = (path or "").lower()
    return any(p.startswith(prefix) for prefix in BLOCKED_GRAFANA_PROXY_PREFIXES)


def _is_dashboard_write_intent(path: str, method: str) -> bool:
    return (path or "").lower().startswith("/grafana/api/dashboards/uid/") and (method or "GET").upper() in {
        "DELETE", "PUT", "PATCH", "POST",
    }


def _is_datasource_write_intent(path: str, method: str) -> bool:
    p = (path or "").lower()
    m = (method or "GET").upper()
    if p.startswith("/grafana/api/datasources/uid/") and m in {"PUT", "PATCH", "DELETE"}:
        return True
    if p.startswith("/grafana/connections/datasources/edit/"):
        return True
    return False


def _is_folder_write_intent(path: str, method: str) -> bool:
    p = (path or "").lower()
    m = (method or "GET").upper()
    return p.startswith("/grafana/api/folders") and m in {"POST", "PUT", "PATCH", "DELETE"}


async def _enforce_writable_datasource(service: GrafanaProxyService, datasource_uid: str) -> None:
    datasource = await service.grafana_service.get_datasource(datasource_uid)
    if datasource and (
        bool(getattr(datasource, "is_default", False)) or bool(getattr(datasource, "read_only", False))
    ):
        raise HTTPException(status_code=403, detail="Default/read-only datasources are view/query only")


def is_admin_user(token_data: TokenData) -> bool:
    return bool(
        getattr(token_data, "is_superuser", False)
        or _role_to_text(getattr(token_data, "role", None)) == Role.ADMIN.value
    )


def is_resource_accessible(
    resource: GrafanaDashboard | GrafanaDatasource | GrafanaFolder | None,
    token_data: TokenData,
    *,
    require_write: bool = False,
) -> bool:
    if not resource:
        return False
    if resource.tenant_id != token_data.tenant_id:
        return False
    hidden_by = getattr(resource, "hidden_by", None) or []
    if token_data.user_id in hidden_by:
        return False
    if resource.created_by == token_data.user_id:
        return True
    if not require_write and (
        bool(getattr(resource, "is_default", False)) or bool(getattr(resource, "read_only", False))
    ):
        return True
    if require_write:
        return False
    visibility = getattr(resource, "visibility", "private") or "private"
    if visibility == "tenant":
        return True
    if visibility == "group":
        user_group_ids = set(token_data.group_ids or [])
        resource_group_ids = {g.id for g in (resource.shared_groups or [])}
        return bool(user_group_ids & resource_group_ids)
    return False


def extract_dashboard_uid(path: str) -> Optional[str]:
    for pattern in (
        r"^/grafana/d/([^/]+)",
        r"^/grafana/d-solo/([^/]+)",
        r"^/grafana/api/dashboards/uid/([^/?]+)",
    ):
        m = re.match(pattern, path or "")
        if m:
            return m.group(1)
    return None


def extract_datasource_uid(path: str) -> Optional[str]:
    for pattern in (
        r"^/grafana/api/datasources/uid/([^/?]+)",
        r"^/grafana/api/datasources/proxy/uid/([^/?]+)",
        r"^/grafana/connections/datasources/edit/([^/?]+)",
    ):
        m = re.match(pattern, path or "")
        if m:
            return m.group(1)
    return None


def extract_datasource_id(path: str) -> Optional[int]:
    m = re.match(r"^/grafana/api/datasources/proxy/(\d+)(?:/|$)", path or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def extract_folder_uid(path: str) -> Optional[str]:
    m = re.match(r"^/grafana/api/folders/([^/?]+)", path or "")
    if not m:
        return None
    uid = m.group(1)
    if uid in {"search", "id"}:
        return None
    return uid


def extract_proxy_token(request: Request, token: Optional[str] = None) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return str(auth_header.split(" ", 1)[1].strip())
    for cookie_name in ("beobservant_token", "access_token"):
        cookie_token = request.cookies.get(cookie_name)
        if cookie_token:
            return str(cookie_token)
    header_token = request.headers.get("X-Auth-Token")
    return str(header_token) if header_token else token


def _grafana_role(token_data: TokenData) -> str:
    if is_admin_user(token_data):
        return "Admin"
    perms = set(token_data.permissions or [])
    editor_perms = {
        Permission.CREATE_DASHBOARDS.value,
        Permission.UPDATE_DASHBOARDS.value,
        Permission.DELETE_DASHBOARDS.value,
        Permission.CREATE_DATASOURCES.value,
        Permission.UPDATE_DATASOURCES.value,
        Permission.DELETE_DATASOURCES.value,
        Permission.CREATE_FOLDERS.value,
        Permission.DELETE_FOLDERS.value,
        Permission.WRITE_DASHBOARDS.value,
    }
    return "Editor" if perms & editor_perms else "Viewer"


def _headers_for(token_data: TokenData) -> Dict[str, str]:
    return {
        "X-WEBAUTH-USER": _sanitize_header_value(token_data.username),
        "X-WEBAUTH-TENANT": _sanitize_header_value(str(token_data.tenant_id)),
        "X-WEBAUTH-ROLE": _grafana_role(token_data),
    }


def _db_load_context(
    auth_service: DatabaseAuthService,
    token_data: TokenData,
    dashboard_uid: Optional[str],
    datasource_uid: Optional[str],
    datasource_id: Optional[int],
    folder_uid: Optional[str],
) -> tuple[User, ProxyAuthorizationContext]:
    with get_db_session() as s:
        orm_user = (
            s.query(User)
            .options(
                joinedload(User.groups).joinedload(Group.permissions),
                joinedload(User.permissions),
            )
            .filter(
                User.id == token_data.user_id,
                User.tenant_id == token_data.tenant_id,
            )
            .first()
        )
        if not orm_user or not orm_user.is_active:
            raise HTTPException(status_code=403, detail="User access denied")

        org_id = str(getattr(orm_user, "org_id", token_data.org_id) or token_data.org_id)
        permissions = [str(permission) for permission in auth_service._collect_permissions(orm_user)]
        group_ids = [str(group.id) for group in (orm_user.groups or []) if str(getattr(group, "id", "")).strip()]

        if not (dashboard_uid or datasource_uid or datasource_id is not None or folder_uid):
            return orm_user, ProxyAuthorizationContext(
                org_id=org_id,
                permissions=permissions,
                group_ids=group_ids,
                dashboard=None,
                datasource_by_uid=None,
                datasource_by_id=None,
                folder=None,
            )

        dash = (
            s.query(GrafanaDashboard)
            .options(joinedload(GrafanaDashboard.shared_groups))
            .filter(
                GrafanaDashboard.grafana_uid == dashboard_uid,
                GrafanaDashboard.tenant_id == token_data.tenant_id,
            )
            .first()
        ) if dashboard_uid else None

        ds_uid = (
            s.query(GrafanaDatasource)
            .options(joinedload(GrafanaDatasource.shared_groups))
            .filter(
                GrafanaDatasource.grafana_uid == datasource_uid,
                GrafanaDatasource.tenant_id == token_data.tenant_id,
            )
            .first()
        ) if datasource_uid else None

        ds_id = (
            s.query(GrafanaDatasource)
            .options(joinedload(GrafanaDatasource.shared_groups))
            .filter(
                GrafanaDatasource.grafana_id == datasource_id,
                GrafanaDatasource.tenant_id == token_data.tenant_id,
            )
            .first()
        ) if datasource_id is not None else None

        effective_folder_uid = folder_uid or (getattr(dash, "folder_uid", None) if dash else None)
        folder = (
            s.query(GrafanaFolder)
            .options(joinedload(GrafanaFolder.shared_groups))
            .filter(
                GrafanaFolder.grafana_uid == effective_folder_uid,
                GrafanaFolder.tenant_id == token_data.tenant_id,
            )
            .first()
        ) if effective_folder_uid else None

        return orm_user, ProxyAuthorizationContext(
            org_id=org_id,
            permissions=permissions,
            group_ids=group_ids,
            dashboard=dash,
            datasource_by_uid=ds_uid,
            datasource_by_id=ds_id,
            folder=folder,
        )


def _db_load_folder(tenant_id: str, folder_uid: Optional[str]) -> Optional[GrafanaFolder]:
    if not folder_uid:
        return None
    with get_db_session() as s:
        return (
            s.query(GrafanaFolder)
            .options(joinedload(GrafanaFolder.shared_groups))
            .filter(
                GrafanaFolder.tenant_id == tenant_id,
                GrafanaFolder.grafana_uid == str(folder_uid),
            )
            .first()
        )


def _db_load_folder_by_id(tenant_id: str, folder_id: Optional[int]) -> Optional[GrafanaFolder]:
    if folder_id is None:
        return None
    try:
        folder_id_int = int(folder_id)
    except (TypeError, ValueError):
        return None
    if folder_id_int <= 0:
        return None
    with get_db_session() as s:
        return (
            s.query(GrafanaFolder)
            .options(joinedload(GrafanaFolder.shared_groups))
            .filter(
                GrafanaFolder.tenant_id == tenant_id,
                GrafanaFolder.grafana_id == folder_id_int,
            )
            .first()
        )


def _db_set_dashboard_folder_uid(tenant_id: str, dashboard_uid: str, folder_uid: str) -> None:
    with get_db_session() as s:
        dash = (
            s.query(GrafanaDashboard)
            .filter(
                GrafanaDashboard.tenant_id == tenant_id,
                GrafanaDashboard.grafana_uid == dashboard_uid,
            )
            .first()
        )
        if not dash:
            return
        dash.folder_uid = folder_uid


def _db_clear_dashboard_folder_uid(tenant_id: str, dashboard_uid: str) -> None:
    with get_db_session() as s:
        dash = (
            s.query(GrafanaDashboard)
            .filter(
                GrafanaDashboard.tenant_id == tenant_id,
                GrafanaDashboard.grafana_uid == dashboard_uid,
            )
            .first()
        )
        if not dash:
            return
        if not dash.folder_uid:
            return
        dash.folder_uid = None


def _is_safe_system_datasource(datasource: object) -> bool:
    return bool(
        getattr(datasource, "is_default", False)
        or getattr(datasource, "isDefault", False)
        or getattr(datasource, "read_only", False)
        or getattr(datasource, "readOnly", False)
    )


async def _lookup_safe_system_datasource(service: GrafanaProxyService, *, datasource_uid: Optional[str], datasource_id: Optional[int]) -> bool:
    if datasource_uid:
        ds = await service.grafana_service.get_datasource(datasource_uid)
        return bool(ds and _is_safe_system_datasource(ds))

    if datasource_id is not None:
        datasources = await service.grafana_service.get_datasources()
        for ds in datasources:
            if getattr(ds, "id", None) == datasource_id and _is_safe_system_datasource(ds):
                return True

    return False


def _apply_proxy_user_context(token_data: TokenData, context: ProxyAuthorizationContext) -> None:
    token_data.org_id = context.org_id
    token_data.permissions = list(context.permissions)
    token_data.group_ids = list(context.group_ids)


def _enforce_proxy_permission_gate(token_data: TokenData, *, original_path: str, original_method: str) -> None:
    user_permissions = set(token_data.permissions or [])
    if not user_permissions & ALLOWED_GRAFANA_PROXY_PERMISSIONS and not getattr(token_data, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    is_admin = is_admin_user(token_data)
    required_permissions = _required_permissions_for_path(original_path, original_method)

    if _is_blocked_proxy_path(original_path):
        raise HTTPException(status_code=403, detail="Public/snapshot dashboard links are disabled by policy")

    if not is_admin and _is_folder_write_intent(original_path, original_method):
        raise HTTPException(
            status_code=403,
            detail="Direct Grafana folder write API is disabled; use BeObservant folder endpoints",
        )

    if not is_admin and (not required_permissions or not _has_any_permission(token_data, required_permissions)):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this Grafana action")


async def _resolve_dashboard_folder_context(
    service: GrafanaProxyService,
    token_data: TokenData,
    *,
    dashboard_uid: str,
    folder_obj: GrafanaFolder | None,
) -> GrafanaFolder | None:
    dash_payload = await service.grafana_service.get_dashboard(dashboard_uid)
    meta = _json_dict((dash_payload or {}).get("meta"))
    dash_folder_uid = str(meta.get("folderUid") or "")
    dash_folder_id_value = meta.get("folderId")
    dash_folder_id = dash_folder_id_value if isinstance(dash_folder_id_value, int) else None

    if dash_folder_uid:
        if not folder_obj:
            folder_obj = await run_in_threadpool(_db_load_folder, token_data.tenant_id, dash_folder_uid)
        await run_in_threadpool(_db_set_dashboard_folder_uid, token_data.tenant_id, dashboard_uid, dash_folder_uid)
    elif dash_folder_id not in (None, 0, "", "0"):
        folder_obj = await run_in_threadpool(_db_load_folder_by_id, token_data.tenant_id, dash_folder_id)
        dash_folder_uid = str(getattr(folder_obj, "grafana_uid", "") or "")
        if dash_folder_uid:
            await run_in_threadpool(_db_set_dashboard_folder_uid, token_data.tenant_id, dashboard_uid, dash_folder_uid)
        else:
            raise HTTPException(status_code=403, detail="Folder access denied")
    else:
        await run_in_threadpool(_db_clear_dashboard_folder_uid, token_data.tenant_id, dashboard_uid)
        return None

    return folder_obj


async def _authorize_dashboard_access(
    service: GrafanaProxyService,
    token_data: TokenData,
    *,
    dashboard_uid: str | None,
    dashboard_obj: GrafanaDashboard | None,
    folder_obj: GrafanaFolder | None,
    original_path: str,
    original_method: str,
) -> GrafanaFolder | None:
    if not dashboard_uid:
        return folder_obj

    dashboard_write_intent = _is_dashboard_write_intent(original_path, original_method)
    if not dashboard_obj or not is_resource_accessible(dashboard_obj, token_data, require_write=dashboard_write_intent):
        raise HTTPException(status_code=403, detail="Dashboard access denied")

    folder_obj = await _resolve_dashboard_folder_context(
        service,
        token_data,
        dashboard_uid=dashboard_uid,
        folder_obj=folder_obj,
    )
    if folder_obj and not is_resource_accessible(folder_obj, token_data, require_write=False):
        raise HTTPException(status_code=403, detail="Folder access denied")
    return folder_obj


async def _authorize_datasource_access(
    service: GrafanaProxyService,
    token_data: TokenData,
    *,
    datasource_uid: str | None,
    datasource_id: int | None,
    datasource_by_uid: GrafanaDatasource | None,
    datasource_by_id: GrafanaDatasource | None,
    original_path: str,
    original_method: str,
) -> None:
    datasource_write_intent = _is_datasource_write_intent(original_path, original_method)

    if datasource_uid:
        if datasource_by_uid:
            if not is_resource_accessible(datasource_by_uid, token_data, require_write=datasource_write_intent):
                raise HTTPException(status_code=403, detail="Datasource access denied")
        elif not await _lookup_safe_system_datasource(service, datasource_uid=datasource_uid, datasource_id=None):
            raise HTTPException(status_code=403, detail="Datasource access denied")
        if datasource_write_intent:
            if not datasource_by_uid:
                raise HTTPException(status_code=403, detail="Default/read-only datasources are view/query only")
            await _enforce_writable_datasource(service, str(getattr(datasource_by_uid, "grafana_uid", "")))

    if datasource_id is not None:
        if datasource_by_id:
            if not is_resource_accessible(datasource_by_id, token_data, require_write=datasource_write_intent):
                raise HTTPException(status_code=403, detail="Datasource access denied")
        elif not await _lookup_safe_system_datasource(service, datasource_uid=None, datasource_id=datasource_id):
            raise HTTPException(status_code=403, detail="Datasource access denied")
        if datasource_write_intent:
            if not datasource_by_id:
                raise HTTPException(status_code=403, detail="Default/read-only datasources are view/query only")
            await _enforce_writable_datasource(service, str(getattr(datasource_by_id, "grafana_uid", "")))


def _authorize_folder_access(
    token_data: TokenData,
    *,
    folder_uid: str | None,
    folder_obj: GrafanaFolder | None,
) -> None:
    if not folder_uid:
        return
    if not folder_obj or not is_resource_accessible(folder_obj, token_data, require_write=False):
        raise HTTPException(status_code=403, detail="Folder access denied")


async def authorize_proxy_request(
    service: GrafanaProxyService,
    request: Request,
    auth_service: DatabaseAuthService,
    token: Optional[str] = None,
    orig: Optional[str] = None,
) -> Dict[str, str]:
    token_to_verify = extract_proxy_token(request, token)
    if not token_to_verify:
        raise HTTPException(status_code=401, detail="You need to log in to access this resource.")

    token_data = await run_in_threadpool(auth_service.decode_token, token_to_verify)
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired or your token is invalid. Let's get you a new one.",
        )
    original_uri = orig or request.headers.get("X-Original-URI", "")
    original_method = (request.headers.get("X-Original-Method") or request.method or "GET").upper()
    original_path = original_uri.split("?", 1)[0] if original_uri else ""
    if not original_path:
        raise HTTPException(status_code=400, detail="Missing original URI context")

    cached = _cache_get(token_to_verify, original_method, original_path, str(token_data.tenant_id))
    if cached is not None:
        return cached

    if _is_static_path(original_path):
        headers = _headers_for(token_data)
        _cache_set(token_to_verify, original_method, original_path, str(token_data.tenant_id), headers)
        return headers

    dashboard_uid = extract_dashboard_uid(original_path)
    datasource_uid = extract_datasource_uid(original_path)
    datasource_id = extract_datasource_id(original_path)
    folder_uid = extract_folder_uid(original_path)

    _, context = await run_in_threadpool(
        _db_load_context,
        auth_service, token_data, dashboard_uid, datasource_uid, datasource_id, folder_uid,
    )

    _apply_proxy_user_context(token_data, context)
    _enforce_proxy_permission_gate(token_data, original_path=original_path, original_method=original_method)

    folder_obj = await _authorize_dashboard_access(
        service,
        token_data,
        dashboard_uid=dashboard_uid,
        dashboard_obj=context.dashboard,
        folder_obj=context.folder,
        original_path=original_path,
        original_method=original_method,
    )
    await _authorize_datasource_access(
        service,
        token_data,
        datasource_uid=datasource_uid,
        datasource_id=datasource_id,
        datasource_by_uid=context.datasource_by_uid,
        datasource_by_id=context.datasource_by_id,
        original_path=original_path,
        original_method=original_method,
    )
    _authorize_folder_access(token_data, folder_uid=folder_uid, folder_obj=folder_obj or context.folder)

    headers = _headers_for(token_data)
    _cache_set(token_to_verify, original_method, original_path, str(token_data.tenant_id), headers)
    return headers
