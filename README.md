# 🔭 Be Observant

## The Unified Control Plane for Modern Observability.

**Be Observant** is an all-in-one observability platform that eliminates "swivel-chair" monitoring. By unifying metrics, logs, traces, AiOps and intelligent alerting into a single, secure control plane, it allows SREs and Developers to focus on resolving issues rather than stitching data together. We built this to make observability free and while this relies on LGTM stack, you can easily swtich to Victoria metrics and you don't have to pay for enterprise licenses for Grafana as we try to cover as much of the features, to ensure a complete free observability tool.

![Be Observant](assets/beobservant.png)

Built on the industry-standard **LGTM stack** (Loki, Grafana, Tempo, Mimir), Be Observant adds a sophisticated layer of security, multi-tenancy, and AI-driven analysis.

[Report Issue](https://github.com/observantio/beobservant/issues) | [BeNotified](https://github.com/observantio/benotified) | [BeCertain](https://github.com/observantio/becertain)

---

## ✨ Key Features

* **🚀 Unified LGTM Stack:** Native integration with Mimir (Metrics), Loki (Logs), and Tempo (Traces).
* **🧠 AI-Powered Insights:** Includes **BeCertain**, a custom engine for automated Root Cause Analysis (RCA) and predictive forecasting.
* **🔔 Incident Orchestration:** Powered by **BeNotified**, managing complex alert routing and team collaboration.
* **🔐 Enterprise-Grade Security:** RBAC-controlled Grafana access, OIDC/Keycloak support, MFA/TOTP, and asymmetric JWT signing.
* **🔌 OTLP Native:** A high-performance Envoy-based gateway for seamless OpenTelemetry ingestion with token-based isolation.

---

## 🏗 System Architecture

Be Observant acts as the orchestrator for several specialized internal services:

| Component | Role | Logic |
| --- | --- | --- |
| **`beobservant`** | **The Brain** | Core FastAPI REST API handling orchestration and UI. |
| **`benotified`** | **The Messenger** | Manages alerts, channels, and incident collaboration. |
| **`becertain`** | **The Analyst** | AI/ML engine for RCA, anomalies, and forecasting. |
| **`gateway-auth`** | **The Guard** | Validates OTLP tokens for secure data ingestion. |
| **`grafana-proxy`** | **The Window** | Authenticated NGINX proxy for secure visualization. |

---

## 🚀 Quick Start

Get your environment up and running in less than 5 minutes. You can use:

```bash
# direct executions
curl -fsSL https://raw.githubusercontent.com/observantio/beobservant/main/install.py | python3
```

This will run a minimal setup to test out observantio

### 1. Environment Setup

Clone the repository and prepare your configuration:

```bash
cp .env.example .env
```

Generate your unique encryption key and add it to `DATA_ENCRYPTION_KEY` in your `.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Launch the Stack

Choose the mode that fits your workflow:

**Option A: Developer Mode (Local Build)**
*Best if you are contributing to BeCertain or BeNotified.*

```bash
# Clone sibling repos first
git clone https://github.com/observantio/becertain BeCertain
git clone https://github.com/observantio/benotified BeNotified
docker compose up -d --build
```

For explicit permissive development overrides:

```bash
docker compose -f docker-compose.yml -d --build
```

### 3. Access the Platform

Once the containers are healthy, access the following interfaces:

* **User Interface:** [http://localhost:5173](https://www.google.com/search?q=http://localhost:5173)
* **Secure Grafana:** [http://localhost:8080/grafana/](https://www.google.com/search?q=http://localhost:8080/grafana/)
* **Interactive API Docs:** [http://localhost:4319/docs](https://www.google.com/search?q=http://localhost:4319/docs)

---

## 🛠 Developer Workflow

We maintain high code quality standards through automated pre-commit hooks. To set up your local environment:

```bash
pip install pre-commit
pre-commit install
```

**What happens on every commit?**

* **Backend:** Pytest suites run for `server`, `BeCertain`, and `BeNotified`.
* **Frontend:** Linting, unit tests, and build checks via `npm`.
* **Security:** Secret scanning and syntax validation.

---

## 🔒 Security & Compliance

Be Observant is built with a "Security First" mindset:

* **Context-Aware Ingestion:** Every OTLP trace/log is validated via `x-otlp-token` to enforce tenant isolation.
* **Identity Management:** Flexible auth via local Bcrypt/MFA or external OIDC (Keycloak).
* **Auditability:** Immutable DB triggers ensure every configuration change is logged.
* **Hardened Proxy:** Grafana is never exposed directly; all traffic passes through an RBAC-enforced NGINX layer.


## ✅ Production Readiness Checklist

Before deploying to production, ensure you have:

* [ ] Switched `JWT_AUTO_GENERATE_KEYS` to `false` and provided custom PEM keys.
* [ ] Enabled `RATE_LIMIT_BACKEND=redis` for distributed throttling.
* [ ] Configured `WEBHOOK_IP_ALLOWLIST` to restrict incoming traffic.
* [ ] Integrated with **Hashicorp Vault** for secret management (`VAULT_ENABLED=true`).
* [ ] Verify startup DB bootstrap behavior for your environment (`server`, `BeNotified`, `BeCertain` now auto-create schema).
