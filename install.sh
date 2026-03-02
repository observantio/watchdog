#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="https://github.com/observantio/beobservant.git"
BECERTAIN_REPO_URL="https://github.com/observantio/becertain.git"
BENOTIFIED_REPO_URL="https://github.com/observantio/benotified.git"
BEGATEWAY_REPO_URL="https://github.com/observantio/begateway.git"

C_RESET="\033[0m"
C_BOLD="\033[1m"
C_BLUE="\033[34m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"

say() { printf "%b\n" "$*"; }
info() { say "${C_BLUE}==>${C_RESET} $*"; }
ok() { say "${C_GREEN}✔${C_RESET} $*"; }
warn() { say "${C_YELLOW}!${C_RESET} $*"; }
err() { say "${C_RED}✖${C_RESET} $*"; }

die() {
  err "$*"
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: $cmd"
}

ask_yes_no() {
  local prompt="$1"
  local default="${2:-y}"
  local answer
  while true; do
    if [[ "$default" == "y" ]]; then
      read -r -p "$prompt [Y/n]: " answer || true
      answer="${answer:-y}"
    else
      read -r -p "$prompt [y/N]: " answer || true
      answer="${answer:-n}"
    fi

    case "${answer,,}" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) warn "Please answer yes or no." ;;
    esac
  done
}

ask_non_empty() {
  local prompt="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -p "$prompt: " value || true
    if [[ -z "$value" ]]; then
      warn "Value cannot be empty."
    fi
  done
  printf "%s" "$value"
}

ask_password() {
  local p1=""
  local p2=""
  while true; do
    read -r -s -p "Admin password (letters/numbers/_/.- only): " p1 || true
    echo
    read -r -s -p "Confirm password: " p2 || true
    echo

    if [[ -z "$p1" ]]; then
      warn "Password cannot be empty."
      continue
    fi

    if [[ "$p1" != "$p2" ]]; then
      warn "Passwords do not match."
      continue
    fi

    if [[ ! "$p1" =~ ^[A-Za-z0-9._-]+$ ]]; then
      warn "Password must match: [A-Za-z0-9._-]"
      continue
    fi

    printf "%s" "$p1"
    return 0
  done
}

random_alnum() {
  local length="$1"
  tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$length"
}

random_urlsafe_b64() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
  else
    random_alnum 43
  fi
}

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
  else
    die "Docker Compose not found. Install Docker Desktop or docker compose plugin."
  fi
}

clone_repo_if_missing() {
  local url="$1"
  local dir="$2"

  if [[ -d "$dir/.git" ]]; then
    ok "Found existing repository: $dir"
    return 0
  fi

  if [[ -d "$dir" ]]; then
    warn "Directory exists and is not a git repo: $dir"
    if ask_yes_no "Remove and clone fresh $dir?" "n"; then
      rm -rf "$dir"
    else
      warn "Skipping clone for $dir"
      return 0
    fi
  fi

  info "Cloning $url -> $dir"
  git clone "$url" "$dir"
  ok "Cloned $dir"
}

ensure_gateway_dirs() {
  local mode="$1"

  if [[ "$mode" == "dev" ]]; then
    clone_repo_if_missing "$BEGATEWAY_REPO_URL" "BeGateway"
    if [[ ! -e "gateway-auth-service" ]]; then
      info "Creating compatibility symlink: gateway-auth-service -> BeGateway"
      ln -s "BeGateway" gateway-auth-service
    fi
  else
    if [[ ! -d "gateway-auth-service/.git" ]]; then
      if [[ -d "BeGateway/.git" ]]; then
        info "Using existing BeGateway and creating symlink gateway-auth-service -> BeGateway"
        ln -sfn "BeGateway" gateway-auth-service
      else
        clone_repo_if_missing "$BEGATEWAY_REPO_URL" "gateway-auth-service"
      fi
    fi
  fi
}

upsert_env() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp
  tmp="$(mktemp)"

  awk -v key="$key" -v value="$value" '
    BEGIN { done = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      done = 1
      next
    }
    { print }
    END {
      if (done == 0) {
        print key "=" value
      }
    }
  ' "$file" > "$tmp"

  mv "$tmp" "$file"
}

prepare_env() {
  local env_file="$1"
  local mode="$2"
  local admin_user="$3"
  local admin_pass="$4"

  if [[ ! -f "$env_file" ]]; then
    if [[ -f ".env.example" ]]; then
      cp .env.example "$env_file"
      ok "Created $env_file from .env.example"
    else
      : > "$env_file"
      ok "Created empty $env_file"
    fi
  fi

  local db_user="beobservant"
  local db_name="beobservant"
  local db_pass="$admin_pass"
  local admin_email="${admin_user}@example.com"

  local db_url="postgresql://${db_user}:${db_pass}@postgres:5432/${db_name}"
  local bn_db_url="postgresql://${db_user}:${db_pass}@postgres:5432/beobservant_notified"
  local bc_db_url="postgresql://${db_user}:${db_pass}@postgres:5432/beobservant_becertain"

  local webhook_token
  local otlp_token
  local gw_token
  local ben_token
  local ben_ctx_key
  local bc_token
  local bc_ctx_key
  local data_key

  webhook_token="$(random_alnum 40)"
  otlp_token="$(random_alnum 40)"
  gw_token="$(random_alnum 40)"
  ben_token="$(random_alnum 40)"
  ben_ctx_key="$(random_alnum 48)"
  bc_token="$(random_alnum 40)"
  bc_ctx_key="$(random_alnum 48)"
  data_key="$(random_urlsafe_b64)"

  upsert_env "$env_file" "APP_ENV" "$mode"
  upsert_env "$env_file" "ENVIRONMENT" "$mode"
  upsert_env "$env_file" "POSTGRES_USER" "$db_user"
  upsert_env "$env_file" "POSTGRES_PASSWORD" "$db_pass"
  upsert_env "$env_file" "POSTGRES_DB" "$db_name"
  upsert_env "$env_file" "DATABASE_URL" "$db_url"
  upsert_env "$env_file" "BENOTIFIED_DATABASE_URL" "$bn_db_url"
  upsert_env "$env_file" "BECERTAIN_DATABASE_URL" "$bc_db_url"

  upsert_env "$env_file" "DEFAULT_ADMIN_BOOTSTRAP_ENABLED" "true"
  upsert_env "$env_file" "DEFAULT_ADMIN_USERNAME" "$admin_user"
  upsert_env "$env_file" "DEFAULT_ADMIN_PASSWORD" "$admin_pass"
  upsert_env "$env_file" "DEFAULT_ADMIN_EMAIL" "$admin_email"

  upsert_env "$env_file" "AUTH_PROVIDER" "local"
  upsert_env "$env_file" "AUTH_PASSWORD_FLOW_ENABLED" "true"

  upsert_env "$env_file" "INBOUND_WEBHOOK_TOKEN" "$webhook_token"
  upsert_env "$env_file" "DEFAULT_OTLP_TOKEN" "$otlp_token"
  upsert_env "$env_file" "OTLP_INGEST_TOKEN" "$otlp_token"
  upsert_env "$env_file" "OTEL_OTLP_TOKEN" "$otlp_token"
  upsert_env "$env_file" "GATEWAY_STATUS_OTLP_TOKEN" "$otlp_token"

  upsert_env "$env_file" "GATEWAY_INTERNAL_SERVICE_TOKEN" "$gw_token"

  upsert_env "$env_file" "BENOTIFIED_SERVICE_TOKEN" "$ben_token"
  upsert_env "$env_file" "BENOTIFIED_EXPECTED_SERVICE_TOKEN" "$ben_token"
  upsert_env "$env_file" "BENOTIFIED_CONTEXT_SIGNING_KEY" "$ben_ctx_key"
  upsert_env "$env_file" "BENOTIFIED_CONTEXT_VERIFY_KEY" "$ben_ctx_key"

  upsert_env "$env_file" "BECERTAIN_SERVICE_TOKEN" "$bc_token"
  upsert_env "$env_file" "BECERTAIN_EXPECTED_SERVICE_TOKEN" "$bc_token"
  upsert_env "$env_file" "BECERTAIN_CONTEXT_SIGNING_KEY" "$bc_ctx_key"
  upsert_env "$env_file" "BECERTAIN_CONTEXT_VERIFY_KEY" "$bc_ctx_key"

  upsert_env "$env_file" "GRAFANA_USERNAME" "admin"
  upsert_env "$env_file" "GRAFANA_PASSWORD" "$admin_pass"
  upsert_env "$env_file" "GF_SECURITY_ADMIN_PASSWORD" "$admin_pass"

  upsert_env "$env_file" "DATA_ENCRYPTION_KEY" "$data_key"
  upsert_env "$env_file" "DB_AUTO_CREATE_SCHEMA" "true"

  ok "Updated $env_file with bootstrap values"
}

start_stack() {
  local mode="$1"
  local project_root="$2"
  local compose_file

  if [[ "$mode" == "dev" ]]; then
    compose_file="$project_root/docker-compose.yml"
  else
    compose_file="$project_root/deployments/compose/docker-compose.stable.yml"
  fi

  [[ -f "$compose_file" ]] || die "Compose file not found: $compose_file"

  info "Starting stack in ${C_BOLD}$mode${C_RESET} mode"
  "${COMPOSE_CMD[@]}" --project-directory "$project_root" -f "$compose_file" up -d --build
  ok "Stack started successfully"

  say
  say "${C_BOLD}Access URLs${C_RESET}"
  say "- UI: http://localhost:5173"
  say "- API docs: http://localhost:4319/docs"
  say "- Grafana proxy: http://localhost:8080/grafana/"
}

main() {
  clear || true
  say "${C_BOLD}BeObservant Interactive Installer${C_RESET}"
  say

  require_cmd git
  require_cmd docker
  detect_compose

  local project_root="$SCRIPT_DIR"
  if ask_yes_no "Clone a fresh BeObservant repository first?" "n"; then
    local target_dir
    target_dir="$(ask_non_empty "Clone destination directory")"

    if [[ -e "$target_dir" ]]; then
      die "Target already exists: $target_dir"
    fi

    info "Cloning main repository"
    git clone "$REPO_URL" "$target_dir"
    project_root="$target_dir"
    ok "Main repository cloned to $project_root"
  fi

  cd "$project_root"

  local mode=""
  while [[ -z "$mode" ]]; do
    say
    say "Choose install mode:"
    say "1) dev  (build local services)"
    say "2) demo (use stable images)"
    read -r -p "Enter 1 or 2: " mode_input || true
    case "$mode_input" in
      1) mode="dev" ;;
      2) mode="demo" ;;
      *) warn "Invalid selection." ;;
    esac
  done

  local admin_user
  local admin_pass
  say
  admin_user="$(ask_non_empty "Admin username")"
  admin_pass="$(ask_password)"

  info "Preparing repositories for $mode mode"
  if [[ "$mode" == "dev" ]]; then
    clone_repo_if_missing "$BECERTAIN_REPO_URL" "BeCertain"
    clone_repo_if_missing "$BENOTIFIED_REPO_URL" "BeNotified"
  fi
  ensure_gateway_dirs "$mode"

  info "Preparing environment file"
  prepare_env "$project_root/.env" "$mode" "$admin_user" "$admin_pass"

  if ask_yes_no "Start containers now?" "y"; then
    start_stack "$mode" "$project_root"
  else
    warn "Setup completed. Start manually with docker compose when ready."
  fi
}

main "$@"
