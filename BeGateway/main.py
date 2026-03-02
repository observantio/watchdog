"""
Gateway auth service entry point.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import config as gw_config
from routers import router as gateway_router
from services.gateway_service import GatewayAuthService

logging.basicConfig(
    level=getattr(logging, gw_config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("gateway_auth")

service = GatewayAuthService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting standalone gateway auth service")

    max_retries = gw_config.GATEWAY_STARTUP_RETRIES
    backoff = gw_config.GATEWAY_STARTUP_BACKOFF
    attempt = 0

    while True:
        try:
            if gw_config.AUTH_API_URL:
                probe_token = gw_config.GATEWAY_STATUS_OTLP_TOKEN
                if not probe_token:
                    if gw_config.GATEWAY_STARTUP_CHECK_MODE == "strict":
                        raise RuntimeError(
                            "GATEWAY_STATUS_OTLP_TOKEN is required when GATEWAY_STARTUP_CHECK_MODE=strict"
                        )
                    probe_token = "__gateway_startup_probe__"
                    logger.warning(
                        "GATEWAY_STATUS_OTLP_TOKEN is not set; using synthetic startup probe token to verify auth API connectivity"
                    )
                service._fetch_org_from_api(probe_token)
            logger.info("Startup connectivity checks passed")
            break
        except Exception as exc:
            attempt += 1
            if attempt >= max_retries:
                logger.exception("Gateway startup check failed after %d attempts: %s", attempt, exc)
                raise
            logger.warning(
                "Startup check failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt, max_retries, exc, backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    yield


app = FastAPI(
    title="BeObservant Gateway Auth Service",
    version="1.0.0",
    docs_url="/docs" if gw_config.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if gw_config.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if gw_config.ENABLE_API_DOCS else None,
    lifespan=lifespan,
)

app.include_router(gateway_router)


@app.get("/health")
async def health_root():
    return service.health()

if __name__ == "__main__":
    uvicorn_kwargs: dict = {
        "app": "main:app",
        "host": gw_config.HOST,
        "port": gw_config.PORT,
        "log_level": gw_config.LOG_LEVEL.lower(),
    }
    if gw_config.SSL_CERTFILE and gw_config.SSL_KEYFILE:
        uvicorn_kwargs["ssl_certfile"] = gw_config.SSL_CERTFILE
        uvicorn_kwargs["ssl_keyfile"] = gw_config.SSL_KEYFILE
        if gw_config.SSL_CA_CERTS:
            uvicorn_kwargs["ssl_ca_certs"] = gw_config.SSL_CA_CERTS
        logger.info("TLS enabled")

    uvicorn.run(**uvicorn_kwargs)
