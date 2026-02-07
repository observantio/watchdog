"""Application configuration and constants."""
import os
from typing import Optional

class Config:
    """Application configuration from environment variables."""
    # Server configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "4319"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")
    
    # Service URLs
    TEMPO_URL: str = os.getenv("TEMPO_URL", "http://tempo:3200")
    LOKI_URL: str = os.getenv("LOKI_URL", "http://loki:3100")
    ALERTMANAGER_URL: str = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")
    GRAFANA_URL: str = os.getenv("GRAFANA_URL", "http://grafana:3000")
    
    # Grafana credentials
    GRAFANA_USERNAME: str = os.getenv("GRAFANA_USERNAME", "admin")
    GRAFANA_PASSWORD: str = os.getenv("GRAFANA_PASSWORD", "admin")
    
    # Authentication
    API_KEY_HEADER: str = "X-API-Key"
    API_KEY: Optional[str] = os.getenv("API_KEY")
    API_KEYS: list = [key.strip() for key in os.getenv("API_KEYS", "").split(",") if key.strip()]
    ENABLE_AUTH: bool = os.getenv("ENABLE_AUTH", "false").lower() == "true"
    TENANT_LABEL_KEY: str = os.getenv("TENANT_LABEL_KEY", "tenant_id")
    REQUIRE_API_KEY_FOR_DATA: bool = os.getenv("REQUIRE_API_KEY_FOR_DATA", "true").lower() == "true"

    # Storage security
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "/data/beobservant")
    DATA_ENCRYPTION_KEY: Optional[str] = os.getenv("DATA_ENCRYPTION_KEY")
    
    # Request settings
    DEFAULT_TIMEOUT: float = float(os.getenv("DEFAULT_TIMEOUT", "30.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_BACKOFF: float = float(os.getenv("RETRY_BACKOFF", "1.0"))
    
    # CORS settings
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # API limits
    MAX_QUERY_LIMIT: int = int(os.getenv("MAX_QUERY_LIMIT", "5000"))
    DEFAULT_QUERY_LIMIT: int = int(os.getenv("DEFAULT_QUERY_LIMIT", "100"))


class Constants:
    """Application constants."""
    APP_NAME: str = "Be Observant with Your Infrastructure"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "Unified API for managing Tempo, Loki, AlertManager, and Grafana"
    )
    
    # HTTP status messages
    STATUS_HEALTHY: str = "Healthy"
    STATUS_SUCCESS: str = "Success"
    STATUS_ERROR: str = "Error"
    
    # Error messages
    ERROR_NOT_FOUND: str = "Resource not found"
    ERROR_INVALID_REQUEST: str = "Invalid request"
    ERROR_INTERNAL: str = "Internal server error"
    ERROR_UNAUTHORIZED: str = "Unauthorized"
    ERROR_TIMEOUT: str = "Request timeout"
    
    # Service names
    SERVICE_TEMPO: str = "Tempo"
    SERVICE_LOKI: str = "Loki"
    SERVICE_ALERTMANAGER: str = "AlertManager"
    SERVICE_GRAFANA: str = "Grafana"

config = Config()
constants = Constants()
