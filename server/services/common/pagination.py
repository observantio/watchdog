"""
Pagination utilities for capping query limits and offsets to prevent excessive data retrieval and ensure efficient database queries. This module provides a function to cap the pagination parameters based on configured default and maximum limits, ensuring that API endpoints that support pagination can enforce reasonable limits on the number of records returned in a single request while allowing clients to specify their desired pagination settings within those constraints.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Tuple, Optional
from config import config as app_config


def _cap_pagination(limit: Optional[int], offset: int) -> Tuple[int, int]:
    capped_limit = max(1, min(int(limit) if limit is not None else int(app_config.DEFAULT_QUERY_LIMIT), int(app_config.MAX_QUERY_LIMIT)))
    return capped_limit, max(0, int(offset))
