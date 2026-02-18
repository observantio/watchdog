from tests._env import ensure_test_env
ensure_test_env()

from services.tempo import params as tempo_params
from models.observability.tempo_models import TraceQuery


def test_build_search_params_various_options():
    q = TraceQuery(limit=10)
    p = tempo_params.build_search_params(q)
    assert p["limit"] == 10

    q2 = TraceQuery(limit=5, service="svc", operation="op", tags={"k": "v"}, start=1000000, end=2000000, min_duration="10ms")
    p2 = tempo_params.build_search_params(q2)
    assert "tags" in p2 and "service.name" in p2["tags"]
    assert p2["start"] == 1
    assert p2["minDuration"] == "10ms"