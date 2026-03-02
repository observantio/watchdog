"""
Vault client for fetching secrets from HashiCorp Vault.

Alerting/incident/rules/channel persistence was moved to BeNotified.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional, Tuple

try:
    import hvac
    from hvac.exceptions import Forbidden, InvalidPath, VaultError
except ImportError: 
    hvac = None
    Forbidden = Exception
    InvalidPath = Exception
    VaultError = Exception


class VaultClientError(RuntimeError):
    pass


_S = object()


class VaultSecretProvider:
    def __init__(
        self,
        address: str,
        token: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id_fn: Optional[Callable[[], str]] = None,
        prefix: str = "secret",
        kv_version: int = 2,
        timeout: float = 2.0,
        cacert: Optional[str] = None,
        cache_ttl: float = 30.0,
    ) -> None:
        if hvac is None:
            raise VaultClientError("hvac library is required for VaultSecretProvider")
        if not address:
            raise VaultClientError("VAULT_ADDR is required")
        if kv_version not in (1, 2):
            raise VaultClientError(f"Unsupported kv_version: {kv_version!r}, must be 1 or 2")

        self._client = hvac.Client(
            url=address,
            timeout=timeout,
            verify=cacert if cacert else True,
        )

        self._prefix = prefix.strip("/")
        self._kv_version = kv_version
        self._cache_ttl = float(cache_ttl)
        self._cache: Dict[str, Tuple[float, Optional[str]]] = {}
        self._lock = threading.Lock()

        self._role_id = role_id
        self._secret_id_fn = secret_id_fn

        self._exc_not_found = InvalidPath
        self._exc_forbidden = Forbidden
        self._exc_vault = VaultError

        if token:
            self._client.token = token
        elif role_id and secret_id_fn:
            self._approle_login()
        else:
            raise VaultClientError("Vault auth not configured (provide token or role_id + secret_id_fn)")

        if not self._client.is_authenticated():
            raise VaultClientError("Vault authentication failed")

    def _approle_login(self) -> None:
        if not self._role_id:
            raise VaultClientError("Vault AppRole role_id is not configured")
        if self._secret_id_fn is None:
            raise VaultClientError("Vault AppRole secret id callback is not configured")

        secret_id = self._secret_id_fn()
        auth = self._client.auth.approle.login(role_id=self._role_id, secret_id=secret_id)
        self._client.token = auth["auth"]["client_token"]

    def _ensure_authenticated(self) -> None:
        if self._client.is_authenticated():
            return
        if self._role_id and self._secret_id_fn:
            self._approle_login()
            return
        raise VaultClientError("Vault token expired and no AppRole credentials to refresh")

    def _from_cache(self, key: str) -> object:
        with self._lock:
            entry = self._cache.get(key, _S)
            if entry is _S:
                return _S
            ts, value = entry
            if time.monotonic() - ts > self._cache_ttl:
                self._cache.pop(key, None)
                return _S
            return value

    def _to_cache(self, key: str, value: Optional[str]) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), value)

    def get(self, key: str) -> Optional[str]:
        cached = self._from_cache(key)
        if cached is not _S:
            return cached  # type: ignore[return-value]

        self._ensure_authenticated()

        try:
            if self._kv_version == 2:
                resp = self._client.secrets.kv.v2.read_secret_version(
                    path=key,
                    mount_point=self._prefix,
                    raise_on_deleted_version=False,
                )
                payload = resp.get("data", {}).get("data", {}) or {}
            else:
                resp = self._client.secrets.kv.v1.read_secret(
                    path=key,
                    mount_point=self._prefix,
                )
                payload = resp.get("data", {}) or {}
        except self._exc_not_found:
            self._to_cache(key, None)
            return None
        except (self._exc_forbidden, self._exc_vault) as exc:
            raise VaultClientError(f"Vault error fetching '{key}'") from exc

        if not payload:
            self._to_cache(key, None)
            return None

        if "value" in payload and isinstance(payload["value"], (str, int, float)):
            val = str(payload["value"])
        elif key in payload and isinstance(payload[key], (str, int, float)):
            val = str(payload[key])
        elif len(payload) == 1:
            val = str(next(iter(payload.values())))
        else:
            self._to_cache(key, None)
            return None

        self._to_cache(key, val)
        return val

    def get_many(self, keys: list[str]) -> Dict[str, Optional[str]]:
        return {k: self.get(k) for k in keys}