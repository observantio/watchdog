"""
NginX proxy authentication operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import hashlib
import re
import threading
import time
from typing import Any, Dict, Optional, Set, Tuple

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import joinedload

from config import config
from database import get_db_session
from db_models import GrafanaDashboard, GrafanaDatasource, Group, User
from models.access.auth_models import Permission, Role, TokenData

PROXY_AUTH_CACHE: Dict[str, Dict[str, Any]] = {}
PROXY_AUTH_CACHE_TTL = int(getattr(config, "GRAFANA_PROXY_CACHE_TTL", 60))
PROXY_AUTH_CACHE_LOCK = threading.Lock()
PROXY_AUTH_CACHE_GC_EVERY = 500
proxy_auth_cache_ops = 0

HEADER_SAFE_RE = re.compile(r"[\r\n\x00]")
STATIC_PREFIXES = ("/grafana/public/", "/grafana/public/build/")


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
        if entry and entry.get("expires", 0) > now:
            return entry.get("headers")
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
            expired = [k for k, v in PROXY_AUTH_CACHE.items() if v.get("expires", 0) <= now]
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


def _is_dashboard_save_request(path: str, method: str) -> bool:
    return (path or "").lower().startswith("/grafana/api/dashboards/db") and (method or "GET").upper() == "POST"


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


async def _enforce_writable_datasource(service, datasource_uid: str) -> None:
    datasource = await service.grafana_service.get_datasource(datasource_uid)
    if datasource and (
        bool(getattr(datasource, "is_default", False)) or bool(getattr(datasource, "read_only", False))
    ):
        raise HTTPException(status_code=403, detail="Default/read-only datasources are view/query only")


def is_admin_user(token_data: TokenData) -> bool:
    return token_data.role == Role.ADMIN or bool(getattr(token_data, "is_superuser", False))


def is_resource_accessible(resource, token_data: TokenData, *, require_write: bool = False) -> bool:
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


def extract_proxy_token(request, token: Optional[str] = None) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    for cookie_name in ("beobservant_token", "access_token"):
        cookie_token = request.cookies.get(cookie_name)
        if cookie_token:
            return cookie_token
    return request.headers.get("X-Auth-Token") or token


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
    auth_service,
    token_data: TokenData,
    dashboard_uid: Optional[str],
    datasource_uid: Optional[str],
    datasource_id: Optional[int],
) -> Tuple[Any, Optional[GrafanaDashboard], Optional[GrafanaDatasource], Optional[GrafanaDatasource]]:
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
            raise HTTPException(status_code=401, detail="User not found or inactive")

        token_data.org_id = getattr(orm_user, "org_id", token_data.org_id)

        # Use the same collect_permissions logic as the original working code
        # but on the already-loaded ORM object — no extra session opened
        token_data.permissions = list(auth_service._collect_permissions(orm_user))
        token_data.group_ids = [g.id for g in (orm_user.groups or [])]

        if not (dashboard_uid or datasource_uid or datasource_id is not None):
            return orm_user, None, None, None

        dash = (
            s.query(GrafanaDashboard)
            .options(joinedload(GrafanaDashboard.shared_groups))
            .filter(GrafanaDashboard.grafana_uid == dashboard_uid)
            .first()
        ) if dashboard_uid else None

        ds_uid = (
            s.query(GrafanaDatasource)
            .options(joinedload(GrafanaDatasource.shared_groups))
            .filter(GrafanaDatasource.grafana_uid == datasource_uid)
            .first()
        ) if datasource_uid else None

        ds_id = (
            s.query(GrafanaDatasource)
            .options(joinedload(GrafanaDatasource.shared_groups))
            .filter(GrafanaDatasource.grafana_id == datasource_id)
            .first()
        ) if datasource_id is not None else None

        return orm_user, dash, ds_uid, ds_id


async def authorize_proxy_request(
    service,
    request,
    auth_service,
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
    if isinstance(token_data, dict):
        token_data = TokenData(**token_data)

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

    _, dash, ds_uid_obj, ds_id_obj = await run_in_threadpool(
        _db_load_context,
        auth_service, token_data, dashboard_uid, datasource_uid, datasource_id,
    )

    user_permissions = set(token_data.permissions or [])
    allowed_grafana_perms = {
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
    if not user_permissions & allowed_grafana_perms and not getattr(token_data, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    is_admin = is_admin_user(token_data)
    required_permissions = _required_permissions_for_path(original_path, original_method)

    if not is_admin and _is_dashboard_save_request(original_path, original_method):
        has_write = Permission.WRITE_DASHBOARDS.value in user_permissions
        has_create = Permission.CREATE_DASHBOARDS.value in user_permissions
        has_update = Permission.UPDATE_DASHBOARDS.value in user_permissions
        if not has_write and not (has_create and has_update):
            raise HTTPException(status_code=403, detail="Insufficient permissions for dashboard create/update")

    if not is_admin and (not required_permissions or not _has_any_permission(token_data, required_permissions)):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this Grafana action")

    dashboard_write_intent = _is_dashboard_write_intent(original_path, original_method)
    datasource_write_intent = _is_datasource_write_intent(original_path, original_method)

    if dashboard_uid:
        if not dash or not is_resource_accessible(dash, token_data, require_write=dashboard_write_intent):
            raise HTTPException(status_code=403, detail="Dashboard access denied")

    if datasource_uid:
        if not ds_uid_obj or not is_resource_accessible(ds_uid_obj, token_data, require_write=datasource_write_intent):
            raise HTTPException(status_code=403, detail="Datasource access denied")
        if datasource_write_intent:
            await _enforce_writable_datasource(service, str(getattr(ds_uid_obj, "grafana_uid", "")))

    if datasource_id is not None:
        if not ds_id_obj or not is_resource_accessible(ds_id_obj, token_data, require_write=datasource_write_intent):
            raise HTTPException(status_code=403, detail="Datasource access denied")
        if datasource_write_intent:
            await _enforce_writable_datasource(service, str(getattr(ds_id_obj, "grafana_uid", "")))

    headers = _headers_for(token_data)
    _cache_set(token_to_verify, original_method, original_path, str(token_data.tenant_id), headers)
    return headers