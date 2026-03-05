# Be Observant User Guide

This guide covers deployment, first-time usage, core workflows, and operational hardening for Be Observant.

## 1. Scope and Assumptions

- Current focus: local, homelab, and pre-production evaluation.
- You should validate hardening, backups, and failure scenarios before production rollout.
- Main stack components: `beobservant`, `gateway-auth`, `otlp-gateway`, `grafana-proxy`, `benotified`, `becertain`.

## 2. Prerequisites

- Docker + Docker Compose
- Linux/macOS shell environment
- Open ports: `5173`, `4319`, `4320`, `8080`
- Git and Python 3 (for installer/manual setup)

## 3. Deployment Options

### Option A: Installer (Fastest)

```bash
curl -fsSL https://raw.githubusercontent.com/observantio/beobservant/main/install.py -o /tmp/install.py
python3 /tmp/install.py
```

### Option B: Source Build (Development)

```bash
git clone https://github.com/observantio/beobservant Observantio
cd Observantio
git clone https://github.com/observantio/becertain BeCertain
git clone https://github.com/observantio/benotified BeNotified
cp .env.example .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Put value into DATA_ENCRYPTION_KEY in .env

docker compose up -d --build
```

### Option C: Stable Images

```bash
curl -fsSL -o docker-compose.stable.yml https://raw.githubusercontent.com/observantio/beobservant/main/docker-compose.stable.yml
docker compose -f docker-compose.stable.yml up -d
```

### Option D: Kubernetes/EKS

Use manifests under `deployments/eks/` as a starting point. You must provide cluster-specific ingress, secrets, storage classes, and TLS.

## 4. Post-Deploy Verification

```bash
docker compose ps
curl http://localhost:4319/health
curl http://localhost:4319/ready
```

Access:

- UI: `http://localhost:5173`
- API Docs: `http://localhost:4319/docs`
- Grafana proxy: `http://localhost:8080/grafana/`
- OTLP gateway: `http://localhost:4320`

## 5. Core User Flows

### 5.1 First Login and Access Model

1. Sign in with bootstrap admin (or configured auth flow).
2. If using OIDC/Keycloak, align account emails for expected mapping behavior.
3. Assign users to groups and permissions (new users should stay least-privileged until approved).

### 5.2 API Key and Tenant Scope Flow

1. Open API Keys / key management.
2. Create a scoped key for the environment/team.
3. Set active key in UI key switcher.
4. Confirm dashboards/queries reflect the selected key scope.

### 5.3 Telemetry Ingestion Flow

1. Configure OTel collector exporter to send to `http://<host>:4320`.
2. Add `x-otlp-token` header using an active API key token.
3. Verify data appears in Logs, Metrics, and Traces pages.

### 5.4 Alert and Incident Flow

1. Configure channels (Slack/Jira/Email/PagerDuty/Teams/Webhook) in integrations.
2. Create alert rules in Alert Manager.
3. Validate test alert delivery.
4. Track incidents in Incident Board (InOps) with assignees and notes.
5. Close incidents with a resolution note for long-term learning context.

### 5.5 RCA Flow (BeCertain)

1. Open RCA page and choose target service/window.
2. Trigger analysis job.
3. Review ranked hypotheses and evidence links.
4. Use output to drive incident actions and post-incident notes.

## 6. Configuration Keys You Should Know

From `.env.example`:

- Core/API: `PORT`, `LOG_LEVEL`, `DATABASE_URL`, `DB_AUTO_CREATE_SCHEMA`
- Auth/JWT: `JWT_ALGORITHM`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_AUTO_GENERATE_KEYS`
- Tenancy: `DEFAULT_ORG_ID`, `DEFAULT_ADMIN_*`
- Proxy/service auth: `BENOTIFIED_*`, `BECERTAIN_*`, `GATEWAY_INTERNAL_SERVICE_TOKEN`
- Security boundaries: `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS`, `FORCE_SECURE_COOKIES`, `ALLOWLIST_FAIL_OPEN`
- Allowlists: `AUTH_PUBLIC_IP_ALLOWLIST`, `WEBHOOK_IP_ALLOWLIST`, `GATEWAY_IP_ALLOWLIST`, `GRAFANA_PROXY_IP_ALLOWLIST`
- Rate limits: `RATE_LIMIT_*`, `MAX_REQUEST_BYTES`, `MAX_CONCURRENT_REQUESTS`
- OIDC/Keycloak: `AUTH_PROVIDER`, `OIDC_*`, `KEYCLOAK_*`
- Secrets: `DATA_ENCRYPTION_KEY`, `VAULT_ENABLED`, `VAULT_*`

## 7. Hardening Checklist

- Set `JWT_AUTO_GENERATE_KEYS=false` and provide managed keys.
- Set strong values for service tokens and context signing keys.
- Restrict CORS origins (`CORS_ORIGINS`) and enable secure cookies in TLS environments.
- Configure allowlists and `TRUST_PROXY_HEADERS` correctly behind reverse proxies.
- Move secrets to Vault or equivalent managed secret stores.
- Use Redis-backed rate limiting in shared/multi-instance setups.
- Define backup/restore procedures for Postgres before broader rollout.

## 8. Common Troubleshooting

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| `403` on API actions | Missing permission or wrong active scope | Verify user permissions, group membership, and selected API key |
| No telemetry data | Token mismatch or collector misconfiguration | Validate `x-otlp-token`, endpoint, and collector exporter config |
| Grafana proxy unauthorized | Missing UI session/auth mismatch | Sign in via UI first; verify auth and proxy configuration |
| RCA jobs fail/hang | BeCertain unavailable or no usable signal | Check service health/logs and ensure dataset has enough volume |
| Alert test fails | No enabled channels or misconfigured integration | Enable channels and validate credentials/config |

## 9. Helpful Links

- README: [README.md](README.md)
- Environment reference: [.env.example](.env.example)
- Issues: https://github.com/observantio/beobservant/issues
- Repository: https://github.com/observantio/beobservant
