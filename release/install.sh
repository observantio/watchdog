#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "docker compose (plugin) or docker-compose is required." >&2
  exit 1
fi

if [[ ! -f ".env" ]]; then
  cp .env.example .env
fi

randomized_keys=()

set_env_key() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -F= -v k="$key" -v v="$value" '
    BEGIN { replaced=0 }
    $1 == k { print k "=" v; replaced=1; next }
    { print $0 }
    END { if (!replaced) print k "=" v }
  ' .env > "$tmp_file"
  mv "$tmp_file" .env
}

get_env_key() {
  local key="$1"
  awk -F= -v k="$key" '$1 == k { print substr($0, index($0, "=") + 1); exit }' .env
}

random_hex() {
  local length="$1"
  local bytes=$(( (length + 1) / 2 ))
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "${bytes}" | cut -c1-"${length}"
  else
    od -An -N"${bytes}" -tx1 /dev/urandom | tr -d ' \n' | cut -c1-"${length}"
  fi
}

random_fernet_key() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import base64
import os
print(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
PY
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr -d '\n' | tr '+/' '-_'
  else
    head -c 32 /dev/urandom | base64 | tr -d '\n' | tr '+/' '-_'
  fi
}

is_insecure_value() {
  local current="$1"
  local known_default="${2:-}"
  [[ -z "${current}" || "${current}" == replace_with_* || "${current}" == changeme* || "${current}" == "${known_default}" ]]
}

looks_like_pem_private_key() {
  local value="$1"
  [[ "${value}" == *"-----BEGIN PRIVATE KEY-----"* || "${value}" == *"-----BEGIN RSA PRIVATE KEY-----"* || "${value}" == *"-----BEGIN EC PRIVATE KEY-----"* ]]
}

looks_like_pem_public_key() {
  local value="$1"
  [[ "${value}" == *"-----BEGIN PUBLIC KEY-----"* || "${value}" == *"-----BEGIN RSA PUBLIC KEY-----"* ]]
}

set_secret_if_insecure() {
  local key="$1"
  local known_default="$2"
  local new_value="$3"
  local current
  current="$(get_env_key "${key}")"
  if is_insecure_value "${current}" "${known_default}"; then
    set_env_key "${key}" "${new_value}"
    randomized_keys+=("${key}")
  fi
}

old_postgres_password="$(get_env_key POSTGRES_PASSWORD)"
new_postgres_password="${old_postgres_password}"
if is_insecure_value "${old_postgres_password}" "Y7vK2mP9sQ4tN8wX3zR6cD1fH5jL0bG"; then
  new_postgres_password="$(random_hex 48)"
  set_env_key "POSTGRES_PASSWORD" "${new_postgres_password}"
  randomized_keys+=("POSTGRES_PASSWORD")
fi

if [[ "${new_postgres_password}" != "${old_postgres_password}" ]]; then
  for db_key in DATABASE_URL NOTIFIER_DATABASE_URL RESOLVER_DATABASE_URL; do
    current_db_url="$(get_env_key "${db_key}")"
    if [[ -n "${current_db_url}" && "${current_db_url}" == *"${old_postgres_password}"* ]]; then
      set_env_key "${db_key}" "${current_db_url//${old_postgres_password}/${new_postgres_password}}"
      randomized_keys+=("${db_key}")
    fi
  done
fi

set_secret_if_insecure "JWT_SECRET_KEY" "S3cr3tK3yF0rJWTs&s3cur3R4nd0mStr1ngG3n3r4t0r" "$(random_hex 64)"

jwt_algorithm="$(get_env_key JWT_ALGORITHM)"
jwt_auto_generate_keys="$(get_env_key JWT_AUTO_GENERATE_KEYS)"
jwt_private_key="$(get_env_key JWT_PRIVATE_KEY)"
jwt_public_key="$(get_env_key JWT_PUBLIC_KEY)"

if [[ "${jwt_algorithm}" == "RS256" || "${jwt_algorithm}" == "ES256" ]]; then
  if [[ "${jwt_auto_generate_keys,,}" == "true" ]]; then
    if [[ -n "${jwt_private_key}" ]] && ! looks_like_pem_private_key "${jwt_private_key}"; then
      set_env_key "JWT_PRIVATE_KEY" ""
      randomized_keys+=("JWT_PRIVATE_KEY")
    fi
    if [[ -n "${jwt_public_key}" ]] && ! looks_like_pem_public_key "${jwt_public_key}"; then
      set_env_key "JWT_PUBLIC_KEY" ""
      randomized_keys+=("JWT_PUBLIC_KEY")
    fi
  fi
fi
old_default_otlp_token="$(get_env_key DEFAULT_OTLP_TOKEN)"
set_secret_if_insecure "DEFAULT_OTLP_TOKEN" "otlp_4fK9qL2mP8rS3tV6wX1yZ7" "otlp_$(random_hex 28)"
default_otlp_token="$(get_env_key DEFAULT_OTLP_TOKEN)"

default_org_id="$(get_env_key DEFAULT_ORG_ID)"
mimir_tenant_id="$(get_env_key MIMIR_TENANT_ID)"
if is_insecure_value "${mimir_tenant_id}" "observantio" || [[ -z "${mimir_tenant_id}" ]]; then
  set_env_key "MIMIR_TENANT_ID" "${default_org_id:-default}"
fi

otel_otlp_token="$(get_env_key OTEL_OTLP_TOKEN)"
if is_insecure_value "${otel_otlp_token}" "otel_5qW1mN7rT3xY9pK2vL6" || [[ "${otel_otlp_token}" == "${old_default_otlp_token}" ]]; then
  set_env_key "OTEL_OTLP_TOKEN" "${default_otlp_token}"
  randomized_keys+=("OTEL_OTLP_TOKEN")
fi

set_secret_if_insecure "INBOUND_WEBHOOK_TOKEN" "whk_2nR8tV4pQ1xY6mK3zL7" "whk_$(random_hex 28)"
set_secret_if_insecure "OTLP_INGEST_TOKEN" "otlp_ingest_9xR3mT7qP2vN6kY1zL5" "otlp_ingest_$(random_hex 28)"
set_secret_if_insecure "AGENT_HEARTBEAT_TOKEN" "heartbeat_7mQ2rP9xT4vN1kY6zL3" "heartbeat_$(random_hex 28)"
set_secret_if_insecure "GATEWAY_STATUS_OTLP_TOKEN" "status_7vN2qP8mR4tX1yZ6kL3" "status_$(random_hex 28)"
set_secret_if_insecure "GATEWAY_INTERNAL_SERVICE_TOKEN" "svc_gateway_8mQ3tP7rN2vW6xY1kL4" "svc_gateway_$(random_hex 28)"
set_secret_if_insecure "DATA_ENCRYPTION_KEY" "YXV0b19nZW5lcmF0ZV9pbl9pbnN0YWxsZXJfMzJfYnl0ZXM=" "$(random_fernet_key)"

notifier_service_token="$(get_env_key NOTIFIER_SERVICE_TOKEN)"
notifier_expected_service_token="$(get_env_key NOTIFIER_EXPECTED_SERVICE_TOKEN)"
if is_insecure_value "${notifier_service_token}" "svc_notifier_9kLm2pQ7rS4tV8xY1zC5" || is_insecure_value "${notifier_expected_service_token}" "svc_notifier_9kLm2pQ7rS4tV8xY1zC5"; then
  new_notifier_service_token="svc_notifier_$(random_hex 28)"
  set_env_key "NOTIFIER_SERVICE_TOKEN" "${new_notifier_service_token}"
  set_env_key "NOTIFIER_EXPECTED_SERVICE_TOKEN" "${new_notifier_service_token}"
  randomized_keys+=("NOTIFIER_SERVICE_TOKEN" "NOTIFIER_EXPECTED_SERVICE_TOKEN")
fi

notifier_ctx_signing="$(get_env_key NOTIFIER_CONTEXT_SIGNING_KEY)"
notifier_ctx_verify="$(get_env_key NOTIFIER_CONTEXT_VERIFY_KEY)"
if is_insecure_value "${notifier_ctx_signing}" "ctx_notifier_Z4pN8wR2yV6mQ1tX7kL9" || is_insecure_value "${notifier_ctx_verify}" "ctx_notifier_Z4pN8wR2yV6mQ1tX7kL9"; then
  new_notifier_ctx="ctx_notifier_$(random_hex 32)"
  set_env_key "NOTIFIER_CONTEXT_SIGNING_KEY" "${new_notifier_ctx}"
  set_env_key "NOTIFIER_CONTEXT_VERIFY_KEY" "${new_notifier_ctx}"
  randomized_keys+=("NOTIFIER_CONTEXT_SIGNING_KEY" "NOTIFIER_CONTEXT_VERIFY_KEY")
fi

resolver_service_token="$(get_env_key RESOLVER_SERVICE_TOKEN)"
resolver_expected_service_token="$(get_env_key RESOLVER_EXPECTED_SERVICE_TOKEN)"
if is_insecure_value "${resolver_service_token}" "svc_resolver_3xT7mQ2pL9rV4wY8kN1" || is_insecure_value "${resolver_expected_service_token}" "svc_resolver_3xT7mQ2pL9rV4wY8kN1"; then
  new_resolver_service_token="svc_resolver_$(random_hex 28)"
  set_env_key "RESOLVER_SERVICE_TOKEN" "${new_resolver_service_token}"
  set_env_key "RESOLVER_EXPECTED_SERVICE_TOKEN" "${new_resolver_service_token}"
  randomized_keys+=("RESOLVER_SERVICE_TOKEN" "RESOLVER_EXPECTED_SERVICE_TOKEN")
fi

resolver_ctx_signing="$(get_env_key RESOLVER_CONTEXT_SIGNING_KEY)"
resolver_ctx_verify="$(get_env_key RESOLVER_CONTEXT_VERIFY_KEY)"
if is_insecure_value "${resolver_ctx_signing}" "ctx_resolver_M2vR8tQ4yK7nP1wX6zL3" || is_insecure_value "${resolver_ctx_verify}" "ctx_resolver_M2vR8tQ4yK7nP1wX6zL3"; then
  new_resolver_ctx="ctx_resolver_$(random_hex 32)"
  set_env_key "RESOLVER_CONTEXT_SIGNING_KEY" "${new_resolver_ctx}"
  set_env_key "RESOLVER_CONTEXT_VERIFY_KEY" "${new_resolver_ctx}"
  randomized_keys+=("RESOLVER_CONTEXT_SIGNING_KEY" "RESOLVER_CONTEXT_VERIFY_KEY")
fi

grafana_password="$(get_env_key GRAFANA_PASSWORD)"
gf_security_admin_password="$(get_env_key GF_SECURITY_ADMIN_PASSWORD)"
if is_insecure_value "${grafana_password}" "GrafanaR4nD0m21" || is_insecure_value "${gf_security_admin_password}" "GrafanaR4nD0m21" || [[ "${grafana_password}" == "Grafana!R4nD0m#21" ]] || [[ "${gf_security_admin_password}" == "Grafana!R4nD0m#21" ]]; then
  new_grafana_password="Grafana!$(random_hex 16)"
  set_env_key "GRAFANA_PASSWORD" "${new_grafana_password}"
  set_env_key "GF_SECURITY_ADMIN_PASSWORD" "${new_grafana_password}"
  randomized_keys+=("GRAFANA_PASSWORD" "GF_SECURITY_ADMIN_PASSWORD")
fi

grafana_username="$(get_env_key GRAFANA_USERNAME)"
if is_insecure_value "${grafana_username}" ""; then
  grafana_username="admin"
  set_env_key "GRAFANA_USERNAME" "${grafana_username}"
  randomized_keys+=("GRAFANA_USERNAME")
fi
set_env_key "GF_SECURITY_ADMIN_USER" "${grafana_username}"

app_env="$(get_env_key APP_ENV)"
if [[ -z "${app_env}" ]]; then
  app_env="$(get_env_key ENVIRONMENT)"
fi
app_env="${app_env,,}"
is_production_env=false
if [[ "${app_env}" == "production" || "${app_env}" == "prod" ]]; then
  is_production_env=true
fi

auth_public_ip_allowlist="$(get_env_key AUTH_PUBLIC_IP_ALLOWLIST)"
if [[ "${is_production_env}" == "false" && -z "${auth_public_ip_allowlist}" ]]; then
  set_env_key "ALLOWLIST_FAIL_OPEN" "true"
fi

gateway_ip_allowlist="$(get_env_key GATEWAY_IP_ALLOWLIST)"
if [[ "${is_production_env}" == "false" && -z "${gateway_ip_allowlist}" ]]; then
  set_env_key "GATEWAY_ALLOWLIST_FAIL_OPEN" "true"
fi

grafana_proxy_ip_allowlist="$(get_env_key GRAFANA_PROXY_IP_ALLOWLIST)"
if [[ -z "${grafana_proxy_ip_allowlist}" ]]; then
  set_env_key "GRAFANA_PROXY_IP_ALLOWLIST" "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
fi

grafana_auth_proxy_whitelist="$(get_env_key GF_AUTH_PROXY_WHITELIST)"
if [[ -z "${grafana_auth_proxy_whitelist}" || "${grafana_auth_proxy_whitelist}" == "127.0.0.1,::1" ]]; then
  set_env_key "GF_AUTH_PROXY_WHITELIST" "127.0.0.1,::1,172.16.0.0/12"
fi

default_admin_username="$(get_env_key DEFAULT_ADMIN_USERNAME)"
default_admin_password="$(get_env_key DEFAULT_ADMIN_PASSWORD)"
default_admin_email="$(get_env_key DEFAULT_ADMIN_EMAIL)"
default_cors_origins="$(get_env_key CORS_ORIGINS)"

default_ui_host="localhost"
if [[ -n "${default_cors_origins}" ]]; then
  first_origin="${default_cors_origins%%,*}"
  first_origin="${first_origin#http://}"
  first_origin="${first_origin#https://}"
  first_origin="${first_origin%%/*}"
  first_origin="${first_origin%%:*}"
  if [[ -n "${first_origin}" ]]; then
    default_ui_host="${first_origin}"
  fi
fi

read -r -p "UI host IP or DNS [${default_ui_host}]: " input_ui_host
ui_host="${input_ui_host:-${default_ui_host}}"
ui_origin="http://${ui_host}:5173"
api_base_url="http://${ui_host}:4319"
otlp_gateway_url="http://${ui_host}:4320"
grafana_root_url="http://${ui_host}:8080/grafana/"
app_login_url="${ui_origin}/login"

read -r -p "Admin username [${default_admin_username:-admin}]: " input_admin_username
read -r -s -p "Admin password [hidden, press Enter to keep default]: " input_admin_password
echo
read -r -p "Admin email [${default_admin_email:-admin@observantio.local}]: " input_admin_email

admin_username="${input_admin_username:-${default_admin_username:-admin}}"
admin_password="${input_admin_password:-${default_admin_password:-Obsrv!AdminR4nD0m}}"
admin_email="${input_admin_email:-${default_admin_email:-admin@observantio.local}}"

set_env_key "DEFAULT_ADMIN_USERNAME" "$admin_username"
set_env_key "DEFAULT_ADMIN_PASSWORD" "$admin_password"
set_env_key "DEFAULT_ADMIN_EMAIL" "$admin_email"
set_env_key "CORS_ORIGINS" "${ui_origin}"
set_env_key "VITE_API_URL" "${api_base_url}"
set_env_key "VITE_OTLP_GATEWAY_HOST" "${otlp_gateway_url}"
set_env_key "GF_SERVER_ROOT_URL" "${grafana_root_url}"
set_env_key "APP_LOGIN_URL" "${app_login_url}"

echo " "
echo "Configured UI host settings:"
echo " - CORS_ORIGINS=${ui_origin}"
echo " - VITE_OTLP_GATEWAY_HOST=${otlp_gateway_url}"
echo " - GF_SERVER_ROOT_URL=${grafana_root_url}"
echo " - APP_LOGIN_URL=${app_login_url}"

echo " "
if [[ "${#randomized_keys[@]}" -gt 0 ]]; then
  echo "Randomized secure defaults for:"
  printf ' - %s\n' "${randomized_keys[@]}"
fi

release_arch="$(get_env_key RELEASE_ARCH)"
if [[ -n "${release_arch}" && "${release_arch}" != "multi" ]]; then
  host_arch="$(uname -m)"
  host_arch="${host_arch/x86_64/amd64}"
  host_arch="${host_arch/aarch64/arm64}"
  if [[ "${host_arch}" != "${release_arch}" ]]; then
    echo "Warning: bundle architecture is ${release_arch} but host appears to be ${host_arch}." >&2
  fi
fi
echo ""
echo "Pulling images for OBSERVANTIO_BUNDLE_VERSION=$(get_env_key OBSERVANTIO_BUNDLE_VERSION)..."
"${COMPOSE_CMD[@]}" -f docker-compose.prod.yml pull
echo ""
read -r -p "Start services now? [Y/n]: " start_now
echo " "
if [[ -z "${start_now}" || "${start_now}" =~ ^[Yy]$ ]]; then
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml up -d
  echo " "
  echo "Observantio is up. This is not an hardened setup, please update the .env file with secure values and consider additional hardening steps for production use."
  if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:4319/health')"; then
      echo "Warning: Watchdog health probe failed at http://localhost:4319/health"
      echo "Check container status with: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml ps"
      echo "Inspect logs with: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml logs watchdog"
    fi
  fi
else
  echo "Skipped start. Run: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml up -d"
fi
echo ""
