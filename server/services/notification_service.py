"""Email notification helpers used by main-server auth/user onboarding flows."""

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


class NotificationService:
    """Minimal notification service for account lifecycle emails.

    Alert/incident/channel notification delivery is owned by BeNotified.
    """

    def __init__(self) -> None:
        self.timeout = float(config.DEFAULT_TIMEOUT)
        self._client = create_async_client(self.timeout)

    @staticmethod
    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    async def _send_smtp_with_retry(
        self,
        *,
        message: EmailMessage,
        hostname: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        start_tls: bool = False,
        use_tls: bool = False,
    ) -> None:
        if aiosmtplib is None:
            raise RuntimeError("aiosmtplib is unavailable")

        await aiosmtplib.send(
            message,
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            start_tls=start_tls,
            use_tls=use_tls,
            timeout=self.timeout,
        )

    async def send_incident_assignment_email(
        self,
        recipient_email: str,
        incident_title: str,
        incident_status: str,
        incident_severity: str,
        actor: str,
    ) -> bool:
        enabled = str(config.get_secret("INCIDENT_ASSIGNMENT_EMAIL_ENABLED") or "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return False

        smtp_host = (config.get_secret("INCIDENT_ASSIGNMENT_SMTP_HOST") or "").strip()
        if not smtp_host:
            logger.info("Incident assignment email skipped: INCIDENT_ASSIGNMENT_SMTP_HOST not set")
            return False

        try:
            smtp_port = int(config.get_secret("INCIDENT_ASSIGNMENT_SMTP_PORT") or "587")
        except ValueError:
            smtp_port = 587

        smtp_user = config.get_secret("INCIDENT_ASSIGNMENT_SMTP_USERNAME")
        smtp_pass = config.get_secret("INCIDENT_ASSIGNMENT_SMTP_PASSWORD")
        smtp_from = config.get_secret("INCIDENT_ASSIGNMENT_FROM") or config.DEFAULT_ADMIN_EMAIL
        use_starttls = self._as_bool(config.get_secret("INCIDENT_ASSIGNMENT_SMTP_STARTTLS") or "true")
        use_ssl = self._as_bool(config.get_secret("INCIDENT_ASSIGNMENT_SMTP_USE_SSL") or "false")

        msg = EmailMessage()
        msg["Subject"] = f"[Incident Assigned] {incident_title}"
        msg["From"] = smtp_from
        msg["To"] = recipient_email
        msg.set_content(
            "\n".join(
                [
                    "You have been assigned an incident in Be Observant.",
                    "",
                    f"Title: {incident_title}",
                    f"Status: {incident_status}",
                    f"Severity: {incident_severity}",
                    f"Updated by: {actor}",
                    f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
                ]
            )
        )

        try:
            await self._send_smtp_with_retry(
                message=msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=use_starttls,
                use_tls=use_ssl,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send incident assignment email to %s: %s", recipient_email, exc)
            return False

    async def send_user_welcome_email(
        self,
        recipient_email: str,
        username: str,
        full_name: Optional[str] = None,
        login_url: Optional[str] = None,
    ) -> bool:
        enabled = str(config.get_secret("USER_WELCOME_EMAIL_ENABLED") or "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return False

        smtp_host = (config.get_secret("USER_WELCOME_SMTP_HOST") or "").strip()
        if not smtp_host:
            logger.info("User welcome email skipped: USER_WELCOME_SMTP_HOST not set")
            return False

        try:
            smtp_port = int(config.get_secret("USER_WELCOME_SMTP_PORT") or "587")
        except ValueError:
            smtp_port = 587

        smtp_user = config.get_secret("USER_WELCOME_SMTP_USERNAME")
        smtp_pass = config.get_secret("USER_WELCOME_SMTP_PASSWORD")
        smtp_from = config.get_secret("USER_WELCOME_FROM") or config.DEFAULT_ADMIN_EMAIL
        use_starttls = self._as_bool(config.get_secret("USER_WELCOME_SMTP_STARTTLS") or "true")
        use_ssl = self._as_bool(config.get_secret("USER_WELCOME_SMTP_USE_SSL") or "false")

        user_label = full_name or username
        app_login_url = (login_url or config.get_secret("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""

        msg = EmailMessage()
        msg["Subject"] = "Welcome to Be Observant"
        msg["From"] = smtp_from
        msg["To"] = recipient_email
        msg.set_content(
            f"Hello {user_label},\n\n"
            "Your account was created in Be Observant.\n"
            f"Username: {username}\n"
            f"{login_line}"
            "If this is your first login, follow your administrator's instructions for credentials and MFA setup.\n"
        )

        try:
            await self._send_smtp_with_retry(
                message=msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=use_starttls,
                use_tls=use_ssl,
            )
            logger.info("User welcome email sent to %s", recipient_email)
            return True
        except Exception as exc:
            logger.warning("Failed to send user welcome email to %s: %s", recipient_email, exc)
            return False

    async def send_temporary_password_email(
        self,
        recipient_email: str,
        username: str,
        temporary_password: str,
        login_url: Optional[str] = None,
    ) -> bool:
        enabled = str(
            config.get_secret("PASSWORD_RESET_EMAIL_ENABLED")
            or config.get_secret("USER_WELCOME_EMAIL_ENABLED")
            or "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return False

        smtp_host = (
            config.get_secret("PASSWORD_RESET_SMTP_HOST")
            or config.get_secret("USER_WELCOME_SMTP_HOST")
            or ""
        ).strip()
        if not smtp_host:
            logger.info("Temporary password email skipped: SMTP host not set")
            return False

        try:
            smtp_port = int(
                config.get_secret("PASSWORD_RESET_SMTP_PORT")
                or config.get_secret("USER_WELCOME_SMTP_PORT")
                or "587"
            )
        except ValueError:
            smtp_port = 587

        smtp_user = (
            config.get_secret("PASSWORD_RESET_SMTP_USERNAME")
            or config.get_secret("USER_WELCOME_SMTP_USERNAME")
        )
        smtp_pass = (
            config.get_secret("PASSWORD_RESET_SMTP_PASSWORD")
            or config.get_secret("USER_WELCOME_SMTP_PASSWORD")
        )
        smtp_from = (
            config.get_secret("PASSWORD_RESET_FROM")
            or config.get_secret("USER_WELCOME_FROM")
            or config.DEFAULT_ADMIN_EMAIL
        )
        use_starttls = self._as_bool(
            config.get_secret("PASSWORD_RESET_SMTP_STARTTLS")
            or config.get_secret("USER_WELCOME_SMTP_STARTTLS")
            or "true"
        )
        use_ssl = self._as_bool(
            config.get_secret("PASSWORD_RESET_SMTP_USE_SSL")
            or config.get_secret("USER_WELCOME_SMTP_USE_SSL")
            or "false"
        )

        app_login_url = (login_url or config.get_secret("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""

        msg = EmailMessage()
        msg["Subject"] = "Temporary Password for Be Observant"
        msg["From"] = smtp_from
        msg["To"] = recipient_email
        msg.set_content(
            f"Hello {username},\n\n"
            "An administrator reset your password.\n"
            f"Temporary password: {temporary_password}\n"
            f"{login_line}"
            "You must change this password immediately after login.\n"
        )

        try:
            await self._send_smtp_with_retry(
                message=msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=use_starttls,
                use_tls=use_ssl,
            )
            logger.info("Temporary password email sent to %s", recipient_email)
            return True
        except Exception as exc:
            logger.warning("Failed to send temporary password email to %s: %s", recipient_email, exc)
            return False
