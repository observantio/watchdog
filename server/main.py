"""
Entrypoint for the FastAPI application, setting up the server, middleware, routes, and database connections. This module initializes the application, configures logging, sets up CORS and security headers, and defines the main API endpoints for health checks and service information. It also includes exception handlers for validation errors and unexpected exceptions to ensure consistent error responses. The application is designed to be modular, with separate routers for different services (Tempo, Loki, Alertmanager, Grafana) and a shared authentication system. The server is configured to use uvloop for improved performance and includes graceful shutdown logic to clean up resources on exit.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
import asyncio
import os
import uvloop
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import httpx

from config import config, constants
from routers import (
    tempo_router,
    loki_router,
    alertmanager_router,
    grafana_router,
    becertain_router,
    auth_router,
    agents_router,
    system_router,
    internal_router,
)
from database import init_database, init_db, connection_test
from db_models import AuditLog
from middleware.limits import RequestSizeLimitMiddleware, ConcurrencyLimitMiddleware
from middleware.rate_limit import client_ip

from middleware.audit import security_headers_middleware
from middleware.error_handlers import (
    validation_exception_handler,
    general_exception_handler,
)
from services.becertain_proxy_service import becertain_proxy_service

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("beobservant")

if os.getenv("SKIP_STARTUP_DB_INIT", "").lower() not in {"1", "true", "yes"}:
    logger.info("Connecting to database: %s", config.DATABASE_URL.split("@")[-1])
    init_database(config.DATABASE_URL, config.LOG_LEVEL == "debug")
    init_db()
    logger.info("✓ Database initialized")
    logger.info("✓ Database schema ready")

    from middleware.dependencies import auth_service
    auth_service._lazy_init()
    auth_service.backfill_otlp_tokens()
    logger.info("✓ Auth service initialized")


async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        clients = []
        for svc in (
            getattr(tempo_router, "tempo_service", None),
            getattr(loki_router, "loki_service", None),
            getattr(alertmanager_router, "alertmanager_service", None),
            getattr(alertmanager_router, "notification_service", None),
            getattr(grafana_router, "grafana_service", None),
            becertain_proxy_service,
        ):
            client = getattr(svc, "_client", None)
            if client is not None:
                clients.append(client)
            extra_client = getattr(svc, "_mimir_client", None)
            if extra_client is not None:
                clients.append(extra_client)

        extra = getattr(agents_router, "_mimir_client", None)
        if extra is not None:
            clients.append(extra)

        unique = {id(c): c for c in clients}.values()
        if unique:
            await asyncio.gather(*(c.aclose() for c in unique), return_exceptions=True)

app = FastAPI(
    title=constants.APP_NAME,
    description=constants.APP_DESCRIPTION,
    version=constants.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.middleware("http")(security_headers_middleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=config.MAX_REQUEST_BYTES)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    ConcurrencyLimitMiddleware,
    max_concurrent=config.MAX_CONCURRENT_REQUESTS,
    acquire_timeout=config.CONCURRENCY_ACQUIRE_TIMEOUT,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(
    "CORS policy initialized: origins=%s credentials=%s",
    config.CORS_ORIGINS,
    config.CORS_ALLOW_CREDENTIALS,
)


app.include_router(internal_router.router)
app.include_router(auth_router.router)
app.include_router(agents_router.router)
app.include_router(system_router.router)
app.include_router(tempo_router.router)
app.include_router(loki_router.router)
app.include_router(alertmanager_router.router)
app.include_router(grafana_router.router)
app.include_router(becertain_router.router)


@app.get("/", tags=["info"])
async def root() -> dict:
    return {
        "service": constants.APP_NAME,
        "version": constants.APP_VERSION,
        "endpoints": {
            constants.SERVICE_TEMPO: "/api/tempo",
            constants.SERVICE_LOKI: "/api/loki",
            constants.SERVICE_ALERTMANAGER: "/api/alertmanager",
            constants.SERVICE_GRAFANA: "/api/grafana",
            constants.SERVICE_BECERTAIN: "/api/becertain",
        },
        "documentation": "/docs",
        "health": "/health"
    }

@app.get("/health", tags=["health"])
async def health() -> dict:
    return {
        "status": constants.STATUS_HEALTHY,
        "service": constants.APP_NAME,
        "version": constants.APP_VERSION
    }


async def _upstream_reachable(base_url: str) -> bool:
    timeout = httpx.Timeout(2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(base_url)
            return 200 <= response.status_code < 500
    except Exception:
        return False


@app.get("/ready", tags=["health"])
async def ready(request: Request):
    checks = {
        "database": connection_test(),
    }

    upstream_targets = {
        "tempo": config.TEMPO_URL,
        "loki": config.LOKI_URL,
        "alertmanager": config.ALERTMANAGER_URL,
        "benotified": config.BENOTIFIED_URL,
        "grafana": config.GRAFANA_URL,
        "mimir": config.MIMIR_URL,
        "becertain": config.BECERTAIN_URL,
    }

    results = await asyncio.gather(*(_upstream_reachable(url) for url in upstream_targets.values()))
    checks.update({name: ok for name, ok in zip(upstream_targets.keys(), results)})

    is_ready = all(checks.values())
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
    }
    if not is_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return payload

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting {constants.APP_NAME} v{constants.APP_VERSION}")

    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        loop="uvloop",
        log_level=config.LOG_LEVEL
    )
