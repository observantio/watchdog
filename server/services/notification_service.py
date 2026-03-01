from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

from config import config
from services.common.http_client import create_async_client

try:
    import aiosmtplib
except Exception:
    aiosmtplib = None

logger = logging.getLogger(__name__)

BOOL_TRUE = {"1", "true", "yes", "on"}

def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in BOOL_TRUE
    return False


def _first_secret(*keys: str) -> Optional[str]:
    for key in keys:
        v = config.get_secret(key)
        if v:
            return v
    return None


def _is_enabled(*keys: str) -> bool:
    v = _first_secret(*keys)
    return str(v or "false").strip().lower() in BOOL_TRUE


def _smtp_config(*prefixes: str) -> dict:
    def get(*suffixes: str) -> Optional[str]:
        return _first_secret(*(f"{p}_{s}" for p in prefixes for s in suffixes))

    try:
        port = int(get("SMTP_PORT") or "587")
    except ValueError:
        port = 587

    return {
        "hostname": (get("SMTP_HOST") or "").strip(),
        "port": port,
        "username": get("SMTP_USERNAME"),
        "password": get("SMTP_PASSWORD"),
        "from_addr": get("FROM") or config.DEFAULT_ADMIN_EMAIL,
        "start_tls": _as_bool(get("SMTP_STARTTLS") or "true"),
        "use_tls": _as_bool(get("SMTP_USE_SSL") or "false"),
    }


class NotificationService:
    def __init__(self) -> None:
        self.timeout = float(config.DEFAULT_TIMEOUT)
        self._client = create_async_client(self.timeout)

    async def _send_smtp(self, *, message: EmailMessage, cfg: dict) -> None:
        if aiosmtplib is None:
            raise RuntimeError("aiosmtplib is unavailable")
        await aiosmtplib.send(
            message,
            hostname=cfg["hostname"],
            port=cfg["port"],
            username=cfg["username"],
            password=cfg["password"],
            start_tls=cfg["start_tls"],
            use_tls=cfg["use_tls"],
            timeout=self.timeout,
        )

    async def _dispatch(self, cfg: dict, msg: EmailMessage, recipient: str) -> bool:
        try:
            await self._send_smtp(message=msg, cfg=cfg)
            return True
        except Exception as exc:
            logger.warning("Failed to send email to %s: %s", recipient, exc)
            return False

    def _build_message(self, *, subject: str, cfg: dict, recipient: str, body: str) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["from_addr"]
        msg["To"] = recipient
        msg.set_content(body)
        return msg

    async def send_incident_assignment_email(
        self,
        recipient_email: str,
        incident_title: str,
        incident_status: str,
        incident_severity: str,
        actor: str,
    ) -> bool:
        if not _is_enabled("INCIDENT_ASSIGNMENT_EMAIL_ENABLED"):
            return False
        cfg = _smtp_config("INCIDENT_ASSIGNMENT")
        if not cfg["hostname"]:
            logger.info("Incident assignment email skipped: SMTP host not set")
            return False
        msg = self._build_message(
            subject=f"[Incident Assigned] {incident_title}",
            cfg=cfg,
            recipient=recipient_email,
            body="\n".join([
                "You have been assigned an incident in Be Observant.", "",
                f"Title: {incident_title}",
                f"Status: {incident_status}",
                f"Severity: {incident_severity}",
                f"Updated by: {actor}",
                f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
            ]),
        )
        return await self._dispatch(cfg, msg, recipient_email)

    async def send_user_welcome_email(
        self,
        recipient_email: str,
        username: str,
        full_name: Optional[str] = None,
        login_url: Optional[str] = None,
    ) -> bool:
        if not _is_enabled("USER_WELCOME_EMAIL_ENABLED"):
            return False
        cfg = _smtp_config("USER_WELCOME")
        if not cfg["hostname"]:
            logger.info("User welcome email skipped: SMTP host not set")
            return False
        app_login_url = (login_url or config.get_secret("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""
        msg = self._build_message(
            subject="Welcome to Be Observant",
            cfg=cfg,
            recipient=recipient_email,
            body=(
                f"Hello {full_name or username},\n\n"
                "Your account was created in Be Observant.\n"
                f"Username: {username}\n"
                f"{login_line}"
                "If this is your first login, follow your administrator's instructions for credentials and MFA setup.\n"
            ),
        )
        result = await self._dispatch(cfg, msg, recipient_email)
        if result:
            logger.info("User welcome email sent to %s", recipient_email)
        return result

    async def send_temporary_password_email(
        self,
        recipient_email: str,
        username: str,
        temporary_password: str,
        login_url: Optional[str] = None,
    ) -> bool:
        if not _is_enabled("PASSWORD_RESET_EMAIL_ENABLED", "USER_WELCOME_EMAIL_ENABLED"):
            return False
        cfg = _smtp_config("PASSWORD_RESET", "USER_WELCOME")
        if not cfg["hostname"]:
            logger.info("Temporary password email skipped: SMTP host not set")
            return False
        app_login_url = (login_url or config.get_secret("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""
        msg = self._build_message(
            subject="Temporary Password for Be Observant",
            cfg=cfg,
            recipient=recipient_email,
            body=(
                f"Hello {username},\n\n"
                "An administrator reset your password.\n"
                f"Temporary password: {temporary_password}\n"
                f"{login_line}"
                "You must change this password immediately after login.\n"
            ),
        )
        result = await self._dispatch(cfg, msg, recipient_email)
        if result:
            logger.info("Temporary password email sent to %s", recipient_email)
        return result