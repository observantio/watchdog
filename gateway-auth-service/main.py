"""
This is the main entry point for the standalone gateway auth service
as this is decoupled from the main server, it has its own FastAPI app and lifecycle management.


Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from db_models import SessionLocal, _validate_schema_compatibility
from routers import router as gateway_router
from services.gateway_service import GatewayAuthService

from services import config as gw_config

LOG_LEVEL = gw_config.LOG_LEVEL
PORT = gw_config.PORT

logger = logging.getLogger("gateway_auth")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting standalone gateway auth service")
    max_retries = gw_config.GATEWAY_DB_STARTUP_RETRIES
    backoff = gw_config.GATEWAY_DB_STARTUP_BACKOFF
    attempt = 0

    while True:
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                _validate_schema_compatibility(db)
            logger.info("Database connectivity and schema checks passed")
            break
        except Exception as exc:
            attempt += 1
            if attempt >= max_retries:
                logger.exception("Gateway auth service startup check failed after %d attempts: %s", attempt, exc)
                raise
            logger.warning(
                "Database not ready (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                max_retries,
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    yield


app = FastAPI(
    title="BeObservant Gateway Auth Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(gateway_router)

# keep a top-level /health for Docker healthchecks (delegates to service)
_service = GatewayAuthService()

@app.get("/health")
async def health_root():
    return _service.health()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        log_level=LOG_LEVEL.lower(),
    )
