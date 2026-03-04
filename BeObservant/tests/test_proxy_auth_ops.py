import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from services.grafana import proxy_auth_ops


class _GrafanaServiceStub:
    def __init__(self, *, datasource=None, datasources=None):
        self._datasource = datasource
        self._datasources = list(datasources or [])

    async def get_datasource(self, uid: str):
        return self._datasource

    async def get_datasources(self):
        return self._datasources


class _ProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service


class _DsObj:
    def __init__(self, *, uid=None, ds_id=None, is_default=False, read_only=False):
        self.uid = uid
        self.id = ds_id
        self.is_default = is_default
        self.read_only = read_only


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_by_uid_allows_default():
    service = _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="default-prom", is_default=True)))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid="default-prom",
        datasource_id=None,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_by_id_allows_read_only():
    service = _ProxyStub(_GrafanaServiceStub(datasources=[_DsObj(ds_id=12, read_only=True)]))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid=None,
        datasource_id=12,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_rejects_non_system():
    service = _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="private-ds", is_default=False, read_only=False)))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid="private-ds",
        datasource_id=None,
    )

    assert allowed is False


def test_blocked_proxy_path_disallows_public_dashboards_and_snapshots():
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/public-dashboards/abcd1234")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/dashboard/snapshot/xyz")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/api/public/dashboards/uid/abcd")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/api/snapshots/abcd")
    assert not proxy_auth_ops._is_blocked_proxy_path("/grafana/d/private-uid/private-dash")
