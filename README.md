# Be Observant

Be Observant is a comprehensive observability control plane that integrates Grafana, Loki, Tempo, Alertmanager, and Mimir into a unified platform for monitoring, logging, tracing, and alerting.

## Architecture Overview

This platform provides:

- **Backend API** (`server`, FastAPI): Core REST API running on `http://localhost:4319`
- **Gateway Auth Service** (`gateway-auth-service`, FastAPI): Standalone OTLP token validation service used by nginx OTLP gateway
- **Grafana Integration**: Reverse proxy access at `http://localhost:8080/grafana/`
- **OTLP Gateway**: Authentication and organization mapping on `http://localhost:4320`
- **Data Services**: Postgres database, Loki for logs, Tempo for traces, Mimir for metrics, and Alertmanager for alerts

## Quick Start with Docker Compose

1. **Configure Environment Variables** (strongly recommended for production):

   Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to set secure values. Key variables to configure:

   - `POSTGRES_PASSWORD`: Database password
   - `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY`: Asymmetric JWT signing keys (RS256 or ES256)
   - `JWT_ALGORITHM`: `RS256` or `ES256`
   - `DEFAULT_ADMIN_PASSWORD`: Initial admin credentials (change immediately)
   - `DATA_ENCRYPTION_KEY`: Fernet key for data encryption (generate with Python)
   - `DEFAULT_OTLP_TOKEN`, `INBOUND_WEBHOOK_TOKEN`: Secure tokens for ingestion
   - `DEFAULT_ADMIN_BOOTSTRAP_ENABLED`: set to `false` in production and run explicit bootstrap
   - `JWT_AUTO_GENERATE_KEYS`: set to `false` in production

   Generate a Fernet key:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   The repository includes `.env.example` and `ui/.env.example` for reference.

2. **Set Required Variables** for non-development environments:

   Ensure these are configured in `.env`:

   - `POSTGRES_PASSWORD`
   - `JWT_PRIVATE_KEY`
   - `JWT_PUBLIC_KEY`
   - `JWT_ALGORITHM`
   - `DEFAULT_ADMIN_PASSWORD`
   - `DEFAULT_OTLP_TOKEN`
   - `INBOUND_WEBHOOK_TOKEN`
   - `DATA_ENCRYPTION_KEY`
   - `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false`
   - `JWT_AUTO_GENERATE_KEYS=false`
   - `REQUIRE_TOTP_ENCRYPTION_KEY=true`

3. **Launch the Stack**:

   ```bash
   docker compose up -d --build
   ```

4. **Verify Deployment**:

   Check service health:

   ```bash
   curl -s http://localhost:4319/health
   ```

5. **Access Interfaces**:

   - API Documentation: `http://localhost:4319/docs`
   - Grafana Dashboard: `http://localhost:8080/grafana/`

## Local Development Setup

### Backend Development

To run the API server locally (requires external services):

```bash
cd server/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Ensure Postgres, Loki, Tempo, Mimir, Alertmanager, and Grafana are accessible via environment URLs.

### Frontend Development

For UI development:

```bash
cd ui/
npm install
npm run dev
```

Build for production:

```bash
npm run build
npm run start
```

## Production Deployment Considerations

- **Proxy Configuration**: Set `TRUST_PROXY_HEADERS=false` unless behind a verified reverse proxy
- **Trusted Proxies**: If `TRUST_PROXY_HEADERS=true`, set `TRUSTED_PROXY_CIDRS` to your ingress/load-balancer subnets
- **Security**: Configure IP allowlists for public endpoints:
  - `WEBHOOK_IP_ALLOWLIST`
  - `GATEWAY_IP_ALLOWLIST`
  - `AUTH_PUBLIC_IP_ALLOWLIST`
   - `GRAFANA_PROXY_IP_ALLOWLIST`
- **Public Endpoint IP Resolution**: Keep `REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS=true` in production
- **Rate limits**: tune public endpoint protection as needed:
   - `RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE`
   - `GATEWAY_RATE_LIMIT_PER_MINUTE`
- **Secrets Management**: Use strong, unique secrets for all tokens and passwords; avoid default values
- **Secret Storage**: Use a secure secret manager (Vault/K8s Secrets/cloud secret manager); do not print or store secrets in logs
- **TLS Termination**: Handle SSL/TLS at your load balancer or edge proxy

### Bootstrap in production

- Disable runtime bootstrap by setting `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false`.
- Create tenant/admin explicitly via an initialization workflow before exposing the API publicly.
- Rotate initial admin credentials immediately and store all long-lived secrets outside repository files.

## Keycloak / OIDC auth mode

Be Observant supports external auth using Keycloak (including Microsoft SSO federated through Keycloak).

- Set `AUTH_PROVIDER=keycloak`
- Set `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` (and `OIDC_CLIENT_SECRET` for confidential clients)
- Optional: `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_SCOPES`
- Keep password grant disabled by default: `AUTH_PASSWORD_FLOW_ENABLED=false`
- Optional fallback (legacy/migration only): `AUTH_PASSWORD_FLOW_ENABLED=true`

OIDC endpoints:

- `POST /api/auth/oidc/authorize-url` (build authorization URL)
- `POST /api/auth/oidc/exchange` (authorization-code exchange)
- `GET /api/auth/mode` (UI/runtime auth capability discovery)

When Keycloak mode is enabled, local self-registration is disabled and app users are resolved by email from the OIDC token. Optional admin-driven Keycloak provisioning is available with `KEYCLOAK_USER_PROVISIONING_ENABLED=true` and Keycloak admin client credentials.

## Testing and load generation

The repo includes telemetry generators under `tests/`:

```bash
bash tests/generator.sh
bash tests/logs.sh localhost:4318 5 0.05
bash tests/traces.sh localhost:4318 200 0.03
```

These scripts require Docker and generate synthetic traces/logs for validation.

## Stop and cleanup

```bash
docker compose down
docker compose down -v   
```
