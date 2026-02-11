"""Tests for Grafana authentication (API key vs Basic auth)."""
import os
import pytest
from unittest.mock import patch, Mock
from services.grafana_service import GrafanaService
from services.grafana_user_sync_service import GrafanaUserSyncService


class TestGrafanaServiceAuth:
    """Test GrafanaService authentication modes."""

    @patch('services.grafana_service.config')
    def test_uses_api_key_when_provided(self, mock_config):
        """Verify Bearer token is used when API key is set."""
        mock_config.GRAFANA_URL = "http://grafana:3000"
        mock_config.GRAFANA_USERNAME = "admin"
        mock_config.GRAFANA_PASSWORD = "admin"
        mock_config.GRAFANA_API_KEY = "test-api-key-12345"
        mock_config.DEFAULT_TIMEOUT = 30.0

        service = GrafanaService()
        
        assert service.auth_header == "Bearer test-api-key-12345"
        headers = service._get_headers()
        assert headers["Authorization"] == "Bearer test-api-key-12345"

    @patch('services.grafana_service.config')
    def test_uses_basic_auth_when_no_api_key(self, mock_config):
        """Verify Basic auth is used when API key is not set."""
        mock_config.GRAFANA_URL = "http://grafana:3000"
        mock_config.GRAFANA_USERNAME = "admin"
        mock_config.GRAFANA_PASSWORD = "testpass"
        mock_config.GRAFANA_API_KEY = None
        mock_config.DEFAULT_TIMEOUT = 30.0

        service = GrafanaService()
        
        assert service.auth_header.startswith("Basic ")
        assert "Bearer" not in service.auth_header
        headers = service._get_headers()
        assert headers["Authorization"].startswith("Basic ")

    @patch('services.grafana_service.config')
    def test_explicit_api_key_overrides_config(self, mock_config):
        """Verify explicit API key parameter takes precedence."""
        mock_config.GRAFANA_URL = "http://grafana:3000"
        mock_config.GRAFANA_USERNAME = "admin"
        mock_config.GRAFANA_PASSWORD = "admin"
        mock_config.GRAFANA_API_KEY = "config-key"
        mock_config.DEFAULT_TIMEOUT = 30.0

        service = GrafanaService(api_key="explicit-key")
        
        assert service.auth_header == "Bearer explicit-key"


class TestGrafanaUserSyncServiceAuth:
    """Test GrafanaUserSyncService authentication modes."""

    @patch('services.grafana_user_sync_service.config')
    def test_uses_api_key_when_provided(self, mock_config):
        """Verify Bearer token is used when API key is set."""
        mock_config.GRAFANA_URL = "http://grafana:3000"
        mock_config.GRAFANA_USERNAME = "admin"
        mock_config.GRAFANA_PASSWORD = "admin"
        mock_config.GRAFANA_API_KEY = "test-api-key-67890"
        mock_config.DEFAULT_TIMEOUT = 30.0

        service = GrafanaUserSyncService()
        
        assert service.auth_header == "Bearer test-api-key-67890"
        headers = service._headers()
        assert headers["Authorization"] == "Bearer test-api-key-67890"

    @patch('services.grafana_user_sync_service.config')
    def test_uses_basic_auth_when_no_api_key(self, mock_config):
        """Verify Basic auth is used when API key is not set."""
        mock_config.GRAFANA_URL = "http://grafana:3000"
        mock_config.GRAFANA_USERNAME = "admin"
        mock_config.GRAFANA_PASSWORD = "testpass"
        mock_config.GRAFANA_API_KEY = None
        mock_config.DEFAULT_TIMEOUT = 30.0

        service = GrafanaUserSyncService()
        
        assert service.auth_header.startswith("Basic ")
        assert "Bearer" not in service.auth_header
        headers = service._headers()
        assert headers["Authorization"].startswith("Basic ")

    @patch('services.grafana_user_sync_service.config')
    def test_explicit_api_key_overrides_config(self, mock_config):
        """Verify explicit API key parameter takes precedence."""
        mock_config.GRAFANA_URL = "http://grafana:3000"
        mock_config.GRAFANA_USERNAME = "admin"
        mock_config.GRAFANA_PASSWORD = "admin"
        mock_config.GRAFANA_API_KEY = "config-key"
        mock_config.DEFAULT_TIMEOUT = 30.0

        service = GrafanaUserSyncService(api_key="explicit-sync-key")
        
        assert service.auth_header == "Bearer explicit-sync-key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
