from tests._env import ensure_test_env
ensure_test_env()

from services.tempo import promql as tempo_promql


def test_build_promql_selector_and_count():
    assert tempo_promql.build_promql_selector(None) == ["{}"]

    sels = tempo_promql.build_promql_selector("svc")
    assert any("service=" in s or "service_name" in s for s in sels)

    count = tempo_promql.build_count_promql("svc", 60)
    assert "count_over_time" in count and "sum(" in count