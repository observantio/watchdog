"""
OIDC authentication service for validating access tokens, exchanging credentials for tokens, and provisioning users in Keycloak if enabled.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import urlencode

import httpx
import jwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from config import config

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS: Set[str] = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
ALLOWED_CODE_CHALLENGE_METHODS: Set[str] = {"S256", "plain"}


def _jwk_to_verification_key(jwk_key: Dict[str, Any], alg: str):
    jwk_json = json.dumps(jwk_key)
    if alg.startswith("RS"):
        return RSAAlgorithm.from_jwk(jwk_json)
    if alg.startswith("ES"):
        return ECAlgorithm.from_jwk(jwk_json)
    raise ValueError(f"Unsupported OIDC token algorithm: {alg}")


class OIDCService:
    def __init__(self):
        self._well_known_cache: Optional[Dict[str, Any]] = None
        self._well_known_cache_at: float = 0.0
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_at: float = 0.0
        self._jwks_by_kid: Dict[str, Dict[str, Any]] = {}

        self._admin_token_cache: Optional[str] = None
        self._admin_token_expires_at: float = 0.0

        self._cache_lock = threading.RLock()
        self._tx_lock = threading.RLock()

        self._oidc_transactions: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_seconds = 600
        self._tx_ttl_seconds = max(60, int(getattr(config, "OIDC_TRANSACTION_TTL_SECONDS", 600) or 600))
        self._timeout = max(float(config.DEFAULT_TIMEOUT), 5.0)

        self._http = httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass

    def is_enabled(self) -> bool:
        return config.AUTH_PROVIDER == "keycloak" and bool(config.OIDC_ISSUER_URL and config.OIDC_CLIENT_ID)

    def _is_fresh(self, ts: float) -> bool:
        return (time.time() - ts) < self._cache_ttl_seconds

    def _get_well_known(self) -> Dict[str, Any]:
        with self._cache_lock:
            if self._well_known_cache and self._is_fresh(self._well_known_cache_at):
                return self._well_known_cache

        issuer = (config.OIDC_ISSUER_URL or "").rstrip("/")
        if not issuer:
            raise ValueError("OIDC_ISSUER_URL is required for OIDC auth")

        url = f"{issuer}/.well-known/openid-configuration"
        response = self._http.get(url)
        response.raise_for_status()
        payload = response.json()

        with self._cache_lock:
            self._well_known_cache = payload
            self._well_known_cache_at = time.time()
        return payload

    def _get_jwks(self) -> Dict[str, Any]:
        with self._cache_lock:
            if self._jwks_cache and self._is_fresh(self._jwks_cache_at):
                return self._jwks_cache

        jwks_url = config.OIDC_JWKS_URL
        if not jwks_url:
            well_known = self._get_well_known()
            jwks_url = well_known.get("jwks_uri")
        if not jwks_url:
            raise ValueError("OIDC JWKS URI is not configured")

        response = self._http.get(jwks_url)
        response.raise_for_status()
        payload = response.json()

        keys = payload.get("keys") or []
        by_kid: Dict[str, Dict[str, Any]] = {}
        for jwk_key in keys:
            kid = str(jwk_key.get("kid") or "").strip()
            if kid:
                by_kid[kid] = jwk_key

        with self._cache_lock:
            self._jwks_cache = payload
            self._jwks_cache_at = time.time()
            self._jwks_by_kid = by_kid
        return payload

    def _select_jwk(self, kid: Optional[str]) -> Optional[Dict[str, Any]]:
        jwks = self._get_jwks()
        keys = jwks.get("keys") or []
        with self._cache_lock:
            if kid and kid in self._jwks_by_kid:
                return self._jwks_by_kid[kid]
        if len(keys) == 1:
            return keys[0]
        return None

    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None

        try:
            unverified_header = jwt.get_unverified_header(token)
            header_alg = str(unverified_header.get("alg") or "").strip()
            if not header_alg or header_alg.lower() == "none":
                logger.warning("OIDC token rejected: missing/none alg")
                return None
            if header_alg not in ALLOWED_ALGORITHMS:
                logger.warning("OIDC token rejected: alg not allowed: %s", header_alg)
                return None

            configured_alg = str(getattr(config, "OIDC_TOKEN_ALGORITHM", "") or "").strip()
            if configured_alg:
                if configured_alg not in ALLOWED_ALGORITHMS:
                    raise ValueError(f"Unsupported OIDC token algorithm in config: {configured_alg}")
                if configured_alg != header_alg:
                    logger.warning("OIDC token rejected: alg mismatch (header=%s, config=%s)", header_alg, configured_alg)
                    return None

            kid = str(unverified_header.get("kid") or "").strip() or None
            key = self._select_jwk(kid)
            if key is None:
                logger.warning("OIDC token key id not found in JWKS")
                return None

            well_known = self._get_well_known()
            issuer = (well_known.get("issuer") or (config.OIDC_ISSUER_URL or "")).rstrip("/")
            audience = config.OIDC_AUDIENCE or config.OIDC_CLIENT_ID

            decode_kwargs: Dict[str, Any] = {
                "algorithms": [header_alg],
                "issuer": issuer,
                "options": {
                    "verify_aud": bool(audience),
                    "require": ["exp", "iat"],
                },
            }
            if audience:
                decode_kwargs["audience"] = audience

            verification_key = _jwk_to_verification_key(key, header_alg)
            claims = jwt.decode(token, verification_key, **decode_kwargs)
            return claims if isinstance(claims, dict) else None

        except jwt.PyJWTError as exc:
            logger.warning("OIDC token validation failed: %s", type(exc).__name__)
            return None
        except Exception as exc:
            logger.error("OIDC token validation error: %s", type(exc).__name__)
            return None

    def exchange_password(self, username: str, password: str) -> Dict[str, Any]:
        well_known = self._get_well_known()
        token_endpoint = well_known.get("token_endpoint")
        if not token_endpoint:
            raise ValueError("OIDC token endpoint not available")

        payload = {
            "grant_type": "password",
            "client_id": config.OIDC_CLIENT_ID,
            "username": username,
            "password": password,
            "scope": config.OIDC_SCOPES,
        }
        if config.OIDC_CLIENT_SECRET:
            payload["client_secret"] = config.OIDC_CLIENT_SECRET

        response = self._http.post(token_endpoint, data=payload)
        response.raise_for_status()
        return response.json()

    def exchange_authorization_code(
        self,
        code: str,
        redirect_uri: str,
        *,
        code_verifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        well_known = self._get_well_known()
        token_endpoint = well_known.get("token_endpoint")
        if not token_endpoint:
            raise ValueError("OIDC token endpoint not available")

        payload = {
            "grant_type": "authorization_code",
            "client_id": config.OIDC_CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if config.OIDC_CLIENT_SECRET:
            payload["client_secret"] = config.OIDC_CLIENT_SECRET
        if code_verifier:
            payload["code_verifier"] = code_verifier

        response = self._http.post(token_endpoint, data=payload)
        response.raise_for_status()
        return response.json()

    def build_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        nonce: str,
        *,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> str:
        well_known = self._get_well_known()
        auth_endpoint = well_known.get("authorization_endpoint")
        if not auth_endpoint:
            raise ValueError("OIDC authorization endpoint not available")

        payload = {
            "response_type": "code",
            "client_id": config.OIDC_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": config.OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
        }
        if code_challenge:
            method = (code_challenge_method or "S256").strip() or "S256"
            if method not in ALLOWED_CODE_CHALLENGE_METHODS:
                raise ValueError("Unsupported PKCE code_challenge_method")
            payload["code_challenge"] = code_challenge
            payload["code_challenge_method"] = method

        return f"{auth_endpoint}?{urlencode(payload)}"

    @staticmethod
    def _random_token(size: int = 32) -> str:
        return secrets.token_urlsafe(size)

    @staticmethod
    def _pkce_s256(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def _cleanup_transactions(self) -> None:
        now = time.time()
        with self._tx_lock:
            expired = [
                tx_id
                for tx_id, payload in self._oidc_transactions.items()
                if float(payload.get("expires_at", 0) or 0) <= now
            ]
            for tx_id in expired:
                self._oidc_transactions.pop(tx_id, None)

    def start_authorization_transaction(
        self,
        *,
        redirect_uri: str,
        state: Optional[str] = None,
        nonce: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> Dict[str, str]:
        self._cleanup_transactions()

        resolved_state = str(state or "").strip() or self._random_token(18)
        resolved_nonce = str(nonce or "").strip() or self._random_token(18)
        resolved_method = str(code_challenge_method or "").strip() or "S256"

        if code_challenge:
            if resolved_method not in ALLOWED_CODE_CHALLENGE_METHODS:
                raise ValueError("Unsupported PKCE code_challenge_method")
        else:
            resolved_method = ""
            if code_challenge_method:
                raise ValueError("code_challenge_method requires code_challenge")

        tx_id = self._random_token(24)
        expires_at = time.time() + self._tx_ttl_seconds
        record = {
            "state": resolved_state,
            "nonce": resolved_nonce,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge or "",
            "code_challenge_method": resolved_method or "",
            "created_at": time.time(),
            "expires_at": expires_at,
            "used": False,
        }

        with self._tx_lock:
            self._oidc_transactions[tx_id] = record

        authorization_url = self.build_authorization_url(
            redirect_uri=redirect_uri,
            state=resolved_state,
            nonce=resolved_nonce,
            code_challenge=(code_challenge or None),
            code_challenge_method=(resolved_method or None),
        )
        return {"authorization_url": authorization_url, "transaction_id": tx_id, "state": resolved_state}

    def consume_authorization_transaction(
        self,
        *,
        transaction_id: Optional[str],
        state: Optional[str],
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._cleanup_transactions()

        tx_id = str(transaction_id or "").strip()
        state_value = str(state or "").strip()
        now = time.time()

        with self._tx_lock:
            if tx_id:
                candidates: Tuple[Tuple[str, Optional[Dict[str, Any]]], ...] = ((tx_id, self._oidc_transactions.get(tx_id)),)
            else:
                candidates = tuple(
                    (candidate_id, record)
                    for candidate_id, record in self._oidc_transactions.items()
                    if record and str(record.get("state", "")) == state_value
                )

            if not candidates:
                raise ValueError("OIDC transaction not found")

            selected_id = ""
            selected: Optional[Dict[str, Any]] = None

            for candidate_id, record in candidates:
                if not record:
                    continue
                if bool(record.get("used")):
                    continue
                if float(record.get("expires_at", 0) or 0) <= now:
                    continue
                if str(record.get("redirect_uri", "")) != str(redirect_uri or ""):
                    continue
                if str(record.get("state", "")) != state_value:
                    continue
                selected_id = candidate_id
                selected = dict(record)
                break

            if not selected_id or not selected:
                raise ValueError("OIDC transaction is invalid or expired")

            challenge = str(selected.get("code_challenge", "") or "")
            method = str(selected.get("code_challenge_method", "") or "")
            if challenge:
                if not code_verifier:
                    raise ValueError("Missing PKCE code_verifier")
                if method == "S256":
                    if self._pkce_s256(code_verifier) != challenge:
                        raise ValueError("Invalid PKCE code_verifier")
                elif method == "plain":
                    if str(code_verifier) != challenge:
                        raise ValueError("Invalid PKCE code_verifier")
                else:
                    raise ValueError("Unsupported PKCE method")

            self._oidc_transactions[selected_id]["used"] = True

        return selected

    def _get_admin_token(self) -> Optional[str]:
        if not (
            config.KEYCLOAK_ADMIN_URL
            and config.KEYCLOAK_ADMIN_REALM
            and config.KEYCLOAK_ADMIN_CLIENT_ID
            and config.KEYCLOAK_ADMIN_CLIENT_SECRET
        ):
            return None

        with self._cache_lock:
            if self._admin_token_cache and time.time() < self._admin_token_expires_at:
                return self._admin_token_cache

        token_url = (
            f"{config.KEYCLOAK_ADMIN_URL.rstrip('/')}/realms/{config.KEYCLOAK_ADMIN_REALM}"
            "/protocol/openid-connect/token"
        )
        payload = {
            "grant_type": "client_credentials",
            "client_id": config.KEYCLOAK_ADMIN_CLIENT_ID,
            "client_secret": config.KEYCLOAK_ADMIN_CLIENT_SECRET,
        }

        response = self._http.post(token_url, data=payload)
        response.raise_for_status()
        body = response.json()

        token = body.get("access_token")
        expires_in = int(body.get("expires_in", 60))

        with self._cache_lock:
            self._admin_token_cache = token
            self._admin_token_expires_at = time.time() + expires_in - 10

        return token

    def create_keycloak_user(
        self,
        *,
        email: str,
        username: Optional[str],
        full_name: Optional[str] = None,
    ) -> Optional[str]:
        if not config.KEYCLOAK_USER_PROVISIONING_ENABLED:
            return None

        admin_token = self._get_admin_token()
        if not admin_token:
            logger.warning("Keycloak admin provisioning is enabled but admin credentials are incomplete")
            return None

        first_name = None
        last_name = None
        if full_name:
            parts = [p for p in full_name.strip().split(" ") if p]
            if parts:
                first_name = parts[0]
            if len(parts) > 1:
                last_name = " ".join(parts[1:])

        realm_admin_base = f"{config.KEYCLOAK_ADMIN_URL.rstrip('/')}/admin/realms/{config.KEYCLOAK_ADMIN_REALM}"
        payload = {
            "email": email,
            "username": username or email,
            "enabled": True,
            "emailVerified": False,
        }
        if first_name:
            payload["firstName"] = first_name
        if last_name:
            payload["lastName"] = last_name

        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        response = self._http.post(f"{realm_admin_base}/users", headers=headers, json=payload)
        if response.status_code not in (201, 204, 409):
            response.raise_for_status()

        if response.status_code == 409:
            query = self._http.get(
                f"{realm_admin_base}/users",
                headers=headers,
                params={"email": email, "exact": "true"},
            )
            query.raise_for_status()
            users = query.json() or []
            return users[0].get("id") if users else None

        location = response.headers.get("Location") or ""
        if "/users/" in location:
            user_id = location.rsplit("/users/", 1)[1].strip("/")
            return user_id if user_id else None
        return None