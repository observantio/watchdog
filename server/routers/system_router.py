from fastapi import APIRouter, Depends
from typing import Dict, Any
import logging

from services.system_service import SystemService
from models.auth_models import Permission, TokenData

try:
    from routers.auth_router import require_permission
except ImportError:
    from fastapi import HTTPException, status
    def require_permission(_permission):
        def _deny():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable"
            )
        return _deny

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])
system_service = SystemService()


@router.get("/metrics", response_model=Dict[str, Any])
async def get_system_metrics(
    current_user: TokenData = Depends(require_permission(Permission.READ_AGENTS))
) -> Dict[str, Any]:
    """
    Get system metrics including CPU, memory, disk, network utilization and stress status.
    Requires READ_AGENTS permission.
    """
    try:
        metrics = system_service.get_all_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Error fetching system metrics: {e}")
        return {
            "cpu": {"utilization": 0, "count": 0, "threads": 0, "frequency_mhz": None},
            "memory": {"rss_mb": 0, "vms_mb": 0, "utilization": 0},
            "io": {"read_mb": 0, "write_mb": 0, "read_count": 0, "write_count": 0},
            "network": {
                "total_connections": 0,
                "established": 0,
                "listen": 0,
                "time_wait": 0,
                "close_wait": 0
            },
            "stress": {
                "status": "unknown",
                "message": "Unable to determine process status",
                "issues": []
            }
        }
