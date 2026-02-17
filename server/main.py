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
import httpx

from config import config, constants
from routers import tempo_router, loki_router, alertmanager_router, grafana_router, auth_router, agents_router, system_router, gateway_router
from database import init_database, init_db, connection_test
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



logger.info("✓ Database schema ready")

from middleware.dependencies import auth_service
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


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=config.MAX_REQUEST_BYTES)
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
        "grafana": config.GRAFANA_URL,
        "mimir": config.MIMIR_URL,
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