"""
OIDC authentication service for validating ID tokens, exchanging credentials for tokens,
and provisioning users in Keycloak if enabled.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from typing import Optional, Set, Tuple, Coroutine, TypeVar, cast
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from config import config
from custom_types.json import JSONDict
from services.common.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS: Set[str] = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
ALLOWED_CODE_CHALLENGE_METHODS: Set[str] = {"S256", "plain"}
RunResult = TypeVar("RunResult")
VerificationKey = rsa.RSAPublicKey | ec.EllipticCurvePublicKey


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _jwk_to_verification_key(jwk_key: JSONDict, alg: str) -> VerificationKey:
    jwk_json = json.dumps(jwk_key)
    if alg.startswith("RS"):
        rsa_key = RSAAlgorithm.from_jwk(jwk_json)
        if isinstance(rsa_key, rsa.RSAPublicKey):
            return rsa_key
        raise ValueError("Invalid RSA JWK key")
    if alg.startswith("ES"):
        ec_key = ECAlgorithm.from_jwk(jwk_json)
        if isinstance(ec_key, ec.EllipticCurvePublicKey):
            return ec_key
        raise ValueError("Invalid EC JWK key")
    raise ValueError(f"Unsupported OIDC token algorithm: {alg}")


def _looks_like_jwt(token: str) -> bool:
    if not token:
        return False
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


class OIDCService:
    def __init__(self) -> None:
        self._well_known_cache: Optional[JSONDict] = None
        self._well_known_cache_at: float = 0.0
        self._jwks_cache: Optional[JSONDict] = None
        self._jwks_cache_at: float = 0.0
        self._jwks_by_kid: dict[str, JSONDict] = {}
        self._verification_key_cache: dict[Tuple[str, str], VerificationKey] = {}
        self._admin_token_cache: Optional[str] = None
        self._admin_token_expires_at: float = 0.0
        self._cache_lock = threading.RLock()
        self._cache_ttl_seconds = 600
        self._tx_ttl_seconds = max(60, int(getattr(config, "OIDC_TRANSACTION_TTL_SECONDS", 600) or 600))
        self._timeout = max(float(config.DEFAULT_TIMEOUT), 5.0)
        self._http = httpx.Client(timeout=self._timeout)
        self._ttl_cache = TTLCache()
        self._bg_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bg_thread: Optional[threading.Thread] = None
        self._bg_ready = threading.Event()
        self._bg_lock = threading.Lock()

    def close(self) -> None:
        try:
            self._http.close()
        except RuntimeError:
            pass

        loop = self._bg_loop
        if loop and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass

    def is_enabled(self) -> bool:
        return config.AUTH_PROVIDER in {"oidc", "keycloak"} and bool(config.OIDC_ISSUER_URL and config.OIDC_CLIENT_ID)

    def _is_fresh(self, ts: float) -> bool:
        return (time.time() - ts) < self._cache_ttl_seconds

    def _get_well_known(self) -> JSONDict:
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
        if not isinstance(payload, dict):
            raise ValueError("OIDC well-known configuration must be an object")

        with self._cache_lock:
            self._well_known_cache = payload
            self._well_known_cache_at = time.time()
        return payload

    def _get_jwks(self, *, force_refresh: bool = False) -> JSONDict:
        with self._cache_lock:
            if (
                not force_refresh
                and self._jwks_cache
                and self._is_fresh(self._jwks_cache_at)
            ):
                return self._jwks_cache

        jwks_url = config.OIDC_JWKS_URL
        if not jwks_url:
            well_known = self._get_well_known()
            jwks_uri = well_known.get("jwks_uri")
            jwks_url = jwks_uri if isinstance(jwks_uri, str) else None
        if not jwks_url:
            raise ValueError("OIDC JWKS URI is not configured")

        response = self._http.get(jwks_url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OIDC JWKS response must be an object")

        raw_keys = payload.get("keys")
        keys_raw = raw_keys if isinstance(raw_keys, list) else []
        keys = [key for key in keys_raw if isinstance(key, dict)]
        by_kid: dict[str, JSONDict] = {}
        for jwk_key in keys:
            identifiers = {
                str(jwk_key.get("kid") or "").strip(),
                str(jwk_key.get("x5t") or "").strip(),
                str(jwk_key.get("x5t#S256") or "").strip(),
            }
            for key_id in identifiers:
                if key_id:
                    by_kid[key_id] = jwk_key

        with self._cache_lock:
            self._jwks_cache = payload
            self._jwks_cache_at = time.time()
            self._jwks_by_kid = by_kid
            self._verification_key_cache.clear()
        return payload

    def _select_jwk(
        self,
        *,
        kid: Optional[str],
        x5t: Optional[str] = None,
        x5t_s256: Optional[str] = None,
        alg: Optional[str] = None,
    ) -> Optional[JSONDict]:
        jwks = self._get_jwks()
        raw_keys = jwks.get("keys")
        keys_raw = raw_keys if isinstance(raw_keys, list) else []
        keys = [key for key in keys_raw if isinstance(key, dict)]

        requested_ids = [
            str(kid or "").strip(),
            str(x5t or "").strip(),
            str(x5t_s256 or "").strip(),
        ]
        requested_ids = [value for value in requested_ids if value]

        def lookup_by_identifier() -> Optional[JSONDict]:
            with self._cache_lock:
                for key_id in requested_ids:
                    if key_id in self._jwks_by_kid:
                        return self._jwks_by_kid[key_id]
            return None

        key = lookup_by_identifier()
        if key is not None:
            return key

        # Try one forced refresh to handle IdP key rotation and stale JWKS cache.
        if requested_ids:
            refreshed = self._get_jwks(force_refresh=True)
            refreshed_raw_keys = refreshed.get("keys")
            refreshed_keys_raw = refreshed_raw_keys if isinstance(refreshed_raw_keys, list) else []
            keys = [key_item for key_item in refreshed_keys_raw if isinstance(key_item, dict)]
            key = lookup_by_identifier()
            if key is not None:
                return key

        with self._cache_lock:
            if kid and kid in self._jwks_by_kid:
                return self._jwks_by_kid[kid]

        if alg:
            candidates = [
                key_item
                for key_item in keys
                if str(key_item.get("kty") or "").strip()
                and (
                    not str(key_item.get("alg") or "").strip()
                    or str(key_item.get("alg") or "").strip() == alg
                )
                and (
                    not str(key_item.get("use") or "").strip()
                    or str(key_item.get("use") or "").strip() == "sig"
                )
            ]
            if len(candidates) == 1:
                return candidates[0]

        if len(keys) == 1:
            return keys[0]
        return None

    def _verification_key_for(self, jwk_key: JSONDict, alg: str, kid: Optional[str]) -> VerificationKey:
        cache_kid = kid or "__single__"
        cache_key = (cache_kid, alg)
        with self._cache_lock:
            cached = self._verification_key_cache.get(cache_key)
        if cached is not None:
            return cached

        vk = _jwk_to_verification_key(jwk_key, alg)
        with self._cache_lock:
            self._verification_key_cache[cache_key] = vk
        return vk

    def _verify_jwt(
        self,
        token: str,
        *,
        nonce: Optional[str] = None,
        require_nonce: bool = False,
    ) -> Optional[JSONDict]:
        if not token or not _looks_like_jwt(token):
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
                    logger.warning(
                        "OIDC token rejected: alg mismatch (header=%s, config=%s)",
                        header_alg,
                        configured_alg,
                    )
                    return None

            kid = str(unverified_header.get("kid") or "").strip() or None
            x5t = str(unverified_header.get("x5t") or "").strip() or None
            x5t_s256 = str(unverified_header.get("x5t#S256") or "").strip() or None
            jwk_key = self._select_jwk(
                kid=kid,
                x5t=x5t,
                x5t_s256=x5t_s256,
                alg=header_alg,
            )
            if jwk_key is None:
                logger.warning(
                    "OIDC token signing key not found in JWKS (kid=%s, x5t=%s, x5t#S256=%s)",
                    kid or "<none>",
                    x5t or "<none>",
                    x5t_s256 or "<none>",
                )
                return None

            well_known = self._get_well_known()
            issuer = (str(well_known.get("issuer") or "") or (config.OIDC_ISSUER_URL or "")).rstrip("/")
            audience = config.OIDC_AUDIENCE or config.OIDC_CLIENT_ID

            verification_key = self._verification_key_for(jwk_key, header_alg, kid)
            claims = jwt.decode(
                token,
                verification_key,
                algorithms=[header_alg],
                options={"verify_aud": bool(audience), "require": ["exp", "iat"]},
                issuer=issuer or None,
                audience=audience or None,
            )
            token_nonce = str(claims.get("nonce") or "")
            if require_nonce and not nonce:
                logger.warning("OIDC token rejected: nonce required but missing")
                return None
            if nonce is not None and token_nonce and token_nonce != str(nonce):
                logger.warning("OIDC token rejected: nonce mismatch")
                return None
            if nonce is not None and not token_nonce:
                logger.warning("OIDC token rejected: nonce missing in token")
                return None

            return cast(JSONDict, claims)

        except jwt.PyJWTError:
            logger.warning("OIDC token validation failed")
            return None
        except (OSError, RuntimeError, ValueError):
            logger.error("OIDC token validation error")
            return None

    def verify_id_token(self, token: str, *, nonce: Optional[str] = None) -> Optional[JSONDict]:
        return self._verify_jwt(token, nonce=nonce, require_nonce=bool(nonce))

    def verify_access_token(self, token: str) -> Optional[JSONDict]:
        return self._verify_jwt(token)

    def fetch_userinfo(self, access_token: str) -> Optional[JSONDict]:
        if not access_token:
            return None
        try:
            well_known = self._get_well_known()
            endpoint = well_known.get("userinfo_endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                return None
            resp = self._http.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except (httpx.HTTPError, RuntimeError, ValueError):
            logger.warning("OIDC userinfo fetch failed")
            return None

    def exchange_password(self, username: str, password: str) -> JSONDict:
        well_known = self._get_well_known()
        token_endpoint = well_known.get("token_endpoint")
        if not isinstance(token_endpoint, str) or not token_endpoint:
            raise ValueError("OIDC token endpoint not available")

        request_data = {
            "grant_type": "password",
            "client_id": config.OIDC_CLIENT_ID,
            "username": username,
            "password": password,
            "scope": config.OIDC_SCOPES,
        }
        if config.OIDC_CLIENT_SECRET:
            request_data["client_secret"] = config.OIDC_CLIENT_SECRET

        response = self._http.post(token_endpoint, data=request_data)
        response.raise_for_status()
        response_body = response.json()
        if not isinstance(response_body, dict):
            raise ValueError("OIDC token endpoint returned invalid payload")
        return {str(key): value for key, value in response_body.items()}

    def exchange_authorization_code(
        self,
        code: str,
        redirect_uri: str,
        *,
        code_verifier: Optional[str] = None,
    ) -> JSONDict:
        well_known = self._get_well_known()
        token_endpoint = well_known.get("token_endpoint")
        if not isinstance(token_endpoint, str) or not token_endpoint:
            raise ValueError("OIDC token endpoint not available")

        request_data = {
            "grant_type": "authorization_code",
            "client_id": config.OIDC_CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if config.OIDC_CLIENT_SECRET:
            request_data["client_secret"] = config.OIDC_CLIENT_SECRET
        if code_verifier:
            request_data["code_verifier"] = code_verifier

        response = self._http.post(token_endpoint, data=request_data)
        response.raise_for_status()
        response_body = response.json()
        if not isinstance(response_body, dict):
            raise ValueError("OIDC token endpoint returned invalid payload")
        return {str(key): value for key, value in response_body.items()}

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

    def _in_event_loop(self) -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    def _ensure_bg_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._bg_loop
        if loop and loop.is_running():
            return loop

        with self._bg_lock:
            loop2 = self._bg_loop
            if loop2 and loop2.is_running():
                return loop2

            self._bg_ready.clear()

            def runner() -> None:
                bg_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(bg_loop)
                self._bg_loop = bg_loop
                self._bg_ready.set()
                bg_loop.run_forever()
                bg_loop.close()

            t = threading.Thread(target=runner, name="oidc-bg-loop", daemon=True)
            self._bg_thread = t
            t.start()
            self._bg_ready.wait()
            if self._bg_loop is None:
                raise RuntimeError("Failed to start OIDC background event loop")
            return self._bg_loop

    def _run_async(self, coro: Coroutine[object, object, RunResult]) -> RunResult:
        if self._in_event_loop():
            raise RuntimeError("OIDCService sync methods cannot run inside an event loop; use *_async variants")
        loop = self._ensure_bg_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result()

    def _tx_key(self, tx_id: str) -> str:
        return f"oidc_tx:{tx_id}"

    def _state_index_key(self, state: str, redirect_uri: str) -> str:
        h = hashlib.sha256((redirect_uri or "").encode("utf-8")).hexdigest()[:16]
        return f"oidc_tx_state:{state}:{h}"

    async def start_authorization_transaction_async(
        self,
        *,
        redirect_uri: str,
        state: Optional[str] = None,
        nonce: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> dict[str, str]:
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
        now = time.time()
        record: JSONDict = {
            "state": resolved_state,
            "nonce": resolved_nonce,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge or "",
            "code_challenge_method": resolved_method or "",
            "created_at": now,
            "expires_at": now + self._tx_ttl_seconds,
            "used": False,
        }

        await self._ttl_cache.set(self._tx_key(tx_id), record, ttl_seconds=self._tx_ttl_seconds)
        await self._ttl_cache.set(
            self._state_index_key(resolved_state, redirect_uri),
            {"tx_id": tx_id},
            ttl_seconds=self._tx_ttl_seconds,
        )

        authorization_url = self.build_authorization_url(
            redirect_uri=redirect_uri,
            state=resolved_state,
            nonce=resolved_nonce,
            code_challenge=(code_challenge or None),
            code_challenge_method=(resolved_method or None),
        )
        return {"authorization_url": authorization_url, "transaction_id": tx_id, "state": resolved_state}

    async def consume_authorization_transaction_async(
        self,
        *,
        transaction_id: Optional[str],
        state: Optional[str],
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> JSONDict:
        tx_id = str(transaction_id or "").strip()
        state_value = str(state or "").strip()
        now = time.time()

        if not tx_id:
            idx = await self._ttl_cache.get(self._state_index_key(state_value, redirect_uri))
            if isinstance(idx, dict):
                tx_id = str(idx.get("tx_id") or "").strip()

        if not tx_id:
            raise ValueError("OIDC transaction not found")

        record = await self._ttl_cache.get(self._tx_key(tx_id))
        if not isinstance(record, dict):
            raise ValueError("OIDC transaction not found")

        if bool(record.get("used")):
            raise ValueError("OIDC transaction is invalid or expired")
        if float(record.get("expires_at", 0) or 0) <= now:
            raise ValueError("OIDC transaction is invalid or expired")
        if str(record.get("redirect_uri", "")) != str(redirect_uri or ""):
            raise ValueError("OIDC transaction is invalid or expired")
        if str(record.get("state", "")) != state_value:
            raise ValueError("OIDC transaction is invalid or expired")

        challenge = str(record.get("code_challenge", "") or "")
        method = str(record.get("code_challenge_method", "") or "")
        if challenge:
            if not code_verifier:
                raise ValueError("Missing PKCE code_verifier")
            if method == "S256":
                if self._pkce_s256(code_verifier) != challenge:
                    raise ValueError("Invalid PKCE code_verifier")
            elif method == "plain":
                if not secrets.compare_digest(str(code_verifier), challenge):
                    raise ValueError("Invalid PKCE code_verifier")
            else:
                raise ValueError("Unsupported PKCE method")

        record["used"] = True
        ttl_remaining = int(max(1, float(record.get("expires_at", 0) or 0) - now))
        await self._ttl_cache.set(self._tx_key(tx_id), record, ttl_seconds=ttl_remaining)

        return dict(record)

    def start_authorization_transaction(
        self,
        *,
        redirect_uri: str,
        state: Optional[str] = None,
        nonce: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> dict[str, str]:
        result = self._run_async(
            self.start_authorization_transaction_async(
                redirect_uri=redirect_uri,
                state=state,
                nonce=nonce,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            )
        )
        return {str(key): str(value) for key, value in result.items()}

    def consume_authorization_transaction(
        self,
        *,
        transaction_id: Optional[str],
        state: Optional[str],
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> JSONDict:
        result = self._run_async(
            self.consume_authorization_transaction_async(
                transaction_id=transaction_id,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        )
        return dict(result)

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
        if not isinstance(body, dict):
            return None

        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            return None
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

        admin_url = str(config.KEYCLOAK_ADMIN_URL or "").rstrip("/")
        realm_admin_base = f"{admin_url}/admin/realms/{config.KEYCLOAK_ADMIN_REALM}"
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
            users_raw = query.json() or []
            users = [user for user in users_raw if isinstance(user, dict)] if isinstance(users_raw, list) else []
            return users[0].get("id") if users else None

        location = response.headers.get("Location") or ""
        if "/users/" in location:
            user_id = location.rsplit("/users/", 1)[1].strip("/")
            return user_id if user_id else None
        return None
