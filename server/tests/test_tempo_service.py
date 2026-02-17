import asyncio

from tests._env import ensure_test_env
ensure_test_env()

from services.tempo_service import TempoService
from models.observability.tempo_models import TraceQuery


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

    service._timed_get_json = fake_search
    service.get_trace = fake_get_trace

    result = asyncio.run(service.search_traces(TraceQuery(limit=3), fetch_full_traces=True))

    assert result.total == 3
    assert len(result.data) == 3
    assert max_inflight > 1


def test_get_trace_volume_counts_buckets_concurrently():
    service = TempoService(tempo_url="http://tempo.test")

    inflight = 0
    max_inflight = 0

    async def fake_count(query, tenant_id="default"):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.02)
        inflight -= 1
        return 1

    service.count_traces = fake_count

    start = 1_700_000_000_000_000
    end = start + (10 * 60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    values = result["data"]["result"][0]["values"]
    assert len(values) > 1
    assert max_inflight > 1
