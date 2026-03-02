"""
Proxy service for Grafana API interactions, including folder management.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)

class GrafanaAPIError(Exception):
    def __init__(self, status: int, body: Any = None):
        self.status = status
        self.body = body
        super().__init__(f"Grafana API error {status}: {body}")


class GrafanaService:
    def __init__(
        self,
        grafana_url: str = config.GRAFANA_URL,
        username: str = config.GRAFANA_USERNAME,
        password: str = config.GRAFANA_PASSWORD,
        api_key: Optional[str] = None,
    ):
        self.grafana_url = grafana_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._basic_auth_header = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()

        resolved_key = api_key or config.GRAFANA_API_KEY
        if resolved_key:
            self.auth_header = f"Bearer {resolved_key}"
            self._using_api_key = True
            logger.info("Using Grafana API key authentication")
        else:
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            logger.info("Using Grafana Basic authentication (consider using API key)")

        self._client = create_async_client(self.timeout)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": self.auth_header, "Content-Type": "application/json"}

    @staticmethod
    def _parse_error_body(exc: httpx.HTTPStatusError) -> Any:
        try:
            return exc.response.json()
        except Exception:
            return exc.response.text or None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.grafana_url}{path}"
        headers = kwargs.pop("headers", None) or self._headers()
        response = await self._client.request(method, url, headers=headers, **kwargs)
        if (
            response.status_code == 401
            and self._using_api_key
            and headers.get("Authorization", "").startswith("Bearer ")
        ):
            logger.warning("Grafana API key rejected (401). Falling back to basic auth.")
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            response = await self._client.request(method, url, headers=self._headers(), **kwargs)
        return response

    async def _safe_request(self, method: str, path: str, default: Any = None, **kwargs) -> Any:
        try:
            r = await self._request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Grafana %s %s failed: %s", method, path, e)
            return default

    async def _mutating_request(self, method: str, path: str, **kwargs) -> Any:
        try:
            r = await self._request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            parsed = self._parse_error_body(e)
            logger.error("Grafana %s %s HTTP %s: %s – %s", method, path, e.response.status_code, e, parsed)
            raise GrafanaAPIError(e.response.status_code, parsed)

    @with_retry()
    @with_timeout()
    async def search_dashboards(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        folder_ids: Optional[List[int]] = None,
        starred: Optional[bool] = None,
    ) -> List[DashboardSearchResult]:
        params: Dict[str, Any] = {"type": "dash-db"}
        if query:
            params["query"] = query
        if tag:
            params["tag"] = tag
        if folder_ids:
            params["folderIds"] = folder_ids
        if starred is not None:
            params["starred"] = starred
        data = await self._safe_request("GET", "/api/search", default=[], params=params)
        return [DashboardSearchResult(**item) for item in data]

    @with_retry()
    @with_timeout()
    async def get_dashboard(self, uid: str) -> Optional[Dict[str, Any]]:
        return await self._safe_request("GET", f"/api/dashboards/uid/{uid}")

    @with_retry()
    @with_timeout()
    async def create_dashboard(self, dashboard_create: DashboardCreate) -> Optional[Dict[str, Any]]:
        return await self._mutating_request(
            "POST", "/api/dashboards/db",
            json=dashboard_create.model_dump(by_alias=True, exclude_none=True),
        )

    @with_retry()
    @with_timeout()
    async def update_dashboard(self, uid: str, dashboard_update: DashboardUpdate) -> Optional[Dict[str, Any]]:
        if not await self.get_dashboard(uid):
            return None
        dashboard_update.dashboard.uid = uid
        return await self._mutating_request(
            "POST", "/api/dashboards/db",
            json=dashboard_update.model_dump(by_alias=True, exclude_none=True),
        )

    @with_retry()
    @with_timeout()
    async def delete_dashboard(self, uid: str) -> bool:
        result = await self._safe_request("DELETE", f"/api/dashboards/uid/{uid}", default=False)
        return result is not False

    @with_retry()
    @with_timeout()
    async def query_datasource(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = await self._request("POST", "/api/ds/query", json=payload)
        r.raise_for_status()
        return r.json()

    @with_retry()
    @with_timeout()
    async def get_datasources(self) -> List[Datasource]:
        data = await self._safe_request("GET", "/api/datasources", default=[])
        return [Datasource(**ds) for ds in data]

    @with_retry()
    @with_timeout()
    async def get_datasource(self, uid: str) -> Optional[Datasource]:
        data = await self._safe_request("GET", f"/api/datasources/uid/{uid}")
        return Datasource(**data) if data else None

    @with_retry()
    @with_timeout()
    async def get_datasource_by_name(self, name: str) -> Optional[Datasource]:
        data = await self._safe_request("GET", f"/api/datasources/name/{name}")
        return Datasource(**data) if data else None

    @with_retry()
    @with_timeout()
    async def create_datasource(self, datasource: DatasourceCreate) -> Optional[Datasource]:
        result = await self._mutating_request(
            "POST", "/api/datasources",
            json=datasource.model_dump(by_alias=True, exclude_none=True, exclude={"org_id"}),
        )
        return Datasource(**result["datasource"]) if result and "datasource" in result else None

    @with_retry()
    @with_timeout()
    async def update_datasource(self, uid: str, datasource_update: DatasourceUpdate) -> Optional[Datasource]:
        existing = await self.get_datasource(uid)
        if not existing:
            return None
        data = datasource_update.model_dump(by_alias=True, exclude_none=True, exclude={"org_id"})
        data.setdefault("type", existing.type)
        data.setdefault("name", existing.name)
        data.setdefault("url", existing.url)
        data.setdefault("access", existing.access)
        data.setdefault("isDefault", getattr(existing, "is_default", None))
        result = await self._mutating_request("PUT", f"/api/datasources/uid/{uid}", json=data)
        return Datasource(**result["datasource"]) if result and "datasource" in result else await self.get_datasource(uid)

    @with_retry()
    @with_timeout()
    async def delete_datasource(self, uid: str) -> bool:
        result = await self._safe_request("DELETE", f"/api/datasources/uid/{uid}", default=False)
        return result is not False

    @with_retry()
    @with_timeout()
    async def get_folders(self) -> List[Folder]:
        data = await self._safe_request("GET", "/api/folders", default=[])
        return [Folder(**f) for f in data]

    @with_retry()
    @with_timeout()
    async def create_folder(self, title: str) -> Optional[Folder]:
        data = await self._mutating_request("POST", "/api/folders", json={"title": title})
        return Folder(**data) if data else None

    @with_retry()
    @with_timeout()
    async def delete_folder(self, uid: str) -> bool:
        result = await self._safe_request("DELETE", f"/api/folders/{uid}", default=False)
        return result is not False