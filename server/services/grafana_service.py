"""Grafana service for dashboard and datasource management."""
import httpx
import logging
from typing import List, Optional, Dict, Any
import base64

from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate, DashboardSearchResult
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from config import config
from middleware.resilience import with_retry, with_timeout
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)


class GrafanaAPIError(Exception):
    """Raised when Grafana returns a non-2xx response.

    Attributes:
        status: HTTP status code returned by Grafana
        body: parsed response body (dict or raw text)
    """
    def __init__(self, status: int, body: Any = None):
        self.status = status
        self.body = body
        super().__init__(f"Grafana API error {status}: {body}")


class GrafanaService:
    """Service for interacting with Grafana."""
    
    def __init__(
        self,
        grafana_url: str = config.GRAFANA_URL,
        username: str = config.GRAFANA_USERNAME,
        password: str = config.GRAFANA_PASSWORD,
        api_key: Optional[str] = None
    ):
        """Initialize Grafana service.
        
        Args:
            grafana_url: Base URL for Grafana instance
            username: Grafana admin username
            password: Grafana admin password
            api_key: Grafana API key (preferred over username/password)
        """
        self.grafana_url = grafana_url.rstrip('/')
        self.timeout = config.DEFAULT_TIMEOUT
        self._using_api_key = False
        self._basic_auth_header: Optional[str] = None
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        basic_auth_header = f"Basic {encoded}"
        
        # Prefer API key (Bearer token) over Basic auth for better security
        api_key = api_key or config.GRAFANA_API_KEY
        if api_key:
            self.auth_header = f"Bearer {api_key}"
            self._using_api_key = True
            logger.info("Using Grafana API key authentication")
        else:
            self.auth_header = basic_auth_header
            logger.info("Using Grafana Basic authentication (consider using API key)")

        self._basic_auth_header = basic_auth_header
        
        self._client = create_async_client(self.timeout)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Grafana API requests."""
        return {
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }

    @staticmethod
    def _parse_http_error_body(exc: httpx.HTTPStatusError) -> Any:
        try:
            return exc.response.json()
        except Exception:
            try:
                return exc.response.text
            except Exception:
                return None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Perform request and fallback to basic auth if API key is invalid."""
        url = f"{self.grafana_url}{path}"
        headers = kwargs.pop("headers", None) or self._get_headers()

        response = await self._client.request(method, url, headers=headers, **kwargs)

        if (
            response.status_code == 401
            and self._using_api_key
            and self._basic_auth_header
            and headers.get("Authorization", "").startswith("Bearer ")
        ):
            logger.warning("Grafana API key rejected (401). Falling back to basic auth.")
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            fallback_headers = self._get_headers()
            response = await self._client.request(method, url, headers=fallback_headers, **kwargs)

        return response
    
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
        
        try:
            response = await self._request("GET", "/api/search", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [DashboardSearchResult(**item) for item in data]
            
        except httpx.HTTPError as e:
            logger.error("Error searching dashboards: %s", e)
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
        try:
            response = await self._request("GET", f"/api/dashboards/uid/{uid}")
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error("Error fetching dashboard %s: %s", uid, e)
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
        try:
            data = dashboard_create.model_dump(by_alias=True, exclude_none=True)
            
            response = await self._request("POST", "/api/dashboards/db", json=data)
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            parsed = self._parse_http_error_body(e)
            logger.error("Error creating dashboard (HTTP %s): %s – response body: %s", e.response.status_code, e, parsed)
            raise GrafanaAPIError(status=e.response.status_code, body=parsed)
        except httpx.HTTPError as e:
            logger.error("Error creating dashboard: %s", e)
            raise
    
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
        
        try:
            data = dashboard_update.model_dump(by_alias=True, exclude_none=True)
            
            response = await self._request("POST", "/api/dashboards/db", json=data)
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            parsed = self._parse_http_error_body(e)
            logger.error("Error updating dashboard %s (HTTP %s): %s – response body: %s", uid, e.response.status_code, e, parsed)
            raise GrafanaAPIError(status=e.response.status_code, body=parsed)
        except httpx.HTTPError as e:
            logger.error("Error updating dashboard %s: %s", uid, e)
            raise
    
    @with_retry()
    @with_timeout()
    async def delete_dashboard(self, uid: str) -> bool:
        """Delete a dashboard.
        
        Args:
            uid: Dashboard UID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = await self._request("DELETE", f"/api/dashboards/uid/{uid}")
            response.raise_for_status()
            return True
            
        except httpx.HTTPError as e:
            logger.error("Error deleting dashboard %s: %s", uid, e)
            return False

    @with_retry()
    @with_timeout()
    async def query_datasource(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Grafana datasource queries via /api/ds/query."""
        response = await self._request("POST", "/api/ds/query", json=payload)
        response.raise_for_status()
        return response.json()
    
    
    
    @with_retry()
    @with_timeout()
    async def get_datasources(self) -> List[Datasource]:
        """Get all datasources.
        
        Returns:
            List of Datasource objects
        """
        try:
            response = await self._request("GET", "/api/datasources")
            response.raise_for_status()
            data = response.json()
            
            return [Datasource(**ds) for ds in data]
            
        except httpx.HTTPError as e:
            logger.error("Error fetching datasources: %s", e)
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
        try:
            response = await self._request("GET", f"/api/datasources/uid/{uid}")
            response.raise_for_status()
            data = response.json()
            
            return Datasource(**data)
            
        except httpx.HTTPError as e:
            logger.error("Error fetching datasource %s: %s", uid, e)
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
        try:
            response = await self._request("GET", f"/api/datasources/name/{name}")
            response.raise_for_status()
            data = response.json()
            
            return Datasource(**data)
            
        except httpx.HTTPError as e:
            logger.error("Error fetching datasource %s: %s", name, e)
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
        try:
            data = datasource.model_dump(by_alias=True, exclude_none=True, exclude={"org_id"})
            
            response = await self._request("POST", "/api/datasources", json=data)
            response.raise_for_status()
            result = response.json()
            
            
            if "datasource" in result:
                return Datasource(**result["datasource"])
            return None
            
        except httpx.HTTPStatusError as e:
            parsed = self._parse_http_error_body(e)
            logger.error(
                "Error creating datasource (HTTP %s): %s – response body: %s",
                e.response.status_code, e, parsed,
            )
            raise GrafanaAPIError(status=e.response.status_code, body=parsed)
        except httpx.HTTPError as e:
            logger.error("Error creating datasource: %s", e)
            raise
    
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
        
        try:
            data = datasource_update.model_dump(by_alias=True, exclude_none=True, exclude={"org_id"})

            # Grafana expects certain required fields on update (type/name/url/access/isDefault).
            # Ensure we merge missing required fields from the existing datasource so Grafana receives a valid payload.
            data.setdefault("type", existing.type)
            data.setdefault("name", existing.name)
            data.setdefault("url", existing.url)
            data.setdefault("access", existing.access)
            if existing.isDefault is not None:
                data.setdefault("isDefault", existing.isDefault)

            response = await self._request("PUT", f"/api/datasources/uid/{uid}", json=data)
            response.raise_for_status()
            result = response.json()
            
            if "datasource" in result:
                return Datasource(**result["datasource"])
            return await self.get_datasource(uid)
            
        except httpx.HTTPStatusError as e:
            parsed = self._parse_http_error_body(e)
            logger.error(
                "Error updating datasource %s (HTTP %s): %s – response body: %s",
                uid, e.response.status_code, e, parsed,
            )
            raise GrafanaAPIError(status=e.response.status_code, body=parsed)
        except httpx.HTTPError as e:
            logger.error("Error updating datasource %s: %s", uid, e)
            raise
    
    @with_retry()
    @with_timeout()
    async def delete_datasource(self, uid: str) -> bool:
        """Delete a datasource.
        
        Args:
            uid: Datasource UID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = await self._request("DELETE", f"/api/datasources/uid/{uid}")
            response.raise_for_status()
            return True
            
        except httpx.HTTPError as e:
            logger.error("Error deleting datasource %s: %s", uid, e)
            return False
    
    @with_retry()
    @with_timeout()
    async def get_folders(self) -> List[Folder]:
        """Get all folders.
        
        Returns:
            List of Folder objects
        """
        try:
            response = await self._request("GET", "/api/folders")
            response.raise_for_status()
            data = response.json()
            
            return [Folder(**folder) for folder in data]
            
        except httpx.HTTPError as e:
            logger.error("Error fetching folders: %s", e)
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
        try:
            response = await self._request("POST", "/api/folders", json={"title": title})
            response.raise_for_status()
            data = response.json()
            
            return Folder(**data)
            
        except httpx.HTTPError as e:
            logger.error("Error creating folder: %s", e)
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
        try:
            response = await self._request("DELETE", f"/api/folders/{uid}")
            response.raise_for_status()
            return True
            
        except httpx.HTTPError as e:
            logger.error("Error deleting folder %s: %s", uid, e)
            return False
