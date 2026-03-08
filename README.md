# Be Observant

Be Observant is a self-hosted observability control plane built around Grafana, Loki, Tempo, Mimir, Alertmanager, and a set of application services that add tenancy, access control, alert workflows, and AI-assisted root cause analysis.

If you are new to the project, the simplest way to think about it is this: the Grafana stack is the storage and query layer, and Be Observant is the application layer that makes it practical for a team and enterprise to use that stack together.

In plain terms, this workspace gives you:

- A secure entry point for telemetry ingestion.
- A web UI for logs, traces, dashboards, alert rules, incidents, and RCA.
- A control-plane API that sits in front of the Grafana stack.
- An alerting service that stores channel, rule, silence, and incident state.
- An RCA engine that correlates logs, metrics, and traces to rank possible causes.

This repository is best understood as one product made of several cooperating services.

## What The System Is Trying To Achieve

Be Observant aims to turn the raw LGTM stack into a usable multi-user application.

The base Grafana components already do storage and querying well:

- Loki stores and queries logs.
- Tempo stores and queries traces.
- Mimir stores and evaluates metrics and alert rules.
- Alertmanager handles alert routing and silences.
- Grafana renders dashboards and data sources.

Be Observant adds the pieces those components do not provide as a single opinionated product:

- Authentication and session management.
- User, group, permission, and API key management.
- Tenant-aware OTLP token validation.
- A single UI across observability, alerting, and RCA workflows.
- Shared integrations such as Jira and notification channels.
- Incident lifecycle tracking.
- AI-assisted RCA and anomaly workflows.

## What Lives In This Workspace

| Component | Role |
| --- | --- |
| `BeObservant` | Main FastAPI control plane. Handles auth, users, groups, API keys, Grafana proxy bootstrap, Loki/Tempo/Mimir-facing APIs, system metrics, and secure proxying to BeNotified and BeCertain. |
| `BeGateway` | OTLP token validation service for Envoy `ext_authz`. Validates `x-otlp-token`, applies allowlists and rate limits, and returns `X-Scope-OrgID` for downstream tenancy. |
| `BeNotified` | Alerting workflow service. Stores and serves alert rules, channels, silences, incidents, and Jira integrations. Consumes Alertmanager webhooks and protects most endpoints with an internal service token. |
| `BeCertain` | RCA and analysis engine. Reads logs, metrics, and traces from Loki, Mimir, and Tempo; runs anomaly detection and job-based RCA; stores RCA jobs and reports. |
| `ui` | React/Vite frontend. Exposes dashboards, logs, traces, alerts, incidents, integrations, API keys, users/groups, audit views, and RCA pages. |
| `docker-compose.yml` | Local reference deployment for the entire stack. |
| `.env.example` | Environment contract for all services. |
| `tests` | OTEL collector and sample telemetry generators used to feed demo traces and logs into the stack. |

## High-Level Architecture

```text
Applications / OTel Collector
  -> otlp-gateway (Envoy)
  -> gateway-auth (BeGateway ext_authz)
  -> Loki / Tempo / Mimir

Users
  -> UI
  -> BeObservant API
     -> Loki / Tempo / Mimir / Alertmanager / Grafana
     -> BeNotified
     -> BeCertain
```

### Service Responsibilities

#### `BeObservant`

This is the main application server.

From the code, it does all of the following:

- Boots the main database schema and auth service.
- Exposes login, logout, registration, OIDC exchange, MFA, user, group, audit, and API key endpoints.
- Stores and resolves the current user context, permissions, and API-key-backed scope.
- Proxies observability operations to Loki, Tempo, Grafana, Alertmanager, and BeCertain.
- Exposes `/api/internal/otlp/validate` so BeGateway can validate OTLP tokens against BeObservant's auth model.
- Provides `/health` and `/ready` checks and a `/api/system/metrics` endpoint for internal UI metrics.
- Sets security headers, request-size limits, concurrency limits, and CORS.

#### `BeGateway`

This service is the telemetry gatekeeper.

It is designed to sit behind Envoy's external authorization hook and does the following:

- Reads `x-otlp-token` from inbound telemetry requests.
- Applies optional IP allowlists.
- Applies request rate limiting.
- Caches token validation results in memory or Redis.
- Calls the BeObservant internal validation API when a cache miss occurs.
- Returns `X-Scope-OrgID` so Loki, Tempo, and Mimir receive the correct tenant scope.

Without this service, the system would still have storage backends, but not a protected multi-tenant OTLP ingestion path.

#### `BeNotified`

This service owns alerting workflows beyond raw Alertmanager delivery.

From the routers and services, it is responsible for:

- CRUD for alert rules.
- Importing rules from YAML, including a dry-run preview flow.
- Syncing rule definitions to Mimir for the target organization.
- CRUD for notification channels such as email, Slack, Teams, webhook, and PagerDuty.
- CRUD for silences.
- Maintaining incidents and enforcing incident lifecycle rules.
- Recording assignment and status changes.
- Sending assignment emails when configured.
- Jira integration management and Jira ticket/comment synchronization.
- Accepting inbound Alertmanager webhooks.

#### `BeCertain`

This service is the RCA engine.

It does not replace Loki, Tempo, or Mimir. It reads from them, analyzes their data, and produces reports.

Its responsibilities include:

- Waiting for logs, metrics, and trace backends to become reachable.
- Creating RCA jobs asynchronously.
- Listing and retrieving jobs and saved reports.
- Running anomaly analysis for metrics, logs, and traces.
- Running signal correlation, topology, causal, forecast, and SLO analysis endpoints.
- Storing RCA jobs and reports in its own database.
- Enforcing internal service-to-service auth and tenant-aware permission context.

#### `ui`

The frontend is not a demo shell. It is the main operator experience.

The route map shows these primary pages:

- Dashboard: system summary cards and activity widgets.
- Logs: Loki query builder, raw LogQL mode, labels, quick filters, log volume, and saved state.
- Traces: Tempo query and exploration UI using Dependency maps.
- Alert Manager: active alerts, alert rules, silences, hidden items, rule import, and rule testing.
- Incidents: incident board with assignment, state changes, notes, Jira actions, and correlation labels.
- Grafana: dashboards, folders, datasources, and a controlled hand-off into Grafana through the auth proxy.
- RCA: job creation, queue view, saved report lookup, root-cause ranking, anomalies, topology, causal analysis, forecast/SLO views, and report deletion.
- Integrations: notification channels and Jira integrations with visibility and sharing controls.
- Users, Groups, API Keys, Audit/Compliance: access-management workflows.

## Docker Compose Topology

The included `docker-compose.yml` brings up the full local stack:

- `postgres` for application data.
- `redis` for rate limiting, token cache, and shared ephemeral state.
- `beobservant` as the main API.
- `benotified` for alerts, incidents, and integrations.
- `gateway-auth` for OTLP auth.
- `becertain` for RCA.
- `otlp-gateway` as Envoy on port `4320`.
- `loki`, `tempo`, `mimir`, and `alertmanager` as the storage and routing backends.
- `grafana` plus `grafana-proxy` on port `8080`.
- `ui` on port `5173`.
- `otel-agent` as a local telemetry generator/test harness.

### Important Runtime Ports

| Port | Service | Purpose |
| --- | --- | --- |
| `5173` | `ui` | Web UI |
| `4319` | `beobservant` | Main API and docs |
| `4320` | `otlp-gateway` | OTLP ingress through Envoy |
| `4321` | `gateway-auth` | OTLP auth service |
| `4322` | `becertain` | RCA engine |
| `4323` | `benotified` | Alerting service |
| `8080` | `grafana-proxy` | Browser access to Grafana |

## Environment File Overview

The root `.env.example` is the configuration contract for the whole stack.

It is large because it configures multiple services at once. Read it in these groups:

- Core runtime: host, port, log level, database URLs.
- Auth: JWT signing, bootstrap admin, OIDC, Keycloak, MFA, cookie security.
- Ingestion security: OTLP tokens, gateway allowlists, rate limits, proxy trust settings.
- Service-to-service auth: shared tokens and signing keys for BeNotified and BeCertain.
- Alerting: channel types, webhook tokens, SMTP settings, Jira support.
- Grafana runtime: admin password, auth proxy config, datasource provisioning.
- BeCertain analysis tuning: correlation window, thresholds, timeouts, quality gating.
- Optional Vault and backup settings.

Two practical warnings for new users:

1. A few example values are placeholders, not safe defaults. Replace every `replace_with_...` value.
2. Some example lines show choices such as `AUTH_PROVIDER=local | oidc | keycloak`. You must replace those with one actual value, for example `AUTH_PROVIDER=local`.

## Quick Start

### Option A: Experimental Installer

The included installer is meant for evaluation and local testing.

It will:

- Check for required commands.
- Clone missing repos for `BeCertain` and `BeNotified`.
- Create or update `.env`.
- Generate secrets and a bootstrap admin account.
- Start the compose stack.

```bash
python3 install.py
```

### Option B: Manual Setup

```bash
git clone https://github.com/observantio/beobservant Observantio
cd Observantio

cp .env.example .env
```

Then edit `.env` and set, at minimum:

- Strong Postgres password values.
- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_ADMIN_EMAIL`
- `DATA_ENCRYPTION_KEY`
- `DEFAULT_OTLP_TOKEN`
- `GATEWAY_INTERNAL_SERVICE_TOKEN`
- `BENOTIFIED_SERVICE_TOKEN` and `BENOTIFIED_EXPECTED_SERVICE_TOKEN`
- `BECERTAIN_SERVICE_TOKEN` and `BECERTAIN_EXPECTED_SERVICE_TOKEN`
- `BENOTIFIED_CONTEXT_SIGNING_KEY` and `BENOTIFIED_CONTEXT_VERIFY_KEY`
- `BECERTAIN_CONTEXT_SIGNING_KEY` and `BECERTAIN_CONTEXT_VERIFY_KEY`

Start the stack:

```bash
docker compose up -d --build
```

Check health:

```bash
docker compose ps
curl http://localhost:4319/health
curl http://localhost:4319/ready
curl http://localhost:4323/health
curl http://localhost:4321/api/gateway/health
```

## First-Run User Journey

1. Open `http://localhost:5173`.
2. Sign in with the bootstrap admin configured in `.env`.
3. Create one or more API keys. These keys are not only UI objects; they drive tenant-scoped access and OTLP token usage.
4. Choose which API key should be the default scope in the UI. That choice affects what the frontend queries and where new rules are targeted.
5. Use the API Keys page to copy the OTLP token or generate a starter OpenTelemetry Collector YAML file.
6. Send telemetry to `http://localhost:4320` with the `x-otlp-token` header.
7. Confirm data in Logs and Traces.
8. Create or import alert rules, then connect channels and test them.
9. Review incident creation and update flows.
10. Run an RCA job after data exists.

## Known-Good Starting Point For Telemetry

The included test harness sends example traces and logs through a local OpenTelemetry Collector. If you want to connect your own collector, the important idea is:

- Logs go to `http://localhost:4320/loki`
- Traces go to `http://localhost:4320/tempo`
- Metrics go to `http://localhost:4320/mimir`
- Every request must include `x-otlp-token`

A collector pattern to start from looks like this:

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

## Alerting Philosophy In This Stack

The alerting flow is intentionally opinionated:

- Rules are managed as application objects, not only as raw backend config.
- Rules are synchronized to Mimir for evaluation.
- Active alerts surface in the Be Observant UI.
- Alertmanager webhook events feed BeNotified.
- Incidents become first-class objects with assignees, notes, and optional Jira linkage.

If you are new to the rule editor, start from a known-good template, then tune expressions and thresholds for your environment. That approach matches how the stack is built: validate the workflow first, then narrow noise and sensitivity.

## What The UI Gives An Operator

### Dashboard

Shows platform health, active alerts, log volume, dashboard count, silence count, datasource count, and service status.

### Logs

Provides label discovery, builder-mode filters, raw LogQL, log volume views, result browsing, and quick filters.

### Traces

Provides Tempo-backed trace exploration, direct trace lookup, and a graph view for comparing selected traces and service relationships.

### Alert Manager

Provides:

- Active alerts.
- Alert rules.
- Silences.
- YAML rule import with preview.
- Rule testing.
- Hidden/shared object handling.

### Incidents

Provides a board-driven view of operational incidents with assignment, notes, status changes, and Jira integration.

### API Keys

Provides tenant and product scoping, OTLP token management, key sharing with users and groups, token regeneration, and a downloadable starter OTel collector configuration.

### Users And Groups

Provides user creation, role and permission management, group-based permission inheritance, temporary password reset flows, and membership administration.

### Audit And Compliance

Provides searchable audit history with filters, detail inspection, and CSV export for administrative review.

### Grafana

Provides controlled management of dashboards, folders, and datasources, plus a secure hand-off into the Grafana UI through the auth proxy.

### RCA

Provides job creation, queue monitoring, historical report lookup, ranked root causes, anomalies, topology, causal views, and forecast/SLO views.

## Important Security Model

There are three different security boundaries in this stack:

1. User-to-application auth.
   BeObservant handles login, sessions, permissions, API keys, and optional OIDC/Keycloak.

2. Telemetry-ingest auth.
   BeGateway validates `x-otlp-token` before Envoy forwards data to Loki, Tempo, or Mimir.

3. Service-to-service auth.
   BeObservant talks to BeNotified and BeCertain using dedicated service tokens and signed context JWTs.

## Limits And Expectations

- This workspace is well suited for local evaluation, demos, and homelab environments.
- The installer is explicitly experimental.
- The docs in this repository should be treated as the source of truth for this workspace, not older external deployment examples.
- Empty environments will not produce useful RCA. BeCertain needs enough logs, metrics, and traces to correlate signals.

## Documentation

- Detailed walkthrough: [USER_GUIDE.md](USER_GUIDE.md)
- Environment reference: [.env.example](.env.example)

## License And Notices

This repository includes Apache 2.0 licensing and notice files in the root and service folders. Review them before redistribution or commercial use.
