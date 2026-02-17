"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Jira integration service.

Supports both global env credentials and per-request tenant-scoped credentials.
"""
import base64
import logging
import os
from typing import Optional, Dict, Any, List

import httpx

from services.common.http_client import create_async_client
from services.common.url_utils import is_safe_http_url
from config import config

logger = logging.getLogger(__name__)


class JiraError(Exception):
    pass


class JiraService:
    def __init__(self, timeout: Optional[float] = None) -> None:
        self.base_url = (os.getenv("JIRA_BASE_URL") or "").strip().rstrip("/")
        self.email = (os.getenv("JIRA_EMAIL") or "").strip() or None
        self.api_token = (os.getenv("JIRA_API_TOKEN") or "").strip() or None
        self.bearer = (os.getenv("JIRA_BEARER_TOKEN") or "").strip() or None
        self.timeout = float(timeout or config.DEFAULT_TIMEOUT)
        self._client = create_async_client(self.timeout)

    def _resolve_base_url(self, credentials: Optional[Dict[str, Any]] = None) -> str:
        scoped = credentials or {}
        return str(scoped.get("base_url") or scoped.get("baseUrl") or self.base_url or "").strip().rstrip("/")

    def _auth_headers(self, credentials: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        scoped = credentials or {}
        bearer = (scoped.get("bearer") or scoped.get("bearer_token") or scoped.get("bearerToken") or self.bearer or "").strip()
        if bearer:
            return {"Authorization": f"Bearer {bearer}"}

        email = (scoped.get("email") or self.email or "").strip()
        api_token = (scoped.get("api_token") or scoped.get("apiToken") or self.api_token or "").strip()
        if email and api_token:
            token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        return {}

    def _headers(self, credentials: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        headers.update(self._auth_headers(credentials))
        if "Authorization" not in headers:
            raise JiraError("No Jira credentials configured")
        return headers

    async def _get(self, path: str, credentials: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        base_url = self._resolve_base_url(credentials)
        if not is_safe_http_url(base_url):
            raise JiraError("JIRA_BASE_URL not configured or invalid")
        url = f"{base_url}{path}"
        try:
            response = await self._client.get(url, headers=self._headers(credentials), params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Jira GET failed: %s %s", exc.response.status_code, exc.response.text[:240])
            raise JiraError(f"Jira API error: {exc.response.status_code}") from exc
        except JiraError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected Jira GET error")
            raise JiraError("Failed to contact Jira API") from exc

    async def _post(self, path: str, payload: Dict[str, Any], credentials: Optional[Dict[str, Any]] = None) -> Any:
        base_url = self._resolve_base_url(credentials)
        if not is_safe_http_url(base_url):
            raise JiraError("JIRA_BASE_URL not configured or invalid")
        url = f"{base_url}{path}"
        try:
            response = await self._client.post(url, json=payload, headers=self._headers(credentials))
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except httpx.HTTPStatusError as exc:
            logger.warning("Jira POST failed: %s %s", exc.response.status_code, exc.response.text[:240])
            raise JiraError(f"Jira API error: {exc.response.status_code}") from exc
        except JiraError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected Jira POST error")
            raise JiraError("Failed to contact Jira API") from exc

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: Optional[str] = None,
        issue_type: str = "Task",
        credentials: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a Jira issue and return a dict with keys: key, url, raw."""
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description or "",
                "issuetype": {"name": issue_type},
            }
        }
        data = await self._post("/rest/api/2/issue", payload, credentials)
        key = data.get("key")
        base_url = self._resolve_base_url(credentials)
        issue_url = f"{base_url.rstrip('/')}/browse/{key}" if key else None
        return {"key": key, "url": issue_url, "raw": data}

    async def list_projects(self, credentials: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        data = await self._get("/rest/api/2/project", credentials)
        projects: List[Dict[str, str]] = []
        for project in data or []:
            key = str(project.get("key") or "").strip()
            name = str(project.get("name") or key).strip()
            if key:
                projects.append({"key": key, "name": name})
        return projects

    async def list_issue_types(self, project_key: str, credentials: Optional[Dict[str, Any]] = None) -> List[str]:
        project = await self._get(f"/rest/api/2/project/{project_key}", credentials)
        issue_types = project.get("issueTypes") if isinstance(project, dict) else []
        names: List[str] = []
        for issue_type in issue_types or []:
            name = str(issue_type.get("name") or "").strip()
            if name:
                names.append(name)
        return names

    async def add_comment(self, issue_key: str, text: str, credentials: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._post(
            f"/rest/api/2/issue/{issue_key}/comment",
            {"body": text},
            credentials,
        )

    async def list_comments(self, issue_key: str, credentials: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        data = await self._get(f"/rest/api/2/issue/{issue_key}/comment", credentials)
        comments = data.get("comments") if isinstance(data, dict) else []
        normalized: List[Dict[str, Any]] = []
        for item in comments or []:
            author = item.get("author") if isinstance(item, dict) else {}
            display_name = ""
            if isinstance(author, dict):
                display_name = str(author.get("displayName") or author.get("name") or "jira")
            normalized.append(
                {
                    "id": str(item.get("id") or ""),
                    "author": display_name or "jira",
                    "body": str(item.get("body") or ""),
                    "created": item.get("created"),
                }
            )
        return normalized


# module-level singleton for router usage
jira_service = JiraService()
