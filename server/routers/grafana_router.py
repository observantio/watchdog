"""Grafana API router."""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List

from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate, Folder
)
from services.grafana_service import GrafanaService

router = APIRouter(
    prefix="/api/grafana",
    tags=["grafana"]
)

grafana_service = GrafanaService()


@router.get(
    "/dashboards/search",
    response_model=List[DashboardSearchResult],
    summary="Search dashboards",
    description="Search Grafana dashboards by query string, tags, or starred status"
)
async def search_dashboards(
    query: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    starred: Optional[bool] = Query(None, description="Filter starred dashboards")
) -> List[DashboardSearchResult]:
    results = await grafana_service.search_dashboards(
        query=query,
        tag=tag,
        starred=starred
    )
    return results


@router.get("/dashboards/{uid}")
async def get_dashboard(uid: str):
    """Get a dashboard by UID.
    
    Returns the complete dashboard JSON including all panels and configuration.
    """
    dashboard = await grafana_service.get_dashboard(uid)
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return dashboard


@router.post("/dashboards")
async def create_dashboard(dashboard: DashboardCreate = Body(..., description="Dashboard to create")):
    """Create a new dashboard.
    
    Creates a new Grafana dashboard with the specified configuration.
    """
    result = await grafana_service.create_dashboard(dashboard)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.put("/dashboards/{uid}")
async def update_dashboard(
    uid: str,
    dashboard: DashboardUpdate = Body(..., description="Dashboard updates")
):
    """Update an existing dashboard.
    
    Updates the dashboard with the specified UID.
    """
    result = await grafana_service.update_dashboard(uid, dashboard)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Dashboard {uid} not found or update failed"
        )
    return result


@router.delete("/dashboards/{uid}")
async def delete_dashboard(uid: str):
    """Delete a dashboard.
    
    Permanently deletes the dashboard with the specified UID.
    """
    success = await grafana_service.delete_dashboard(uid)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Dashboard {uid} not found or delete failed"
        )
    return {"status": "success", "message": f"Dashboard {uid} deleted"}


# Datasource endpoints

@router.get("/datasources", response_model=List[Datasource])
async def get_datasources():
    """Get all datasources.
    
    Returns a list of all configured datasources in Grafana.
    """
    datasources = await grafana_service.get_datasources()
    return datasources


@router.get("/datasources/uid/{uid}", response_model=Datasource)
async def get_datasource_by_uid(uid: str):
    """Get a datasource by UID.
    
    Returns detailed information about a specific datasource.
    """
    datasource = await grafana_service.get_datasource(uid)
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found")
    return datasource


@router.get("/datasources/name/{name}", response_model=Datasource)
async def get_datasource_by_name(name: str):
    """Get a datasource by name.
    
    Returns detailed information about a specific datasource by its name.
    """
    datasource = await grafana_service.get_datasource_by_name(name)
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found")
    return datasource


@router.post("/datasources", response_model=Datasource)
async def create_datasource(
    datasource: DatasourceCreate = Body(..., description="Datasource to create")
):
    """Create a new datasource.
    
    Creates a new datasource in Grafana (Prometheus, Loki, Tempo, etc.).
    """
    result = await grafana_service.create_datasource(datasource)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create datasource")
    return result


@router.put("/datasources/{uid}", response_model=Datasource)
async def update_datasource(
    uid: str,
    datasource: DatasourceUpdate = Body(..., description="Datasource updates")
):
    """Update an existing datasource.
    
    Updates the datasource configuration for the specified UID.
    """
    result = await grafana_service.update_datasource(uid, datasource)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Datasource {uid} not found or update failed"
        )
    return result


@router.delete("/datasources/{uid}")
async def delete_datasource(uid: str):
    """Delete a datasource.
    
    Permanently deletes the datasource with the specified UID.
    """
    success = await grafana_service.delete_datasource(uid)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Datasource {uid} not found or delete failed"
        )
    return {"status": "success", "message": f"Datasource {uid} deleted"}




@router.get("/folders", response_model=List[Folder])
async def get_folders():
    """Get all folders.
    
    Returns a list of all dashboard folders in Grafana.
    """
    folders = await grafana_service.get_folders()
    return folders


@router.post("/folders", response_model=Folder)
async def create_folder(title: str = Body(..., embed=True, description="Folder title")):
    """Create a new folder.
    
    Creates a new folder for organizing dashboards.
    """
    result = await grafana_service.create_folder(title)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
async def delete_folder(uid: str):
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
