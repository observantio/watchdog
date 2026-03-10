"""
Proxy service for Grafana API interactions, including folder management.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import base64
import logging
from collections.abc import Mapping, Sequence
from typing import List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from custom_types.json import JSONDict, JSONValue
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)

QueryParamScalar = str | int | float | bool | None
QueryParamValue = QueryParamScalar | Sequence[QueryParamScalar]
QueryParams = Mapping[str, QueryParamValue]


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

class GrafanaAPIError(Exception):
    def __init__(self, status: int, body: JSONValue | None = None):
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
    ) -> None:
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

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.auth_header, "Content-Type": "application/json"}

    @staticmethod
    def _parse_error_body(exc: httpx.HTTPStatusError) -> JSONValue | None:
        try:
            body = exc.response.json()
            if isinstance(body, (dict, list, str, int, float, bool)) or body is None:
                return body
            return str(body)
        except (TypeError, ValueError):
            return exc.response.text or None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: QueryParams | None = None,
        json: object | None = None,
    ) -> httpx.Response:
        url = f"{self.grafana_url}{path}"
        request_headers = dict(headers or self._headers())
        response = await self._client.request(method, url, headers=request_headers, params=params, json=json)
        if (
            response.status_code == 401
            and self._using_api_key
            and request_headers.get("Authorization", "").startswith("Bearer ")
        ):
            logger.warning("Grafana API key rejected (401). Falling back to basic auth.")
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            response = await self._client.request(method, url, headers=self._headers(), params=params, json=json)
        return response

    async def _safe_request(
        self,
        method: str,
        path: str,
        default: JSONValue | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        params: QueryParams | None = None,
        json: object | None = None,
    ) -> JSONValue | None:
        try:
            r = await self._request(method, path, headers=headers, params=params, json=json)
            r.raise_for_status()
            payload = r.json()
            if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None:
                return payload
            return default
        except httpx.HTTPError as e:
            logger.error("Grafana %s %s failed: %s", method, path, e)
            return default

    async def _mutating_request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: QueryParams | None = None,
        json: object | None = None,
    ) -> JSONValue | None:
        try:
            r = await self._request(method, path, headers=headers, params=params, json=json)
            r.raise_for_status()
            payload = r.json()
            if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None:
                return payload
            return None
        except httpx.HTTPStatusError as e:
            parsed = self._parse_error_body(e)
            logger.error("Grafana %s %s HTTP %s: %s – %s", method, path, e.response.status_code, e, parsed)
            raise GrafanaAPIError(e.response.status_code, parsed) from e

    @with_retry()
    @with_timeout()
    async def search_dashboards(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        folder_ids: Optional[List[int]] = None,
        folder_uids: Optional[List[str]] = None,
        dashboard_uids: Optional[List[str]] = None,
        starred: Optional[bool] = None,
    ) -> List[DashboardSearchResult]:
        params: dict[str, QueryParamValue] = {"type": "dash-db"}
        if query:
            params["query"] = query
        if tag:
            params["tag"] = tag
        if folder_ids:
            params["folderIds"] = folder_ids
        if folder_uids:
            params["folderUIDs"] = folder_uids
        if dashboard_uids:
            params["dashboardUID"] = dashboard_uids
        if starred is not None:
            params["starred"] = starred
        data = await self._safe_request("GET", "/api/search", default=[], params=params)
        return [DashboardSearchResult.model_validate(item) for item in _dict_list(data)]

    @with_retry()
    @with_timeout()
    async def get_dashboard(self, uid: str) -> Optional[JSONDict]:
        result = await self._safe_request("GET", f"/api/dashboards/uid/{uid}")
        return result if isinstance(result, dict) or result is None else None

    @with_retry()
    @with_timeout()
    async def create_dashboard(self, dashboard_create: DashboardCreate) -> Optional[JSONDict]:
        result = await self._mutating_request(
            "POST", "/api/dashboards/db",
            json=dashboard_create.model_dump(by_alias=True, exclude_none=True),
        )
        return result if isinstance(result, dict) or result is None else None

    @with_retry()
    @with_timeout()
    async def update_dashboard(self, uid: str, dashboard_update: DashboardUpdate) -> Optional[JSONDict]:
        if not await self.get_dashboard(uid):
            return None
        dashboard_update.dashboard.uid = uid
        result = await self._mutating_request(
            "POST", "/api/dashboards/db",
            json=dashboard_update.model_dump(by_alias=True, exclude_none=True),
        )
        return result if isinstance(result, dict) or result is None else None

    @with_retry()
    @with_timeout()
    async def delete_dashboard(self, uid: str) -> bool:
        result = await self._safe_request("DELETE", f"/api/dashboards/uid/{uid}", default=False)
        return result is not False

    @with_retry()
    @with_timeout()
    async def query_datasource(self, payload: JSONDict) -> JSONDict:
        r = await self._request("POST", "/api/ds/query", json=payload)
        r.raise_for_status()
        payload_json = r.json()
        return payload_json if isinstance(payload_json, dict) else {}

    @with_retry()
    @with_timeout()
    async def get_datasources(self) -> List[Datasource]:
        data = await self._safe_request("GET", "/api/datasources", default=[])
        return [Datasource.model_validate(ds) for ds in _dict_list(data)]

    @with_retry()
    @with_timeout()
    async def get_datasource(self, uid: str) -> Optional[Datasource]:
        data = await self._safe_request("GET", f"/api/datasources/uid/{uid}")
        return Datasource.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def get_datasource_by_name(self, name: str) -> Optional[Datasource]:
        data = await self._safe_request("GET", f"/api/datasources/name/{name}")
        return Datasource.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def create_datasource(self, datasource: DatasourceCreate) -> Optional[Datasource]:
        result = await self._mutating_request(
            "POST", "/api/datasources",
            json=datasource.model_dump(by_alias=True, exclude_none=True),
        )
        datasource_payload = _json_dict(result).get("datasource")
        return Datasource.model_validate(datasource_payload) if isinstance(datasource_payload, dict) else None

    @with_retry()
    @with_timeout()
    async def update_datasource(self, uid: str, datasource_update: DatasourceUpdate) -> Optional[Datasource]:
        existing = await self.get_datasource(uid)
        if not existing:
            return None
        data = datasource_update.model_dump(by_alias=True, exclude_none=True)
        data.setdefault("type", existing.type)
        data.setdefault("name", existing.name)
        data.setdefault("url", existing.url)
        data.setdefault("access", existing.access)
        data.setdefault("isDefault", getattr(existing, "is_default", None))
        result = await self._mutating_request("PUT", f"/api/datasources/uid/{uid}", json=data)
        datasource_payload = _json_dict(result).get("datasource")
        return Datasource.model_validate(datasource_payload) if isinstance(datasource_payload, dict) else await self.get_datasource(uid)

    @with_retry()
    @with_timeout()
    async def delete_datasource(self, uid: str) -> bool:
        result = await self._safe_request("DELETE", f"/api/datasources/uid/{uid}", default=False)
        return result is not False

    @with_retry()
    @with_timeout()
    async def get_folders(self) -> List[Folder]:
        data = await self._safe_request("GET", "/api/folders", default=[])
        return [Folder.model_validate(folder) for folder in _dict_list(data)]

    @with_retry()
    @with_timeout()
    async def create_folder(self, title: str) -> Optional[Folder]:
        data = await self._mutating_request("POST", "/api/folders", json={"title": title})
        return Folder.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def get_folder(self, uid: str) -> Optional[Folder]:
        data = await self._safe_request("GET", f"/api/folders/{uid}")
        return Folder.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def update_folder(self, uid: str, title: str) -> Optional[Folder]:
        existing = await self.get_folder(uid)
        if not existing:
            return None
        payload = {"title": title, "overwrite": True}
        if getattr(existing, "version", None) is not None:
            payload["version"] = existing.version
        try:
            data = await self._mutating_request("PUT", f"/api/folders/{uid}", json=payload)
            return Folder.model_validate(data) if isinstance(data, dict) else None
        except GrafanaAPIError as exc:
            if exc.status != 412:
                raise
            refreshed = await self.get_folder(uid)
            if not refreshed:
                return None
            retry_payload = {"title": title, "overwrite": True}
            if getattr(refreshed, "version", None) is not None:
                retry_payload["version"] = refreshed.version
            data = await self._mutating_request("PUT", f"/api/folders/{uid}", json=retry_payload)
            return Folder.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def delete_folder(self, uid: str) -> bool:
        result = await self._safe_request("DELETE", f"/api/folders/{uid}", default=False)
        return result is not False
