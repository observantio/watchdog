import asyncio

from tests._env import ensure_test_env
ensure_test_env()

from services.loki_service import LokiService
from models.observability.loki_models import LogQuery


def test_query_logs_limits_fallback_candidates():
    service = LokiService(loki_url="http://loki.test")

    call_queries = []

    async def fake_get_json(url, *, params, headers):
        query = params.get("query", "")
        call_queries.append(query)
        if query.endswith('.*"}'):
            return {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [{"stream": {"service_name": "api"}, "values": [["1", "ok"]]}],
                },
            }
        return {"status": "success", "data": {"resultType": "streams", "result": []}}

    service._timed_get_json = fake_get_json

    query = LogQuery(query='{service.name="api"}', limit=100)
    result = asyncio.run(service.query_logs(query))

    assert result.status == "success"
    assert len(call_queries) <= 1 + 4
    assert result.data.get("result")


def test_get_log_volume_stops_on_first_successful_candidate():
    service = LokiService(loki_url="http://loki.test")

    called = []

    async def fake_aggregate(query_str, start=None, end=None, step=300, tenant_id="default"):
        called.append(query_str)
        if "service=~\".+\"" in query_str or "{}" in query_str:
            return {"status": "success", "data": {"result": [["1", "2"]]}, "query": query_str, "step": step}
        return {"status": "success", "data": {"result": []}, "query": query_str, "step": step}

    service.aggregate_logs = fake_aggregate

    result = asyncio.run(service.get_log_volume('{service.name="api"}', step=60))

    assert result["status"] == "success"
    assert result["data"]["result"]
    assert len(called) >= 1
