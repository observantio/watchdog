"""
Folder operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from config import config
from db_models import GrafanaFolder, Group
from models.grafana.grafana_folder_models import Folder
from services.grafana.grafana_service import GrafanaAPIError


def _group_id_strs(group_ids: List[str]) -> List[str]:
    return [str(g) for g in (group_ids or [])]


def _db_folder_by_uid(db: Session, tenant_id: str, uid: str) -> Optional[GrafanaFolder]:
    return (
        db.query(GrafanaFolder)
        .filter(GrafanaFolder.tenant_id == tenant_id, GrafanaFolder.grafana_uid == uid)
        .first()
    )


def check_folder_access(
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    require_write: bool = False,
    is_admin: bool = False,
) -> Optional[GrafanaFolder]:
    folder = _db_folder_by_uid(db, tenant_id, uid)
    if not folder:
        return None
    if folder.created_by == user_id:
        return folder
    if require_write:
        return None
    if folder.visibility == "tenant":
        return folder
    if folder.visibility == "group":
        allowed = set(_group_id_strs(group_ids))
        shared = {str(g.id) for g in (folder.shared_groups or [])}
        return folder if allowed.intersection(shared) else None
    return None


def is_folder_accessible(
    db: Session,
    uid: Optional[str],
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    require_write: bool = False,
    is_admin: bool = False,
) -> bool:
    if not uid:
        return True
    db_folder = _db_folder_by_uid(db, tenant_id, uid)
    if db_folder is None:
        return False
    folder = check_folder_access(
        db, uid, user_id, tenant_id, group_ids, require_write=require_write, is_admin=is_admin,
    )
    return folder is not None


def _folder_payload(folder_obj, *, db_folder: Optional[GrafanaFolder], user_id: str) -> Dict:
    if hasattr(folder_obj, "model_dump"):
        payload = folder_obj.model_dump()
    elif isinstance(folder_obj, dict):
        payload = dict(folder_obj)
    else:
        payload = dict(vars(folder_obj))
    payload["created_by"] = db_folder.created_by if db_folder else None
    payload["visibility"] = (db_folder.visibility if db_folder else "tenant") or "tenant"
    payload["sharedGroupIds"] = [str(g.id) for g in (db_folder.shared_groups or [])] if db_folder else []
    payload["is_owned"] = bool(db_folder and db_folder.created_by == user_id)
    return payload


async def get_folders(
    service,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    is_admin: bool = False,
) -> List[Folder]:
    folders = await service.grafana_service.get_folders()
    db_rows = (
        db.query(GrafanaFolder)
        .filter(GrafanaFolder.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    db_map = {f.grafana_uid: f for f in db_rows}

    out: List[Folder] = []
    for folder in folders:
        uid = str(getattr(folder, "uid", "") or "")
        db_folder = db_map.get(uid)
        if not db_folder:
            continue
        if not check_folder_access(
            db, uid, user_id, tenant_id, group_ids, require_write=False, is_admin=is_admin,
        ):
            continue
        out.append(Folder.model_validate(_folder_payload(folder, db_folder=db_folder, user_id=user_id)))
    return out


async def get_folder(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    is_admin: bool = False,
) -> Optional[Folder]:
    db_folder = _db_folder_by_uid(db, tenant_id, uid)
    if not db_folder:
        return None
    if not check_folder_access(
        db, uid, user_id, tenant_id, group_ids, require_write=False, is_admin=is_admin,
    ):
        return None
    folder = await service.grafana_service.get_folder(uid)
    if not folder:
        return None
    return Folder.model_validate(_folder_payload(folder, db_folder=db_folder, user_id=user_id))


async def create_folder(
    service,
    db: Session,
    title: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    visibility: str = "private",
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
) -> Optional[Folder]:
    groups = []
    if visibility == "group":
        groups = service._validate_group_visibility(
            db, tenant_id=tenant_id, group_ids=group_ids,
            shared_group_ids=shared_group_ids, is_admin=is_admin,
        )

    created = await service.grafana_service.create_folder(title)
    if not created:
        return None

    uid = str(getattr(created, "uid", "") or "")
    if not uid:
        return created

    db_folder = GrafanaFolder(
        tenant_id=tenant_id,
        created_by=user_id,
        grafana_uid=uid,
        grafana_id=getattr(created, "id", None),
        title=str(getattr(created, "title", title) or title),
        visibility=visibility or "private",
    )
    if visibility == "group" and shared_group_ids:
        db_folder.shared_groups.extend(groups)

    try:
        db.add(db_folder)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Folder.model_validate(_folder_payload(created, db_folder=db_folder, user_id=user_id))


async def update_folder(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    title: Optional[str] = None,
    visibility: Optional[str] = None,
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
) -> Optional[Folder]:
    db_folder = _db_folder_by_uid(db, tenant_id, uid)
    if not db_folder:
        return None
    if not check_folder_access(
        db, uid, user_id, tenant_id, group_ids, require_write=True, is_admin=is_admin,
    ):
        return None

    new_title = str(title or db_folder.title).strip()
    try:
        updated = await service.grafana_service.update_folder(uid, new_title)
    except Exception as exc:
        if isinstance(exc, GrafanaAPIError) and exc.status == 412:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=409,
                detail="Folder changed by another request; reload folders and retry.",
            )
        service._raise_http_from_grafana_error(exc)
        return None
    if not updated:
        return None

    db_folder.title = str(getattr(updated, "title", new_title) or new_title)
    if visibility:
        db_folder.visibility = visibility
        if visibility == "group":
            groups = service._validate_group_visibility(
                db, tenant_id=tenant_id, group_ids=group_ids,
                shared_group_ids=shared_group_ids, is_admin=is_admin,
            )
            db_folder.shared_groups.clear()
            db_folder.shared_groups.extend(groups)
        else:
            db_folder.shared_groups.clear()

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Folder.model_validate(_folder_payload(updated, db_folder=db_folder, user_id=user_id))


async def delete_folder(
    service,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    *,
    is_admin: bool = False,
) -> bool:
    db_folder = _db_folder_by_uid(db, tenant_id, uid)
    if not db_folder:
        return False
    if not check_folder_access(
        db, uid, user_id, tenant_id, group_ids, require_write=True, is_admin=is_admin,
    ):
        return False

    ok = await service.grafana_service.delete_folder(uid)
    if not ok:
        return False

    if db_folder:
        try:
            db.delete(db_folder)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return True
