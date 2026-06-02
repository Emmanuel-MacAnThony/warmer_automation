"""
SMTPSender — generic SMTP sender.

Works with any SMTP provider — SendGrid, Mailgun, Outlook, Amazon SES, custom.

SendGrid example:
    SMTPSender(
        host="smtp.sendgrid.net", port=587,
        username="apikey", password=Config.SENDGRID_API_KEY,
        from_email="outreach@yourorg.com", from_name="Sarah Chen",
    )

Mailgun example:
    SMTPSender(
        host="smtp.mailgun.org", port=587,
        username="postmaster@mg.yourorg.com", password=Config.MAILGUN_SMTP_PASSWORD,
        from_email="outreach@yourorg.com",
    )
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from backend.infra.email import EmailProvider, EmailSender, OutboundEmail, SendResult

logger = logging.getLogger(__name__)


class SMTPSender:
    rate_limit_ms: int = 100  # 10/sec default; set lower for stricter providers

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: Optional[str] = None,
        rate_limit_ms: int = 100,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self.rate_limit_ms = rate_limit_ms

    def _send_sync(self, email: OutboundEmail) -> SendResult:
        """Blocking SMTP send — runs in thread pool."""
        try:
            msg = MIMEMultipart("alternative")
            from_header = (
                f"{self._from_name} <{self._from_email}>"
                if self._from_name
                else self._from_email
            )
            msg["From"] = from_header
            msg["To"] = email.to
            msg["Subject"] = email.subject
            if email.reply_to:
                msg["Reply-To"] = email.reply_to
            msg.attach(MIMEText(email.body_html, "html"))

            with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._username, self._password)
                smtp.sendmail(self._from_email, [email.to], msg.as_string())

            return SendResult(ok=True)
        except smtplib.SMTPException as e:
            return SendResult(ok=False, error=f"SMTP error: {e}")
        except Exception as e:
            return SendResult(ok=False, error=str(e))

    async def send(self, email: OutboundEmail) -> SendResult:
        return await asyncio.to_thread(self._send_sync, email)

    async def health_check(self) -> bool:
        try:
            def _ping():
                with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(self._username, self._password)
            await asyncio.to_thread(_ping)
            return True
        except Exception:
            return False


# ── Provider entry point (called by factory.py via importlib) ────────────────

async def build(sender_account=None) -> EmailProvider:
    """
    Build an EmailProvider for the configured SMTP account.

    SMTP only supports send. Reply/bounce detection would require an IMAP
    poller (future GenericIMAPReplyDetector / GenericIMAPBounceDetector);
    not wired yet, so both detectors are None.
    """
    from backend.config import Config
    if not Config.SMTP_HOST:
        raise ValueError("SMTP_HOST is not configured in .env")
    sender = SMTPSender(
        host=Config.SMTP_HOST,
        port=Config.SMTP_PORT,
        username=Config.SMTP_USER,
        password=Config.SMTP_PASS,
        from_email=Config.SMTP_FROM_EMAIL,
        from_name=Config.SMTP_FROM_NAME,
    )
    return EmailProvider(sender=sender)
