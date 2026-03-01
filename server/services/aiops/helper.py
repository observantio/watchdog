"""
Utility functions for AIOps services.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
"""

from typing import Optional, Dict, Any
from fastapi import Request

def inject_tenant(payload: Optional[Dict[str, Any]], tenant_id: str) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(payload or {})
    data["tenant_id"] = tenant_id
    return data


def correlation_id(request: Request) -> Optional[str]:
    return request.headers.get("x-correlation-id") or request.headers.get("X-Correlation-ID")
