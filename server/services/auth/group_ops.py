"""
Group operations for managing user groups, including creating, updating, deleting groups, and managing group memberships and permissions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from database import get_db_session
from db_models import Group, Permission, User
from models.access.group_models import GroupCreate, GroupUpdate, Group as GroupSchema

_MUTABLE_GROUP_FIELDS = {"name", "description", "is_active"}


from typing import Optional

def create_group(service, group_create: GroupCreate, tenant_id: str, creator_id: Optional[str] = None) -> GroupSchema:
    with get_db_session() as db:
        if db.query(Group).filter(
            func.lower(Group.name) == group_create.name.strip().lower(),
            Group.tenant_id == tenant_id,
        ).first():
            raise ValueError(f"Group name '{group_create.name}' already exists in this tenant")

        group = Group(
            tenant_id=tenant_id,
            name=group_create.name.strip(),
            description=group_create.description,
            is_active=True,
        )
        db.add(group)
        db.flush()

        if creator_id:
            service._log_audit(db, tenant_id, creator_id, "create_group", "groups", group.id, {
                "name": group.name,
            })

        db.commit()
        group = db.query(Group).options(joinedload(Group.permissions)).filter_by(id=group.id).first()
        return service._to_group_schema(group)


def list_groups(service, tenant_id: str) -> List[GroupSchema]:
    with get_db_session() as db:
        groups = (
            db.query(Group)
            .options(joinedload(Group.permissions))
            .filter_by(tenant_id=tenant_id)
            .all()
        )
        return [service._to_group_schema(g) for g in groups]


def get_group(service, group_id: str, tenant_id: str) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = (
            db.query(Group)
            .options(joinedload(Group.permissions))
            .filter_by(id=group_id, tenant_id=tenant_id)
            .first()
        )
        if not group:
            return None
        return service._to_group_schema(group)


def delete_group(service, group_id: str, tenant_id: str, deleter_id: Optional[str] = None) -> bool:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        if deleter_id:
            service._log_audit(db, tenant_id, deleter_id, "delete_group", "groups", group_id, {
                "name": group.name,
            })

        db.delete(group)
        db.commit()
        return True


def update_group(
    service, group_id: str, group_update: GroupUpdate, tenant_id: str, updater_id: Optional[str] = None
) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return None

        update_data = {
            k: v for k, v in group_update.model_dump(exclude_unset=True).items()
            if k in _MUTABLE_GROUP_FIELDS
        }

        if "name" in update_data:
            name_candidate = update_data["name"].strip().lower()
            conflict = db.query(Group).filter(
                func.lower(Group.name) == name_candidate,
                Group.tenant_id == tenant_id,
                Group.id != group_id,
            ).first()
            if conflict:
                raise ValueError(f"Group name '{update_data['name']}' already exists in this tenant")
            update_data["name"] = update_data["name"].strip()

        for field, value in update_data.items():
            setattr(group, field, value)

        group.updated_at = datetime.now(timezone.utc)

        if updater_id:
            service._log_audit(db, tenant_id, updater_id, "update_group", "groups", group_id, update_data)

        db.commit()
        group = db.query(Group).options(joinedload(Group.permissions)).filter_by(id=group_id).first()
        return service._to_group_schema(group)


def update_group_permissions(
    service, group_id: str, permission_names: List[str], tenant_id: str
) -> bool:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        known_names = {
            name for (name,) in db.query(Permission.name).filter(Permission.name.in_(permission_names)).all()
        }
        unknown = set(permission_names) - known_names
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")

        permissions = db.query(Permission).filter(Permission.name.in_(known_names)).all()
        group.permissions = permissions

        service._log_audit(db, tenant_id, None, "update_group_permissions", "groups", group_id, {
            "permissions": list(known_names),
        })

        db.commit()
        return True


def update_group_members(service, group_id: str, user_ids: List[str], tenant_id: str) -> bool:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        members = []
        if user_ids:
            members = db.query(User).filter(
                and_(
                    User.id.in_(user_ids),
                    User.tenant_id == tenant_id,
                )
            ).all()
            found_ids = {str(u.id) for u in members}
            missing = set(user_ids) - found_ids
            if missing:
                raise ValueError(f"Users not found in tenant: {sorted(missing)}")

        group.members = members

        service._log_audit(db, tenant_id, None, "update_group_members", "groups", group_id, {
            "user_ids": user_ids,
        })

        db.commit()
        return True