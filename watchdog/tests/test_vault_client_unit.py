"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.secrets import vault_client


class FakeInvalidPath(Exception):
    pass


class FakeForbidden(Exception):
    pass


class FakeVaultError(Exception):
    pass


class _KVV2:
    def __init__(self, client):
        self.client = client

    def read_secret_version(self, path, mount_point, raise_on_deleted_version=False):
        value = self.client.read_map.get(("v2", path))
        if isinstance(value, Exception):
            raise value
        return value


class _KVV1:
    def __init__(self, client):
        self.client = client

    def read_secret(self, path, mount_point):
        value = self.client.read_map.get(("v1", path))
        if isinstance(value, Exception):
            raise value
        return value


class FakeHVACClient:
    def __init__(self, *, auth_ok=True, read_map=None):
        self.token = None
        self.auth_ok = auth_ok
        self.read_map = read_map or {}
        self.login_calls = []
        self.auth = SimpleNamespace(approle=SimpleNamespace(login=self._login))
        self.secrets = SimpleNamespace(kv=SimpleNamespace(v1=_KVV1(self), v2=_KVV2(self)))

    def _login(self, role_id, secret_id):
        self.login_calls.append((role_id, secret_id))
        return {"auth": {"client_token": "approle-token"}}

    def is_authenticated(self):
        return self.auth_ok


def _patch_hvac(monkeypatch, *, client):
    monkeypatch.setattr(vault_client, "hvac", SimpleNamespace(Client=lambda **kwargs: client))
    monkeypatch.setattr(vault_client, "Forbidden", FakeForbidden)
    monkeypatch.setattr(vault_client, "InvalidPath", FakeInvalidPath)
    monkeypatch.setattr(vault_client, "VaultError", FakeVaultError)


def test_vault_provider_init_validation(monkeypatch):
    monkeypatch.setattr(vault_client, "hvac", None)
    with pytest.raises(vault_client.VaultClientError, match="hvac library"):
        vault_client.VaultSecretProvider(address="https://vault", token="tok")

    client = FakeHVACClient()
    _patch_hvac(monkeypatch, client=client)

    with pytest.raises(vault_client.VaultClientError, match="VAULT_ADDR"):
        vault_client.VaultSecretProvider(address="", token="tok")
    with pytest.raises(vault_client.VaultClientError, match="Unsupported kv_version"):
        vault_client.VaultSecretProvider(address="https://vault", token="tok", kv_version=3)
    with pytest.raises(vault_client.VaultClientError, match="Vault auth not configured"):
        vault_client.VaultSecretProvider(address="https://vault")

    client.auth_ok = False
    with pytest.raises(vault_client.VaultClientError, match="authentication failed"):
        vault_client.VaultSecretProvider(address="https://vault", token="tok")


def test_vault_provider_approle_and_refresh_validation(monkeypatch):
    client = FakeHVACClient(auth_ok=True)
    _patch_hvac(monkeypatch, client=client)

    provider = vault_client.VaultSecretProvider(
        address="https://vault",
        role_id="role",
        secret_id_fn=lambda: "secret",
    )
    assert client.login_calls == [("role", "secret")]
    assert client.token == "approle-token"

    provider._client.auth_ok = False
    provider._ensure_authenticated()
    assert client.login_calls[-1] == ("role", "secret")

    provider._role_id = None
    with pytest.raises(vault_client.VaultClientError, match="expired"):
        provider._ensure_authenticated()

    fresh_client = FakeHVACClient(auth_ok=True)
    _patch_hvac(monkeypatch, client=fresh_client)
    provider2 = vault_client.VaultSecretProvider(address="https://vault", token="tok")
    provider2._client.auth_ok = False
    with pytest.raises(vault_client.VaultClientError, match="expired"):
        provider2._ensure_authenticated()


def test_vault_provider_get_cache_and_payload_shapes(monkeypatch):
    client = FakeHVACClient(
        read_map={
            ("v2", "alpha"): {"data": {"data": {"value": "secret-alpha"}}},
            ("v2", "beta"): {"data": {"data": {"beta": 2}}},
            ("v2", "gamma"): {"data": {"data": {"only": "one"}}},
            ("v2", "empty"): {"data": {"data": {}}},
            ("v1", "legacy"): {"data": {"value": "legacy-secret"}},
            ("v1", "missing"): FakeInvalidPath(),
        }
    )
    _patch_hvac(monkeypatch, client=client)

    provider = vault_client.VaultSecretProvider(address="https://vault", token="tok", cache_ttl=100)
    assert provider.get("alpha") == "secret-alpha"
    client.read_map[("v2", "alpha")] = {"data": {"data": {"value": "changed"}}}
    assert provider.get("alpha") == "secret-alpha"
    assert provider.get("beta") == "2"
    assert provider.get("gamma") == "one"
    assert provider.get("empty") is None

    provider_v1 = vault_client.VaultSecretProvider(address="https://vault", token="tok", kv_version=1)
    assert provider_v1.get("legacy") == "legacy-secret"
    assert provider_v1.get_many(["legacy", "missing"]) == {"legacy": "legacy-secret", "missing": None}


def test_vault_provider_errors_not_found_and_cache_cleanup(monkeypatch):
    client = FakeHVACClient(
        read_map={
            ("v2", "missing"): FakeInvalidPath(),
            ("v2", "forbidden"): FakeForbidden(),
            ("v2", "error"): FakeVaultError(),
            ("v2", "weird"): {"data": {"data": {"a": 1, "b": 2}}},
        }
    )
    _patch_hvac(monkeypatch, client=client)
    provider = vault_client.VaultSecretProvider(address="https://vault", token="tok", cache_ttl=0)

    assert provider.get("missing") is None
    with pytest.raises(vault_client.VaultClientError, match="forbidden"):
        provider.get("forbidden")
    with pytest.raises(vault_client.VaultClientError, match="error"):
        provider.get("error")
    assert provider.get("weird") is None

    provider._cache["broken"] = (1.0,)  # type: ignore[assignment]
    assert provider._from_cache("broken") is vault_client._S
