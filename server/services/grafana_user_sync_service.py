"""Grafana user and permission sync service.

Automatically creates Grafana users when app users are created,
syncs passwords, and manages Grafana-level permissions via service accounts
and API tokens for secure, dynamic authentication.
"""
import httpx
import logging
import base64
from typing import Optional, Dict, Any, List

from config import config
from middleware.resilience import with_retry, with_timeout

logger = logging.getLogger(__name__)


class GrafanaUserSyncService:
    """Service for syncing users and permissions to Grafana."""

    # Grafana role mapping from our app roles
    ROLE_MAP = {
        "admin": "Admin",
        "user": "Editor",
        "viewer": "Viewer",
    }

    def __init__(
        self,
        grafana_url: str = config.GRAFANA_URL,
        admin_user: str = config.GRAFANA_USERNAME,
        admin_pass: str = config.GRAFANA_PASSWORD,
        api_key: Optional[str] = None,
    ):
        self.grafana_url = grafana_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._using_api_key = False
        self._basic_auth_header: Optional[str] = None
        
        # Prefer API key (Bearer token) over Basic auth for better security
        api_key = api_key or config.GRAFANA_API_KEY
        if api_key:
            self.auth_header = f"Bearer {api_key}"
            self._using_api_key = True
            logger.info("Using Grafana API key authentication for user sync")
        else:
            credentials = f"{admin_user}:{admin_pass}"
            encoded = base64.b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {encoded}"
            logger.info("Using Grafana Basic authentication for user sync (consider using API key)")

        credentials = f"{admin_user}:{admin_pass}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self._basic_auth_header = f"Basic {encoded}"
        
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.grafana_url}{path}"
        headers = kwargs.pop("headers", None) or self._headers()

        response = await self._client.request(method, url, headers=headers, **kwargs)

        if (
            response.status_code == 401
            and self._using_api_key
            and self._basic_auth_header
            and headers.get("Authorization", "").startswith("Bearer ")
        ):
            logger.warning("Grafana API key rejected for user-sync (401). Falling back to basic auth.")
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            response = await self._client.request(method, url, headers=self._headers(), **kwargs)

        return response

    # ------------------------------------------------------------------
    # Grafana User CRUD
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def create_grafana_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "user",
    ) -> Optional[Dict[str, Any]]:
        """Create a user in Grafana.

        Returns the Grafana user dict or None on failure.
        """
        grafana_role = self.ROLE_MAP.get(role, "Viewer")
        payload = {
            "name": full_name or username,
            "login": username,
            "email": email,
            "password": password,
            "OrgId": 1,
        }
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/admin/users",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code == 412:
                # User already exists – look them up instead
                logger.info("Grafana user '%s' already exists, fetching...", username)
                return await self.get_grafana_user_by_login(username)

            resp.raise_for_status()
            data = resp.json()
            grafana_user_id = data.get("id")

            # Set org role
            if grafana_user_id and grafana_role != "Viewer":
                await self._set_user_org_role(grafana_user_id, grafana_role)

            logger.info("Created Grafana user '%s' (id=%s)", username, grafana_user_id)
            return data
        except httpx.HTTPError as e:
            logger.error("Error creating Grafana user '%s': %s", username, e)
            return None

    @with_retry()
    @with_timeout()
    async def get_grafana_user_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        """Lookup Grafana user by login name."""
        try:
            resp = await self._client.get(
                f"{self.grafana_url}/api/users/lookup",
                params={"loginOrEmail": login},
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Error looking up Grafana user '%s': %s", login, e)
            return None

    @with_retry()
    @with_timeout()
    async def update_grafana_user(
        self,
        grafana_user_id: int,
        *,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        login: Optional[str] = None,
    ) -> bool:
        """Update basic Grafana user profile fields."""
        payload: Dict[str, Any] = {}
        if email:
            payload["email"] = email
        if full_name:
            payload["name"] = full_name
        if login:
            payload["login"] = login
        if not payload:
            return True
        try:
            resp = await self._client.put(
                f"{self.grafana_url}/api/admin/users/{grafana_user_id}",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error updating Grafana user %s: %s", grafana_user_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def update_grafana_user_password(
        self, grafana_user_id: int, new_password: str
    ) -> bool:
        """Change Grafana user password via admin API."""
        try:
            resp = await self._client.put(
                f"{self.grafana_url}/api/admin/users/{grafana_user_id}/password",
                json={"password": new_password},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error updating Grafana password for user %s: %s", grafana_user_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def delete_grafana_user(self, grafana_user_id: int) -> bool:
        """Delete a Grafana user."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/admin/users/{grafana_user_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            logger.info("Deleted Grafana user id=%s", grafana_user_id)
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting Grafana user %s: %s", grafana_user_id, e)
            return False

    async def _set_user_org_role(self, grafana_user_id: int, role: str) -> bool:
        """Set the user's role in the default org."""
        try:
            resp = await self._client.patch(
                f"{self.grafana_url}/api/org/users/{grafana_user_id}",
                json={"role": role},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error setting role for Grafana user %s: %s", grafana_user_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def sync_user_role(self, grafana_user_id: int, app_role: str) -> bool:
        """Sync the app role to Grafana org role."""
        grafana_role = self.ROLE_MAP.get(app_role, "Viewer")
        return await self._set_user_org_role(grafana_user_id, grafana_role)

    # ------------------------------------------------------------------
    # Grafana Team management (maps to our groups)
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def create_team(self, name: str, email: str = "") -> Optional[Dict[str, Any]]:
        """Create a Grafana team."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/teams",
                json={"name": name, "email": email},
                headers=self._headers(),
            )
            if resp.status_code == 409:
                # Team already exists
                return await self.get_team_by_name(name)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Error creating Grafana team '%s': %s", name, e)
            return None

    @with_retry()
    @with_timeout()
    async def get_team_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a Grafana team by name."""
        try:
            resp = await self._client.get(
                f"{self.grafana_url}/api/teams/search",
                params={"name": name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            teams = data.get("teams", [])
            for t in teams:
                if t.get("name") == name:
                    return t
            return None
        except httpx.HTTPError as e:
            logger.error("Error searching Grafana team '%s': %s", name, e)
            return None

    @with_retry()
    @with_timeout()
    async def add_user_to_team(self, team_id: int, grafana_user_id: int) -> bool:
        """Add a Grafana user to a Grafana team."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/teams/{team_id}/members",
                json={"userId": grafana_user_id},
                headers=self._headers(),
            )
            if resp.status_code == 400:
                # Already a member
                return True
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error adding user %s to team %s: %s", grafana_user_id, team_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def remove_user_from_team(self, team_id: int, grafana_user_id: int) -> bool:
        """Remove a Grafana user from a Grafana team."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/teams/{team_id}/members/{grafana_user_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error removing user %s from team %s: %s", grafana_user_id, team_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def delete_team(self, team_id: int) -> bool:
        """Delete a Grafana team."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/teams/{team_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting Grafana team %s: %s", team_id, e)
            return False

    # ------------------------------------------------------------------
    # Dashboard / folder permissions in Grafana
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def set_dashboard_permissions(
        self,
        dashboard_uid: str,
        permissions: List[Dict[str, Any]],
    ) -> bool:
        """Set Grafana-native permissions on a dashboard.

        ``permissions`` is a list of dicts, each with:
            - ``role``, ``userId``, or ``teamId``
            - ``permission``: 1=View, 2=Edit, 4=Admin
        """
        try:
            # First get dashboard id from uid
            resp = await self._client.get(
                f"{self.grafana_url}/api/dashboards/uid/{dashboard_uid}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            dash_data = resp.json()
            dash_id = dash_data.get("dashboard", {}).get("id")
            if not dash_id:
                return False

            resp = await self._client.post(
                f"{self.grafana_url}/api/dashboards/id/{dash_id}/permissions",
                json={"items": permissions},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error setting dashboard permissions for %s: %s", dashboard_uid, e)
            return False

    @with_retry()
    @with_timeout()
    async def set_folder_permissions(
        self,
        folder_uid: str,
        permissions: List[Dict[str, Any]],
    ) -> bool:
        """Set Grafana-native permissions on a folder."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/folders/{folder_uid}/permissions",
                json={"items": permissions},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error setting folder permissions for %s: %s", folder_uid, e)
            return False

    # ------------------------------------------------------------------
    # Service account & API token management
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def create_service_account(
        self, name: str, role: str = "Viewer"
    ) -> Optional[Dict[str, Any]]:
        """Create a Grafana service account for API token generation."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/serviceaccounts",
                json={"name": name, "role": role, "isDisabled": False},
                headers=self._headers(),
            )
            if resp.status_code == 409:
                logger.info("Service account '%s' already exists", name)
                return await self._find_service_account(name)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Error creating service account '%s': %s", name, e)
            return None

    async def _find_service_account(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a service account by name."""
        try:
            resp = await self._client.get(
                f"{self.grafana_url}/api/serviceaccounts/search",
                params={"query": name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            for sa in data.get("serviceAccounts", []):
                if sa.get("name") == name:
                    return sa
            return None
        except httpx.HTTPError:
            return None

    @with_retry()
    @with_timeout()
    async def create_service_account_token(
        self, sa_id: int, token_name: str
    ) -> Optional[str]:
        """Create API token for a service account. Returns the token string."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/serviceaccounts/{sa_id}/tokens",
                json={"name": token_name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("key")
        except httpx.HTTPError as e:
            logger.error("Error creating SA token for %s: %s", sa_id, e)
            return None

    @with_retry()
    @with_timeout()
    async def delete_service_account(self, sa_id: int) -> bool:
        """Delete a Grafana service account."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/serviceaccounts/{sa_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting service account %s: %s", sa_id, e)
            return False

    # ------------------------------------------------------------------
    # Convenience: full user lifecycle sync
    # ------------------------------------------------------------------

    async def sync_user_create(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "user",
    ) -> Optional[int]:
        """Create Grafana user and return grafana_user_id, or None on error."""
        result = await self.create_grafana_user(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
            role=role,
        )
        if result:
            return result.get("id")
        return None

    async def sync_user_delete(self, grafana_user_id: int) -> bool:
        """Remove user from Grafana entirely."""
        if not grafana_user_id:
            return True
        return await self.delete_grafana_user(grafana_user_id)

    async def sync_group_to_team(self, group_name: str) -> Optional[int]:
        """Ensure a Grafana team exists for the group. Returns team_id."""
        result = await self.create_team(group_name)
        if result:
            return result.get("teamId") or result.get("id")
        return None
