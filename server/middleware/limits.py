"""
Request limiting middleware (backpressure and payload protection).

These middlewares are intentionally dependency-free and work per-process.
For horizontally scaled deployments, combine them with an upstream proxy
(e.g. Nginx/Envoy) and/or a distributed rate limiter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional
import logging
from starlette.responses import PlainTextResponse


@dataclass(frozen=True)
class _TooLarge(Exception):
    max_bytes: int


logger = logging.getLogger(__name__)

class RequestSizeLimitMiddleware:
    """Reject requests whose body exceeds *max_bytes*.

    - Uses Content-Length when available (fast path).
    - Enforces a hard cap while reading the body when Content-Length is
      missing or incorrect.
    """

    def __init__(self, app, max_bytes: int = 1_048_576) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    resp = PlainTextResponse("Request body too large", status_code=413)
                    await resp(scope, receive, send)
                    return
            except ValueError:
                logger.warning("Invalid content-length header")

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body") or b""
                received += len(body)
                if received > self.max_bytes:
                    raise _TooLarge(self.max_bytes)
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLarge:
            resp = PlainTextResponse("Request body too large", status_code=413)
            await resp(scope, receive, send)


class ConcurrencyLimitMiddleware:
    """Apply backpressure by limiting concurrent in-flight requests.

    If the semaphore cannot be acquired within *acquire_timeout*, return 503.
    """

    def __init__(
        self,
        app,
        max_concurrent: int = 200,
        acquire_timeout: float = 1.0,
    ) -> None:
        self.app = app
        self._sem = asyncio.Semaphore(int(max_concurrent))
        self._timeout = float(acquire_timeout)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self._timeout)
        except asyncio.TimeoutError:
            resp = PlainTextResponse("Server busy, please retry", status_code=503)
            await resp(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        finally:
            self._sem.release()

