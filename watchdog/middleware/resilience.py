"""
Resilience decorators for service calls.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar

import httpx

from config import config

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def _is_retriable_httpx(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        resp = getattr(exc, "response", None)
        if resp is None:
            return True
        status = resp.status_code
        if 400 <= status < 500 and status not in (408, 429):
            return False
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError)):
        return True
    return False


def _backoff_delay(attempt: int, base: float, cap: float, jitter_ratio: float) -> float:
    delay = min(cap, max(0.0, base) * (2**attempt))
    jr = max(0.0, jitter_ratio)
    if jr:
        jitter = delay * jr
        delay = max(0.0, delay + random.uniform(-jitter, jitter))
    return float(delay)


def with_retry(
    max_retries: int = config.MAX_RETRIES,
    backoff: float = config.RETRY_BACKOFF,
    *,
    max_backoff: float = config.RETRY_MAX_BACKOFF,
    jitter: float = config.RETRY_JITTER,
    retriable: Callable[[Exception], bool] = _is_retriable_httpx,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    max_retries = max(0, int(max_retries))

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (httpx.HTTPError, asyncio.TimeoutError, OSError, RuntimeError, ValueError) as e:
                    if not retriable(e):
                        raise

                    last_exc = e
                    if attempt >= max_retries:
                        logger.error(
                            "Retry exhausted: fn=%s attempts=%d last_error=%r",
                            func.__name__,
                            max_retries + 1,
                            e,
                        )
                        raise

                    delay = _backoff_delay(attempt, backoff, max_backoff, jitter)
                    logger.warning(
                        "Retrying: fn=%s attempt=%d/%d delay=%.3fs error=%r",
                        func.__name__,
                        attempt + 1,
                        max_retries + 1,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)

            raise last_exc if last_exc is not None else RuntimeError(
                f"Retry wrapper exited unexpectedly for {func.__name__}"
            )

        return wrapper

    return decorator


def with_timeout(
    timeout: float = config.DEFAULT_TIMEOUT,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    timeout = float(timeout)

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError as e:
                logger.error("Timeout: fn=%s timeout=%.3fs", func.__name__, timeout)
                raise e

        return wrapper

    return decorator
