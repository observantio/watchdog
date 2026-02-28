from typing import Dict, Optional, Union

import httpx

from models.access.auth_models import Token


def _check_local_mfa(service, user, mfa_code: Optional[str]) -> Optional[Union[Token, dict]]:
    if service._needs_mfa_setup(user):
        return service._mfa_setup_challenge(user)
    if getattr(user, "mfa_enabled", False):
        if not mfa_code:
            return {service._MFA_REQUIRED_RESPONSE: True}
        if not service.verify_totp_code(user, mfa_code):
            return None
    return True


def login(service, username: str, password: str, mfa_code: Optional[str] = None) -> Optional[Union[Token, dict]]:
    external_flow = service.is_external_auth_enabled()

    if external_flow:
        if not service.is_password_auth_enabled():
            return None

        try:
            oidc_token = service.oidc_service.exchange_password(username, password)
        except (httpx.HTTPError, ValueError) as exc:
            service.logger.error("OIDC password login failed for user %s: %s", username, type(exc).__name__)
            return None

        access_token = oidc_token.get("access_token") or ""
        id_token = oidc_token.get("id_token") or ""
        if not access_token and not id_token:
            return None

        claims = None
        if id_token:
            claims = service.oidc_service.verify_id_token(id_token, nonce=None)

        if claims is None and access_token:
            userinfo = service.oidc_service.fetch_userinfo(access_token)
            if isinstance(userinfo, dict) and userinfo:
                claims = userinfo

        if claims is None and access_token:
            claims = service.oidc_service.verify_access_token(access_token)

        if not claims:
            return None

        user = service._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None

        # Policy: OIDC is the MFA boundary. Do NOT enforce local MFA here.
        return service.create_access_token(user)

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

        oidc_token = service.oidc_service.exchange_authorization_code(
            code,
            redirect_uri,
            code_verifier=(code_verifier if txn.get("code_challenge") else None),
        )

        access_token = oidc_token.get("access_token") or ""
        id_token = oidc_token.get("id_token") or ""
        if not access_token and not id_token:
            service.logger.warning("OIDC exchange returned no tokens")
            return None

        expected_nonce = str(txn.get("nonce") or "").strip()

        claims = None
        if id_token:
            claims = service.oidc_service.verify_id_token(id_token, nonce=expected_nonce)
            if not claims:
                service.logger.warning("OIDC id_token validation failed during authorization code exchange")
                return None

        if claims is None:
            if access_token:
                userinfo = service.oidc_service.fetch_userinfo(access_token)
                if isinstance(userinfo, dict) and userinfo:
                    claims = userinfo

            if claims is None and access_token:
                claims = service.oidc_service.verify_access_token(access_token)

            if not claims:
                service.logger.warning("OIDC claims resolution failed")
                return None

            if expected_nonce:
                service.logger.warning("OIDC nonce could not be enforced (no id_token). Rejecting.")
                return None

        user = service._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None

        # Policy: OIDC is the MFA boundary. Do NOT enforce local MFA here.
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