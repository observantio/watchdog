"""
Shared router-level error handling helpers (moved from routers).
Decorators for mapping expected exceptions to HTTP status codes consistently across route handlers.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from functools import wraps
from typing import Awaitable, Callable, TypeVar
import logging
import asyncio

import httpx
from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
RouteResult = TypeVar("RouteResult")


def _json_safe(value: object) -> object:
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _request_id_for_response(request: Request) -> str | None:
    state_request_id = getattr(getattr(request, "state", None), "request_id", None)
    if isinstance(state_request_id, str) and state_request_id.strip():
        return state_request_id.strip()
    header_request_id = request.headers.get("x-request-id")
    if header_request_id and header_request_id.strip():
        return header_request_id.strip()
    return None


def build_api_error_response(
    *,
    request: Request,
    status_code: int,
    detail: object,
    error_code: str,
) -> JSONResponse:
    payload: dict[str, object] = {
        "detail": _json_safe(detail),
        "error_code": error_code,
    }
    request_id = _request_id_for_response(request)
    if request_id:
        payload["request_id"] = request_id
    response = JSONResponse(status_code=status_code, content=payload)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


def _request_id_from_route_args(args: tuple[object, ...], kwargs: dict[str, object]) -> str | None:
    candidate = kwargs.get("request")
    if isinstance(candidate, Request):
        return _request_id_for_response(candidate)
    for arg in args:
        if isinstance(arg, Request):
            return _request_id_for_response(arg)
    return None


def handle_route_errors(
    *,
    bad_request_exceptions: tuple[type[Exception], ...] = (ValueError,),
    bad_request_detail: str | None = None,
    bad_gateway_exceptions: tuple[type[Exception], ...] = (httpx.HTTPError,),
    bad_gateway_detail: str = "Upstream request failed",
    gateway_timeout_exceptions: tuple[type[Exception], ...] = (asyncio.TimeoutError,),
    gateway_timeout_detail: str = "Upstream request timed out",
    internal_detail: str | None = "Internal server error",
) -> Callable[[Callable[..., Awaitable[RouteResult]]], Callable[..., Awaitable[RouteResult]]]:

    def decorator(func: Callable[..., Awaitable[RouteResult]]) -> Callable[..., Awaitable[RouteResult]]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> RouteResult:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except gateway_timeout_exceptions as exc:
                request_id = _request_id_from_route_args(args, kwargs)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=gateway_timeout_detail,
                    headers={"X-Request-ID": request_id} if request_id else None,
                ) from exc
            except bad_request_exceptions as exc:
                detail = bad_request_detail or str(exc) or "Invalid request"
                request_id = _request_id_from_route_args(args, kwargs)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=detail,
                    headers={"X-Request-ID": request_id} if request_id else None,
                ) from exc
            except bad_gateway_exceptions as exc:
                logger.warning("Upstream request failed in %s: %s", func.__name__, exc)
                request_id = _request_id_from_route_args(args, kwargs)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=bad_gateway_detail,
                    headers={"X-Request-ID": request_id} if request_id else None,
                ) from exc
            except Exception as exc:
                logger.exception("Unhandled exception in route %s: %s", func.__name__, exc)
                if internal_detail:
                    request_id = _request_id_from_route_args(args, kwargs)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=internal_detail,
                        headers={"X-Request-ID": request_id} if request_id else None,
                    ) from exc
                raise

        return wrapper

    return decorator


def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.warning(f"Request validation error for {request.url}: {exc}")
    detail = exc.errors() if hasattr(exc, "errors") else [{"msg": str(exc)}]
    return build_api_error_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detail,
        error_code="VALIDATION_ERROR",
    )


def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(f"Unhandled exception for {request.url}: {exc}")
    return build_api_error_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        error_code="INTERNAL_SERVER_ERROR",
    )
