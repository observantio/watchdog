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


def test_get_trace_volume_uses_metrics_query_range():
    service = TempoService(tempo_url="http://tempo.test")

    called = []

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        called.append((promql, start_us, end_us, step_s))
        # return a single-sample matrix matching expected shape
        ts = int((start_us or int(__import__('time').time() * 1_000_000)) / 1_000_000)
        return {"status": "success", "data": {"result": [{"metric": {}, "values": [[ts, "5"]]}]}}

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    assert len(called) == 1
    values = result["data"]["result"][0]["values"]
    assert values[0][1] == "5"


def test_get_trace_volume_normalizes_sparse_metric_series_to_full_buckets():
    """If the metrics backend returns a sparse series, ensure the service fills missing
    buckets with zeros so the UI receives a complete time series of the requested
    resolution (start/end/step).
    """
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        # return values only for the 0th and 2nd buckets
        start_s = int((start_us or int(__import__('time').time() * 1_000_000)) / 1_000_000)
        vals = [[start_s, "2"], [start_s + 2 * step_s, "7"]]
        return {"status": "success", "data": {"result": [{"metric": {}, "values": vals}]}}

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (5 * 60 * 1_000_000)  # 5 minutes -> 5 buckets at step=60
    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    values = result["data"]["result"][0]["values"]
    # should return a value for every expected bucket
    assert len(values) == 5
    assert values[0][1] == "2"
    assert values[1][1] == "0"
    assert values[2][1] == "7"
    # timestamps should be integer seconds
    assert all(isinstance(v[0], int) for v in values)


def test_get_trace_volume_falls_back_to_bucket_when_metrics_unavailable():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        # metrics endpoint returns no result -> fallback expected
        return {"status": "success", "data": {"result": []}}

    service._query_metrics_range = fake_query_metrics
    # Prepare a fake search_traces that returns traces across multiple buckets
    start = 1_700_000_000_000_000
    end = start + (10 * 60 * 1_000_000)

    async def fake_search_traces(query, tenant_id="default", fetch_full_traces=False):
        # create one trace per 2-minute interval within the range
        traces = []
        for i in range(0, 10):
            # place traces at start + i*60s
            ts_us = int(start + i * 60 * 1_000_000)
            spans = [{"spanID": "root", "traceID": f"t{i}", "startTime": ts_us, "duration": 1000, "serviceName": "svc", "attributes": {}, "processID": "svc"}]
            traces.append({"traceID": f"t{i}", "spans": spans})

        # Build a TraceResponse-like object matching service expectations
        from models.observability.tempo_models import TraceResponse, Trace, Span

        trace_objs = []
        for t in traces:
            span = Span(spanID=t["spans"][0]["spanID"], traceID=t["spans"][0]["traceID"], operationName="op", startTime=t["spans"][0]["startTime"], duration=t["spans"][0]["duration"], tags=[], serviceName=t["spans"][0]["serviceName"], attributes={}, processID=t["spans"][0]["processID"])
            trace_objs.append(Trace(traceID=t["traceID"], spans=[span], processes={}))

        return TraceResponse(data=trace_objs, total=len(trace_objs), limit=query.limit, offset=0)

    service.search_traces = fake_search_traces

    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    values = result["data"]["result"][0]["values"]
    assert len(values) > 1


def test_get_trace_volume_tries_label_candidates_in_order():
    service = TempoService(tempo_url="http://tempo.test")

    called = []

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        called.append(promql)
        # Simulate the first selector returning a non-empty result; others should
        # not be called in that case.
        if 'resource.service.name' in promql:
            ts = int((start_us or int(__import__('time').time() * 1_000_000)) / 1_000_000)
            return {"status": "success", "data": {"result": [{"metric": {}, "values": [[ts, "3"]]}]}}
        return {"status": "success", "data": {"result": []}}

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(service="svc", start=start, end=end, step=60))

    # ensure we tried the first candidate, did not use a combined '+' expression,
    # and stopped after finding the first non-empty selector
    assert any("resource.service.name" in p for p in called)
    assert all(" + " not in p for p in called)
    assert len(called) == 1
    values = result["data"]["result"][0]["values"]
    assert values[0][1] == "3"


def test_get_trace_volume_uses_first_non_empty_selector():
    service = TempoService(tempo_url="http://tempo.test")

    called = []

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        called.append(promql)
        # First candidate returns empty; second candidate returns data.
        if 'resource.service.name' in promql:
            return {"status": "success", "data": {"result": []}}
        if 'service_name' in promql:
            ts = int((start_us or int(__import__('time').time() * 1_000_000)) / 1_000_000)
            return {"status": "success", "data": {"result": [{"metric": {}, "values": [[ts, "7"]]}]}}
        return {"status": "success", "data": {"result": []}}

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(service="svc", start=start, end=end, step=60))

    # ensure we tried selectors in order and used the first non-empty result
    assert len(called) >= 2
    assert 'resource.service.name' in called[0]
    assert 'service_name' in called[1]
    values = result["data"]["result"][0]["values"]
    assert values[0][1] == "7"


def test_get_trace_volume_estimates_from_total_traces_when_metrics_missing():
    service = TempoService(tempo_url="http://tempo.test")

    # metrics query returns empty (unavailable)
    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        return {"status": "success", "data": {"result": []}}

    service._query_metrics_range = fake_query_metrics

    # get_trace_metrics returns a total count we can use to estimate per-bucket values
    async def fake_get_trace_metrics(service=None, start=None, end=None, tenant_id="default"):
        return {"total_traces": 95}

    service.get_trace_metrics = fake_get_trace_metrics

    start = 1_700_000_000_000_000
    end = start + (10 * 60 * 1_000_000)  # 10 minutes
    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    values = result["data"]["result"][0]["values"]
    assert len(values) == 10
    total = sum(int(v[1]) for v in values)
    assert total == 95


def test_get_trace_volume_caches_results_for_ttl():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        return {"status": "success", "data": {"result": []}}

    service._query_metrics_range = fake_query_metrics

    # first call returns 60 traces
    async def first_metrics(service=None, start=None, end=None, tenant_id="default"):
        return {"total_traces": 60}

    service.get_trace_metrics = first_metrics

    start = 1_700_000_000_000_000
    end = start + (60 * 1_000_000)  # 1 minute
    res1 = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    # change the underlying metric provider to a different value; cached result should be returned
    async def second_metrics(service_arg=None, start=None, end=None, tenant_id="default"):
        return {"total_traces": 5}

    service.get_trace_metrics = second_metrics

    res2 = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))
    assert res1 == res2
