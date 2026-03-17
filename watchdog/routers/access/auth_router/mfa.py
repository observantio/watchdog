"""
MFA management endpoints for Watchdog authentication router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from middleware.dependencies import (
    auth_service,
    get_current_user_or_mfa_setup,
    require_any_permission_with_scope,
    require_authenticated_with_scope,
)
from models.access.auth_models import Permission, TokenData
from models.access.user_models import MfaDisableRequest, MfaVerifyRequest, RecoveryCodesResponse, TotpEnrollResponse

from .shared import USER_NOT_FOUND, router, rtp


@router.post("/mfa/enroll", response_model=TotpEnrollResponse)
async def mfa_enroll(current_user: TokenData = Depends(get_current_user_or_mfa_setup)) -> TotpEnrollResponse:
    try:
        return TotpEnrollResponse(**(await rtp(auth_service.enroll_totp, current_user.user_id)))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unable to enroll MFA") from exc


@router.post("/mfa/verify", response_model=RecoveryCodesResponse)
async def mfa_verify(payload: MfaVerifyRequest, current_user: TokenData = Depends(get_current_user_or_mfa_setup)) -> RecoveryCodesResponse:
    try:
        codes = await rtp(auth_service.verify_enable_totp, current_user.user_id, payload.code)
        return RecoveryCodesResponse(recovery_codes=codes)
    except ValueError as exc:
        msg = str(exc)
        detail = (
            "TOTP not enrolled for user"
            if "not enrolled" in msg
            else "Invalid TOTP code"
            if "Invalid TOTP code" in msg
            else msg
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail) from exc


@router.post("/mfa/disable")
async def mfa_disable(
    payload: MfaDisableRequest,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
) -> dict[str, str]:
    if not await rtp(
        auth_service.disable_totp,
        current_user.user_id,
        current_password=payload.current_password,
        code=payload.code,
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unable to disable MFA")
    return {"message": "MFA disabled"}


@router.post("/users/{user_id}/mfa/reset")
async def admin_reset_user_mfa(
    user_id: str,
    current_user: TokenData = Depends(require_any_permission_with_scope([Permission.MANAGE_USERS], "auth")),
) -> dict[str, str]:
    if not await rtp(auth_service.reset_totp, user_id, current_user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return {"message": "User MFA reset"}
