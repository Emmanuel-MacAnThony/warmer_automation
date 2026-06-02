"""
DryRunSender — no-op sender for dev / CI.

Logs each send at INFO level so you can see what would have gone out.
Never touches any email provider. Always returns ok=True.

Activated when Config.DRY_RUN=true or EMAIL_DRY_RUN=true in .env.
"""
from __future__ import annotations

import logging

from backend.infra.email import EmailProvider, EmailSender, OutboundEmail, SendResult

logger = logging.getLogger(__name__)


class DryRunSender:
    rate_limit_ms: int = 0

    async def send(self, email: OutboundEmail) -> SendResult:
        logger.info(
            f"[DryRunSender] WOULD SEND → {email.to!r} | subject={email.subject!r}"
        )
        return SendResult(ok=True, message_id="dry-run")

    async def health_check(self) -> bool:
        return True


# ── Provider entry point (matches the shape of gmail/smtp/resend) ────────────

async def build(sender_account=None) -> EmailProvider:
    """Build an EmailProvider that no-ops every send. No detectors needed."""
    return EmailProvider(sender=DryRunSender())
