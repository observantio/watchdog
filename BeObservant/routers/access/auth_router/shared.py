"""
Shared components and utilities for Be Observant authentication router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])
notification_service = NotificationService()
rtp = run_in_threadpool
