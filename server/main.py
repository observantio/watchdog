"""
BeObservant - Observability Control Plane.

A FastAPI server that provides a unified API for managing and querying
observability backends: Tempo (traces), Loki (logs), AlertManager (alerts),
and Grafana (dashboards/datasources).
"""
import logging
import asyncio
import uvloop
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import config, constants
from routers import tempo_router, loki_router, alertmanager_router, grafana_router, auth_router, agents_router, system_router, gateway_router
from database import init_database, init_db, run_column_migration
from middleware.limits import RequestSizeLimitMiddleware, ConcurrencyLimitMiddleware

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("beobservant")

logger.info("Connecting to database: %s", config.DATABASE_URL.split("@")[-1])
init_database(config.DATABASE_URL, config.LOG_LEVEL == "debug")
init_db()
logger.info("✓ Database initialized")

run_column_migration("user_api_keys", "otlp_token", "VARCHAR(200)")
run_column_migration("alert_rules", "org_id", "VARCHAR")

# Grafana enterprise feature columns
run_column_migration("users", "grafana_user_id", "INTEGER")
run_column_migration("groups", "grafana_team_id", "INTEGER")
run_column_migration("grafana_dashboards", "labels", "JSON DEFAULT '{}'")
run_column_migration("grafana_dashboards", "is_hidden", "BOOLEAN DEFAULT FALSE")
run_column_migration("grafana_dashboards", "hidden_by", "JSON DEFAULT '[]'")
run_column_migration("grafana_datasources", "labels", "JSON DEFAULT '{}'")
run_column_migration("grafana_datasources", "is_hidden", "BOOLEAN DEFAULT FALSE")
run_column_migration("grafana_datasources", "hidden_by", "JSON DEFAULT '[]'")

logger.info("✓ Database migrations checked")

from routers.auth_router import auth_service
auth_service._lazy_init()

auth_service.backfill_otlp_tokens()
logger.info("✓ Auth service initialized")

from contextlib import asynccontextmanager

@asynccontextmanager
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
            getattr(agents_router, "loki_service", None),
            getattr(agents_router, "tempo_service", None),
        ):
            client = getattr(svc, "_client", None)
            if client is not None:
                clients.append(client)

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

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=config.MAX_REQUEST_BYTES)
app.add_middleware(
    ConcurrencyLimitMiddleware,
    max_concurrent=config.MAX_CONCURRENT_REQUESTS,
    acquire_timeout=config.CONCURRENCY_ACQUIRE_TIMEOUT,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, 
    exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors with detailed error messages."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
        },
    )

@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request, 
    exc: Exception
) -> JSONResponse:
    """Handle unexpected errors gracefully."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": constants.ERROR_INTERNAL},
    )


@app.on_event("shutdown")
async def _shutdown_http_clients() -> None:
    """Close shared httpx.AsyncClient instances for a clean shutdown."""
    clients = []
    for svc in (
        getattr(tempo_router, "tempo_service", None),
        getattr(loki_router, "loki_service", None),
        getattr(alertmanager_router, "alertmanager_service", None),
        getattr(alertmanager_router, "notification_service", None),
        getattr(grafana_router, "grafana_service", None),
        getattr(agents_router, "loki_service", None),
        getattr(agents_router, "tempo_service", None),
    ):
        client = getattr(svc, "_client", None)
        if client is not None:
            clients.append(client)

    extra = getattr(agents_router, "_mimir_client", None)
    if extra is not None:
        clients.append(extra)

    unique = {id(c): c for c in clients}.values()
    if unique:
        await asyncio.gather(*(c.aclose() for c in unique), return_exceptions=True)

app.include_router(auth_router.router)
app.include_router(gateway_router.router)
app.include_router(agents_router.router)
app.include_router(system_router.router)
app.include_router(tempo_router.router)
app.include_router(loki_router.router)
app.include_router(alertmanager_router.router)
app.include_router(alertmanager_router.webhook_router)
app.include_router(grafana_router.router)


@app.get("/", tags=["info"])
async def root() -> dict:
    """Root endpoint with API information and available endpoints."""
    return {
        "service": constants.APP_NAME,
        "version": constants.APP_VERSION,
        "endpoints": {
            constants.SERVICE_TEMPO: "/api/tempo",
            constants.SERVICE_LOKI: "/api/loki",
            constants.SERVICE_ALERTMANAGER: "/api/alertmanager",
            constants.SERVICE_GRAFANA: "/api/grafana"
        },
        "documentation": "/docs",
        "health": "/health"
    }

@app.get("/health", tags=["health"])
async def health() -> dict:
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": constants.STATUS_HEALTHY,
        "service": constants.APP_NAME,
        "version": constants.APP_VERSION
    }

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