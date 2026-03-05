"""
Audit log endpoints for Be Observant authentication router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import aliased

from config import config
from database import get_db_session
from db_models import AuditLog, User
from models.access.auth_models import TokenData
from services.audit_context import get_request_audit_context
from services.auth.helper import (
    apply_audit_filters_func,
    build_audit_log_query,
    require_admin_with_audit_permission,
    sanitize_audit_details,
    sanitize_resource_id,
)

from .shared import router, rtp


@router.get("/audit-logs")
async def list_audit_logs(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_admin_with_audit_permission),
):
    actor = aliased(User)

    def _query():
        with get_db_session() as db:
            q_obj = apply_audit_filters_func(
                build_audit_log_query(db, current_user, tenant_id, actor),
                start,
                end,
                user_id,
                action,
                resource_type,
                q,
            )
            rows = q_obj.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
            items = [
                {
                    "id": log.id,
                    "tenant_id": log.tenant_id,
                    "user_id": log.user_id,
                    "username": username,
                    "email": email,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": sanitize_resource_id(log.resource_id),
                    "details": sanitize_audit_details(log.details),
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "created_at": log.created_at,
                }
                for log, username, email in rows
            ]
            ip_address, user_agent = get_request_audit_context()
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
            already_logged = (
                db.query(AuditLog.id)
                .filter(
                    AuditLog.tenant_id == current_user.tenant_id,
                    AuditLog.user_id == current_user.user_id,
                    AuditLog.action == "audit_logs.view",
                    AuditLog.resource_type == "audit_logs",
                    AuditLog.resource_id == "list",
                    AuditLog.created_at >= cutoff,
                )
                .first()
            )
            if not already_logged:
                db.add(
                    AuditLog(
                        tenant_id=current_user.tenant_id,
                        user_id=current_user.user_id,
                        action="audit_logs.view",
                        resource_type="audit_logs",
                        resource_id="list",
                        details={"limit": limit, "offset": offset},
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                )
            return items

    return await rtp(_query)


@router.get("/audit-logs/export")
async def export_audit_logs_csv(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(require_admin_with_audit_permission),
):
    actor = aliased(User)

    def _export():
        with get_db_session() as db:
            q_obj = apply_audit_filters_func(
                build_audit_log_query(db, current_user, tenant_id, actor),
                start,
                end,
                user_id,
                action,
                resource_type,
            )
            rows = q_obj.order_by(AuditLog.created_at.desc()).all()
            ip_address, user_agent = get_request_audit_context()
            db.add(
                AuditLog(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.user_id,
                    action="audit_logs.export",
                    resource_type="audit_logs",
                    resource_id="csv",
                    details={"count": len(rows)},
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            return rows

    rows = await rtp(_export)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "created_at",
            "tenant_id",
            "user_id",
            "username",
            "email",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "user_agent",
            "details",
        ]
    )
    for log, username, email in rows:
        writer.writerow(
            [
                log.id,
                log.created_at.isoformat() if log.created_at else "",
                log.tenant_id or "",
                log.user_id or "",
                username or "",
                email or "",
                log.action,
                log.resource_type,
                sanitize_resource_id(log.resource_id) or "",
                log.ip_address or "",
                log.user_agent or "",
                json.dumps(sanitize_audit_details(log.details)),
            ]
        )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )
