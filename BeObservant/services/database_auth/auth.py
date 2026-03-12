from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, TYPE_CHECKING, Union

import httpx

from config import config
from db_models import User
from models.access.auth_models import Token
from custom_types.json import JSONDict
from services.database_auth.shared import sync_active_user_from_claims

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

AuthResult = Optional[Union[Token, JSONDict]]

@dataclass(frozen=True)
class _OidcTokens:
    access_token: str
    id_token: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "_OidcTokens":
        return cls(
            access_token=str(payload.get("access_token") or ""),
            id_token=str(payload.get("id_token") or ""),
        )

    def is_empty(self) -> bool:
        return not self.access_token and not self.id_token


def _mfa_gate(service: DatabaseAuthService, user: User, mfa_code: Optional[str]) -> Optional[Union[bool, JSONDict, Token]]:
    if service._needs_mfa_setup(user):
        return service._mfa_setup_challenge(user)

    if getattr(user, "mfa_enabled", False):
        if not mfa_code:
            return {service._MFA_REQUIRED_RESPONSE: True}
        if not service.verify_totp_code(user, mfa_code):
            return None

    return True


def _resolve_oidc_claims(service: DatabaseAuthService, *, tokens: _OidcTokens, expected_nonce: str, enforce_nonce: bool) -> Optional[JSONDict]:
    if enforce_nonce and expected_nonce and not tokens.id_token:
        return None

    claims: Optional[JSONDict] = None

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

    return claims


def login(service: DatabaseAuthService, username: str, password: str, mfa_code: Optional[str] = None) -> AuthResult:
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
        user = sync_active_user_from_claims(service, claims)
        if user is None:
            return None

        if not bool(getattr(config, "SKIP_LOCAL_MFA_FOR_EXTERNAL", True)):
            mfa_result = _mfa_gate(service, user, mfa_code)
            if mfa_result is None or isinstance(mfa_result, dict) or isinstance(mfa_result, Token):
                return mfa_result

        token = service.create_access_token(user)
        return token if isinstance(token, Token) else None

    user = service.authenticate_user(username, password)
    if not user:
        return None

    mfa_result = _mfa_gate(service, user, mfa_code)
    if mfa_result is None or isinstance(mfa_result, dict) or isinstance(mfa_result, Token):
        return mfa_result

    token = service.create_access_token(user)
    return token if isinstance(token, Token) else None


def exchange_oidc_authorization_code(
    service: DatabaseAuthService,
    code: str,
    redirect_uri: str,
    transaction_id: Optional[str] = None,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> AuthResult:
    if not service.is_external_auth_enabled():
        return None

    try:
        txn: JSONDict = {}
        if transaction_id or state:
            txn_raw = service.oidc_service.consume_authorization_transaction(
                transaction_id=transaction_id,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
            txn = txn_raw if isinstance(txn_raw, dict) else {}

        tokens_payload = service.oidc_service.exchange_authorization_code(
            code,
            redirect_uri,
            code_verifier=(code_verifier if (txn.get("code_challenge") or code_verifier) else None),
        )

        tokens = _OidcTokens.from_mapping(tokens_payload if isinstance(tokens_payload, dict) else {})
        if tokens.is_empty():
            service.logger.warning("OIDC exchange returned no tokens")
            return None

        nonce_value = txn.get("nonce")
        expected_nonce = nonce_value.strip() if isinstance(nonce_value, str) else ""

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

        token = service.create_access_token(user)
        return token if isinstance(token, Token) else None

    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("OIDC code exchange failed: %s", type(exc).__name__)
        return None


def get_oidc_authorization_url(
    service: DatabaseAuthService,
    redirect_uri: str,
    state: Optional[str] = None,
    nonce: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
) -> Dict[str, str]:
    result = service.oidc_service.start_authorization_transaction(
        redirect_uri=redirect_uri,
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    if not isinstance(result, dict):
        raise ValueError("OIDC authorization transaction did not return a mapping")

    authorization_url = result.get("authorization_url")
    if not isinstance(authorization_url, str) or not authorization_url.strip():
        raise ValueError("OIDC authorization transaction did not return an authorization_url")

    return {str(key): str(value) for key, value in result.items()}


def provision_external_user(service: DatabaseAuthService, *, email: str, username: str, full_name: Optional[str]) -> Optional[str]:
    if not service.is_external_auth_enabled():
        return None
    try:
        result = service.oidc_service.create_keycloak_user(email=email, username=username, full_name=full_name)
        return result if isinstance(result, str) or result is None else str(result)
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("External user provisioning failed for %s: %s", username, type(exc).__name__)
        return None
