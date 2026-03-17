"""
Authentication endpoints for Watchdog access management.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from fastapi import HTTPException, Request, Response, status

from config import config
from database import get_db_session
from db_models import Tenant
from middleware.dependencies import auth_service
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import (
    AuthModeResponse,
    OIDCAuthURLRequest,
    OIDCAuthURLResponse,
    OIDCCodeExchangeRequest,
    Token,
)
from models.access.user_models import LoginRequest, RegisterRequest, UserCreate, UserResponse
from services.auth.helper import clear_auth_cookie, role_permission_strings, set_auth_cookie, rate_limit_func

from .shared import logger, notification_service, router, rtp


@router.get("/mode", response_model=AuthModeResponse)
async def auth_mode() -> AuthModeResponse:
    oidc_enabled = await rtp(auth_service.is_external_auth_enabled)
    password_enabled = await rtp(auth_service.is_password_auth_enabled) if oidc_enabled else True
    return AuthModeResponse(
        provider=config.AUTH_PROVIDER,
        oidc_enabled=oidc_enabled,
        password_enabled=password_enabled,
        registration_enabled=not oidc_enabled,
        oidc_scopes=config.OIDC_SCOPES,
    )


@router.post("/login", response_model=Token)
async def login(request: Request, login_request: LoginRequest, response: Response) -> Token:
    rate_limit_func(request, "auth_login", config.RATE_LIMIT_LOGIN_PER_MINUTE, 60)
    token_or_challenge = await rtp(
        auth_service.login,
        login_request.username,
        login_request.password,
        getattr(login_request, "mfa_code", None),
    )
    if not token_or_challenge:
        if await rtp(auth_service.is_external_auth_enabled) and not await rtp(auth_service.is_password_auth_enabled):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password login is disabled. Use OIDC login.")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password or invalid MFA code",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if isinstance(token_or_challenge, dict):
        if token_or_challenge.get("mfa_required"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA required")
        if token_or_challenge.get("mfa_setup_required"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=token_or_challenge)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication challenge could not be completed")
    set_auth_cookie(request, response, token_or_challenge.access_token)
    return token_or_challenge


@router.post("/oidc/authorize-url", response_model=OIDCAuthURLResponse)
async def oidc_authorize_url(request: Request, payload: OIDCAuthURLRequest) -> OIDCAuthURLResponse:
    rate_limit_func(request, "auth_oidc_authorize", config.RATE_LIMIT_LOGIN_PER_MINUTE, 60)
    if not await rtp(auth_service.is_external_auth_enabled):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OIDC is not enabled")
    try:
        session = await rtp(
            auth_service.get_oidc_authorization_url,
            payload.redirect_uri,
            payload.state,
            payload.nonce,
            payload.code_challenge,
            payload.code_challenge_method,
        )
        return OIDCAuthURLResponse(**session)
    except ValueError as exc:
        logger.error("Failed to build OIDC authorization URL: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to initialize OIDC login") from exc


@router.post("/oidc/exchange", response_model=Token)
async def oidc_exchange_token(request: Request, payload: OIDCCodeExchangeRequest, response: Response) -> Token:
    rate_limit_func(request, "auth_oidc_exchange", config.RATE_LIMIT_LOGIN_PER_MINUTE, 60)
    if not await rtp(auth_service.is_external_auth_enabled):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OIDC is not enabled")
    try:
        token_or_challenge = await rtp(
            auth_service.exchange_oidc_authorization_code,
            payload.code,
            payload.redirect_uri,
            payload.transaction_id,
            payload.state,
            payload.code_verifier,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc) or "OIDC authentication failed") from exc
    except (OSError, RuntimeError) as exc:
        logger.exception("OIDC exchange failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC authentication failed") from exc
    if not token_or_challenge:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC authentication failed")
    if isinstance(token_or_challenge, dict) and token_or_challenge.get("mfa_setup_required"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=token_or_challenge)
    if isinstance(token_or_challenge, dict):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC authentication challenge could not be completed")
    set_auth_cookie(request, response, token_or_challenge.access_token)
    return token_or_challenge


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    clear_auth_cookie(request, response)
    return {"message": "Logged out"}


@router.post("/register", response_model=UserResponse)
@handle_route_errors()
async def register(request: Request, register_request: RegisterRequest) -> UserResponse:
    if await rtp(auth_service.is_external_auth_enabled):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is managed by the external identity provider")
    rate_limit_func(request, "auth_register", config.RATE_LIMIT_REGISTER_PER_HOUR, 3600)

    def _default_tenant_id() -> str:
        with get_db_session() as db:
            tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
            return tenant.id if tenant else config.DEFAULT_ADMIN_TENANT

    tenant_id = await rtp(_default_tenant_id)
    user = await rtp(
        auth_service.create_user,
        UserCreate(
            username=register_request.username,
            email=register_request.email,
            password=register_request.password,
            full_name=register_request.full_name,
        ),
        tenant_id,
    )
    await notification_service.send_user_welcome_email(
        recipient_email=user.email,
        username=user.username,
        full_name=user.full_name,
        login_url=None,
    )
    return await rtp(auth_service.build_user_response, user, role_permission_strings(user.role))
