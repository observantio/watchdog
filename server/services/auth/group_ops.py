"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Group-related operations for DatabaseAuthService.

Includes group creation, listing, updating, deletion, and permission/member management.
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from database import get_db_session
from db_models import Group, Permission, User
from models.access.group_models import GroupCreate, GroupUpdate, Group as GroupSchema


def create_group(service, group_create: GroupCreate, tenant_id: str, creator_id: str = None) -> GroupSchema:
    with get_db_session() as db:
        group = Group(
            tenant_id=tenant_id,
            name=group_create.name,
            description=group_create.description,
            is_active=True
        )

        db.add(group)
        db.flush()

        if creator_id:
            service._log_audit(db, tenant_id, creator_id, "create_group", "groups", group.id, {
                "name": group.name
            })

        db.commit()
        group = db.query(Group).options(
            joinedload(Group.permissions)
        ).filter_by(id=group.id).first()
        return service._to_group_schema(group)


def list_groups(service, tenant_id: str) -> List[GroupSchema]:
    with get_db_session() as db:
        groups = db.query(Group).options(joinedload(Group.permissions)).filter_by(tenant_id=tenant_id).all()
        return [service._to_group_schema(group) for group in groups]


def get_group(service, group_id: str, tenant_id: str) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = db.query(Group).options(joinedload(Group.permissions)).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return None
        return service._to_group_schema(group)


def delete_group(service, group_id: str, tenant_id: str, deleter_id: str = None) -> bool:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()

        if not group:
            return False

        if deleter_id:
            service._log_audit(db, tenant_id, deleter_id, "delete_group", "groups", group_id, {
                "name": group.name
            })

        db.delete(group)
        db.commit()
        return True


def update_group(service, group_id: str, group_update: GroupUpdate, tenant_id: str, updater_id: str = None) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return None

        update_data = group_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(group, field, value)

        group.updated_at = datetime.now(timezone.utc)

        if updater_id:
            service._log_audit(db, tenant_id, updater_id, "update_group", "groups", group_id, update_data)

        db.commit()
        group = db.query(Group).options(
            joinedload(Group.permissions)
        ).filter_by(id=group_id).first()
        return service._to_group_schema(group)


def update_group_permissions(service, group_id: str, permission_names: List[str], tenant_id: str) -> bool:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        permissions = db.query(Permission).filter(Permission.name.in_(permission_names)).all()
        group.permissions = permissions

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
                    User.tenant_id == tenant_id
                )
            ).all()

        group.members = members
        db.commit()
        return True
