"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env
ensure_test_env()
import asyncio
from services.tempo import metrics as tempo_metrics

def test_extract_metric_values_aggregates_and_skips():
    resp = {
        "data": {
            "result": [
                {"values": [[1600000000, "1"], [1600000060, "2"]]},
                {"values": [[1600000000, "3"], [1600000060, "1"]]},
            ]
        }
    }
    out = tempo_metrics.extract_metric_values(resp)
    assert out == [[1600000000, "4"], [1600000060, "3"]]
    resp2 = {"data": {"result": [{"values": [[1600000000, "x"], [1600000060, "1"]]}]}}
    out2 = tempo_metrics.extract_metric_values(resp2)
    assert out2 == [[1600000060, "1"]]


def test_query_metrics_range_disabled_and_4xx_behavior():
    result, enabled = asyncio.run(tempo_metrics.query_metrics_range(client=None, promql="x", start_us=None, end_us=None, metrics_enabled=False))
    assert isinstance(result, dict) and result.get("status") == "error"
    assert enabled is False
    class DummyClient:
        async def get(self, url, params=None, headers=None):
            class R:
                status_code = 200
                def json(self):
                    return {"data": {"result": [[1, "2"]]}}
                def raise_for_status(self):
                    return None
            return R()

    client = DummyClient()
    result2, enabled2 = asyncio.run(
        tempo_metrics.query_metrics_range(
            client=client,
            promql="q",
            start_us=1,
            end_us=2,
            mimir_url="http://mimir",
            metrics_enabled=True,
        )
    )
    assert isinstance(result2, dict)
    assert enabled2 is True
