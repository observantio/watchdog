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
    MIMIR_URL: str = os.getenv("MIMIR_URL", "http://mimir:9009")
    
    # Grafana credentials
    GRAFANA_USERNAME: str = os.getenv("GRAFANA_USERNAME", "admin")
    GRAFANA_PASSWORD: str = os.getenv("GRAFANA_PASSWORD", "admin")
    GRAFANA_API_KEY: Optional[str] = os.getenv("GRAFANA_API_KEY")  # Preferred over Basic auth
    
    # Encryption key for sensitive data at rest (channel config in DB)
    DATA_ENCRYPTION_KEY: Optional[str] = os.getenv("DATA_ENCRYPTION_KEY")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://beobservant:changeme123@localhost:5432/beobservant")
    
    # Request settings
    DEFAULT_TIMEOUT: float = float(os.getenv("DEFAULT_TIMEOUT", "30.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_BACKOFF: float = float(os.getenv("RETRY_BACKOFF", "1.0"))
    
    # CORS settings
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # API limits
    MAX_QUERY_LIMIT: int = int(os.getenv("MAX_QUERY_LIMIT", "5000"))
    DEFAULT_QUERY_LIMIT: int = int(os.getenv("DEFAULT_QUERY_LIMIT", "100"))

    # Request protection / backpressure
    MAX_REQUEST_BYTES: int = int(os.getenv("MAX_REQUEST_BYTES", "1048576"))  # 1 MiB
    MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "200"))
    CONCURRENCY_ACQUIRE_TIMEOUT: float = float(os.getenv("CONCURRENCY_ACQUIRE_TIMEOUT", "1.0"))

    # Rate limiting / spam protection (per-process; use an API gateway for global limits)
    RATE_LIMIT_USER_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_USER_PER_MINUTE", "600"))
    RATE_LIMIT_PUBLIC_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PUBLIC_PER_MINUTE", "120"))
    RATE_LIMIT_LOGIN_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
    RATE_LIMIT_REGISTER_PER_HOUR: int = int(os.getenv("RATE_LIMIT_REGISTER_PER_HOUR", "5"))

    # Client IP and network boundary controls
    TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes", "on")
    AUTH_PUBLIC_IP_ALLOWLIST: Optional[str] = os.getenv("AUTH_PUBLIC_IP_ALLOWLIST")
    GATEWAY_IP_ALLOWLIST: Optional[str] = os.getenv("GATEWAY_IP_ALLOWLIST")
    WEBHOOK_IP_ALLOWLIST: Optional[str] = os.getenv("WEBHOOK_IP_ALLOWLIST")
    AGENT_INGEST_IP_ALLOWLIST: Optional[str] = os.getenv("AGENT_INGEST_IP_ALLOWLIST")
    AGENT_HEARTBEAT_TOKEN: Optional[str] = os.getenv("AGENT_HEARTBEAT_TOKEN")

    # Optional shared secrets for inbound endpoints
    INBOUND_WEBHOOK_TOKEN: Optional[str] = os.getenv("INBOUND_WEBHOOK_TOKEN")
    OTLP_INGEST_TOKEN: Optional[str] = os.getenv("OTLP_INGEST_TOKEN")
    
    # Authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-this-secret-key-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_MINUTES: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))

    # Identity provider / OIDC (Keycloak recommended)
    AUTH_PROVIDER: str = os.getenv("AUTH_PROVIDER", "local").strip().lower()  # local | keycloak
    AUTH_PASSWORD_FLOW_ENABLED: bool = os.getenv("AUTH_PASSWORD_FLOW_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    OIDC_ISSUER_URL: Optional[str] = os.getenv("OIDC_ISSUER_URL")
    OIDC_CLIENT_ID: Optional[str] = os.getenv("OIDC_CLIENT_ID")
    OIDC_CLIENT_SECRET: Optional[str] = os.getenv("OIDC_CLIENT_SECRET")
    OIDC_AUDIENCE: Optional[str] = os.getenv("OIDC_AUDIENCE")
    OIDC_JWKS_URL: Optional[str] = os.getenv("OIDC_JWKS_URL")
    OIDC_SCOPES: str = os.getenv("OIDC_SCOPES", "openid profile email")
    OIDC_AUTO_PROVISION_USERS: bool = os.getenv("OIDC_AUTO_PROVISION_USERS", "true").lower() in ("1", "true", "yes", "on")

    # Keycloak admin API (optional, for app-driven user provisioning)
    KEYCLOAK_ADMIN_URL: Optional[str] = os.getenv("KEYCLOAK_ADMIN_URL")
    KEYCLOAK_ADMIN_REALM: Optional[str] = os.getenv("KEYCLOAK_ADMIN_REALM")
    KEYCLOAK_ADMIN_CLIENT_ID: Optional[str] = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID")
    KEYCLOAK_ADMIN_CLIENT_SECRET: Optional[str] = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET")
    KEYCLOAK_USER_PROVISIONING_ENABLED: bool = os.getenv("KEYCLOAK_USER_PROVISIONING_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    
    # Default admin bootstrap (can be overridden via environment)
    DEFAULT_ADMIN_USERNAME: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    DEFAULT_ADMIN_EMAIL: str = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
    DEFAULT_ADMIN_TENANT: str = os.getenv("DEFAULT_ADMIN_TENANT", "default")
    
    # Multi-tenancy
    DEFAULT_ORG_ID: str = os.getenv("DEFAULT_ORG_ID", "default")
    OTLP_GATEWAY_URL: str = os.getenv("OTLP_GATEWAY_URL", "http://otlp-gateway:4320")
    DEFAULT_OTLP_TOKEN: Optional[str] = os.getenv("DEFAULT_OTLP_TOKEN")

    # Alerting and notifications defaults
    DEFAULT_RULE_GROUP: str = os.getenv("DEFAULT_RULE_GROUP", "default")
    DEFAULT_SLACK_CHANNEL: str = os.getenv("DEFAULT_SLACK_CHANNEL", "default")
    ENABLED_NOTIFICATION_CHANNEL_TYPES: list = [
        channel_type.strip().lower()
        for channel_type in os.getenv(
            "ENABLED_NOTIFICATION_CHANNEL_TYPES",
            "email,slack,teams,webhook,pagerduty",
        ).split(",")
        if channel_type.strip()
    ]


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
