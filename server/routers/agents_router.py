"""Agents router for OTLP heartbeat and agent listing."""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

import httpx
from fastapi import APIRouter, Request, status, Depends, HTTPException
from fastapi.responses import JSONResponse

from models.agent_models import AgentHeartbeat
from services.agent_service import AgentService
from models.auth_models import TokenData
from config import config

from routers.auth_router import get_current_user, auth_service
from middleware.rate_limit import enforce_ip_rate_limit

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

_otlp_router = APIRouter(tags=["otlp"])

agent_service = AgentService()
_mimir_client = httpx.AsyncClient(
    timeout=httpx.Timeout(config.DEFAULT_TIMEOUT),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)


def _require_otlp_ingest_token(request: Request) -> None:
    """Optional shared-secret protection for OTLP ingest endpoints."""
    if not config.OTLP_INGEST_TOKEN:
        return
    provided = request.headers.get("x-otlp-token")
    if provided != config.OTLP_INGEST_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OTLP ingest token",
        )


def _any_value_to_python(value) -> Any:
    if value is None:
        return None
    kind = value.WhichOneof("value")
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "bytes_value":
        try:
            return value.bytes_value.decode("utf-8", errors="replace")
        except Exception:
            return value.bytes_value
    if kind == "array_value":
        return [_any_value_to_python(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _any_value_to_python(kv.value) for kv in value.kvlist_value.values}
    return None


def _attributes_to_dict(attributes) -> Dict[str, Any]:
    return {kv.key: _any_value_to_python(kv.value) for kv in attributes}


def _update_agents_from_resources(resources, signal: str) -> int:
    count = 0
    for res in resources:
        attrs = _attributes_to_dict(res.resource.attributes)
        if attrs:
            agent_service.update_from_resource(attrs, signal)
            count += 1
    return count


@router.get("/")
async def list_agents(request: Request):
    """List known OTLP agents."""
    enforce_ip_rate_limit(
        request,
        scope="agents_list",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    return [agent.model_dump() for agent in agent_service.list_agents()]


async def _key_activity(key_value: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    # Use same 1-hour window as dashboard
    start_ns = int((now - timedelta(hours=1)).timestamp() * 1_000_000_000)
    end_ns = int(now.timestamp() * 1_000_000_000)

    metrics_active = False
    metrics_count = 0

    try:
        resp = await _mimir_client.get(
            f"{config.MIMIR_URL.rstrip('/')}/prometheus/api/v1/query",
            params={"query": "count({__name__=~\".+\"})"},
            headers={"X-Scope-OrgID": key_value},
        )
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("data", {}).get("result", [])
        if result:
            try:
                metrics_count = int(float(result[0].get("value", [0, 0])[1]))
            except Exception:
                metrics_count = 0
        metrics_active = metrics_count > 0
    except Exception:
        metrics_active = False

    return {
        "metrics_active": metrics_active,
        "metrics_count": metrics_count,
    }


@router.get("/active")
async def list_active_agents(current_user: TokenData = Depends(get_current_user)):
    """List activity per API key assigned to the user."""
    api_keys = auth_service.list_api_keys(current_user.user_id)

    tasks: List[asyncio.Task] = []
    for key in api_keys:
        tasks.append(asyncio.create_task(_key_activity(key.key)))

    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    activity = []
    recent_agents = agent_service.list_agents()
    for key, result in zip(api_keys, results):
        if isinstance(result, Exception):
            activity.append({
                "name": key.name,
                "is_enabled": key.is_enabled,
                "active": False,
                "success": False,
                "clean": False,
                "host_names": [],
                "metrics_active": False,
                "metrics_count": 0
            })
            continue

        active = bool(result.get("metrics_active"))
        host_names = sorted({a.host_name for a in recent_agents if a.tenant_id == key.key and a.host_name})
        activity.append({
            "name": key.name,
            "is_enabled": key.is_enabled,
            "active": active,
            "success": active,
            "clean": active,
            "host_names": host_names,
            **result
        })

    return activity


@router.post("/heartbeat")
async def heartbeat(request: Request, payload: AgentHeartbeat):
    """Receive explicit heartbeat payloads."""
    enforce_ip_rate_limit(
        request,
        scope="agents_heartbeat",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    agent_service.update_from_heartbeat(payload)
    return {"status": "ok"}


@_otlp_router.post("/v1/traces")
async def otlp_traces(request: Request):
    """Receive OTLP trace exports and update agent registry."""
    enforce_ip_rate_limit(
        request,
        scope="otlp_traces",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    _require_otlp_ingest_token(request)
    body = await request.body()
    try:
        msg = ExportTraceServiceRequest()
        msg.ParseFromString(body)
        count = _update_agents_from_resources(msg.resource_spans, "traces")
        return {"status": "ok", "agents_updated": count}
    except Exception as exc:
        logger.warning("Failed to parse OTLP traces payload: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid OTLP traces payload"},
        )


@_otlp_router.post("/v1/metrics")
async def otlp_metrics(request: Request):
    """Receive OTLP metric exports, update agent registry, and drop metric data."""
    enforce_ip_rate_limit(
        request,
        scope="otlp_metrics",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    _require_otlp_ingest_token(request)
    body = await request.body()
    try:
        msg = ExportMetricsServiceRequest()
        msg.ParseFromString(body)
        count = _update_agents_from_resources(msg.resource_metrics, "metrics")
        return {"status": "ok", "agents_updated": count}
    except Exception as exc:
        logger.warning("Failed to parse OTLP metrics payload: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid OTLP metrics payload"},
        )


otlp_router = _otlp_router
