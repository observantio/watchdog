"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from .observability import tempo_router
from .observability import loki_router
from .observability import alertmanager_router
from .observability import grafana_router
from .observability import resolver_router
from .access import auth_router
from .observability import agents_router
from .platform import system_router

__all__ = [
    "tempo_router",
    "loki_router",
    "alertmanager_router",
    "grafana_router",
    "resolver_router",
    "auth_router",
    "agents_router",
    "system_router",
]
