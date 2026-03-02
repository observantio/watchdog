from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Union

import httpx

from models.access.auth_models import Token

MFARequired = Dict[str, bool]
AuthResult = Optional[Union[Token, MFARequired]]

@dataclass(frozen=True)
class _OidcTokens:
    access_token: str
    id_token: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "_OidcTokens":
        return cls(
            access_token=str(payload.get("access_token") or ""),
            id_token=str(payload.get("id_token") or ""),
        )

    def is_empty(self) -> bool:
        return not self.access_token and not self.id_token


def _mfa_gate(service, user, mfa_code: Optional[str]) -> Optional[Union[bool, MFARequired, Token]]:
    if service._needs_mfa_setup(user):
        return service._mfa_setup_challenge(user)

    if getattr(user, "mfa_enabled", False):
        if not mfa_code:
            return {service._MFA_REQUIRED_RESPONSE: True}
        if not service.verify_totp_code(user, mfa_code):
            return None

    return True


def _resolve_oidc_claims(service, *, tokens: _OidcTokens, expected_nonce: str, enforce_nonce: bool) -> Optional[Dict[str, Any]]:
    claims: Optional[Dict[str, Any]] = None

    if tokens.id_token:
        claims = service.oidc_service.verify_id_token(tokens.id_token, nonce=(expected_nonce or None))
        if not claims:
            return None

    if claims is None and tokens.access_token:
        userinfo = service.oidc_service.fetch_userinfo(tokens.access_token)
        if isinstance(userinfo, dict) and userinfo:
            claims = userinfo

    if claims is None and tokens.access_token:
        claims = service.oidc_service.verify_access_token(tokens.access_token)

    if not claims:
        return None

    if enforce_nonce and expected_nonce and not tokens.id_token:
        return None

    return claims


def login(service, username: str, password: str, mfa_code: Optional[str] = None) -> AuthResult:
    external_flow = service.is_external_auth_enabled()

    if external_flow:
        if not service.is_password_auth_enabled():
            return None

        try:
            oidc_token = service.oidc_service.exchange_password(username, password)
        except (httpx.HTTPError, ValueError) as exc:
            service.logger.error("OIDC password login failed for user %s: %s", username, type(exc).__name__)
            return None

        tokens = _OidcTokens.from_mapping(oidc_token if isinstance(oidc_token, dict) else {})
        if tokens.is_empty():
            return None

        claims = _resolve_oidc_claims(
            service,
            tokens=tokens,
            expected_nonce="",
            enforce_nonce=False,
        )
        if not claims:
            return None

        user = service._sync_user_from_oidc_claims(claims)
        if not user or not getattr(user, "is_active", False):
            return None

        return service.create_access_token(user)

    user = service.authenticate_user(username, password)
    if not user:
        return None

    mfa_result = _mfa_gate(service, user, mfa_code)
    if mfa_result is None or isinstance(mfa_result, dict) or isinstance(mfa_result, Token):
        return mfa_result if mfa_result is not True else service.create_access_token(user)

    return service.create_access_token(user)


def exchange_oidc_authorization_code(
    service,
    code: str,
    redirect_uri: str,
    transaction_id: Optional[str] = None,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> AuthResult:
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
            ) or {}

        tokens_payload = service.oidc_service.exchange_authorization_code(
            code,
            redirect_uri,
            code_verifier=(code_verifier if txn.get("code_challenge") else None),
        )

        tokens = _OidcTokens.from_mapping(tokens_payload if isinstance(tokens_payload, dict) else {})
        if tokens.is_empty():
            service.logger.warning("OIDC exchange returned no tokens")
            return None

        expected_nonce = str(txn.get("nonce") or "").strip()

        claims = _resolve_oidc_claims(
            service,
            tokens=tokens,
            expected_nonce=expected_nonce,
            enforce_nonce=True,
        )
        if not claims:
            if expected_nonce and not tokens.id_token:
                service.logger.warning("OIDC nonce could not be enforced (no id_token). Rejecting.")
            else:
                service.logger.warning("OIDC claims resolution failed")
            return None

        user = service._sync_user_from_oidc_claims(claims)
        if not user or not getattr(user, "is_active", False):
            return None

        return service.create_access_token(user)

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


def provision_external_user(service, *, email: str, username: str, full_name: Optional[str]) -> Optional[str]:
    if not service.is_external_auth_enabled():
        return None
    try:
        return service.oidc_service.create_keycloak_user(email=email, username=username, full_name=full_name)
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("External user provisioning failed for %s: %s", username, type(exc).__name__)
        return None