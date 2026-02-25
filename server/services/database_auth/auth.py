"""
Authentication utilities for handling user login, token exchange, and external user provisioning in the database authentication service, including functions to authenticate users with either local credentials or external OIDC providers, exchange authorization codes for tokens, and provision new users in the external authentication provider when necessary. This module provides a common interface for performing authentication-related operations within the database authentication service, abstracting away the details of the underlying authentication mechanisms and allowing for flexible support of different authentication configurations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Dict, Optional, Union

import httpx

from config import config
from models.access.auth_models import Token
from services.auth.auth_ops import (
    create_access_token as create_access_token_op,
    validate_otlp_token as validate_otlp_token_op,
)


def _check_local_mfa(
    service, user, mfa_code: Optional[str]
) -> Optional[Union[Token, dict]]:
    if service._needs_mfa_setup(user):
        return service._mfa_setup_challenge(user)
    if getattr(user, "mfa_enabled", False):
        if not mfa_code:
            return {service._MFA_REQUIRED_RESPONSE: True}
        if not service.verify_totp_code(user, mfa_code):
            return None
    return True


def login(
    service, username: str, password: str, mfa_code: Optional[str] = None
) -> Optional[Union[Token, dict]]:
    if service.is_external_auth_enabled():
        if not service.is_password_auth_enabled():
            return None
        try:
            oidc_token = service.oidc_service.exchange_password(username, password)
        except (httpx.HTTPError, ValueError) as exc:
            service.logger.error(
                "OIDC password login failed for user %s: %s", username, type(exc).__name__
            )
            return None
        access_token = oidc_token.get("access_token")
        if not access_token:
            return None
        claims = service.oidc_service.verify_access_token(access_token)
        if not claims:
            return None
        user = service._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None
        mfa_result = _check_local_mfa(service, user, mfa_code)
        if mfa_result is None or isinstance(mfa_result, dict):
            return mfa_result
        return Token(
            access_token=access_token,
            token_type=oidc_token.get("token_type", "bearer"),
            expires_in=int(oidc_token.get("expires_in", config.JWT_EXPIRATION_MINUTES * 60)),
        )

    user = service.authenticate_user(username, password)
    if not user:
        return None
    mfa_result = _check_local_mfa(service, user, mfa_code)
    if mfa_result is None or isinstance(mfa_result, dict):
        return mfa_result
    return service.create_access_token(user)


def exchange_oidc_authorization_code(
    service,
    code: str,
    redirect_uri: str,
    transaction_id: Optional[str] = None,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> Optional[Union[Token, dict]]:
    if not service.is_external_auth_enabled():
        return None
    try:
        txn: Dict[str, str] = {}
        if transaction_id or state:
            txn = service.oidc_service.consume_authorization_transaction(
                transaction_id=transaction_id,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        else:
            service.logger.warning("OIDC exchange received without transaction context; using compatibility fallback")
        oidc_token = service.oidc_service.exchange_authorization_code(
            code,
            redirect_uri,
            code_verifier=(code_verifier if txn.get("code_challenge") else None),
        )
        access_token = oidc_token.get("access_token")
        if not access_token:
            return None
        claims = service.oidc_service.verify_access_token(access_token)
        if not claims:
            return None
        expected_nonce = str(txn.get("nonce") or "").strip()
        token_nonce = str((claims or {}).get("nonce") or "").strip()
        if expected_nonce and token_nonce and expected_nonce != token_nonce:
            service.logger.warning("OIDC nonce mismatch during authorization code exchange")
            return None
        if expected_nonce and not token_nonce:
            service.logger.warning("OIDC token nonce missing during authorization code exchange")
            return None
        user = service._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None
        mfa_result = _check_local_mfa(service, user, None)
        if mfa_result is None or isinstance(mfa_result, dict):
            return mfa_result
        return Token(
            access_token=access_token,
            token_type=oidc_token.get("token_type", "bearer"),
            expires_in=int(oidc_token.get("expires_in", config.JWT_EXPIRATION_MINUTES * 60)),
        )
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("OIDC code exchange failed: %s", type(exc).__name__)
        return None


def get_oidc_authorization_url(
    service,
    redirect_uri: str,
    state: Optional[str] = None,
    nonce: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
) -> Dict[str, str]:
    return service.oidc_service.start_authorization_transaction(
        redirect_uri=redirect_uri,
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )


def provision_external_user(
    service, *, email: str, username: str, full_name: Optional[str]
) -> Optional[str]:
    if not service.is_external_auth_enabled():
        return None
    try:
        return service.oidc_service.create_keycloak_user(
            email=email, username=username, full_name=full_name
        )
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error(
            "External user provisioning failed for %s: %s", username, type(exc).__name__
        )
        return None
