"""
Email sender abstraction — vendor-neutral interface for outbound email.

The domain specifies what it needs; implementations meet the contract.
The runner only talks to EmailSender — never to Gmail or SMTP directly.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class OutboundEmail:
    to: str
    subject: str
    body_html: str
    from_name: Optional[str] = None
    reply_to: Optional[str] = None


@dataclass
class SendResult:
    ok: bool
    message_id: Optional[str] = None
    thread_id: Optional[str] = None  # Gmail thread id — used for reply detection
    error: Optional[str] = None
    rate_limited: bool = False
    retry_after_seconds: Optional[int] = None  # from Retry-After header; None = unknown


@runtime_checkable
class EmailSender(Protocol):
    """
    Vendor-neutral send interface. Implementations:
      GmailSender    — Gmail API (OAuth), personal or Workspace
      SMTPSender     — any SMTP provider (SendGrid, Mailgun, Outlook)
      DryRunSender   — no-op logger, for dev / CI
    """
    rate_limit_ms: int  # minimum gap between consecutive sends on this sender

    async def send(self, email: OutboundEmail) -> SendResult: ...
    async def health_check(self) -> bool: ...
