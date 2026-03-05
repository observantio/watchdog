"""
PromQL query construction logic for Tempo trace metrics.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import List, Optional

def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

def build_promql_selectors(service: Optional[str]) -> List[str]:
    if not service:
        return ["{}"]
    svc = _escape(service)
    return [
        f'{{resource.service.name="{svc}"}}',
        f'{{service_name="{svc}"}}',
        f'{{service="{svc}"}}',
        f'{{service.name="{svc}"}}',
    ]

def build_count_promql(service: Optional[str], range_s: int, label_variant: int = 0) -> str:
    selectors = build_promql_selectors(service)
    selector = selectors[min(label_variant, len(selectors) - 1)]
    return f"sum(count_over_time({selector}[{range_s}s]))"