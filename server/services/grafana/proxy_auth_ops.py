"""Proxy authorization and path extraction operations for GrafanaProxyService."""

import re
from typing import Dict, Optional, Set

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from db_models import GrafanaDashboard, GrafanaDatasource
from models.access.auth_models import Permission, TokenData, Role


def _has_any_permission(token_data: TokenData, required: Set[str]) -> bool:
    if not required:
        return True
    if getattr(token_data, "is_superuser", False):
        return True
    user_permissions = set(token_data.permissions or [])
    return bool(user_permissions.intersection(required))


def _required_permissions_for_path(path: str, method: str) -> Set[str]:
    """Map Grafana proxy requests to required Be Observant permissions."""
    p = (path or "").lower()
    m = (method or "GET").upper()

    if p.startswith("/grafana/d/") or p.startswith("/grafana/d-solo/"):
        return {Permission.READ_DASHBOARDS.value}

    if p.startswith("/grafana/connections/datasources/edit/"):
        return {
            Permission.UPDATE_DATASOURCES.value,
            Permission.CREATE_DATASOURCES.value,
        }

    if p.startswith("/grafana/api/search"):
        return {Permission.READ_DASHBOARDS.value}

    if p.startswith("/grafana/api/ds/query"):
        return {Permission.QUERY_DATASOURCES.value}

    if p.startswith("/grafana/api/query-history"):
        if m in {"POST", "PUT", "PATCH", "DELETE"}:
            return {Permission.QUERY_DATASOURCES.value}
        return {
            Permission.QUERY_DATASOURCES.value,
            Permission.READ_DASHBOARDS.value,
        }

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
    p = (path or "").lower()
    m = (method or "GET").upper()
    return p.startswith("/grafana/api/dashboards/db") and m == "POST"


def _is_dashboard_write_intent(path: str, method: str) -> bool:
    p = (path or "").lower()
    m = (method or "GET").upper()
    return p.startswith("/grafana/api/dashboards/uid/") and m in {"DELETE", "PUT", "PATCH", "POST"}


def _is_datasource_write_intent(path: str, method: str) -> bool:
    p = (path or "").lower()
    m = (method or "GET").upper()
    if p.startswith("/grafana/api/datasources/uid/") and m in {"PUT", "PATCH", "DELETE"}:
        return True
    # Opening/editing datasource configuration page is a write-intent UI path.
    if p.startswith("/grafana/connections/datasources/edit/"):
        return True
    return False


async def _enforce_writable_datasource(service, datasource_uid: str) -> None:
    datasource = await service.grafana_service.get_datasource(datasource_uid)
    if datasource and (bool(getattr(datasource, "is_default", False)) or bool(getattr(datasource, "read_only", False))):
        raise HTTPException(status_code=403, detail="Default/read-only datasources are view/query only")


def is_admin_user(service, token_data: TokenData) -> bool:
    return token_data.role == Role.ADMIN or token_data.is_superuser


def is_resource_accessible(service, resource, token_data: TokenData, *, require_write: bool = False) -> bool:
    if not resource:
        return False

    if resource.tenant_id != token_data.tenant_id:
        return False

    hidden_by = getattr(resource, "hidden_by", None) or []
    if token_data.user_id in hidden_by:
        return False

    if is_admin_user(service, token_data):
        return True

    if resource.created_by == token_data.user_id:
        return True

    # Grafana default/read-only datasources are tenant-wide query/read resources.
    if not require_write and (bool(getattr(resource, "is_default", False)) or bool(getattr(resource, "read_only", False))):
        return True

    if require_write:
        return False

    visibility = getattr(resource, "visibility", "private") or "private"
    if visibility == "tenant":
        return True

    if visibility == "group":
        user_group_ids = set(token_data.group_ids or [])
        resource_group_ids = {group.id for group in (resource.shared_groups or [])}
        return bool(user_group_ids.intersection(resource_group_ids))

    return False


def extract_dashboard_uid(service, path: str) -> Optional[str]:
    patterns = [
        r"^/grafana/d/([^/]+)",
        r"^/grafana/d-solo/([^/]+)",
        r"^/grafana/api/dashboards/uid/([^/?]+)",
    ]
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


def extract_datasource_uid(service, path: str) -> Optional[str]:
    patterns = [
        r"^/grafana/api/datasources/uid/([^/?]+)",
        r"^/grafana/api/datasources/proxy/uid/([^/?]+)",
        r"^/grafana/connections/datasources/edit/([^/?]+)",
    ]
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


def extract_datasource_id(service, path: str) -> Optional[int]:
    patterns = [
        r"^/grafana/api/datasources/proxy/(\d+)(?:/|$)",
    ]
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def extract_proxy_token(service, request, token: Optional[str] = None) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]

    cookie_token = request.cookies.get("beobservant_token")
    if cookie_token:
        return cookie_token

    access_token = request.cookies.get("access_token")
    if access_token:
        return access_token

    return request.headers.get("X-Auth-Token") or token


async def authorize_proxy_request(
    service,
    request,
    db: Session,
    auth_service,
    token: Optional[str] = None,
    orig: Optional[str] = None,
) -> Dict[str, str]:
    token_to_verify = extract_proxy_token(service, request, token)
    if not token_to_verify:
        raise HTTPException(status_code=401, detail="You need to log in to access this resource.")

    token_data = auth_service.decode_token(token_to_verify)
    if not token_data:
        raise HTTPException(status_code=401, detail="Your session has expired or your token is invalid. Let's get you a new one.")

    if isinstance(token_data, dict):
        token_data = TokenData(**token_data)

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
    if not user_permissions.intersection(allowed_grafana_perms) and not token_data.is_superuser:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    is_admin = is_admin_user(service, token_data)
    original_uri = orig or request.headers.get("X-Original-URI", "")
    original_method = (request.headers.get("X-Original-Method") or request.method or "GET").upper()
    original_path = original_uri.split("?", 1)[0] if original_uri else ""
    if not original_path:
        raise HTTPException(status_code=400, detail="Missing original URI context")

    required_permissions = _required_permissions_for_path(original_path, original_method)

    if not is_admin and _is_dashboard_save_request(original_path, original_method):
        has_write = Permission.WRITE_DASHBOARDS.value in user_permissions
        has_create = Permission.CREATE_DASHBOARDS.value in user_permissions
        has_update = Permission.UPDATE_DASHBOARDS.value in user_permissions
        if not has_write and not (has_create and has_update):
            raise HTTPException(status_code=403, detail="Insufficient permissions for dashboard create/update")

    if not is_admin and (not required_permissions or not _has_any_permission(token_data, required_permissions)):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this Grafana action")

    if not is_admin:
        dashboard_write_intent = _is_dashboard_write_intent(original_path, original_method)
        datasource_write_intent = _is_datasource_write_intent(original_path, original_method)

        dashboard_uid = extract_dashboard_uid(service, original_path)
        if dashboard_uid:
            dashboard = db.query(GrafanaDashboard).options(joinedload(GrafanaDashboard.shared_groups)).filter(
                GrafanaDashboard.grafana_uid == dashboard_uid
            ).first()
            if dashboard:
                if not is_resource_accessible(service, dashboard, token_data, require_write=dashboard_write_intent):
                    raise HTTPException(status_code=403, detail="Dashboard access denied")
            elif dashboard_write_intent:
                raise HTTPException(status_code=403, detail="Dashboard write denied: unregistered dashboard")

        datasource_uid = extract_datasource_uid(service, original_path)
        if datasource_uid:
            datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(
                GrafanaDatasource.grafana_uid == datasource_uid
            ).first()
            if datasource:
                if not is_resource_accessible(service, datasource, token_data, require_write=datasource_write_intent):
                    raise HTTPException(status_code=403, detail="Datasource access denied")
                if datasource_write_intent:
                    await _enforce_writable_datasource(service, datasource.grafana_uid)
            elif datasource_write_intent:
                raise HTTPException(status_code=403, detail="Datasource write denied: unregistered datasource")

        datasource_id = extract_datasource_id(service, original_path)
        if datasource_id is not None:
            datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(
                GrafanaDatasource.grafana_id == datasource_id
            ).first()
            if datasource:
                if not is_resource_accessible(service, datasource, token_data, require_write=datasource_write_intent):
                    raise HTTPException(status_code=403, detail="Datasource access denied")
                if datasource_write_intent:
                    await _enforce_writable_datasource(service, datasource.grafana_uid)
            elif datasource_write_intent:
                raise HTTPException(status_code=403, detail="Datasource write denied: unregistered datasource")

    grafana_role = "Viewer"
    if is_admin:
        grafana_role = "Admin"
    elif user_permissions.intersection({
        Permission.CREATE_DASHBOARDS.value,
        Permission.UPDATE_DASHBOARDS.value,
        Permission.DELETE_DASHBOARDS.value,
        Permission.CREATE_DATASOURCES.value,
        Permission.UPDATE_DATASOURCES.value,
        Permission.DELETE_DATASOURCES.value,
        Permission.CREATE_FOLDERS.value,
        Permission.DELETE_FOLDERS.value,
        Permission.WRITE_DASHBOARDS.value,
    }):
        grafana_role = "Editor"

    return {
        "X-WEBAUTH-USER": token_data.username,
        "X-WEBAUTH-TENANT": token_data.tenant_id,
        "X-WEBAUTH-ROLE": grafana_role,
    }
