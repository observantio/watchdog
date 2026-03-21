# Deployment Guide

This guide explains how to deploy Observantio from the release tarball, what to open on the host firewall/security group, and what to harden after first boot.

## Prerequisites

- Linux host with Docker Engine installed
- Docker Compose plugin (`docker compose`) or `docker-compose`
- Internet egress from host to pull container images from `ghcr.io`

## Install From Release Tarball

Quick install script:

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-v0.0.1}"
ARCH="${2:-multi}" # amd64 | arm64 | multi
REPO="observantio/watchdog"
ASSET="observantio-${VERSION}-linux-${ARCH}.tar.gz"
URL="https://github.com/${REPO}/releases/download/${VERSION}/${ASSET}"

mkdir -p "$HOME/observantio" && cd "$HOME/observantio"

if command -v curl >/dev/null 2>&1; then
  curl -fL -o "${ASSET}" "${URL}"
elif command -v wget >/dev/null 2>&1; then
  wget -O "${ASSET}" "${URL}"
else
  echo "Need curl or wget to download release asset." >&2
  exit 1
fi

tar -xzf "${ASSET}"
cd "observantio-${VERSION}-linux-${ARCH}"
chmod +x install.sh restart.sh uninstall.sh
./install.sh
```

Manual install steps:

1. Download the release asset, for example:
   `observantio-vX.Y.Z-linux-amd64.tar.gz`
2. Extract it:
   `tar -xzf observantio-vX.Y.Z-linux-amd64.tar.gz`
3. Enter the extracted directory:
   `cd observantio-vX.Y.Z-linux-amd64`
4. Run installer:
   `chmod +x install.sh && ./install.sh`

The installer will:
- Create `.env` from `.env.example` if missing
- Randomize important secrets if defaults/placeholders are detected
- Ask for UI host and admin bootstrap values
- Pull images and optionally start the stack

## Day-2 Operations

- Restart:
  `./restart.sh`
- Stop/uninstall:
  `./uninstall.sh`
- Uninstall and remove named volumes:
  `./uninstall.sh --purge`

## Required Network Ports

Open only what you actually need.

- `5173/tcp` UI
- `8080/tcp` Grafana proxy
- `4320/tcp` OTLP gateway ingest
- `4319/tcp` Watchdog API direct access (recommended to keep private and front with reverse proxy instead)

## Recommended Public Exposure Model

For internet-facing deployments, prefer exposing only `80/443` through a reverse proxy and routing:

- `/` to UI
- `/api` to Watchdog
- `/grafana` to Grafana proxy

This removes most cross-origin complexity and lets you keep `4319` private.

## Post-Install Hardening Checklist

Apply these before production usage.

1. Set `APP_ENV=production` and `ENVIRONMENT=production`.
2. Set `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false` after initial admin setup.
3. Keep strong, unique values for all service tokens and signing keys.
4. Set `ALLOWLIST_FAIL_OPEN=false` and `GATEWAY_ALLOWLIST_FAIL_OPEN=false`.
5. Configure concrete allowlists instead of empty values:
   `AUTH_PUBLIC_IP_ALLOWLIST`, `GATEWAY_IP_ALLOWLIST`, `GRAFANA_PROXY_IP_ALLOWLIST`.
6. Keep `GF_AUTH_PROXY_WHITELIST` correct for your proxy path.
7. Use TLS termination at the edge and set secure cookie behavior (`FORCE_SECURE_COOKIES=true` when applicable).
8. Rotate bootstrap/default credentials and remove any placeholder values.
9. Use persistent backups for PostgreSQL and observability data volumes.

## Local Passwords vs OIDC

You can run with local auth, but for production teams OIDC is recommended.

Local auth:
- Simpler bootstrap
- More operational burden (password lifecycle, reset, MFA policy management)

OIDC:
- Centralized identity, MFA, deprovisioning
- Better audit/compliance posture

If moving to OIDC later:
1. Configure OIDC settings in `.env` (`AUTH_PROVIDER`, issuer, client id/secret, scopes, JWKS).
2. Validate login flow with a test account.
3. Keep at least one break-glass admin path documented.

## Verification

After startup, check:

- `docker compose -f docker-compose.prod.yml ps`
- `curl http://localhost:4319/health`

If host port `4319` is private, run the health check on the host itself or from inside the Docker network.

## Grafana Proxy Auth Note

If `GRAFANA_PROXY_IP_ALLOWLIST` or `GF_AUTH_PROXY_WHITELIST` is empty/incorrect, Grafana proxy auth will not be trusted and users will see the native Grafana login page.

Minimum recommended values:

- `GRAFANA_PROXY_IP_ALLOWLIST=127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`
- `GF_AUTH_PROXY_WHITELIST=127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`

Also ensure users access Grafana through the proxy path (`/grafana` on port `8080`) rather than direct port `3000`.
