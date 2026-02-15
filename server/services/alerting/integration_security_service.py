"""Alertmanager integration security and tenant-scoped helper operations."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException, status

from config import config
from database import get_db_session
from db_models import Tenant, User, Group, AlertIncident as AlertIncidentDB
from models.access.auth_models import TokenData, Role


def _tenant_id_from_scope_header(scoped_header: Optional[str]) -> str:
    candidate = (scoped_header.split("|")[0].strip() if scoped_header else None) or config.DEFAULT_ORG_ID

    with get_db_session() as db:
        tenant = db.query(Tenant).filter(Tenant.id == candidate).first()
        if tenant:
            return tenant.id

        user = db.query(User).filter(User.org_id == candidate).first()
        if user:
            return user.tenant_id

        tenant = db.query(Tenant).filter(Tenant.name == candidate).first()
        if tenant:
            return tenant.id

        default = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        return default.id if default else config.DEFAULT_ADMIN_TENANT


def _encrypt_tenant_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if not config.DATA_ENCRYPTION_KEY:
        return value
    try:
        fernet = Fernet(config.DATA_ENCRYPTION_KEY)
        return f"enc:{fernet.encrypt(value.encode()).decode()}"
    except Exception:
        return value


def _decrypt_tenant_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value)
    if not text.startswith("enc:"):
        return text
    token = text[4:]
    if not config.DATA_ENCRYPTION_KEY:
        return None
    try:
        fernet = Fernet(config.DATA_ENCRYPTION_KEY)
        return fernet.decrypt(token.encode()).decode()
    except Exception:
        return None


def _load_tenant_jira_config(tenant_id: str) -> Dict[str, Optional[str]]:
    with get_db_session() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        settings = tenant.settings or {} if tenant else {}
        raw_jira = settings.get("jira") if isinstance(settings, dict) else {}
        if not isinstance(raw_jira, dict):
            raw_jira = {}
        return {
            "enabled": bool(raw_jira.get("enabled", False)),
            "base_url": str(raw_jira.get("base_url") or raw_jira.get("baseUrl") or "").strip() or None,
            "email": str(raw_jira.get("email") or "").strip() or None,
            "api_token": _decrypt_tenant_secret(raw_jira.get("api_token")) or None,
            "bearer": _decrypt_tenant_secret(raw_jira.get("bearer")) or None,
        }


def _save_tenant_jira_config(
    tenant_id: str,
    *,
    enabled: bool,
    base_url: Optional[str],
    email: Optional[str],
    api_token: Optional[str],
    bearer: Optional[str],
) -> Dict[str, object]:
    with get_db_session() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        settings = tenant.settings or {}
        if not isinstance(settings, dict):
            settings = {}

        jira_cfg = {
            "enabled": bool(enabled),
            "base_url": str(base_url or "").strip() or None,
            "email": str(email or "").strip() or None,
            "api_token": _encrypt_tenant_secret(str(api_token or "").strip() or None),
            "bearer": _encrypt_tenant_secret(str(bearer or "").strip() or None),
        }
        settings["jira"] = jira_cfg
        tenant.settings = settings
        db.flush()
        return {
            "enabled": jira_cfg["enabled"],
            "baseUrl": jira_cfg["base_url"],
            "email": jira_cfg["email"],
            "hasApiToken": bool(jira_cfg["api_token"]),
            "hasBearerToken": bool(jira_cfg["bearer"]),
        }


def _get_effective_jira_credentials(tenant_id: str) -> Dict[str, Optional[str]]:
    tenant_cfg = _load_tenant_jira_config(tenant_id)
    if tenant_cfg.get("enabled") and tenant_cfg.get("base_url") and (tenant_cfg.get("api_token") or tenant_cfg.get("bearer")):
        return tenant_cfg
    return {}


def _jira_is_enabled_for_tenant(tenant_id: str) -> bool:
    credentials = _get_effective_jira_credentials(tenant_id)
    return bool(credentials.get("base_url") and (credentials.get("api_token") or credentials.get("bearer")))


def _allowed_channel_types() -> List[str]:
    return [channel_type.lower() for channel_type in (config.ENABLED_NOTIFICATION_CHANNEL_TYPES or [])]


def _normalize_visibility(value: Optional[str], default_value: str = "private") -> str:
    normalized = str(value or default_value).strip().lower()
    if normalized in {"tenant", "group", "private"}:
        return normalized
    if normalized == "public":
        return "tenant"
    return default_value


def _load_tenant_jira_integrations(tenant_id: str) -> List[Dict[str, object]]:
    with get_db_session() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        settings = tenant.settings or {} if tenant else {}
        raw_items = settings.get("jira_integrations", []) if isinstance(settings, dict) else []
        if not isinstance(raw_items, list):
            return []
        return [item for item in raw_items if isinstance(item, dict)]


def _save_tenant_jira_integrations(tenant_id: str, items: List[Dict[str, object]]) -> None:
    with get_db_session() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        settings = tenant.settings or {}
        if not isinstance(settings, dict):
            settings = {}
        settings["jira_integrations"] = items
        tenant.settings = settings
        db.flush()


def _validate_shared_group_ids_for_user(
    tenant_id: str,
    shared_group_ids: List[str],
    current_user: TokenData,
) -> List[str]:
    normalized = [str(group_id).strip() for group_id in (shared_group_ids or []) if str(group_id).strip()]
    if not normalized:
        return []

    with get_db_session() as db:
        groups = db.query(Group).filter(Group.tenant_id == tenant_id, Group.id.in_(normalized)).all()
        found_ids = {group.id for group in groups}
        missing = sorted(set(normalized) - found_ids)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid group ids: {missing}",
            )

    is_admin = bool(
        getattr(current_user, "is_superuser", False)
        or getattr(current_user, "role", None) == Role.ADMIN
    )
    if not is_admin:
        actor_groups = set(getattr(current_user, "group_ids", []) or [])
        unauthorized = sorted({group_id for group_id in normalized if group_id not in actor_groups})
        if unauthorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User not member of groups: {unauthorized}",
            )

    return normalized


def _jira_integration_has_access(item: Dict[str, object], current_user: TokenData, *, write: bool = False) -> bool:
    created_by = str(item.get("createdBy") or "")
    if created_by and created_by == current_user.user_id:
        return True
    if write:
        return False
    visibility = _normalize_visibility(str(item.get("visibility") or "private"), "private")
    if visibility == "tenant":
        return True
    if visibility == "group":
        shared_group_ids = [
            str(group_id)
            for group_id in (item.get("sharedGroupIds") or [])
            if isinstance(group_id, str) and group_id.strip()
        ]
        user_groups = getattr(current_user, "group_ids", []) or []
        return bool(set(shared_group_ids) & set(user_groups))
    return False


def _mask_jira_integration(item: Dict[str, object], current_user: TokenData) -> Dict[str, object]:
    is_owner = str(item.get("createdBy") or "") == current_user.user_id
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "enabled": bool(item.get("enabled", True)),
        "visibility": _normalize_visibility(str(item.get("visibility") or "private"), "private"),
        "sharedGroupIds": item.get("sharedGroupIds") or [],
        "createdBy": item.get("createdBy"),
        "authMode": item.get("authMode") or "api_token",
        "baseUrl": item.get("baseUrl") if is_owner else None,
        "email": item.get("email") if is_owner else None,
        "hasApiToken": bool(item.get("apiToken")),
        "hasBearerToken": bool(item.get("bearerToken")),
        "supportsSso": bool(item.get("supportsSso", False)),
    }


def _resolve_jira_integration(
    tenant_id: str,
    integration_id: str,
    current_user: TokenData,
    *,
    require_write: bool = False,
) -> Dict[str, object]:
    integrations = _load_tenant_jira_integrations(tenant_id)
    match = next((item for item in integrations if str(item.get("id")) == integration_id), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira integration not found")
    if not _jira_integration_has_access(match, current_user, write=require_write):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira integration not found")
    return match


def _jira_integration_credentials(item: Dict[str, object]) -> Dict[str, Optional[str]]:
    return {
        "base_url": str(item.get("baseUrl") or "").strip() or None,
        "email": str(item.get("email") or "").strip() or None,
        "api_token": _decrypt_tenant_secret(item.get("apiToken")) or None,
        "bearer": _decrypt_tenant_secret(item.get("bearerToken")) or None,
    }


def _integration_is_usable(item: Dict[str, object]) -> bool:
    if not bool(item.get("enabled", True)):
        return False
    credentials = _jira_integration_credentials(item)
    return bool(credentials.get("base_url") and (credentials.get("api_token") or credentials.get("bearer")))


def _sync_jira_comments_to_incident_notes(incident_id: str, tenant_id: str, comments: List[Dict[str, object]]) -> int:
    if not comments:
        return 0
    with get_db_session() as db:
        incident = (
            db.query(AlertIncidentDB)
            .filter(AlertIncidentDB.id == incident_id, AlertIncidentDB.tenant_id == tenant_id)
            .first()
        )
        if not incident:
            return 0

        notes = list(incident.notes or [])
        existing_comment_ids = {
            str(note.get("jiraCommentId"))
            for note in notes
            if isinstance(note, dict) and note.get("jiraCommentId")
        }
        appended = 0
        for comment in comments:
            comment_id = str(comment.get("id") or "").strip()
            if not comment_id or comment_id in existing_comment_ids:
                continue
            notes.append(
                {
                    "author": f"jira:{str(comment.get('author') or 'jira')}",
                    "text": str(comment.get("body") or ""),
                    "createdAt": str(comment.get("created") or datetime.now(timezone.utc).isoformat()),
                    "jiraCommentId": comment_id,
                }
            )
            existing_comment_ids.add(comment_id)
            appended += 1

        if appended:
            incident.notes = notes
            db.flush()
        return appended