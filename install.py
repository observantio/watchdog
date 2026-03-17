#!/usr/bin/env python3

from __future__ import annotations

import base64
import os
import re
import shutil
import secrets
import string
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence

REPO_URL = "https://github.com/observantio/watchdog.git"
RESOLVER_REPO_URL = "https://github.com/observantio/resolver.git"
NOTIFIER_REPO_URL = "https://github.com/observantio/notifier.git"

PASSWORD_RE = re.compile(r"^[A-Za-z0-9._-]+$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


INTRO_TEXT = """\
Observantio Installer (Experimental)

IMPORTANT:
- Before you use this installer, you are agreeing to the LICENSE and NOTICE terms
  of the repositories and any included dependencies.
- This installer is NOT for production use. It is for experimentation/testing only.
- You are responsible for reviewing the code, licenses, and security posture.

If you do not agree, quit now.
"""


def say(msg: str = "") -> None:
    print(msg)


def hr() -> None:
    print("-" * 60)


def info(msg: str) -> None:
    print(f"==> {msg}")


def ok(msg: str) -> None:
    print(f"✔ {msg}")


def warn(msg: str) -> None:
    print(f"! {msg}")


def err(msg: str) -> None:
    print(f"✖ {msg}")


def require_cmd(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise SystemExit(f"Required command not found: {cmd}")


def run(cmd: Sequence[str], *, cwd: Path | None = None) -> None:
    try:
        subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"Command failed ({e.returncode}): {' '.join(map(str, e.cmd))}") from e


def detect_compose() -> List[str]:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return ["docker", "compose"]
    except Exception:
        pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise SystemExit("Docker Compose not found. Install Docker Desktop or docker compose plugin.")


def ask_line(prompt: str) -> str:
    return input(prompt).strip()


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        ans = ask_line(f"{prompt} {suffix}: ").lower()
        if not ans:
            return default_yes
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        warn("Please answer yes or no.")


def ask_non_empty(prompt: str) -> str:
    while True:
        v = ask_line(f"{prompt}: ")
        if v:
            return v
        warn("Value cannot be empty.")


def ask_email(prompt: str) -> str:
    while True:
        v = ask_non_empty(prompt)
        if EMAIL_RE.fullmatch(v):
            return v
        warn("Invalid email. Example: user@example.com")


def ask_password() -> str:
    import getpass

    while True:
        p1 = getpass.getpass("Admin password (letters/numbers/_/.- only): ")
        p2 = getpass.getpass("Confirm password: ")
        if not p1:
            warn("Password cannot be empty.")
            continue
        if len(p1) < 16:
            warn("Password must be at least 16 characters long.")
            continue
        if p1 != p2:
            warn("Passwords do not match.")
            continue
        if not PASSWORD_RE.fullmatch(p1):
            warn("Password must match: [A-Za-z0-9._-]")
            continue
        return p1


def random_alnum(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def fernet_key() -> str:
    try:
        from cryptography.fernet import Fernet 

        return Fernet.generate_key().decode("ascii")
    except Exception:
        raw = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(raw).decode("ascii")


def clone_repo_if_missing(url: str, dir_path: Path) -> None:
    if (dir_path / ".git").is_dir():
        ok(f"Found repository: {dir_path}")
        return

    if dir_path.exists():
        warn(f"Directory exists and is not a git repo: {dir_path}")
        if ask_yes_no(f"Remove and clone fresh '{dir_path}'?", default_yes=False):
            shutil.rmtree(dir_path)
        else:
            warn(f"Skipping clone for {dir_path}")
            return

    info(f"Cloning {url} -> {dir_path}")
    run(["git", "clone", url, str(dir_path)])
    ok(f"Cloned: {dir_path}")


def upsert_env(file_path: Path, key: str, value: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    key_prefix = f"{key}="

    lines: List[str] = []
    if file_path.exists():
        lines = file_path.read_text(encoding="utf-8").splitlines(True)

    out: List[str] = []
    done = False
    for line in lines:
        if line.startswith(key_prefix):
            out.append(f"{key}={value}\n")
            done = True
        else:
            out.append(line)

    if not done:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key}={value}\n")

    file_path.write_text("".join(out), encoding="utf-8")


def read_env_value(file_path: Path, key: str) -> str | None:
    if not file_path.exists():
        return None
    prefix = f"{key}="
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def upsert_env_if_missing(file_path: Path, key: str, value: str) -> None:
    if read_env_value(file_path, key) is None:
        upsert_env(file_path, key, value)


def choose_api_service_host(workdir: Path, compose_file: Path) -> str:
    try:
        text = compose_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "gateway"

    for candidate in ("watchdog", "gateway", "server", "api"):
        if re.search(rf"(?m)^\s*{re.escape(candidate)}\s*:\s*$", text):
            return candidate

    try:
        compose_cmd = detect_compose()
        p = subprocess.run(
            [*compose_cmd, "-f", str(compose_file), "--project-directory", str(workdir), "config", "--services"],
            cwd=str(workdir),
            check=True,
            capture_output=True,
            text=True,
        )
        services = [s.strip() for s in p.stdout.splitlines() if s.strip()]
        for candidate in ("watchdog", "gateway", "server", "api"):
            if candidate in services:
                return candidate
        if services:
            return services[0]
    except Exception:
        pass

    return "gateway"


def normalize_bool(v: str, default: str) -> str:
    s = v.strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return "true"
    if s in ("false", "0", "no", "n", "off"):
        return "false"
    return default


def normalize_choice(v: str, allowed: Iterable[str], default: str) -> str:
    s = v.strip().lower()
    allowed_l = {a.lower() for a in allowed}
    return s if s in allowed_l else default


def prepare_env(
    env_file: Path,
    mode: str,
    admin_user: str,
    admin_email: str,
    admin_pass: str,
    api_service_host: str,
) -> None:
    if not env_file.exists():
        env_file.write_text("", encoding="utf-8")
        ok(f"Created: {env_file}")

    db_user = "watchdog"
    db_name = "watchdog"
    db_pass = admin_pass

    db_url = f"postgresql://{db_user}:{db_pass}@postgres:5432/{db_name}"
    bn_db_url = f"postgresql://{db_user}:{db_pass}@postgres:5432/watchdog_notified"
    bc_db_url = f"postgresql://{db_user}:{db_pass}@postgres:5432/watchdog_resolver"

    upsert_env(env_file, "APP_ENV", mode)
    upsert_env(env_file, "ENVIRONMENT", mode)

    upsert_env(env_file, "HOST", "0.0.0.0")
    upsert_env(env_file, "PORT", "4319")
    upsert_env(env_file, "LOG_LEVEL", "info")

    upsert_env(env_file, "POSTGRES_USER", db_user)
    upsert_env(env_file, "POSTGRES_PASSWORD", db_pass)
    upsert_env(env_file, "POSTGRES_DB", db_name)

    upsert_env(env_file, "DATABASE_URL", db_url)
    upsert_env(env_file, "NOTIFIER_DATABASE_URL", bn_db_url)
    upsert_env(env_file, "RESOLVER_DATABASE_URL", bc_db_url)
    upsert_env(env_file, "DB_AUTO_CREATE_SCHEMA", "true")

    upsert_env(env_file, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED", "true")
    upsert_env(env_file, "DEFAULT_ADMIN_USERNAME", admin_user)
    upsert_env(env_file, "DEFAULT_ADMIN_PASSWORD", admin_pass)
    upsert_env(env_file, "DEFAULT_ADMIN_EMAIL", admin_email)
    upsert_env_if_missing(env_file, "DEFAULT_ADMIN_TENANT", "default")
    upsert_env_if_missing(env_file, "DEFAULT_ORG_ID", "default")

    auth_provider = normalize_choice(
        read_env_value(env_file, "AUTH_PROVIDER") or "",
        ("local", "oidc", "keycloak"),
        "local",
    )
    upsert_env(env_file, "AUTH_PROVIDER", auth_provider)

    pw_flow = normalize_bool(read_env_value(env_file, "AUTH_PASSWORD_FLOW_ENABLED") or "", "true")
    upsert_env(env_file, "AUTH_PASSWORD_FLOW_ENABLED", pw_flow)

    upsert_env_if_missing(env_file, "JWT_ALGORITHM", "RS256")
    upsert_env_if_missing(env_file, "JWT_EXPIRATION_MINUTES", "1440")
    upsert_env(env_file, "JWT_AUTO_GENERATE_KEYS", "true")

    upsert_env_if_missing(env_file, "INBOUND_WEBHOOK_TOKEN", random_alnum(40))

    otlp_token = read_env_value(env_file, "DEFAULT_OTLP_TOKEN") or random_alnum(40)
    upsert_env(env_file, "DEFAULT_OTLP_TOKEN", otlp_token)
    upsert_env(env_file, "OTLP_INGEST_TOKEN", otlp_token)
    upsert_env(env_file, "OTEL_OTLP_TOKEN", otlp_token)
    upsert_env(env_file, "GATEWAY_STATUS_OTLP_TOKEN", otlp_token)

    upsert_env_if_missing(env_file, "GATEWAY_INTERNAL_SERVICE_TOKEN", random_alnum(40))

    bn_token = read_env_value(env_file, "NOTIFIER_SERVICE_TOKEN") or random_alnum(40)
    upsert_env(env_file, "NOTIFIER_SERVICE_TOKEN", bn_token)
    upsert_env(env_file, "NOTIFIER_EXPECTED_SERVICE_TOKEN", bn_token)
    bn_sign = read_env_value(env_file, "NOTIFIER_CONTEXT_SIGNING_KEY") or random_alnum(48)
    upsert_env(env_file, "NOTIFIER_CONTEXT_SIGNING_KEY", bn_sign)
    upsert_env(env_file, "NOTIFIER_CONTEXT_VERIFY_KEY", bn_sign)
    upsert_env(env_file, "NOTIFIER_URL", "http://notifier:4323")

    bc_token = read_env_value(env_file, "RESOLVER_SERVICE_TOKEN") or random_alnum(40)
    upsert_env(env_file, "RESOLVER_SERVICE_TOKEN", bc_token)
    upsert_env(env_file, "RESOLVER_EXPECTED_SERVICE_TOKEN", bc_token)
    bc_sign = read_env_value(env_file, "RESOLVER_CONTEXT_SIGNING_KEY") or random_alnum(48)
    upsert_env(env_file, "RESOLVER_CONTEXT_SIGNING_KEY", bc_sign)
    upsert_env(env_file, "RESOLVER_CONTEXT_VERIFY_KEY", bc_sign)
    upsert_env(env_file, "RESOLVER_URL", "http://resolver:4322")

    upsert_env(env_file, "GATEWAY_PORT", "4321")
    upsert_env(env_file, "GATEWAY_AUTH_API_URL", f"http://{api_service_host}:4319/api/internal/otlp/validate")
    upsert_env_if_missing(env_file, "GATEWAY_IP_ALLOWLIST", "")
    upsert_env(env_file, "GATEWAY_ALLOWLIST_FAIL_OPEN", "true")
    upsert_env_if_missing(env_file, "GATEWAY_TRUST_PROXY_HEADERS", "false")
    upsert_env(env_file, "RATE_LIMIT_BACKEND", "redis")
    upsert_env(env_file, "RATE_LIMIT_REDIS_URL", "redis://redis:6379/0")

    upsert_env_if_missing(env_file, "DATA_ENCRYPTION_KEY", fernet_key())
    upsert_env(env_file, "CORS_ORIGINS", "http://localhost:5173")

    upsert_env_if_missing(env_file, "GRAFANA_USERNAME", "admin")
    upsert_env(env_file, "GRAFANA_PASSWORD", admin_pass)
    upsert_env(env_file, "GF_SECURITY_ADMIN_PASSWORD", admin_pass)

    ok(f"Updated: {env_file}")


def print_urls() -> None:
    say()
    hr()
    say("Access URLs")
    say("  UI:            http://localhost:5173")
    hr()


def start_stack(workdir: Path, compose_file: Path, compose_cmd: Sequence[str]) -> None:
    if not compose_file.is_file():
        raise SystemExit(f"Compose file not found: {compose_file}")
    info("Starting stack")
    run([*compose_cmd, "-f", str(compose_file), "--project-directory", str(workdir), "up", "-d", "--build"], cwd=workdir)
    ok("Stack started")
    print_urls()


def stop_stack(workdir: Path, compose_file: Path, compose_cmd: Sequence[str]) -> None:
    if not compose_file.is_file():
        raise SystemExit(f"Compose file not found: {compose_file}")
    info("Stopping stack")
    run([*compose_cmd, "-f", str(compose_file), "--project-directory", str(workdir), "down"], cwd=workdir)
    ok("Stack stopped")


def choose_mode_or_quit() -> str:
    while True:
        say()
        hr()
        say("Choose install mode")
        say("  1) dev   (clone repos + build locally)")
        say("  2) stop  (stop an existing compose stack)")
        say("  q) quit")
        hr()
        say()
        choice = ask_line("Select 1, 2, or q: ").lower()
        if choice in ("q", "quit"):
            return "quit"
        if choice == "1":
            return "dev"
        if choice == "2":
            return "stop"
        warn("Invalid selection.")


def setup_dev() -> Path:
    hr()
    say("Dev setup")
    say("This will clone repositories into a directory you choose.")
    hr()

    while True:
        target = Path(ask_non_empty("Clone destination directory (will be created)")).expanduser().resolve()
        if not target.exists():
            break
        warn(f"Target already exists: {target}")
        if ask_yes_no("Override existing directory (delete and recreate)?", default_yes=False):
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            break
        warn("Please choose a different destination.")

    require_cmd("git")
    info("Cloning main repo")
    run(["git", "clone", REPO_URL, str(target)])
    ok(f"Cloned: {target}")

    info("Cloning dependent repos (if missing)")
    clone_repo_if_missing(RESOLVER_REPO_URL, target / "resolver")
    clone_repo_if_missing(NOTIFIER_REPO_URL, target / "Notifier")
    return target


def require_acceptance() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    say(INTRO_TEXT)
    hr()
    if not ask_yes_no("Do you agree to proceed under these terms?", default_yes=False):
        raise SystemExit("Not accepted. Exiting.")


def main() -> int:
    require_acceptance()

    say()
    say("1) Development - clone full repo + dependencies, build locally")
    say()

    require_cmd("docker")
    compose_cmd = detect_compose()

    while True:
        mode = choose_mode_or_quit()
        if mode == "quit":
            return 0

        try:
            if mode == "stop":
                workdir = Path(ask_non_empty("Existing stack directory")).expanduser().resolve()
                compose_name = ask_line("Compose file name [docker-compose.yml]: ") or "docker-compose.yml"
                compose_file = workdir / compose_name
                stop_stack(workdir, compose_file, compose_cmd)
                return 0

            require_cmd("git")
            workdir = setup_dev()
            compose_file = workdir / "docker-compose.yml"

            api_host = choose_api_service_host(workdir, compose_file)
            ok(f"Detected API service host: {api_host}")

            hr()
            say("Bootstrap admin")
            hr()
            admin_user = ask_non_empty("Admin username")
            admin_email = ask_email("Admin email")
            admin_pass = ask_password()

            info("Writing .env")
            prepare_env(workdir / ".env", "dev", admin_user, admin_email, admin_pass, api_host)

            say()
            if ask_yes_no("Start containers now?", default_yes=True):
                start_stack(workdir, compose_file, compose_cmd)
                return 0
            else:
                warn("Setup complete. Start later with:")
                say(f'  cd "{workdir}" && {" ".join(compose_cmd)} -f "{compose_file.name}" up -d --build')
                return 0

        except SystemExit as e:
            err(str(e))
        except Exception as e:
            err(str(e))


if __name__ == "__main__":
    raise SystemExit(main())
