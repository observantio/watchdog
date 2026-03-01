"""
Normalization logic for Grafana "next" paths.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


from __future__ import annotations
from typing import Optional

def normalize_grafana_next_path(path: Optional[str]) -> str:
    candidate = (path or "/dashboards").strip() or "/dashboards"
    if candidate.startswith(("http://", "https://", "//")):
        return "/dashboards"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    if candidate.startswith("/grafana"):
        candidate = candidate[len("/grafana"):] or "/dashboards"
    return candidate