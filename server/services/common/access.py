"""Shared access utilities extracted from storage_db_service.py."""
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from db_models import Group, User
import logging

logger = logging.getLogger(__name__)


def _is_tenant_admin(db: Session, tenant_id: str, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    return bool(user and (getattr(user, "is_superuser", False) or str(getattr(user, "role", "")).lower() == "admin"))


def _resolve_groups(
    db: Session, tenant_id: str, group_ids: List[str], *,
    actor_user_id: Optional[str] = None,
    actor_group_ids: Optional[List[str]] = None,
    enforce_membership: bool = True,
) -> List[Group]:
    normalized = [s for gid in (group_ids or []) if (s := str(gid).strip())]
    if not normalized:
        return []

    groups = db.query(Group).filter(Group.tenant_id == tenant_id, Group.id.in_(normalized)).all()
    missing = sorted(set(normalized) - {g.id for g in groups})
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid group ids: {missing}")

    if enforce_membership and not _is_tenant_admin(db, tenant_id, actor_user_id):
        actor_groups = set(actor_group_ids or [])
        unauthorized = sorted({gid for gid in normalized if gid not in actor_groups})
        if unauthorized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User not member of groups: {unauthorized}")

    return groups


def _assign_shared_groups(db_obj, db: Session, tenant_id: str, visibility: str, group_ids: Optional[List[str]], *, actor_user_id: str, actor_group_ids: Optional[List[str]]):
    if group_ids is None:
        return
    db_obj.shared_groups = (
        _resolve_groups(db, tenant_id, group_ids, actor_user_id=actor_user_id, actor_group_ids=actor_group_ids)
        if visibility == "group" else []
    )


def _has_access(
    visibility: str, created_by: Optional[str], user_id: str,
    shared_group_ids: List[str], user_group_ids: List[str], require_write: bool = False,
) -> bool:
    if created_by == user_id:
        return True
    if require_write:
        return False
    if visibility in ("public", "tenant"):
        return True
    if visibility == "group" and user_group_ids:
        return bool(set(shared_group_ids) & set(user_group_ids))
    return False
