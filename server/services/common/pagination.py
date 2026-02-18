"""Pagination helper shared across storage modules."""
from typing import Tuple, Optional
from config import config as app_config


def _cap_pagination(limit: Optional[int], offset: int) -> Tuple[int, int]:
    capped_limit = max(1, min(int(limit) if limit is not None else int(app_config.DEFAULT_QUERY_LIMIT), int(app_config.MAX_QUERY_LIMIT)))
    return capped_limit, max(0, int(offset))
