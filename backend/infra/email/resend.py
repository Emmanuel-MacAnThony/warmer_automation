"""
ResendSender — sends via the Resend HTTP API (https://resend.com).

Free tier: 3,000 emails/month, 100/day, ~2 requests/second.

IMPORTANT — deliverability constraint:
  Resend can only send from a domain you have verified (DKIM/SPF) in the Resend
  dashboard. You CANNOT send "from" an @gmail.com address through Resend —
  Gmail publishes a strict DMARC policy and such mail is rejected/spam-foldered.
  → For personal Gmail, use EMAIL_PROVIDER=gmail (the Gmail API sends as the
    real account). Use Resend only for a custom domain / Google Workspace domain.

Uses the `requests` library in a worker thread (matches SMTPSender) so no new
async HTTP dependency is introduced.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from backend.infra.email import EmailSender, OutboundEmail, SendResult

logger = logging.getLogger(__name__)

_API_URL = "https://api.resend.com/emails"


class ResendSender:
    # Resend free tier allows ~2 req/sec; 600ms gap keeps us safely under it.
    rate_limit_ms: int = 600

    def __init__(
        self,
        api_key: str,
        from_email: str,
        from_name: Optional[str] = None,
        rate_limit_ms: int = 600,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name
        self.rate_limit_ms = rate_limit_ms

    def _from_header(self) -> str:
        return f"{self._from_name} <{self._from_email}>" if self._from_name else self._from_email

    def _send_sync(self, email: OutboundEmail) -> SendResult:
        import requests

        payload = {
            "from": self._from_header(),
            "to": [email.to],
            "subject": email.subject,
            "html": email.body_html,
        }
        if email.reply_to:
            payload["reply_to"] = email.reply_to

        try:
            resp = requests.post(
                _API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            return SendResult(ok=False, error=f"Resend request failed: {e}")

        if resp.status_code == 429:
            retry_after: Optional[int] = None
            raw = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
            if raw:
                try:
                    retry_after = int(raw)
                except ValueError:
                    pass
            return SendResult(
                ok=False, error="Resend rate limit", rate_limited=True,
                retry_after_seconds=retry_after,
            )

        if resp.status_code >= 400:
            return SendResult(ok=False, error=f"Resend {resp.status_code}: {resp.text[:200]}")

        try:
            message_id = resp.json().get("id")
        except Exception:
            message_id = None
        return SendResult(ok=True, message_id=message_id)

    async def send(self, email: OutboundEmail) -> SendResult:
        return await asyncio.to_thread(self._send_sync, email)

    async def health_check(self) -> bool:
        return bool(self._api_key and self._from_email)


# ── Provider entry point (called by factory.py via importlib) ────────────────

async def build(sender_account=None):
    """Build a ResendSender from environment configuration."""
    from backend.config import Config
    if not Config.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured in .env")
    if not Config.RESEND_FROM_EMAIL:
        raise ValueError("RESEND_FROM_EMAIL is not configured (must be a Resend-verified domain address)")
    return ResendSender(
        api_key=Config.RESEND_API_KEY,
        from_email=Config.RESEND_FROM_EMAIL,
        from_name=Config.RESEND_FROM_NAME or None,
    )
