"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
import time
import json
import threading
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm, ECAlgorithm

from config import config

logger = logging.getLogger(__name__)

_ALLOWED_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


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
        self._well_known_cache_at: float = 0
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_at: float = 0
        self._admin_token_cache: Optional[str] = None
        self._admin_token_expires_at: float = 0
        self._cache_lock = threading.RLock()
        self._cache_ttl_seconds = 600
        self._timeout = max(float(config.DEFAULT_TIMEOUT), 5.0)

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
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()

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

            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(jwks_url)
                response.raise_for_status()
                payload = response.json()

            self._jwks_cache = payload
            self._jwks_cache_at = time.time()
            return payload

    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None

        try:
            alg = config.OIDC_TOKEN_ALGORITHM or "RS256"
            if alg not in _ALLOWED_ALGORITHMS:
                raise ValueError(f"Unsupported OIDC token algorithm in config: {alg}")

            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            jwks = self._get_jwks()
            keys = jwks.get("keys") or []
            key = None
            for jwk_key in keys:
                if jwk_key.get("kid") == kid:
                    key = jwk_key
                    break
            if key is None and len(keys) == 1:
                key = keys[0]
            if key is None:
                logger.warning("OIDC token key id not found in JWKS")
                return None

            well_known = self._get_well_known()
            issuer = well_known.get("issuer") or (config.OIDC_ISSUER_URL or "").rstrip("/")
            audience = config.OIDC_AUDIENCE or config.OIDC_CLIENT_ID

            decode_kwargs: Dict[str, Any] = {
                "algorithms": [alg],
                "issuer": issuer,
                "options": {"verify_aud": bool(audience)},
            }
            if audience:
                decode_kwargs["audience"] = audience

            verification_key = _jwk_to_verification_key(key, alg)
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

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(token_endpoint, data=payload)
            response.raise_for_status()
            return response.json()

    def exchange_authorization_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
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

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(token_endpoint, data=payload)
            response.raise_for_status()
            return response.json()

    def build_authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str:
        well_known = self._get_well_known()
        auth_endpoint = well_known.get("authorization_endpoint")
        if not auth_endpoint:
            raise ValueError("OIDC authorization endpoint not available")

        query = urlencode({
            "response_type": "code",
            "client_id": config.OIDC_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": config.OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
        })
        return f"{auth_endpoint}?{query}"

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
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(token_url, data=payload)
                response.raise_for_status()
                body = response.json()

            token = body.get("access_token")
            expires_in = int(body.get("expires_in", 60))
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

        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(f"{realm_admin_base}/users", headers=headers, json=payload)
            if response.status_code not in (201, 204, 409):
                response.raise_for_status()

            if response.status_code == 409:
                query = client.get(
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