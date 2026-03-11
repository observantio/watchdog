# Observantio User Guide

This guide explains how to install, understand, and use the full application stack in this workspace.

It is written for someone who wants more than a quick start. The goal is to make the system understandable enough that you know what each service does, why it exists, how the pieces fit together, and what to do first after the stack is running.

## 1. What You Are Deploying

When you run this project, you are not starting one server. You are starting a product composed of multiple servers and infrastructure components.

### Core application services

| Service | Port| Why It Exists |
|:---|:---|:---|
| `beobservant` | `4319` | Main API and control plane. Owns users, groups, API keys, auth, most UI-facing APIs, and secure proxying to the rest of the platform. |
| `begateway` | `4321` | Validates OTLP tokens for telemetry ingestion and returns tenant scope. |
| `benotified` | `4323` | Stores and serves alert rules, channels, silences, incidents, and Jira integrations. |
| `becertain` | `4322` | Runs RCA and anomaly analysis over logs, metrics, and traces. |
| `ui` | `5173` | React frontend for operators. |

### Supporting infrastructure

| Service | Why It Exists |
|:---|:---|
| `postgres` | Persistent storage for beobservant, benotified, and beertain. |
| `redis` | Rate limits, token caches, and shared fast state. |
| `otlp-gateway` | Envoy edge for OTLP traffic. Calls begateway before forwarding telemetry. |
| `gateway-auth` | Decoupled server that acts as redis cache between the main server and envoy to validate and translate otlp keys to tenant keys |
| `loki` | Log storage and query engine. |
| `tempo` | Trace storage and query engine. |
| `mimir` | Metrics storage and rule evaluation backend. |
| `alertmanager` | Alert routing and silence management backend. |
| `grafana` | Dashboard and datasource UI backend. |
| `grafana-proxy` | Browser-facing proxy for Grafana with BeObservant auth in front. |
| `otel-agent` | Demo/test telemetry generator included in the compose stack. |

## 2. How The Whole System Works

### 2.1 User flow

1. A user opens the UI.
2. The UI authenticates against BeObservant.
3. BeObservant returns user identity, permissions, and API-key-backed scope.
4. The UI calls BeObservant APIs for logs, traces, alerts, incidents, Grafana objects, and RCA.
5. BeObservant proxies or signs downstream requests to the appropriate backend service.

### 2.2 Telemetry flow

1. An app or collector sends OTLP traffic to `otlp-gateway` on port `4320`.
2. Envoy calls BeGateway for authorization.
3. BeGateway validates `x-otlp-token`, applies allowlists and rate limits, and resolves the org scope.
4. Envoy forwards the request to Loki, Tempo, or Mimir with `X-Scope-OrgID`.

### 2.3 Alert flow

1. Alert rules are created in the UI.
2. BeObservant forwards those actions into BeNotified.
3. BeNotified stores the rule and synchronizes rule definitions to Mimir.
4. Mimir evaluates rules.
5. Alertmanager routes alerts.
6. Webhook events feed BeNotified.
7. BeNotified stores incidents and exposes them back to the UI.

### 2.4 RCA flow

1. A user creates an RCA job in the UI.
2. BeObservant signs and forwards the request to BeCertain.
3. BeCertain reads from Loki, Tempo, and Mimir.
4. BeCertain stores job state and report output.
5. The UI retrieves the completed report and shows summaries, anomalies, topology, causal views, and ranked root causes.

## 3. Before You Start

You need:

- Docker with `docker compose`
- Git
- Python 3 for the installer
- Free local ports: `5173`, `4319`, `4320`, `4321`, `4322`, `4323`, `8080`

Recommended for first use:

- Start with the included Docker Compose setup.
- Keep auth in `local` mode first.
- Keep TLS disabled internally first.
- Use the built-in OTEL test generator before wiring your own applications.

## 4. Choose A Setup Path

### 4.1 Fastest path: installer

Run:

```bash
python3 install.py
```

What the installer does:

- Confirms required tools exist.
- Clones missing repositories if needed.
- Creates or updates `.env`.
- Generates bootstrap secrets and tokens.
- Creates admin credentials.
- Starts the compose stack.

When to use it:

- You want a local evaluation environment quickly.
- You do not need to hand-tune every setting on first boot.

When not to use it:

- You need a production-ready configuration.
- You want full manual control over secret values before first start.

### 4.2 Manual setup

Copy the example env file and edit it.

```bash
cp .env.example .env
```

Then bring the stack up.

```bash
docker compose up -d --build
```

## 5. Minimum `.env` Values You Must Understand

The `.env` file is large because it configures several services at once. For a successful first run, focus on the sections below.

### 5.1 Bootstrap admin

Set these values deliberately:

- `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=true`
- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_ADMIN_EMAIL`
- `DEFAULT_ADMIN_TENANT`
- `DEFAULT_ORG_ID`

This is the first account you will use to sign into the UI.

### 5.2 Database values

These must be internally consistent:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `DATABASE_URL`
- `BENOTIFIED_DATABASE_URL`
- `BECERTAIN_DATABASE_URL`

If you change the Postgres username or password, update all dependent URLs too.

### 5.3 Auth mode

For a simple first deployment, use:

```env
AUTH_PROVIDER=local
AUTH_PASSWORD_FLOW_ENABLED=true
```

Do not leave the literal example `local | oidc | keycloak` in place.

### 5.4 Encryption and signing

These values must be strong and unique:

- `DATA_ENCRYPTION_KEY`
- `GATEWAY_INTERNAL_SERVICE_TOKEN`
- `BENOTIFIED_SERVICE_TOKEN`
- `BENOTIFIED_EXPECTED_SERVICE_TOKEN`
- `BENOTIFIED_CONTEXT_SIGNING_KEY`
- `BENOTIFIED_CONTEXT_VERIFY_KEY`
- `BECERTAIN_SERVICE_TOKEN`
- `BECERTAIN_EXPECTED_SERVICE_TOKEN`
- `BECERTAIN_CONTEXT_SIGNING_KEY`
- `BECERTAIN_CONTEXT_VERIFY_KEY`

Recommended first-run rule:

- Set each token pair to the same strong value when the pair represents request authentication.
- Set each HS256 signing and verify key pair to the same strong value unless you intentionally redesign that trust model.

### 5.5 OTLP ingestion

Important keys:

- `DEFAULT_OTLP_TOKEN`
- `OTLP_INGEST_TOKEN`
- `OTEL_OTLP_TOKEN`
- `GATEWAY_IP_ALLOWLIST`
- `GATEWAY_RATE_LIMIT_PER_MINUTE`
- `GATEWAY_RATE_LIMIT_BACKEND`
- `GATEWAY_TOKEN_CACHE_REDIS_URL`

For local testing, a single strong `DEFAULT_OTLP_TOKEN` is enough to get started.

### 5.6 Grafana and browser access

Important keys:

- `GRAFANA_USERNAME`
- `GRAFANA_PASSWORD`
- `GF_SECURITY_ADMIN_PASSWORD`
- `GF_SERVER_ROOT_URL`
- `GF_SERVER_SERVE_FROM_SUB_PATH`
- `GF_AUTH_PROXY_ENABLED`

Leave the root URL aligned with the proxied path unless you know you need a different reverse-proxy layout.

### 5.7 BeCertain tuning

These settings control how strict or permissive RCA becomes:

- `BECERTAIN_CORRELATION_WINDOW_SECONDS`
- `BECERTAIN_QUALITY_GATING_PROFILE`
- `BECERTAIN_QUALITY_MAX_ANOMALY_DENSITY_PER_METRIC_PER_HOUR`
- `BECERTAIN_QUALITY_MAX_CHANGE_POINT_DENSITY_PER_METRIC_PER_HOUR`
- `BECERTAIN_QUALITY_MIN_CORROBORATION_SIGNALS`
- `BECERTAIN_RCA_EVENT_CONFIDENCE_THRESHOLD`
- `BECERTAIN_RCA_MIN_CONFIDENCE_DISPLAY`

Start with the defaults. Tune only after you have real telemetry and understand how noisy your environment is.

## 6. Start The Stack

```bash
docker compose up -d --build
docker compose ps
```

Initial startup can take a while because multiple images are being built and the application services wait on databases and observability backends.

## 7. Verify The Stack Cleanly

Run these checks:

```bash
curl http://localhost:4319/health
curl http://localhost:4319/ready
curl http://localhost:4323/health
curl http://localhost:4321/api/gateway/health
```

Open these URLs in a browser:

- UI: `http://localhost:5173`
- API docs: `http://localhost:4319/docs`
- Grafana proxy: `http://localhost:8080/grafana/` must be accessed via the UI or else 401 error

What success looks like:

- The UI login page loads.
- The BeObservant health endpoint is healthy.
- The BeObservant ready endpoint eventually reports downstream checks as ready.
- Grafana loads through the proxy after UI authentication.

## 8. First Login And Access Setup

1. Sign in with the bootstrap admin.
2. Open the API Key page.
3. Create at least one API key.
4. Treat that key as your first product or tenant scope.
5. Keep note of its OTLP token usage because telemetry routing depends on it.

Why API keys matter here:

- They are not only secrets for ingestion.
- The UI also uses the active scope to send `X-Scope-OrgID` on observability and alerting requests.
- Alert rules and metrics names can be scoped by org/product.

## 9. Send Test Telemetry

The compose stack already includes `otel-agent`, which runs an OTel collector and sample log/trace generators from the `tests` folder.

That gives you a known-good local signal source without needing a real application first.

### 9.1 Expected result

After the system settles, you should see:

- Logs in the Logs page.
- Traces in the Traces page.
- Backend health reflected on the dashboard.

### 9.2 Collector pattern for your own app

Use separate OTLP HTTP exporters per signal and send them to the Envoy prefixes.

```yaml
exporters:
  otlphttp/logs:
    endpoint: http://localhost:4320/loki
    headers:
      x-otlp-token: YOUR_OTLP_TOKEN

  otlphttp/traces:
    endpoint: http://localhost:4320/tempo
    headers:
      x-otlp-token: YOUR_OTLP_TOKEN

  otlphttp/metrics:
    endpoint: http://localhost:4320/mimir
    headers:
      x-otlp-token: YOUR_OTLP_TOKEN
```

## 10. Learn The UI By Page

### 10.1 Dashboard

Use it to answer basic questions fast:

- Is the platform healthy?
- Are there active alerts?
- Is log volume arriving?
- How many Grafana objects exist?

### 10.2 Logs

Use the Logs page when you want:

- Label discovery.
- Quick filtering.
- Builder-mode queries.
- Raw LogQL queries.
- Log volume context.

Good first test:

1. Open Logs.
2. Choose a time range like 60 minutes.
3. Query without filters first.
4. Add service labels after confirming data exists.

### 10.3 Traces

Use the Traces page to inspect request paths, latency, parent/child spans, and service relationships.

Good first test:

1. Open Traces.
2. Search within the last hour.
3. Pick a generated trace.
4. Confirm span trees and service names are visible.

### 10.4 Alert Manager

This page combines several operator workflows:

- View active alerts.
- Create and edit rules.
- Test rules.
- Import rule YAML with a preview step.
- Create and manage silences.

Best practice:

Start from a known-good rule template, confirm the workflow works end to end, then tune the expression and thresholds for your own environment. Do not start by over-optimizing thresholds on an empty or noisy dataset.

### 10.5 Integrations

Use this page to manage:

- Notification channels.
- Shared or private visibility for channels.
- Jira integrations.
- Jira auth mode and connectivity.

Recommended first action:

Create one test webhook or email/slack channel and use the built-in channel test before wiring incident workflows around it.

### 10.6 Incidents

This is the operational board.

Use it to:

- Review incidents created from alerts.
- Assign incidents.
- Add notes.
- Move incidents through status changes.
- Link or sync activity to Jira.

Behavior worth knowing:

- The system prevents resolving some incidents if the underlying alert is still active.
- Assignment and status changes can trigger downstream notes or Jira synchronization.

### 10.7 Grafana

This page is a controlled management layer, not just a link out.

Use it to:

- Search dashboards.
- Create and edit dashboards.
- Manage folders.
- Manage datasources.
- Open Grafana through a bootstrap session and auth proxy.

### 10.8 RCA

This page is the BeCertain frontend.

Use it to:

- Create analysis jobs.
- Monitor queued and finished jobs.
- Look up reports by ID.
- Review root causes, anomalies, topology, causal signals, warnings, and forecast/SLO views.

Important expectation:

RCA quality depends on data quality. Sparse or synthetic data can still demonstrate the workflow, but the most useful reports appear once your environment has enough real cross-signal activity.

## 11. Alerting Setup Walkthrough

### 11.1 Create a notification channel

1. Open Integrations.
2. Create a channel.
3. Keep it enabled.
4. Test it immediately.

### 11.2 Create or import a rule

1. Open Alert Manager.
2. Create a simple rule or import YAML with dry run first.
3. Bind the rule to the correct org/product scope.
4. Save and allow the rule to sync to Mimir.

### 11.3 Watch active alerts

1. Trigger or wait for a condition.
2. Confirm it appears under Active Alerts.
3. Confirm notification delivery.

### 11.4 Work the incident

1. Open Incidents.
2. Assign the incident.
3. Add notes.
4. Change state only when the underlying alert state makes sense.

## 12. RCA Setup Walkthrough

### 12.1 Before you run RCA

Make sure:

- Logs exist.
- Traces exist.
- Metrics exist if you expect metric-based evidence.
- The service or scope you care about has enough activity to analyze.

### 12.2 Run a first RCA job

1. Open RCA.
2. Create a job for a recent time window.
3. Wait for completion.
4. Open the report.

### 12.3 How to read the report

Read it in this order:

1. Summary.
2. Root Causes.
3. Anomalies.
4. Topology and Causal tabs.
5. Warnings.

This keeps you from over-trusting one weak signal before you check corroboration.

## 13. Auth And Identity Modes

### 13.1 Local auth

Best for first deployment.

- Username/password login.
- Optional MFA flows.
- Bootstrap admin support.

### 13.2 OIDC or Keycloak

Use once the local flow is understood.

You will need to configure:

- `AUTH_PROVIDER`
- `OIDC_*` or `KEYCLOAK_*` values
- redirect URIs
- client credentials

The frontend supports OIDC authorization URL creation, PKCE, state/nonce handling, and callback exchange.

## 14. Security Hardening Checklist

For anything beyond local evaluation, review this list:

1. Replace every placeholder token and signing key.
2. Disable automatic JWT key generation and supply managed keys.
3. Restrict `CORS_ORIGINS`.
4. Enable secure cookies behind TLS.
5. Set `TRUST_PROXY_HEADERS` and `TRUSTED_PROXY_CIDRS` correctly if running behind a reverse proxy.
6. Configure IP allowlists for public-sensitive endpoints.
7. Move secrets to Vault or another secret manager if required.
8. Back up Postgres before testing destructive operations.

## 15. Common Problems And What They Usually Mean

| Symptom | Likely Cause | What To Check |
|:---|:---|:---|
| UI loads but login fails | Bootstrap credentials or auth mode mismatch | `.env`, auth provider, admin bootstrap values |
| No logs or traces appear | Bad OTLP token, wrong endpoint, or collector misrouting | `x-otlp-token`, `http://localhost:4320`, collector exporter endpoints |
| `ready` stays not ready | One or more downstream services are still unhealthy | `docker compose ps`, BeObservant ready payload |
| Grafana opens incorrectly | Proxy/root URL mismatch or not authenticated | Grafana proxy settings and browser auth state |
| Alert rule exists but nothing fires | Rule expression, scope, or dataset mismatch | org/product selection, metric names, actual metric presence |
| Incident cannot be resolved | Underlying alert still active | active alerts state in Alert Manager |
| RCA job completes with weak results | Not enough cross-signal data | logs/traces/metrics volume and time window |

## 16. What To Tune Later, Not First

Do not tune these on day one unless something is clearly broken:

- RCA confidence thresholds
- quality gating density limits
- gateway rate limits
- per-service HTTP tuning values
- alert thresholds for every service

First prove that:

1. Authentication works.
2. Telemetry reaches Loki, Tempo, and Mimir.
3. The UI can query data.
4. Alert rules can be created and tested.
5. Incidents appear and can be worked.
6. RCA jobs complete.

Then tune noise, sensitivity, and performance.

## 17. Source Of Truth In This Workspace

If documentation and code disagree, prefer the code in this order:

1. `docker-compose.yml`
2. `.env.example`
3. service `main.py`, routers, and config files
4. frontend route and API files

That order reflects how this guide was derived.# Be Observant User Guide

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
|:---|:---|:---|
| `403` on API actions | Missing permission or wrong active scope | Verify user permissions, group membership, and selected API key |
| No telemetry data | Token mismatch or collector misconfiguration | Validate `x-otlp-token`, endpoint, and collector exporter config |
| Grafana proxy unauthorized | Missing UI session/auth mismatch | Sign in via UI first; verify auth and proxy configuration |
| RCA jobs fail/hang | BeCertain unavailable or no usable signal | Check service health/logs and ensure dataset has enough volume |
| Alert test fails | No enabled channels or misconfigured integration | Enable channels and validate credentials/config |
| Grafana Proxy 500 | This means the proxy can't communicate with either Be Observant or Grafana and is an IP drift, restart the grafana proxy server |

## 9. Helpful Links

- README: [README.md](README.md)
- Environment reference: [.env.example](.env.example)
- Issues: https://github.com/observantio/beobservant/issues
- Repository: https://github.com/observantio/beobservant
