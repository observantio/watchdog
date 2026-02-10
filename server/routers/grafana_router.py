"""Grafana API router with multi-tenancy support."""
from fastapi import APIRouter, HTTPException, Query, Body, Depends, status
from typing import Optional, List

from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate, Folder
)
from services.grafana_proxy_service import GrafanaProxyService
from services.grafana_service import GrafanaService
from models.auth_models import Permission, TokenData
from database import get_db
from sqlalchemy.orm import Session

from routers.auth_router import require_permission

router = APIRouter(
    prefix="/api/grafana",
    tags=["grafana"]
)

grafana_proxy_service = GrafanaProxyService()
grafana_service = GrafanaService()  # For folders (not multi-tenant yet)


@router.get(
    "/dashboards/search",
    response_model=List[DashboardSearchResult],
    summary="Search dashboards",
    description="Search Grafana dashboards with multi-tenant access control"
)
async def search_dashboards(
    query: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    starred: Optional[bool] = Query(None, description="Filter starred dashboards"),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db)
) -> List[DashboardSearchResult]:
    results = await grafana_proxy_service.search_dashboards(
        db=db,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or [],
        query=query,
        tag=tag,
        starred=starred
    )
    return results


@router.get("/dashboards/{uid}")
async def get_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Get a dashboard by UID with access control.
    
    Returns the complete dashboard JSON including all panels and configuration.
    """
    dashboard = await grafana_proxy_service.get_dashboard(
        db=db,
        uid=uid,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or []
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return dashboard


@router.post("/dashboards")
async def create_dashboard(
    dashboard: DashboardCreate = Body(..., description="Dashboard to create"),
    visibility: str = Query("private", description="Visibility scope: private, group, or tenant"),
    shared_group_ids: Optional[List[str]] = Query(None, description="Group IDs to share with (for group visibility)"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Create a new dashboard with visibility control.
    
    Creates a new Grafana dashboard with specified visibility:
    - private: Only visible to creator
    - group: Visible to specified groups
    - tenant: Visible to all users in tenant
    """
    if visibility not in ["private", "group", "tenant"]:
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    
    result = await grafana_proxy_service.create_dashboard(
        db=db,
        dashboard_create=dashboard,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or [],
        visibility=visibility,
        shared_group_ids=shared_group_ids or []
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.put("/dashboards/{uid}")
async def update_dashboard(
    uid: str,
    dashboard: DashboardUpdate = Body(..., description="Dashboard updates"),
    visibility: Optional[str] = Query(None, description="New visibility scope"),
    shared_group_ids: Optional[List[str]] = Query(None, description="New group IDs to share with"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Update an existing dashboard with access control.
    
    Updates the dashboard with the specified UID. Only the owner can update.
    Optionally update visibility settings.
    """
    if visibility and visibility not in ["private", "group", "tenant"]:
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    
    result = await grafana_proxy_service.update_dashboard(
        db=db,
        uid=uid,
        dashboard_update=dashboard,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or [],
        visibility=visibility,
        shared_group_ids=shared_group_ids
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Dashboard {uid} not found, access denied, or update failed"
        )
    return result


@router.delete("/dashboards/{uid}")
async def delete_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.DELETE_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Delete a dashboard with access control.
    
    Permanently deletes the dashboard. Only the owner can delete.
    """
    success = await grafana_proxy_service.delete_dashboard(
        db=db,
        uid=uid,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or []
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Dashboard {uid} not found, access denied, or delete failed"
        )
    return {"status": "success", "message": f"Dashboard {uid} deleted"}


# Datasource endpoints

@router.get("/datasources", response_model=List[Datasource])
async def get_datasources(
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Get all datasources with multi-tenant access control.
    
    Returns a list of datasources accessible to the current user.
    """
    datasources = await grafana_proxy_service.get_datasources(
        db=db,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or []
    )
    return datasources


@router.get("/datasources/uid/{uid}", response_model=Datasource)
async def get_datasource_by_uid(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Get a datasource by UID with access control.
    
    Returns detailed information about a specific datasource.
    """
    datasource = await grafana_proxy_service.get_datasource(
        db=db,
        uid=uid,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or []
    )
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found or access denied")
    return datasource


@router.get("/datasources/name/{name}", response_model=Datasource)
async def get_datasource_by_name(
    name: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Get a datasource by name.
    
    Note: This endpoint queries Grafana directly without multi-tenant filtering.
    For secure access, use the UID-based endpoint.
    """
    datasource = await grafana_service.get_datasource_by_name(name)
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found")
    
    # Check if user has access to this datasource
    accessible = await grafana_proxy_service.get_datasource(
        db=db,
        uid=datasource.uid,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or []
    )
    
    if not accessible:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found or access denied")
    
    return datasource


@router.post("/datasources", response_model=Datasource)
async def create_datasource(
    datasource: DatasourceCreate = Body(..., description="Datasource to create"),
    visibility: str = Query("private", description="Visibility scope: private, group, or tenant"),
    shared_group_ids: Optional[List[str]] = Query(None, description="Group IDs to share with"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Create a new datasource with visibility control.
    
    Creates a new datasource in Grafana with specified visibility.
    """
    if visibility not in ["private", "group", "tenant"]:
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    
    result = await grafana_proxy_service.create_datasource(
        db=db,
        datasource_create=datasource,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or [],
        visibility=visibility,
        shared_group_ids=shared_group_ids or []
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create datasource")
    return result


@router.put("/datasources/{uid}", response_model=Datasource)
async def update_datasource(
    uid: str,
    datasource: DatasourceUpdate = Body(..., description="Datasource updates"),
    visibility: Optional[str] = Query(None, description="New visibility scope"),
    shared_group_ids: Optional[List[str]] = Query(None, description="New group IDs to share with"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Update an existing datasource with access control.
    
    Updates the datasource configuration. Only the owner can update.
    """
    if visibility and visibility not in ["private", "group", "tenant"]:
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    
    result = await grafana_proxy_service.update_datasource(
        db=db,
        uid=uid,
        datasource_update=datasource,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or [],
        visibility=visibility,
        shared_group_ids=shared_group_ids
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Datasource {uid} not found, access denied, or update failed"
        )
    return result


@router.delete("/datasources/{uid}")
async def delete_datasource(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.DELETE_DASHBOARDS)),
    db: Session = Depends(get_db)
):
    """Delete a datasource with access control.
    
    Permanently deletes the datasource. Only the owner can delete.
    """
    success = await grafana_proxy_service.delete_datasource(
        db=db,
        uid=uid,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=getattr(current_user, 'group_ids', []) or []
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Datasource {uid} not found, access denied, or delete failed"
        )
    return {"status": "success", "message": f"Datasource {uid} deleted"}




@router.get("/folders", response_model=List[Folder])
async def get_folders(current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS))):
    """Get all folders.
    
    Returns a list of all dashboard folders in Grafana.
    Note: Folders are not currently multi-tenant filtered.
    """
    folders = await grafana_service.get_folders()
    return folders


@router.post("/folders", response_model=Folder)
async def create_folder(
    title: str = Body(..., embed=True, description="Folder title"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS))
):
    """Create a new folder.
    
    Creates a new folder for organizing dashboards.
    """
    result = await grafana_service.create_folder(title)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
async def delete_folder(uid: str, current_user: TokenData = Depends(require_permission(Permission.DELETE_DASHBOARDS))):
    """Delete a folder.
    
    Permanently deletes the folder with the specified UID.
    """
    success = await grafana_service.delete_folder(uid)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Folder {uid} not found or delete failed"
        )
    return {"status": "success", "message": f"Folder {uid} deleted"}
