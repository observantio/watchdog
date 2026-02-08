"""Grafana service for dashboard and datasource management."""
import httpx
import logging
from typing import List, Optional, Dict, Any
import base64

from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate, Folder
)
from config import config
from middleware.resilience import with_retry, with_timeout

logger = logging.getLogger(__name__)

class GrafanaService:
    """Service for interacting with Grafana."""
    
    def __init__(
        self,
        grafana_url: str = config.GRAFANA_URL,
        username: str = config.GRAFANA_USERNAME,
        password: str = config.GRAFANA_PASSWORD
    ):
        """Initialize Grafana service.
        
        Args:
            grafana_url: Base URL for Grafana instance
            username: Grafana admin username
            password: Grafana admin password
        """
        self.grafana_url = grafana_url.rstrip('/')
        self.timeout = config.DEFAULT_TIMEOUT
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.auth_header = f"Basic {encoded}"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Grafana API requests."""
        return {
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
    
    @with_retry()
    @with_timeout()
    async def search_dashboards(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        folder_ids: Optional[List[int]] = None,
        starred: Optional[bool] = None
    ) -> List[DashboardSearchResult]:
        """Search for dashboards.
        
        Args:
            query: Search query string
            tag: Filter by tag
            folder_ids: Filter by folder IDs
            starred: Filter starred dashboards
            
        Returns:
            List of DashboardSearchResult objects
        """
        params = {"type": "dash-db"}
        if query:
            params["query"] = query
        if tag:
            params["tag"] = tag
        if folder_ids:
            params["folderIds"] = folder_ids
        if starred is not None:
            params["starred"] = starred
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.grafana_url}/api/search",
                    params=params,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                return [DashboardSearchResult(**item) for item in data]
                
            except httpx.HTTPError as e:
                logger.error(f"Error searching dashboards: {e}")
                return []
    
    @with_retry()
    @with_timeout()
    async def get_dashboard(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get a dashboard by UID.
        
        Args:
            uid: Dashboard UID
            
        Returns:
            Dashboard data or None if not found
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.grafana_url}/api/dashboards/uid/{uid}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching dashboard {uid}: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def create_dashboard(self, dashboard_create: DashboardCreate) -> Optional[Dict[str, Any]]:
        """Create a new dashboard.
        
        Args:
            dashboard_create: DashboardCreate object
            
        Returns:
            Created dashboard info or None if error
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                data = dashboard_create.model_dump(by_alias=True, exclude_none=True)
                
                response = await client.post(
                    f"{self.grafana_url}/api/dashboards/db",
                    json=data,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPError as e:
                logger.error(f"Error creating dashboard: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def update_dashboard(
        self,
        uid: str,
        dashboard_update: DashboardUpdate
    ) -> Optional[Dict[str, Any]]:
        """Update an existing dashboard.
        
        Args:
            uid: Dashboard UID
            dashboard_update: DashboardUpdate object
            
        Returns:
            Updated dashboard info or None if error
        """
        
        existing = await self.get_dashboard(uid)
        if not existing:
            return None
        
        
        dashboard_update.dashboard.uid = uid
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                data = dashboard_update.model_dump(by_alias=True, exclude_none=True)
                
                response = await client.post(
                    f"{self.grafana_url}/api/dashboards/db",
                    json=data,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPError as e:
                logger.error(f"Error updating dashboard {uid}: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def delete_dashboard(self, uid: str) -> bool:
        """Delete a dashboard.
        
        Args:
            uid: Dashboard UID
            
        Returns:
            True if successful, False otherwise
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.delete(
                    f"{self.grafana_url}/api/dashboards/uid/{uid}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return True
                
            except httpx.HTTPError as e:
                logger.error(f"Error deleting dashboard {uid}: {e}")
                return False
    
    
    
    @with_retry()
    @with_timeout()
    async def get_datasources(self) -> List[Datasource]:
        """Get all datasources.
        
        Returns:
            List of Datasource objects
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.grafana_url}/api/datasources",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                return [Datasource(**ds) for ds in data]
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching datasources: {e}")
                return []
    
    @with_retry()
    @with_timeout()
    async def get_datasource(self, uid: str) -> Optional[Datasource]:
        """Get a datasource by UID.
        
        Args:
            uid: Datasource UID
            
        Returns:
            Datasource object or None if not found
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.grafana_url}/api/datasources/uid/{uid}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                return Datasource(**data)
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching datasource {uid}: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def get_datasource_by_name(self, name: str) -> Optional[Datasource]:
        """Get a datasource by name.
        
        Args:
            name: Datasource name
            
        Returns:
            Datasource object or None if not found
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.grafana_url}/api/datasources/name/{name}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                return Datasource(**data)
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching datasource {name}: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def create_datasource(self, datasource: DatasourceCreate) -> Optional[Datasource]:
        """Create a new datasource.
        
        Args:
            datasource: DatasourceCreate object
            
        Returns:
            Created Datasource object or None if error
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                data = datasource.model_dump(by_alias=True, exclude_none=True)
                
                response = await client.post(
                    f"{self.grafana_url}/api/datasources",
                    json=data,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                
                
                if "datasource" in result:
                    return Datasource(**result["datasource"])
                return None
                
            except httpx.HTTPError as e:
                logger.error(f"Error creating datasource: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def update_datasource(
        self,
        uid: str,
        datasource_update: DatasourceUpdate
    ) -> Optional[Datasource]:
        """Update an existing datasource.
        
        Args:
            uid: Datasource UID
            datasource_update: DatasourceUpdate object
            
        Returns:
            Updated Datasource object or None if error
        """
        existing = await self.get_datasource(uid)
        if not existing:
            return None
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                data = datasource_update.model_dump(by_alias=True, exclude_none=True)
                
                response = await client.put(
                    f"{self.grafana_url}/api/datasources/uid/{uid}",
                    json=data,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                
                if "datasource" in result:
                    return Datasource(**result["datasource"])
                return await self.get_datasource(uid)
                
            except httpx.HTTPError as e:
                logger.error(f"Error updating datasource {uid}: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def delete_datasource(self, uid: str) -> bool:
        """Delete a datasource.
        
        Args:
            uid: Datasource UID
            
        Returns:
            True if successful, False otherwise
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.delete(
                    f"{self.grafana_url}/api/datasources/uid/{uid}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return True
                
            except httpx.HTTPError as e:
                logger.error(f"Error deleting datasource {uid}: {e}")
                return False
    
    @with_retry()
    @with_timeout()
    async def get_folders(self) -> List[Folder]:
        """Get all folders.
        
        Returns:
            List of Folder objects
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.grafana_url}/api/folders",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                return [Folder(**folder) for folder in data]
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching folders: {e}")
                return []
    
    @with_retry()
    @with_timeout()
    async def create_folder(self, title: str) -> Optional[Folder]:
        """Create a new folder.
        
        Args:
            title: Folder title
            
        Returns:
            Created Folder object or None if error
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.grafana_url}/api/folders",
                    json={"title": title},
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                
                return Folder(**data)
                
            except httpx.HTTPError as e:
                logger.error(f"Error creating folder: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def delete_folder(self, uid: str) -> bool:
        """Delete a folder.
        
        Args:
            uid: Folder UID
            
        Returns:
            True if successful, False otherwise
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.delete(
                    f"{self.grafana_url}/api/folders/{uid}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return True
                
            except httpx.HTTPError as e:
                logger.error(f"Error deleting folder {uid}: {e}")
                return False
