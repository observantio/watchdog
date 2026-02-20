"""
PromQL query construction logic for Tempo trace metrics to get volume

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


from typing import List, Optional

_SERVICE_NAME_KEY = "service.name"
_SERVICE_ALIAS_KEY = "service"


def build_promql_selector(service: Optional[str]) -> List[str]:
    if not service:
        return ["{}"]
    return list(dict.fromkeys([
        f'{{resource.service.name="{service}"}}',
        f'{{service_name="{service}"}}',
        f'{{service="{service}"}}',
        f'{{service.name="{service}"}}',
    ]))


def build_count_promql(service: Optional[str], range_s: int) -> str:
    parts = [f"count_over_time({sel}[{range_s}s])" for sel in build_promql_selector(service)]
    return f"sum({ ' + '.join(parts) })"
