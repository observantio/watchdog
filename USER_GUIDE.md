# Be Observant User Guide

Welcome to Be Observant, your observability platform. This guide walks you through authentication, core features, and best practices for effective system monitoring.

## Authentication and Access

### Signing In

1. Navigate to `http://localhost:8080/grafana/` (or your deployed URL).
2. **OIDC Authentication**: If configured (Keycloak/Microsoft SSO), select **Continue with SSO** and authenticate via your identity provider.
3. **Password Authentication**: If enabled, use your Be Observant username and password.
4. **Initial Setup**: For first-time access, use the bootstrap admin credentials from environment variables (`DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`).

**Note**: When OIDC is active and password fallback is disabled, self-registration is blocked. Users are provisioned based on email claims from OIDC.

## Core Platform Features

Be Observant integrates multiple observability tools into a unified interface:

- **Dashboards**: Create, view, and manage Grafana dashboards with role-based permissions
- **Datasources**: Configure and query data sources for metrics, logs, and traces
- **Logs (Loki)**: Execute log queries with advanced filtering and search capabilities
- **Traces (Tempo)**: Search and analyze distributed traces and spans
- **Alerts (Alertmanager)**: Manage alert rules, silences, and notification channels
- **Access Management**: Administer users, groups, and API keys for secure access control

## Resource Visibility Model

Resources in Be Observant follow a hierarchical visibility system:

- **`private`**: Accessible only to the resource owner
- **`group`**: Shared with the owner and designated user groups
- **`tenant`**: Available to all users within the tenant organization

If a resource is inaccessible, verify its visibility settings and your group memberships.

## OTLP Data Ingestion

For application and agent telemetry ingestion via the OTLP gateway (`:4320`):

- Include the authentication token in requests: `x-otlp-token: <token>`
- The gateway validates the token and automatically maps requests to the appropriate tenant and organization.

## Email Notifications Configuration

Be Observant supports SMTP-based email sending for both user onboarding and incident assignment notifications.

- **New user welcome emails** are triggered on `/api/auth/users` and `/api/auth/register` when enabled.
- **Incident assignment emails** are triggered when an incident assignee changes and email is enabled.

Set these environment variables on the `beobservant` service (already exposed in `docker-compose.yml`):

- `USER_WELCOME_EMAIL_ENABLED` (`true|false`)
- `USER_WELCOME_SMTP_HOST`, `USER_WELCOME_SMTP_PORT`, `USER_WELCOME_SMTP_USERNAME`, `USER_WELCOME_SMTP_PASSWORD`
- `USER_WELCOME_FROM`, `USER_WELCOME_SMTP_STARTTLS`, `USER_WELCOME_SMTP_USE_SSL`, `APP_LOGIN_URL`
- `INCIDENT_ASSIGNMENT_EMAIL_ENABLED` (`true|false`)
- `INCIDENT_ASSIGNMENT_SMTP_HOST`, `INCIDENT_ASSIGNMENT_SMTP_PORT`, `INCIDENT_ASSIGNMENT_SMTP_USERNAME`, `INCIDENT_ASSIGNMENT_SMTP_PASSWORD`
- `INCIDENT_ASSIGNMENT_FROM`, `INCIDENT_ASSIGNMENT_SMTP_STARTTLS`, `INCIDENT_ASSIGNMENT_SMTP_USE_SSL`

Keep secrets in `.env` (or your secret manager), not hard-coded in compose files.

## Common Workflows

### Creating a Dashboard

1. Navigate to the Dashboards section
2. Create a new dashboard or modify an existing one
3. Configure panels, queries, and visualizations
4. Set visibility level (`private`, `group`, or `tenant`)
5. For group visibility, select applicable user groups

### Managing Alert Silences

1. Access the Silences interface
2. Create a new silence with appropriate matchers and time range
3. Configure visibility and optional group sharing
4. Monitor and extend silences as needed

### API Key Management

1. Visit the API Keys management page
2. Generate new keys for automated workflows or service accounts
3. Immediately disable or delete unused keys to maintain security

## Troubleshooting Guide

### Common Issues

- **Authentication Errors (401/403)**: Check token expiration, permissions, or tenant scope configuration
- **Missing Dashboard Data**: Verify datasource permissions and backend service availability
- **Absent Logs/Traces/Alerts**: Confirm OTLP token validity, tenant mapping, and service health
- **Rejected Webhooks/Gateway Requests**: Review IP allowlists and token configurations

### Diagnostic Steps

1. Check service logs: `docker compose logs <service>`
2. Verify API health: `curl http://localhost:4319/health`
3. Validate configuration in `.env` file
4. Review network connectivity and firewall rules

## Best Practices

- **Security**: Implement least-privilege access controls
- **Access Control**: Prefer group-level sharing over tenant-wide visibility when possible
- **Key Rotation**: Regularly rotate API keys and OTLP tokens
- **Environment Hygiene**: Disable default credentials in production deployments
- **Monitoring**: Set up alerts for critical system metrics and service health
