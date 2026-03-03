# 🔭 Be Observant: The Complete User Guide

Welcome to the central command for your observability stack. This guide will walk you through deploying, using, and hardening the **Be Observant** platform.

---

## 🏗️ Part 1: Deployment & Getting Started

### Choosing Your Workflow

Be Observant supports three deployment paths. **Note:** These are intended for **experimentation and homelab use only**. You must manually create configuration files (like EKS config or Docker Swarm) for specific environments.

#### Option A: Quick Mode

Best for rapid setups. This script creates a workspace and clones the services and runs docker compose

```bash
# direct executions
curl -fsSL https://raw.githubusercontent.com/observantio/beobservant/main/install.py | python3

# or using the git clone
git clone https://github.com/observantio/benotified Observantio && cd Observantio
python3 install.py
```

* **Setup:** You will be prompted for a username and a password (**min 16 characters**).
* **Secrets:** This method defaults to password auth. If you require OIDC, manually update the `.env` file after installation. Vault providers are recommended only for cloud or production-simulated hosting.
* **Networking:** Ensure the following ports are available:
    * **5173:** UI Login Page
    * **8080:** Grafana Proxy (Requires UI token; will 401 otherwise)
    * **4139:** Actual Control Plane
    * **4320:** OTel Gateway (The only port needing external exposure)

#### Option B: Manual Mode

Ideal for developers who want to modify the source code.

```bash
# clone the main repo and dependencies
git clone https://github.com/observantio/benotified Observantio && cd Observantio
git clone https://github.com/observantio/becertain BeCertain
git clone https://github.com/observantio/benotified BeNotified

# configure environment
cp .env.example .env
```

You must configure credentials, OIDC, and default tokens. For the AI engine (**BeCertain**), you may need to tweak configurations for your specific hardware to get optimal AI outcomes. Note that you need to set the data encryption key using the below method

**Generate your Fernet encryption key:**

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# set the output as the data encryption key in the .env or in your vault
```

#### Option C: Image Mode

For those who prefer stable, pre-built containers.

1. Define your tags in `.env` (e.g., `BEOBSERVANT_IMAGE=observantio/beobservant:latest`).
2. Download the stable compose file and start:

```bash
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/observantio/beobservant/main/docker-compose.stable.yml
docker compose -f docker-compose.stable.yml up -d
```
---

## 👤 Part 2: The User Experience

### Accessing the Platform

The UI is hosted at `http://localhost:5173`.

* **Authentication Logic:** OIDC is mapped 1:1 to email addresses. If you create a local password account, you can later sign in via OIDC using the same email seamlessly.
* **Bootstrap Admin:** The initial admin account is created locally. It is recommended to use this to "claim" the admin identity via OIDC before disabling local database syncing or ensure that you match the email that you set for the admin so the OIDC can be automatically mapped
* **External IDP:** You can set up a local Keycloak instance instead of relying on the local DB.

### Core Capabilities

| Feature | Your Workflow |
| --- | --- |
| **Grafana Management** | Scoped dashboard and datasource creation via proxy for a swift DX. |
| **Alert Engine** | Integrate with PagerDuty, Email, Teams, Slack, and Webhooks. |
| **Logs & Traces** | Search Loki logs and analyze Tempo traces with deep context. |
| **RCA (BeCertain)** | Run AI-driven jobs to find the "smoking gun" using statistical/deterministic AI. |
| **Incidents (InOps)** | Manage alerts from trigger to Jira resolution via a collaborative board. |
| **RBAC & Groups** | Users inherit permissions from groups. New users default to a "provisioning" role. |
| **Auditing** | Detailed logs of user actions, routes, responses, and timestamps. |
| **KBAC (Key Management)** | Create tenant-specific API keys for isolation (Multi-tenancy). |

### Visibility Scopes
* 👤 **Private:** Visible only to the creator.
* 👥 **Group:** Shared with the team (**Read-only**). Shared alerts notify all group members.
* 🏢 **Tenant:** Global visibility across the org (**Read-only**).

---

## 🛠️ Part 3: Operational Workflows

### 1. Visualizing Telemetry

1. **Generate API Key:** Create a token in the **API Keys** section.
2. **Configure:** Use the generated config file for your OTel agent.
3. **Active Scope:** Switch your active API key in the top nav to filter metrics/traces for that specific environment.
4. **Grafana:** Connect your datasource (that you configured to use the specific API key) and click "Open in Grafana" to view data.

### 2. Investigating with BeCertain (RCA)

Trigger an asynchronous analysis job via the RCA page when an anomaly occurs.

* **How it works:** It analyzes anomaly groups, topology blast radius, and causal links.
* **Requirement:** Ensure you have a large enough dataset to reduce sensitivity and prevent false positives.

### 3. Incident Management (InOps)

Alerts automatically populate the **Incident Board**.

* **Collaboration:** Add notes and assign teammates directly.
* **Knowledge Base:** Closing an incident requires a resolution note, which populates the system's long-term knowledge base.
* **Security:** Channel configurations are encrypted and scoped to the owner unless visibility is explicitly granted to others.

---

## 🔐 Part 4: The Administrator’s Handbook

### Security & Hardening

* **Secret Management:** Enable `VAULT_ENABLED=true` for HashiCorp Vault.
* **Asymmetric Auth:** Use RS256/ES256 keys via `JWT_PRIVATE_KEY` for production-like setups.
* **MFA:** Enforce TOTP for local accounts. Use `SKIP_LOCAL_MFA_FOR_EXTERNAL=true` if using an external IDP.
* **Rate Limiting:** Powered by Redis for user-level protection.
* **CORS:** Restrict origins with `CORS_ORIGINS` and set `CORS_ALLOW_CREDENTIALS` appropriately. In production, list only the hostnames your UI or services use.
* **Proxy & IP controls:**
  * `TRUST_PROXY_HEADERS=true` when running behind a reverse proxy; configure `TRUSTED_PROXY_CIDRS`.
  * Whitelist client IPs with `AUTH_PUBLIC_IP_ALLOWLIST`, `WEBHOOK_IP_ALLOWLIST` and `GATEWAY_IP_ALLOWLIST`.
  * Fail‑open behavior can be toggled with `ALLOWLIST_FAIL_OPEN=false`.
* **Secure Cookies:** `FORCE_SECURE_COOKIES=true` (requires SSL/TLS) and set `SESSION_COOKIE_DOMAIN`/`SESSION_COOKIE_PATH` if needed.
* **Other hardening keys:** Consider `MAX_REQUEST_BYTES`, `MAX_CONCURRENT_REQUESTS`, and `RATE_LIMIT_*` values to cap abuse.

### Administrative Runbooks

| Task | Action |
| --- | --- |
| **Rotate Keys** | Update `JWT_PRIVATE_KEY` and restart the `beobservant` service. |
| **Reset MFA** | `POST /api/auth/users/{id}/mfa/reset`. |
| **Secure Cookies** | Set `FORCE_SECURE_COOKIES=true` (Requires SSL). |
| **CORS** | Adjust `CORS_ORIGINS` and `CORS_ALLOW_CREDENTIALS` for the UI. |
| **Whitelisting** | Use `WEBHOOK_IP_ALLOWLIST`, `AUTH_PUBLIC_IP_ALLOWLIST` and `GATEWAY_IP_ALLOWLIST`. |

> **Note:** If "fail-open" is disabled, the system will throw a 403 error for any IP not explicitly whitelisted.

---

## 🚀 Pre-Production Checklist

* [ ] **Auth:** `JWT_AUTO_GENERATE_KEYS=false` (Use your own PEM keys).
* [ ] **Bootstrap:** `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false`.
* [ ] **Encryption:** `DATA_ENCRYPTION_KEY` set for channel storage and TOTP storage
* [ ] **Networking:** `RATE_LIMIT_BACKEND=redis` is active.
* [ ] **Database:** `DB_AUTO_CREATE_SCHEMA=false` (Use CI/CD migrations).

---

## ❓ Troubleshooting

* **403 Forbidden?** Check your Tenant ID scope or API key expiration or it could be the FAILOPEN gateway which requires the IP listing or CORS setup or Certificate setup.
* **No Data in Grafana?** Check OTLP gateway health: `curl http://localhost:4319/ready` and ensure you are using the correct key and datasource.
* **RCA Job Hanging?** Verify the `BeCertain` service connectivity and token matching.

