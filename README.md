# Be Observant

Be Observant is a unified observability control plane built around the LGTM stack.
It combines secure telemetry ingestion, multi-tenant access control, alert/incident workflows, and AI-assisted RCA across one platform.

## Project Goals

- Remove enterprise lock-in for core observability operations.
- Keep Loki, Mimir, Tempo, and Grafana usable in a secure multi-tenant model.
- Provide one operational plane for metrics, logs, traces, incidents, and RCA.
- Make production-style security available in self-hosted environments.

## Architecture

| Service | Purpose |
| --- | --- |
| `beobservant` | Main control plane API + orchestration layer + UI backend |
| `gateway-auth` | Validates OTLP tokens and enforces tenant mapping |
| `otlp-gateway` | Envoy ingress for telemetry (`x-otlp-token`) |
| `grafana-proxy` | Authenticated RBAC proxy for Grafana access |
| `benotified` | Alerting, channels, routing, and incident board APIs |
| `becertain` | RCA/anomaly/forecast analysis engine |

Core dependencies include PostgreSQL, Redis, Grafana, Loki, Mimir, Tempo, and Alertmanager.

## Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/observantio/beobservant/main/install.py -o /tmp/install.py
python3 /tmp/install.py
```

The installer prepares a local environment for evaluation and testing.

## Manual Setup

```bash
git clone https://github.com/observantio/beobservant Observantio
cd Observantio
git clone https://github.com/observantio/becertain BeCertain
git clone https://github.com/observantio/benotified BeNotified
cp .env.example .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Set output as DATA_ENCRYPTION_KEY in .env

docker compose up -d --build
```

## Default Local Endpoints

- UI: `http://localhost:5173`
- Be Observant API docs: `http://localhost:4319/docs`
- Grafana proxy: `http://localhost:8080/grafana/`
- OTLP gateway: `http://localhost:4320`

## First-Run User Flow

1. Log in to the UI with bootstrap credentials.
2. Create or select an API key (tenant scope).
3. Configure your OpenTelemetry collector with `x-otlp-token`.
4. Verify data in Metrics/Logs/Traces pages.
5. Configure alert channels and rules in Alert Manager.
6. Trigger RCA in BeCertain and manage incidents in the Incident Board.

## Deployment Paths

- Local/dev compose: `docker-compose.yml`
- Stable image compose: `docker-compose.stable.yml`
- Kubernetes manifests: `deployments/eks/` (adapt to your cluster and secrets model)

## Security Highlights

- OTLP token validation at gateway ingress.
- JWT-based auth with support for asymmetric signing.
- Local + OIDC/Keycloak authentication options.
- Route-level RBAC and group-based access.
- Audit logging for sensitive operations.
- Optional Vault-backed secret loading.

## Current Project Status

Be Observant is in active development (beta). Recommended usage is local/homelab/testing until your own hardening and reliability criteria are satisfied.

## Documentation

- User guide: [USER_GUIDE.md](USER_GUIDE.md)
- Environment reference: [.env.example](.env.example)

## Contributing and Feedback

- Issues and feature requests: https://github.com/observantio/beobservant/issues
- Repository: https://github.com/observantio/beobservant
