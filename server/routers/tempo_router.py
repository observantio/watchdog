"""Tempo API router."""
from fastapi import APIRouter, HTTPException, Query, status, Depends, Request
from typing import Optional, List

from models.tempo_models import Trace, TraceQuery, TraceResponse
from services.tempo_service import TempoService
from config import config
from models.auth_models import Permission, TokenData

from routers.auth_router import require_permission

router = APIRouter(
    prefix="/api/tempo",
    tags=["tempo"]
)
tempo_service = TempoService()


def _resolve_tenant_id(request: Request, current_user: TokenData) -> str:
    header_value = request.headers.get("x-scope-orgid") or request.headers.get("X-Scope-OrgID")
    if header_value:
        return header_value
    return getattr(current_user, 'org_id', config.DEFAULT_ORG_ID)


@router.get(
    "/traces/search",
    response_model=TraceResponse,
    summary="Search traces",
    description="Search for traces matching the given criteria by service, operation, duration, and time range"
)
async def search_traces(
    request: Request,
    service: Optional[str] = Query(None, description="Service name filter"),
    operation: Optional[str] = Query(None, description="Operation name filter"),
    min_duration: Optional[str] = Query(None, alias="minDuration", description="Min duration (e.g., 100ms)"),
    max_duration: Optional[str] = Query(None, alias="maxDuration", description="Max duration (e.g., 1s)"),
    start: Optional[int] = Query(None, description="Start time in microseconds"),
    end: Optional[int] = Query(None, description="End time in microseconds"),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Maximum traces to return"),
    current_user: TokenData = Depends(require_permission(Permission.READ_TRACES))
) -> TraceResponse:
    query = TraceQuery(
        service=service,
        operation=operation,
        min_duration=min_duration,
        max_duration=max_duration,
        start=start,
        end=end,
        limit=limit
    )
    
    tenant_id = _resolve_tenant_id(request, current_user)
    result = await tempo_service.search_traces(query, tenant_id=tenant_id)
    return result


@router.get(
    "/traces/{trace_id}",
    response_model=Trace,
    summary="Get trace by ID",
    description="Returns the complete trace with all spans and their details"
)
async def get_trace(
    trace_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission(Permission.READ_TRACES))
) -> Trace:
    tenant_id = _resolve_tenant_id(request, current_user)
    trace = await tempo_service.get_trace(trace_id, tenant_id=tenant_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found"
        )
    return trace


@router.get(
    "/services",
    response_model=List[str],
    summary="List services",
    description="Return list of services that have traces"
)
async def get_services(request: Request, current_user: TokenData = Depends(require_permission(Permission.READ_TRACES))) -> List[str]:
    tenant_id = _resolve_tenant_id(request, current_user)
    services = await tempo_service.get_services(tenant_id=tenant_id)
    return services

@router.get(
    "/services/{service}/operations",
    response_model=List[str],
    summary="List operations for service",
    description="Get all unique operation names for the given service"
)
async def get_operations(
    service: str,
    request: Request,
    current_user: TokenData = Depends(require_permission(Permission.READ_TRACES))
) -> List[str]:
    tenant_id = _resolve_tenant_id(request, current_user)
    operations = await tempo_service.get_operations(service, tenant_id=tenant_id)
    return operations


@router.get(
    "/metrics",
    summary="Get trace metrics",
    description="Returns aggregated metrics like trace count, span count, durations, and error rates"
)
async def get_trace_metrics(
    service: Optional[str] = Query(None, description="Service name filter"),
    start: Optional[int] = Query(None, description="Start time in microseconds"),
    end: Optional[int] = Query(None, description="End time in microseconds"),
    request: Request = None,
    current_user: TokenData = Depends(require_permission(Permission.READ_TRACES))
) -> dict:
    """Get trace metrics and statistics.
    
    Returns aggregated metrics like trace count, span count, durations, and error rates.
    """
    tenant_id = _resolve_tenant_id(request, current_user) if request else getattr(current_user, 'org_id', config.DEFAULT_ORG_ID)
    metrics = await tempo_service.get_trace_metrics(service, start, end, tenant_id=tenant_id)
    return metrics
