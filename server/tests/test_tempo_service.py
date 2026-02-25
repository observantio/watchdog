import asyncio

from tests._env import ensure_test_env
ensure_test_env()

from models.observability.tempo_models import TraceQuery
from services.tempo_service import TempoService


def test_search_traces_fetches_full_traces_with_concurrency():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_search(*args, **kwargs):
        return {"traces": [{"traceID": "t1"}, {"traceID": "t2"}, {"traceID": "t3"}]}

    inflight = 0
    max_inflight = 0

    async def fake_get_trace(trace_id, tenant_id="default"):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.03)
        inflight -= 1
        return {
            "traceID": trace_id,
            "spans": [],
            "processes": {},
            "warnings": None,
        }

    service._get_json = fake_search
    service.get_trace = fake_get_trace

    result = asyncio.run(service.search_traces(TraceQuery(limit=3), fetch_full_traces=True))

    assert result.total == 3
    assert len(result.data) == 3
    assert max_inflight > 1


def test_get_trace_volume_uses_single_mimir_query_and_normalizes_buckets():
    service = TempoService(tempo_url="http://tempo.test")

    called = []

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        called.append(promql)
        start_s = int((start_us or 0) / 1_000_000)
        return {
            "status": "success",
            "data": {"result": [{"metric": {}, "values": [[start_s, "2"], [start_s + 120, "7"]]}]},
        }

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (5 * 60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(service="svc", start=start, end=end, step=60))

    assert len(called) == 1
    values = result["data"]["result"][0]["values"]
    assert len(values) == 5
    assert values[0][1] == "2"
    assert values[1][1] == "0"
    assert values[2][1] == "7"


def test_count_traces_reads_last_sample_from_mimir():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        return {
            "status": "success",
            "data": {"result": [{"metric": {}, "values": [[1700000000, "3"], [1700000060, "11"]]}]},
        }

    service._query_metrics_range = fake_query_metrics

    total = asyncio.run(
        service.count_traces(
            TraceQuery.model_validate(
                {"service": "svc", "start": 1_700_000_000_000_000, "end": 1_700_000_600_000_000, "limit": 100}
            )
        )
    )
    assert total == 11


def test_get_trace_metrics_relies_on_mimir_count_only():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_count_traces(query, tenant_id="default"):
        return 42

    service.count_traces = fake_count_traces

    metrics = asyncio.run(
        service.get_trace_metrics(service="svc", start=1_700_000_000_000_000, end=1_700_000_600_000_000)
    )

    assert metrics["total_traces"] == 42
    assert metrics["service"] == "svc"
    assert metrics["error_count"] is None
