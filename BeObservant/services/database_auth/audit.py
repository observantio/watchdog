"""
Database for log and audit utilities for the database authentication service, providing functions to log audit events related to authentication operations such as user creation, group management, and MFA changes. This module defines a common interface for logging audit events in the database, allowing for consistent tracking of important actions and changes within the authentication service while ensuring that relevant information is captured for auditing purposes.
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Optional

from sqlalchemy.orm import Session

from custom_types.json import JSONDict
from db_models import AuditLog
from services.audit_context import get_request_audit_context

def log_audit(
    db: Session,
    tenant_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: JSONDict,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    ctx_ip, ctx_user_agent = get_request_audit_context()
    db.add(AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address or ctx_ip,
        user_agent=user_agent or ctx_user_agent,
    ))
