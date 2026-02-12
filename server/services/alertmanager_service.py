"""AlertManager service for alert operations."""
import httpx
import logging
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta

from models.alerts import Alert, AlertGroup
from models.silences import Silence, SilenceCreate, Matcher
from models.receivers import AlertManagerStatus
from config import config
from middleware.resilience import with_retry, with_timeout

logger = logging.getLogger(__name__)


class AlertManagerService:
    """Service for interacting with AlertManager."""
    
    def __init__(self, alertmanager_url: str = config.ALERTMANAGER_URL):
        """Initialize AlertManager service.
        
        Args:
            alertmanager_url: Base URL for AlertManager instance
        """
        self.alertmanager_url = alertmanager_url.rstrip('/')
        self.timeout = config.DEFAULT_TIMEOUT
        # Shared client with connection pooling – avoids TCP handshake per request
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    
    @with_retry()
    @with_timeout()
    async def get_alerts(
        self,
        filter_labels: Optional[Dict[str, str]] = None,
        active: Optional[bool] = None,
        silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None
    ) -> List[Alert]:
        """Get all alerts with optional filters.
        
        Args:
            filter_labels: Filter by label key-value pairs
            active: Filter active alerts
            silenced: Filter silenced alerts
            inhibited: Filter inhibited alerts
            
        Returns:
            List of Alert objects
        """
        params = {}
        
        filters = []
        if filter_labels:
            for key, value in filter_labels.items():
                filters.append(f'{key}="{value}"')
        
        if active is not None:
            filters.append(f'active={str(active).lower()}')
        if silenced is not None:
            filters.append(f'silenced={str(silenced).lower()}')
        if inhibited is not None:
            filters.append(f'inhibited={str(inhibited).lower()}')
        
        if filters:
            params["filter"] = filters
        
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/alerts",
                params=params,
            )
            response.raise_for_status()
            return [Alert(**alert) for alert in response.json()]
        except httpx.HTTPError as e:
            logger.error("Error fetching alerts: %s", e)
            return []
    
    async def get_alert_groups(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> List[AlertGroup]:
        """Get alert groups.
        
        Args:
            filter_labels: Filter by label key-value pairs
            
        Returns:
            List of AlertGroup objects
        """
        params = {}
        if filter_labels:
            filters = [f'{k}="{v}"' for k, v in filter_labels.items()]
            params["filter"] = filters
        
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/alerts/groups",
                params=params,
            )
            response.raise_for_status()
            return [AlertGroup(**group) for group in response.json()]
        except httpx.HTTPError as e:
            logger.error("Error fetching alert groups: %s", e)
            return []
    
    async def post_alerts(self, alerts: List[Alert]) -> bool:
        """Post new alerts to AlertManager.
        
        Args:
            alerts: List of Alert objects to post
            
        Returns:
            True if successful, False otherwise
        """
        try:
            alert_data = [alert.model_dump(by_alias=True) for alert in alerts]
            response = await self._client.post(
                f"{self.alertmanager_url}/api/v2/alerts",
                json=alert_data,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error posting alerts: %s", e)
            return False
    
    async def get_silences(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> List[Silence]:
        """Get all silences.
        
        Args:
            filter_labels: Filter by label key-value pairs
            
        Returns:
            List of Silence objects
        """
        params = {}
        if filter_labels:
            filters = [f'{k}="{v}"' for k, v in filter_labels.items()]
            params["filter"] = filters
        
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/silences",
                params=params,
            )
            response.raise_for_status()
            return [Silence(**silence) for silence in response.json()]
        except httpx.HTTPError as e:
            logger.error("Error fetching silences: %s", e)
            return []
    
    async def get_silence(self, silence_id: str) -> Optional[Silence]:
        """Get a specific silence by ID.
        
        Args:
            silence_id: Silence identifier
            
        Returns:
            Silence object or None if not found
        """
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/silence/{silence_id}",
            )
            response.raise_for_status()
            return Silence(**response.json())
        except httpx.HTTPError as e:
            logger.error("Error fetching silence %s: %s", silence_id, e)
            return None
    
    async def create_silence(self, silence: SilenceCreate) -> Optional[str]:
        """Create a new silence.
        
        Args:
            silence: SilenceCreate object
            
        Returns:
            Silence ID if successful, None otherwise
        """
        try:
            silence_data = silence.model_dump(by_alias=True, exclude_none=True)
            response = await self._client.post(
                f"{self.alertmanager_url}/api/v2/silences",
                json=silence_data,
            )
            response.raise_for_status()
            return response.json().get("silenceID")
        except httpx.HTTPError as e:
            logger.error("Error creating silence: %s", e)
            return None
    
    async def delete_silence(self, silence_id: str) -> bool:
        """Delete a silence.
        
        Args:
            silence_id: Silence identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = await self._client.delete(
                f"{self.alertmanager_url}/api/v2/silence/{silence_id}",
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting silence %s: %s", silence_id, e)
            return False
    
    async def get_status(self) -> Optional[AlertManagerStatus]:
        """Get AlertManager status.
        
        Returns:
            AlertManagerStatus object or None if error
        """
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/status",
            )
            response.raise_for_status()
            return AlertManagerStatus(**response.json())
        except httpx.HTTPError as e:
            logger.error("Error fetching status: %s", e)
            return None
    
    async def get_receivers(self) -> List[str]:
        """Get list of configured receivers.
        
        Returns:
            List of receiver names
        """
        status = await self.get_status()
        if status and status.config:
            receivers = status.config.get("receivers", [])
            return [r.get("name") for r in receivers if r.get("name")]
        return []
    
    async def delete_alerts(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> bool:
        """Delete alerts matching the filter.
        
        Note: AlertManager doesn't have a direct delete endpoint for alerts.
        This creates a silence to suppress matching alerts.
        
        Args:
            filter_labels: Filter by label key-value pairs
            
        Returns:
            True if silence created successfully
        """
        if not filter_labels:
            logger.warning("Cannot delete all alerts without filter")
            return False
        
        matchers = [
            Matcher(name=k, value=v, isRegex=False, isEqual=True)
            for k, v in filter_labels.items()
        ]
        
        now = datetime.now(timezone.utc)
        end = now + timedelta(seconds=60)
        
        starts_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ends_at = end.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        
        silence = SilenceCreate(
            matchers=matchers,
            startsAt=starts_at,
            endsAt=ends_at,
            createdBy="beobservant",
            comment="Alert deletion via API"
        )
        
        silence_id = await self.create_silence(silence)
        return silence_id is not None
    
    async def update_silence(self, silence_id: str, silence: SilenceCreate) -> Optional[str]:
        """Update an existing silence.
        
        Note: AlertManager doesn't have update, so we delete and recreate.
        
        Args:
            silence_id: Existing silence ID
            silence: New silence data
            
        Returns:
            New silence ID if successful
        """
        await self.delete_silence(silence_id)
        
        return await self.create_silence(silence)
