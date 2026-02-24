# User Guide

This guide covers authentication, core features, workflows, and operational runbooks for Be Observant.

---

## Running The Stack

Two compose modes are supported:

1. Source-build mode (`docker-compose.yml`)
- Use for active development.
- Requires sibling repos in this workspace, you might need to rename it to these folders:
  - `./BeCertain`
  - `./BeNotified`
  
- If missing, clone them before `docker compose up -d --build`.

2. Image mode (`docker-compose.stable.yml`)
- Use when you want a packaged stack and do not want local source checkouts.
- Set these in `.env`:
  - `BEOBSERVANT_IMAGE`
  - `BENOTIFIED_IMAGE`
  - `BECERTAIN_IMAGE`
- Then run `docker compose -f docker-compose.stable.yml up -d`.
- Default values are placeholders and must be replaced with published tags.

---

## Developer Pre-commit

This repository uses pre-commit quality gates for local development. Each commit runs:

- `server` unit tests
- `BeCertain` unit tests
- `BeNotified` unit tests
- `gateway-auth-service` unit tests
- `ui` lint, tests, and production build

Setup:

```bash
pip install pre-commit
pre-commit install
```

Optional manual run:

```bash
pre-commit run --all-files
```

---

## Signing In

Navigate to `http://localhost:5173` (or your deployed URL).

- **SSO / OIDC** — select **Continue with SSO** and authenticate through your identity provider (Keycloak, Microsoft, etc.)
- **Password** — enter your Be Observant username and password
- **First-time setup** — use the bootstrap admin credentials from `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`

When OIDC is active and password fallback is disabled, self-registration is blocked. Users are provisioned from the email claim in the OIDC token. Password-based sign-in requires the admin to configure 2FA.

---

## Core Features

| Feature | Description |
|---|---|
| Dashboards | Create, view, and manage Grafana dashboards with role-based permissions |
| Datasources | Configure and query metrics, logs, and trace data sources |
| Logs (Loki) | Execute log queries with advanced filtering |
| Traces (Tempo) | Search and analyse distributed traces and spans |
| RCA (BeCertain) | Run async root-cause analysis reports and review anomalies, causal links, and topology |
| Alerts (Alertmanager) | Manage alert rules, silences, and notification channels |
| Access Management | Administer users, groups, and API keys |

---

## Resource Visibility

Every resource has a visibility scope:

| Scope | Access |
|---|---|
| `private` | Owner only |
| `group` | Owner and designated groups |
| `tenant` | All users within the tenant |

If a resource is inaccessible, check its visibility setting and your group memberships. Admins can access all Grafana dashboards and datasources by design.

---

## Common Workflows

### Visualise Metrics

1. Create an API key and use the provided config file for your OTel agent.
2. Share that key with teammates as needed.
3. Configure a datasource and select the API key to use for it.
4. Create a dashboard by pasting your JSON file or using the built-in template.
5. Set the visibility and click **Open in Grafana** once created.
6. You will be taken directly to the dashboard. Based on your visibility and scope, you can see other dashboards or datasources, but you cannot configure metadata or delete resources that are shared to you.

### Manage Alert Silences

1. Go to the **Silences** interface and create a new silence.
2. Set matchers, time range, and optional group sharing.
3. Monitor active silences and extend them as needed.

### Manage API Keys

1. Go to **API Keys** and generate a key for your service.
2. Delete unused keys immediately.
3. The **active key** is the key used when reading traces and logs.
4. The **default key** is used when creating Grafana datasources.

---

## Logs & Traces

**Logs** — Select the target service from the top-right service selector, then filter and query logs using the available controls.

**Traces** — Select the target service from the top-right service selector, then filter traces as needed. A trace map is available to visualise multiple traces and traces with multiple spans.

---

## RCA Console

The **RCA** page (`/rca`) creates and monitors asynchronous analysis jobs through Be Observant.

- Job APIs are exposed on Be Observant under `/api/becertain/analyze/jobs*`
- The UI never talks to BeCertain directly
- Full reports include anomaly groups, ranked root causes, topology blast radius, forecast/SLO, and causal outputs
- Tenant scope is injected server-side; client-provided `tenant_id` is ignored

Key proxy/auth variables:

```env
BECERTAIN_URL=http://becertain:4322
BECERTAIN_SERVICE_TOKEN=
BECERTAIN_EXPECTED_SERVICE_TOKEN=
BECERTAIN_CONTEXT_SIGNING_KEY=
BECERTAIN_CONTEXT_VERIFY_KEY=
BECERTAIN_CONTEXT_ISSUER=beobservant-main
BECERTAIN_CONTEXT_AUDIENCE=becertain
BECERTAIN_TLS_ENABLED=false
BECERTAIN_SSL_ENABLED=false
BECERTAIN_ANALYZE_STORAGE_PATH=./data/becertain_jobs
BECERTAIN_ANALYZE_JOB_TTL_SECONDS=3600
BECERTAIN_ANALYZE_REPORT_RETENTION_DAYS=7
```

---

## Alerting

Alert rules are written in PromQL. Batch rules can also be created by supplying a YAML definition. Rules, channels, and silences are scoped to a group, organisation, or private visibility.

When an alert fires, Be Observant notifies the configured channel. Supported channel types are email, PagerDuty, Slack, and any others enabled by your admin at startup. Specific channel types can be disabled by the admin.

---

## Incidents (InOps)

When an alert fires, it is recorded on the incident board according to its visibility scope. From the board, team members can write notes, assign users, sync with Jira tickets, and resolve incidents with notes.

---

## Integrations

Configure Jira under **Integrations** to allow the InOps board to automatically create Jira tickets when an incident is created. Notification channels are also created here and are scoped by their configured visibility.

---

## Email Notifications

Be Observant sends emails for new user onboarding and incident assignment changes. If any required variable is missing or incomplete, email sending is silently skipped.

Set the following variables on the `beobservant` service:

```env
USER_WELCOME_EMAIL_ENABLED=true
USER_WELCOME_SMTP_HOST=
USER_WELCOME_SMTP_PORT=
USER_WELCOME_SMTP_USERNAME=
USER_WELCOME_SMTP_PASSWORD=
USER_WELCOME_FROM=
USER_WELCOME_SMTP_STARTTLS=
USER_WELCOME_SMTP_USE_SSL=
APP_LOGIN_URL=

INCIDENT_ASSIGNMENT_EMAIL_ENABLED=true
INCIDENT_ASSIGNMENT_SMTP_HOST=
INCIDENT_ASSIGNMENT_SMTP_PORT=
INCIDENT_ASSIGNMENT_SMTP_USERNAME=
INCIDENT_ASSIGNMENT_SMTP_PASSWORD=
INCIDENT_ASSIGNMENT_FROM=
INCIDENT_ASSIGNMENT_SMTP_STARTTLS=
INCIDENT_ASSIGNMENT_SMTP_USE_SSL=
```

Keep all credentials in `.env` or your secret manager — never hard-coded in compose files.

---

## Security & Authentication

### Secret management / Vault

Be Observant supports fetching sensitive configuration from a secret store (HashiCorp Vault) in addition to environment variables. This is opt-in — enable it with `VAULT_ENABLED=true`.

Recommendations:

- Kubernetes: prefer Vault Agent Injector or the Vault CSI driver (Kubernetes auth is recommended).
- Containers/VMs: use AppRole (RoleID + SecretID) or a short-lived Vault token provisioned at deploy time.

Important environment variables (examples in `.env.example`):

```env
VAULT_ENABLED=false
VAULT_ADDR=
VAULT_TOKEN=            # optional (token auth)
VAULT_ROLE_ID=          # optional (AppRole)
VAULT_SECRET_ID=        # optional (AppRole)
VAULT_SECRETS_PREFIX=secret
VAULT_KV_VERSION=2
VAULT_TIMEOUT=2.0
VAULT_FAIL_ON_MISSING=false
```

Behavior:

- When `VAULT_ENABLED=true` the server will attempt to read critical secrets (DATABASE_URL, JWT_PRIVATE_KEY/JWT_PUBLIC_KEY, DEFAULT_ADMIN_PASSWORD, DATA_ENCRYPTION_KEY, and other credentials).
- In production, set `VAULT_FAIL_ON_MISSING=true` (or `APP_ENV=production`) to make startup fail if Vault is unreachable or required secrets are missing.
- During rollout, keep `VAULT_ENABLED=false` to use environment variables; switch to Vault in staging before enabling in production.

Integration notes:

- The application exposes `config.get_secret("KEY_NAME")` which reads from Vault when enabled and falls back to environment variables.
- For Kubernetes we recommend using the Vault Agent Injector (renders secrets as files/env) or the CSI driver (mounts secrets). AppRole may be used for non-k8s deployments.

---

## Security & Authentication

### JWT Keys

Production requires explicit asymmetric key material:

```env
JWT_PRIVATE_KEY=<PEM>
JWT_PUBLIC_KEY=<PEM>
JWT_ALGORITHM=RS256
JWT_AUTO_GENERATE_KEYS=false
```

### MFA / TOTP

```
POST /api/auth/mfa/enroll
POST /api/auth/mfa/verify
```

TOTP secrets are stored encrypted. Recovery codes are generated at enrolment and hashed in the database. Set `REQUIRE_TOTP_ENCRYPTION_KEY=true` and configure `DATA_ENCRYPTION_KEY` to enforce encryption.

### API Keys & OTLP Tokens

All tokens are tenant-scoped and revocable from the UI or API. OTLP token validation is handled by the `gateway-auth-service`.

### BeCertain Internal Trust

BeCertain endpoints require:

- `X-Service-Token` (shared secret)
- Bearer context JWT signed by Be Observant (`tenant_id`, `org_id`, user claims)

Requests without valid internal credentials are rejected before route execution.

### Audit Logs

All `GET /api/*` requests produce `resource.view` audit entries. On Postgres, the `audit_logs` table is append-only — a DB trigger prevents `UPDATE` and `DELETE`.

### Rate Limiting

Per-user and per-IP fixed-window limits are enforced with Redis (or other backend via
`GATEWAY_RATE_LIMIT_BACKEND`) and an in-memory fallback. Set
`GATEWAY_RATE_LIMIT_STRICT=true` to require a working Redis backend; the gateway
will refuse to start if Redis cannot be initialised. Request payload sizes and
concurrency are capped at the middleware level.

---

## Grafana Proxy

The server proxies Grafana through `/api/grafana/*` and enforces:

- Dashboard and datasource visibility (private / group / tenant)
- Group membership checks for shared resources
- Query-level authorisation for datasource endpoints
- Scoped and restricted management of assets

---

## Admin Runbook

### Rotate JWT Keys

Replace `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` and restart the `beobservant` service. For zero-downtime rotation, implement JWK key IDs.

### Enforce Secure Cookies

```env
FORCE_SECURE_COOKIES=true
```

Or, if behind a verified reverse proxy:

```env
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_CIDRS=<your-ingress-subnets>
```

### Enable TOTP Encryption

```env
REQUIRE_TOTP_ENCRYPTION_KEY=true
DATA_ENCRYPTION_KEY=<fernet-key>
```

### Update IP Allowlists

Update the relevant `*_IP_ALLOWLIST` environment variable and restart the service.

### Disable Bootstrap in Production

```env
DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false
```

Provision admin accounts via your initialisation workflow before exposing the API.

### Reset a Locked MFA User

This operation is not available in the UI and requires a direct API call. It requires the **Manage Users** permission. Alternatively, use the recovery codes generated at enrolment.

```
POST /api/auth/users/{user_id}/mfa/reset
```

### Verify Audit Log Integrity

On Postgres deployments, confirm the append-only trigger exists in the DB schema. Audit entries cannot be modified or deleted through the application.

### Debug OTLP Ingestion Failures

1. Validate the token against `gateway-auth-service`.
   * The gateway performs no database operations; it first checks its Redis
     cache then calls the main server (`GATEWAY_AUTH_API_URL`) if necessary.
     Ensure Redis and the API are reachable by the gateway container.
2. Check `GATEWAY_IP_ALLOWLIST` for the sending IP.
3. Review `docker compose logs otlp-gateway`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `401` / `403` errors | Token expiration, permissions, tenant scope |
| Missing dashboard data | Datasource permissions, backend service health |
| No logs / traces / alerts | OTLP token validity, tenant mapping, service health |
| Rejected webhook / gateway requests | IP allowlists, token configuration |

**Useful commands**

```bash
docker compose logs <service>         # service logs
curl http://localhost:4319/health     # API health
curl http://localhost:4319/ready      # readiness (DB + upstream checks)
```

---

## Pre-Production Checklist

- [ ] Explicit `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` provided; `JWT_AUTO_GENERATE_KEYS=false`
- [ ] `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false`; admin provisioned via automation
- [ ] `DATA_ENCRYPTION_KEY` configured; `REQUIRE_TOTP_ENCRYPTION_KEY=true`
- [ ] IP allowlists configured for all public endpoints
- [ ] `REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS=true`
- [ ] Redis configured for rate limiting in multi-instance deployments
- [ ] TLS termination and secure cookie settings in place
- [ ] DB migrations complete; `DB_AUTO_CREATE_SCHEMA=false`
- [ ] Monitoring and alerts set up for rate limits, DB connectivity, and upstream reachability
- [ ] All default credentials rotated and stored in a secret manager
