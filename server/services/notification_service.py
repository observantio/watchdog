"""Notification service for sending alerts through various channels."""
import httpx
import logging
import os
from typing import Optional
from datetime import datetime

# email transport
import re
import aiosmtplib
from email.message import EmailMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, retry_if_exception_type, before_sleep_log

from models.alerting.channels import NotificationChannel, ChannelType
from models.alerting.alerts import Alert
from config import config
from services.common.url_utils import is_safe_http_url
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)
NO_VALUE = "(none)"

class NotificationService:
    """Service for sending notifications through various channels."""
    
    def __init__(self):
        self.timeout = config.DEFAULT_TIMEOUT
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

    def validate_channel_config(self, channel_type: str, channel_config: dict | None) -> list[str]:
        cfg = channel_config or {}
        normalized_type = str(channel_type or "").strip().lower()
        errors: list[str] = []

        if normalized_type == "email":
            to_field = cfg.get('to') or cfg.get('recipient')
            recipients = [r.strip() for r in re.split(r"[,;\s]+", str(to_field or "")) if r.strip()]
            if not recipients:
                errors.append("Email channel requires at least one recipient in 'to'")

            provider = (cfg.get('email_provider') or cfg.get('emailProvider') or 'smtp').strip().lower()
            if provider == 'smtp':
                smtp_host = cfg.get('smtp_host') or cfg.get('smtpHost')
                if not str(smtp_host or "").strip():
                    errors.append("SMTP email channel requires 'smtp_host'")
            elif provider == 'sendgrid':
                api_key = cfg.get('sendgrid_api_key') or cfg.get('sendgridApiKey') or cfg.get('api_key') or cfg.get('apiKey')
                if not str(api_key or "").strip():
                    errors.append("SendGrid email channel requires 'sendgrid_api_key'")
            elif provider == 'resend':
                api_key = cfg.get('resend_api_key') or cfg.get('resendApiKey') or cfg.get('api_key') or cfg.get('apiKey')
                if not str(api_key or "").strip():
                    errors.append("Resend email channel requires 'resend_api_key'")
            else:
                errors.append(f"Unsupported email provider '{provider}'")

        elif normalized_type == "slack":
            webhook_url = cfg.get('webhook_url') or cfg.get('webhookUrl')
            if not is_safe_http_url(webhook_url):
                errors.append("Slack channel requires a valid 'webhook_url'")

        elif normalized_type == "teams":
            webhook_url = cfg.get('webhook_url') or cfg.get('webhookUrl')
            if not is_safe_http_url(webhook_url):
                errors.append("Teams channel requires a valid 'webhook_url'")

        elif normalized_type == "webhook":
            webhook_url = cfg.get('url') or cfg.get('webhook_url') or cfg.get('webhookUrl')
            if not is_safe_http_url(webhook_url):
                errors.append("Webhook channel requires a valid URL")

        elif normalized_type == "pagerduty":
            routing_key = cfg.get('routing_key') or cfg.get('integrationKey')
            if not str(routing_key or "").strip():
                errors.append("PagerDuty channel requires 'routing_key'")

        return errors

    def _is_transient_http_exception(self, exc) -> bool:
        """Return True for exceptions that should be retried for HTTP calls."""
        # network / transport errors
        if isinstance(exc, httpx.RequestError):
            return True
        # server errors (5xx)
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code if exc.response is not None else 0
            return 500 <= status < 600
        return False

    @retry(
        retry=retry_if_exception(lambda e: self._is_transient_http_exception(e)),
        stop=stop_after_attempt(config.MAX_RETRIES),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF),
        before_sleep=before_sleep_log(logger, logging.INFO),
        reraise=True,
    )
    async def _post_with_retry(self, url: str, json: dict | None = None, headers: dict | None = None, params: dict | None = None) -> httpx.Response:
        resp = await self._client.post(url, json=json, headers=headers, params=params)
        resp.raise_for_status()
        return resp

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(config.MAX_RETRIES),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF),
        before_sleep=before_sleep_log(logger, logging.INFO),
        reraise=True,
    )
    async def _send_smtp_with_retry(self, message: EmailMessage, hostname: str, port: int, username: str | None = None, password: str | None = None, start_tls: bool = False, use_tls: bool = False):
        return await aiosmtplib.send(
            message=message,
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            start_tls=start_tls,
            timeout=self.timeout,
            use_tls=use_tls,
        )

    async def send_notification(
        self,
        channel: NotificationChannel,
        alert: Alert,
        action: str = "firing"
    ) -> bool:
        """Send notification through the specified channel.
        
        Args:
            channel: Notification channel configuration
            alert: Alert to send
            action: Alert action (firing or resolved)
            
        Returns:
            True if notification was sent successfully
        """
        if not channel.enabled:
            logger.info(f"Channel {channel.name} is disabled, skipping notification")
            return False
        
        try:
            async_senders = {
                ChannelType.SLACK: self._send_slack,
                ChannelType.TEAMS: self._send_teams,
                ChannelType.WEBHOOK: self._send_webhook,
                ChannelType.PAGERDUTY: self._send_pagerduty,
            }
            if channel.type == ChannelType.EMAIL:
                return await self._send_email(channel, alert, action)
            sender = async_senders.get(channel.type)
            if not sender:
                logger.error(f"Unknown channel type: {channel.type}")
                return False
            return await sender(channel, alert, action)
        except Exception as e:
            logger.exception("Error sending notification via %s: %s", channel.name, e)
            return False

    async def send_incident_assignment_email(
        self,
        recipient_email: str,
        incident_title: str,
        incident_status: str,
        incident_severity: str,
        actor: str,
    ) -> bool:
        """Best-effort assignment email using optional INCIDENT_ASSIGNMENT_SMTP_* env vars."""
        enabled = str(os.getenv("INCIDENT_ASSIGNMENT_EMAIL_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return False

        smtp_host = os.getenv("INCIDENT_ASSIGNMENT_SMTP_HOST", "").strip()
        if not smtp_host:
            logger.info("Incident assignment email skipped: INCIDENT_ASSIGNMENT_SMTP_HOST not set")
            return False

        smtp_port_raw = os.getenv("INCIDENT_ASSIGNMENT_SMTP_PORT", "587")
        try:
            smtp_port = int(smtp_port_raw)
        except ValueError:
            smtp_port = 587

        smtp_user = os.getenv("INCIDENT_ASSIGNMENT_SMTP_USERNAME")
        smtp_pass = os.getenv("INCIDENT_ASSIGNMENT_SMTP_PASSWORD")
        smtp_from = os.getenv("INCIDENT_ASSIGNMENT_FROM", config.DEFAULT_ADMIN_EMAIL)
        use_starttls = self._as_bool(os.getenv("INCIDENT_ASSIGNMENT_SMTP_STARTTLS", "true"))
        use_ssl = self._as_bool(os.getenv("INCIDENT_ASSIGNMENT_SMTP_USE_SSL", "false"))

        subject = f"[Incident Assigned] {incident_title}"
        body = (
            f"You have been assigned an incident in Be Observant.\n\n"
            f"Title: {incident_title}\n"
            f"Status: {incident_status}\n"
            f"Severity: {incident_severity}\n"
            f"Updated by: {actor}\n"
            f"Timestamp: {datetime.utcnow().isoformat()}Z\n"
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = recipient_email
        msg.set_content(body)

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
            logger.info("Incident assignment email sent to %s", recipient_email)
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
        """Best-effort new-user welcome email.

        Sends only when USER_WELCOME_EMAIL_ENABLED and USER_WELCOME_SMTP_HOST are configured.
        """
        enabled = str(os.getenv("USER_WELCOME_EMAIL_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return False

        smtp_host = os.getenv("USER_WELCOME_SMTP_HOST", "").strip()
        if not smtp_host:
            logger.info("User welcome email skipped: USER_WELCOME_SMTP_HOST not set")
            return False

        smtp_port_raw = os.getenv("USER_WELCOME_SMTP_PORT", "587")
        try:
            smtp_port = int(smtp_port_raw)
        except ValueError:
            smtp_port = 587

        smtp_user = os.getenv("USER_WELCOME_SMTP_USERNAME")
        smtp_pass = os.getenv("USER_WELCOME_SMTP_PASSWORD")
        smtp_from = os.getenv("USER_WELCOME_FROM", config.DEFAULT_ADMIN_EMAIL)
        use_starttls = self._as_bool(os.getenv("USER_WELCOME_SMTP_STARTTLS", "true"))
        use_ssl = self._as_bool(os.getenv("USER_WELCOME_SMTP_USE_SSL", "false"))

        user_label = full_name or username
        app_login_url = (login_url or os.getenv("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""
        subject = "Welcome to Be Observant"
        body = (
            f"Hello {user_label},\n\n"
            f"Your account was created in Be Observant.\n"
            f"Username: {username}\n"
            f"{login_line}"
            "If this is your first login, follow your administrator's instructions for credentials and MFA setup.\n"
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = recipient_email
        msg.set_content(body)

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
    
    async def _send_email(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send email notification via SMTP or API provider.

        Expected channel.config keys (common names accepted):
        - to (comma-separated string or single address)
        - email_provider / emailProvider: smtp | sendgrid | resend
        - smtp_host / smtpHost
        - smtp_port / smtpPort
        - smtp_username / smtpUsername
        - smtp_password / smtpPassword
        - smtp_api_key / smtpApiKey (SMTP API-key auth)
        - smtp_auth_type / smtpAuthType: password | api_key | none
        - smtp_from / smtpFrom / from
        - smtp_starttls / smtpStartTLS (boolean)
        - smtp_use_ssl / smtpUseSSL (boolean)
        - sendgrid_api_key / sendgridApiKey / api_key
        - resend_api_key / resendApiKey / api_key
        """
        channel_config = channel.config or {}

        # recipients
        to_field = channel_config.get('to') or channel_config.get('recipient')
        if not to_field:
            logger.error("Email channel '%s' has no 'to' address configured", channel.name)
            return False
        recipients = [r.strip() for r in re.split(r"[,;\s]+", str(to_field)) if r.strip()]
        if not recipients:
            logger.error("No valid recipient addresses for channel %s", channel.name)
            return False

        subject = f"[{action.upper()}] {alert.labels.get('alertname', 'Alert')}"
        body = self._format_alert_body(alert, action)

        provider = (channel_config.get('email_provider') or channel_config.get('emailProvider') or 'smtp').strip().lower()
        smtp_from = (
            channel_config.get('smtp_from')
            or channel_config.get('smtpFrom')
            or channel_config.get('from')
            or config.DEFAULT_ADMIN_EMAIL
        )

        if provider == 'sendgrid':
            api_key = channel_config.get('sendgrid_api_key') or channel_config.get('sendgridApiKey') or channel_config.get('api_key') or channel_config.get('apiKey')
            if not api_key:
                logger.error("SendGrid API key not configured for email channel %s", channel.name)
                return False
            payload = {
                "personalizations": [{"to": [{"email": recipient} for recipient in recipients]}],
                "from": {"email": smtp_from},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            try:
                await self._post_with_retry("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
                logger.info("Email notification sent via SendGrid (channel=%s)", channel.name)
                return True
            except Exception as exc:
                logger.exception("Failed SendGrid email for channel %s after retries: %s", channel.name, exc)
                return False

        if provider == 'resend':
            api_key = channel_config.get('resend_api_key') or channel_config.get('resendApiKey') or channel_config.get('api_key') or channel_config.get('apiKey')
            if not api_key:
                logger.error("Resend API key not configured for email channel %s", channel.name)
                return False
            payload = {
                "from": smtp_from,
                "to": recipients,
                "subject": subject,
                "text": body,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            try:
                await self._post_with_retry("https://api.resend.com/emails", json=payload, headers=headers)
                logger.info("Email notification sent via Resend (channel=%s)", channel.name)
                return True
            except Exception as exc:
                logger.exception("Failed Resend email for channel %s after retries: %s", channel.name, exc)
                return False

        if provider != 'smtp':
            logger.error("Unsupported email provider '%s' for channel %s", provider, channel.name)
            return False

        # SMTP connection params (accept multiple key names)
        smtp_host = channel_config.get('smtp_host') or channel_config.get('smtpHost')
        smtp_port = int(channel_config.get('smtp_port') or channel_config.get('smtpPort') or 0)
        smtp_user = channel_config.get('smtp_username') or channel_config.get('smtpUsername') or channel_config.get('username')
        smtp_pass = channel_config.get('smtp_password') or channel_config.get('smtpPassword') or channel_config.get('password')
        smtp_api_key = channel_config.get('smtp_api_key') or channel_config.get('smtpApiKey') or channel_config.get('api_key') or channel_config.get('apiKey')
        smtp_auth_type = (channel_config.get('smtp_auth_type') or channel_config.get('smtpAuthType') or 'password').strip().lower()
        use_starttls = self._as_bool(channel_config.get('smtp_starttls') or channel_config.get('smtpStartTLS') or channel_config.get('starttls') or False)
        use_ssl = self._as_bool(channel_config.get('smtp_use_ssl') or channel_config.get('smtpUseSSL') or False)

        if not smtp_host:
            logger.error("SMTP host not configured for email channel %s", channel.name)
            return False
        if smtp_port == 0:
            # sensible defaults
            smtp_port = 465 if use_ssl else 587 if use_starttls else 25

        if smtp_auth_type == 'none':
            smtp_user = None
            smtp_pass = None
        elif smtp_auth_type == 'api_key':
            smtp_user = smtp_user or 'apikey'
            smtp_pass = smtp_api_key
            if not smtp_pass:
                logger.error("SMTP API key not configured for email channel %s", channel.name)
                return False
        else:
            if smtp_user and not smtp_pass and smtp_api_key:
                smtp_pass = smtp_api_key

        # Build message
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)

        logger.info("Sending email notification to %s via %s:%s (channel=%s)", recipients, smtp_host, smtp_port, channel.name)

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
            logger.info("Email notification sent (channel=%s)", channel.name)
            return True
        except Exception as exc:
            logger.exception("Failed to send email for channel %s after retries: %s", channel.name, exc)
            return False
    
    async def _send_slack(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send Slack notification."""
        channel_config = channel.config
        webhook_url = channel_config.get('webhook_url') or channel_config.get('webhookUrl')
        
        if not is_safe_http_url(webhook_url):
            logger.error("Slack webhook URL is missing or invalid")
            return False
        
        color = "danger" if action == "firing" else "good"
        if alert.labels.get('severity') == 'warning':
            color = "warning"
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        payload = {
            "attachments": [{
                "color": color,
                "title": f"[{action.upper()}] {self._get_label(alert, 'alertname', 'Alert')}",
                "text": self._get_alert_text(alert),
                "fields": [
                    {
                        "title": "Severity",
                        "value": self._get_label(alert, 'severity', 'unknown'),
                        "short": True
                    },
                    {
                        "title": "Status",
                        "value": action,
                        "short": True
                    },
                    {
                        "title": "Summary",
                        "value": summary or NO_VALUE,
                        "short": False
                    },
                    {
                        "title": "Description",
                        "value": description or NO_VALUE,
                        "short": False
                    }
                ],
                "footer": f"Started: {alert.starts_at}",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        response = await self._post_with_retry(webhook_url, json=payload)
        logger.info(
            "Slack notification sent to %s",
            channel_config.get('channel', config.DEFAULT_SLACK_CHANNEL),
        )
        return True
    
    async def _send_teams(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send Microsoft Teams notification."""
        channel_config = channel.config
        webhook_url = channel_config.get('webhook_url') or channel_config.get('webhookUrl')
        
        if not is_safe_http_url(webhook_url):
            logger.error("Teams webhook URL is missing or invalid")
            return False
        
        theme_color = "FF0000" if action == "firing" else "00FF00"
        if alert.labels.get('severity') == 'warning':
            theme_color = "FFA500"
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": theme_color,
            "title": f"[{action.upper()}] {self._get_label(alert, 'alertname', 'Alert')}",
            "text": self._get_alert_text(alert),
            "sections": [{
                "facts": [
                    {"name": "Severity", "value": self._get_label(alert, 'severity', 'unknown')},
                    {"name": "Status", "value": action},
                    {"name": "Started", "value": alert.starts_at},
                    {"name": "Summary", "value": summary or NO_VALUE},
                    {"name": "Description", "value": description or NO_VALUE}
                ]
            }]
        }
        
        response = await self._post_with_retry(webhook_url, json=payload)
        logger.info("Teams notification sent")
        return True
    
    async def _send_webhook(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send webhook notification."""
        channel_config = channel.config
        webhook_url = channel_config.get('url') or channel_config.get('webhook_url') or channel_config.get('webhookUrl')
        
        if not is_safe_http_url(webhook_url):
            logger.error("Webhook URL is missing or invalid")
            return False
        
        payload = {
            "action": action,
            "alert": {
                "labels": alert.labels,
                "annotations": alert.annotations,
                "startsAt": alert.starts_at,
                "endsAt": alert.ends_at,
                "fingerprint": alert.fingerprint
            }
        }
        
        headers = channel_config.get('headers', {})
        
        response = await self._post_with_retry(webhook_url, json=payload, headers=headers)
        logger.info("Webhook notification sent to %s", webhook_url)
        return True
    
    async def _send_pagerduty(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send PagerDuty notification."""
        channel_config = channel.config
        routing_key = channel_config.get('routing_key') or channel_config.get('integrationKey')
        
        if not routing_key:
            logger.error("PagerDuty routing key not configured")
            return False
        
        event_action = "trigger" if action == "firing" else "resolve"
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        payload = {
            "routing_key": routing_key,
            "event_action": event_action,
            "dedup_key": alert.fingerprint,
            "payload": {
                "summary": summary or description or self._get_label(alert, 'alertname', 'Alert'),
                "severity": self._get_label(alert, 'severity', 'warning'),
                "source": self._get_label(alert, 'instance', 'unknown'),
                "custom_details": {
                    "labels": alert.labels or {},
                    "annotations": alert.annotations or {},
                    "summary": summary,
                    "description": description
                }
            }
        }
        
        response = await self._post_with_retry("https://events.pagerduty.com/v2/enqueue", json=payload)
        logger.info("PagerDuty notification sent")
        return True

    
    def _format_alert_body(self, alert: Alert, action: str) -> str:
        """Format alert body for email/text notifications."""
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        lines = [
            f"Alert: {self._get_label(alert, 'alertname', 'Unknown')}",
            f"Status: {action}",
            f"Severity: {self._get_label(alert, 'severity', 'unknown')}",
            f"Started: {alert.starts_at}",
            "",
            "Summary:",
            summary or "No summary",
            "",
            "Description:",
            description or "No description",
            "",
            "Labels:"
        ]
        
        for key, value in alert.labels.items():
            lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)

    def _get_label(self, alert: Alert, key: str, default: str = "") -> str:
        labels = alert.labels or {}
        return str(labels.get(key, default))

    def _get_annotation(self, alert: Alert, key: str) -> Optional[str]:
        annotations = alert.annotations or {}
        value = annotations.get(key)
        if value is None:
            return None
        return str(value)

    def _get_alert_text(self, alert: Alert) -> str:
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        if summary and description and summary != description:
            return f"{summary}\n{description}"
        return summary or description or "No description"
