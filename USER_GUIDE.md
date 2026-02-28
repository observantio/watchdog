This is a comprehensive guide. To make it "more human" and professional, we should shift from a purely technical manual to a **User-Centric Documentation** style. This means focusing on *intent* (what the user wants to achieve) rather than just *settings*.

I have reorganized the content into logical "Journeys": **Getting Started**, **The User Experience**, and **The Administrator’s Handbook**.

---

# 🔭 Be Observant: The Complete User Guide

Welcome to the central command for your observability stack. This guide will walk you through deploying, using, and hardening the Be Observant platform.

---

## 🏗 Part 1: Deployment & Getting Started

### Running the Stack

Be Observant supports two deployment workflows depending on your goals.

#### Option A: Source-Build Mode (For Developers)

Best for active development or customizing internal services.

* **Requirement:** Sibling repositories (`./BeCertain` and `./BeNotified`) must exist in the workspace.
* **Launch:**
```bash
git clone https://github.com/observantio/becertain BeCertain
git clone https://github.com/observantio/benotified BeNotified
docker compose up -d --build

```


#### Option B: Image Mode (For Users)

Best for testing or production-like environments using pre-packaged images.

* **Setup:** Define your tags in `.env` (e.g., `BEOBSERVANT_IMAGE=observantio/beobservant:latest`).
* **Launch:**
```bash
docker compose -f docker-compose.stable.yml up -d

```


### Developer Quality Gates

To ensure stability, we enforce pre-commit checks.

```bash
pip install pre-commit && pre-commit install

```

*Every commit validates backend unit tests (Server, BeCertain, BeNotified), UI linting, and production builds.*

---

## 👤 Part 2: The User Experience

### Signing In

Access the UI at `http://localhost:5173`.

* **Corporate SSO:** Click **Continue with SSO** for OIDC-based login (Keycloak, Okta, etc.).
* **Standard Login:** Use your provisioned credentials.
* **First Time?** Use the bootstrap admin credentials defined in your `.env`.

### Core Capabilities at a Glance

| Feature | Your Workflow |
| --- | --- |
| **Dashboards** | Visualize system health via RBAC-protected Grafana instances. |
| **Logs & Traces** | Search Loki logs and analyze Tempo traces with deep context. |
| **RCA (BeCertain)** | Run AI-driven jobs to find the "smoking gun" in minutes. |
| **Incidents (InOps)** | Manage the lifecycle of an alert from trigger to Jira resolution. |

### Managing Visibility

Control who sees what using **Visibility Scopes**:

* **Private:** Only you can see it.
* **Group:** Shared with specific team members.
* **Tenant:** Visible to everyone in your organization.

---

## 🛠 Part 3: Operational Workflows

### 1. Visualizing Telemetry

1. **Generate an API Key:** Navigate to **API Keys** and create a token for your OTel agent.
2. **Configure Datasource:** Use the key to connect your metrics/logs.
3. **Open in Grafana:** Click "Open in Grafana" to see your data instantly. *Note: You can view shared dashboards but cannot edit their metadata unless granted permission.*  
  > **HTTP development caveat:** when the UI is served over plain HTTP the
  > Grafana session cookie is normally marked `Secure` and will be ignored by
  > the browser, causing a never‑ending loading spinner and repeated
  > `/api/grafana/auth` requests. To fix this set `GF_SECURITY_COOKIE_SECURE=false`
  > in your `.env` (or run the server on HTTPS).
### 2. Investigating with RCA engine (BeCertain)

When an anomaly occurs, use the `/rca` console to trigger an asynchronous analysis job.

* **The Intelligence:** BeCertain analyzes anomaly groups, topology blast radius, and causal links.
* **The Result:** A full report is generated, providing a ranked list of potential root causes.

### 3. Incident Management (InOps)

When an alert fires, it appears on the **Incident Board**.

* **Collaborate:** Add notes and assign teammates.
* **Integrate:** If Jira is configured, a ticket is created automatically.
* **Resolve:** Closing an incident requires a resolution note to feed the internal knowledge base.

---

## 🔐 Part 4: The Administrator’s Handbook

### Security & Hardening

Be Observant is built for high-security environments.

* **Secret Management:** Set `VAULT_ENABLED=true` to fetch credentials from HashiCorp Vault instead of `.env` files.
* **Asymmetric Auth:** In production, use explicit RS256/ES256 keys via `JWT_PRIVATE_KEY`.
* **MFA/TOTP:** Enforce two-factor authentication for all password-based accounts.  
  When using an external identity provider you can disable the local requirement by setting `SKIP_LOCAL_MFA_FOR_EXTERNAL=true` (the default); turn the flag off if you still want the app to prompt for TOTP even when `auth_provider` is not "local".

* **OIDC user role:** Accounts automatically provisioned or linked via SSO will receive the **viewer** role by default. Administrators may elevate the role to `user` or higher after initial login.
* **Audit Logs:** Every action is recorded in an append-only Postgres table protected by DB triggers.

### Administrative Runbooks

| Task | Action |
| --- | --- |
| **Rotate Keys** | Update `JWT_PRIVATE_KEY` and restart the `beobservant` service. |
| **Reset MFA** | If a user is locked out, use: `POST /api/auth/users/{id}/mfa/reset`. |
| **Secure Cookies** | Set `FORCE_SECURE_COOKIES=true` when running behind SSL. |
| **IP Whitelisting** | Restrict access via `WEBHOOK_IP_ALLOWLIST` and `GATEWAY_IP_ALLOWLIST`. |

---

## 🚀 Pre-Production Checklist

Before "going live," ensure these boxes are checked:

* [ ] **Auth:** `JWT_AUTO_GENERATE_KEYS=false` (Use your own PEM keys).
* [ ] **Bootstrap:** `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false` (Admin provisioned manually).
* [ ] **Encryption:** `DATA_ENCRYPTION_KEY` set for MFA secrets.
* [ ] **Networking:** IP allowlists and Rate Limiting (`RATE_LIMIT_BACKEND=redis`) active.
* [ ] **Database:** `DB_AUTO_CREATE_SCHEMA=false` (Migrations managed by CI/CD).
* [ ] **Environment** Ensure to have a look at the all the environment keys needed `.env.example`

---

## ❓ Troubleshooting

* **403 Forbidden?** Check your Tenant ID scope and API Key expiration.
* **No Data in Grafana?** Verify the OTLP gateway health: `curl http://localhost:4319/ready`.
* **RCA Job Hanging?** Ensure the `BeCertain` service is reachable and its service token matches.

