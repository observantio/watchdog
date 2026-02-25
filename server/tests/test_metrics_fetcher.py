from tests._env import ensure_test_env
ensure_test_env()

import asyncio
import importlib.util
import os
import sys
import pytest

_SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_SERVER_ROOT, ".."))
_BECERTAIN_ROOT = os.path.join(_REPO_ROOT, "BeCertain")
if not os.path.exists(os.path.join(_BECERTAIN_ROOT, "config.py")):
    pytest.skip("BeCertain engine not present in this checkout; skipping cross-service fetcher test", allow_module_level=True)

_added = False
_prev_config = sys.modules.get("config")
if _BECERTAIN_ROOT not in sys.path:
    sys.path.insert(0, _BECERTAIN_ROOT)
    _added = True
try:
    _config_path = os.path.join(_BECERTAIN_ROOT, "config.py")
    _config_spec = importlib.util.spec_from_file_location("config", _config_path)
    if _config_spec is None or _config_spec.loader is None:
        raise RuntimeError(f"Unable to load BeCertain config at {_config_path}")
    _config_module = importlib.util.module_from_spec(_config_spec)
    sys.modules["config"] = _config_module
    _config_spec.loader.exec_module(_config_module)
    from engine.fetcher import fetch_metrics
finally:
    if _prev_config is not None:
        sys.modules["config"] = _prev_config
    else:
        sys.modules.pop("config", None)
    if _added and sys.path and sys.path[0] == _BECERTAIN_ROOT:
        sys.path.pop(0)


class DummyMetrics:
    def __init__(self):
        self.queried = []

    async def query_range(self, query, start, end, step):
        self.queried.append((query, start, end, step))
        # always return an empty result set to simulate an empty TSDB
        return {"data": {"result": []}}

    async def scrape(self):
        # simulate a Prometheus exposition string with a couple of metrics
        return """
# HELP process_cpu_seconds_total CPU time
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 123.5
some_other_metric 7
"""


class DummyProvider:
    def __init__(self):
        self.metrics = DummyMetrics()

    async def query_metrics(self, query, start, end, step):
        # delegate to the underlying metrics connector
        return await self.metrics.query_range(query, start, end, step)


def test_fetch_metrics_fallback_from_scrape():
    provider = DummyProvider()
    queries = [
        "rate(process_cpu_seconds_total[5m])",
        "process_resident_memory_bytes",
    ]
    # using arbitrary start/end values
    results = asyncio.run(fetch_metrics(provider, queries, start=10, end=20, step="60"))

    # should have produced at least one synthetic series for cpu
    assert results, "fetch_metrics should return a non-empty list when scrape fallback succeeds"
    # inspect the first response for the cpu metric
    cpu_resp = next(
        (
            response
            for _query, response in results
            if response.get("data", {}).get("result")
            and response["data"]["result"][0]["metric"]["__name__"] == "process_cpu_seconds_total"
        ),
        None,
    )
    assert cpu_resp is not None, "cpu metric should appear in fallback response"
    vals = cpu_resp["data"]["result"][0]["values"]
    # two points (start + end) with the same scraped value
    assert len(vals) == 2
    assert vals[0][1] == vals[1][1] == 123.5


def test_mimir_connector_scrape(monkeypatch):
    import httpx
    from connectors.mimir import MimirConnector

    captured = {}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            captured['url'] = url
            captured['headers'] = headers

            class R:
                status_code = 200
                text = "foo 1\n"

                def raise_for_status(self):
                    return None

            return R()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    conn = MimirConnector("http://mimir:9009", "mytenant")
    scraped = asyncio.run(conn.scrape())
    assert "foo" in scraped
    assert captured['url'].endswith("/metrics")
    assert captured['headers']['X-Scope-OrgID'] == "mytenant"
