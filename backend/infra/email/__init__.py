"""
Email infra — vendor-neutral interfaces for outbound email AND post-send
signals (replies, bounces).

The runner talks ONLY to these Protocols (EmailSender / ReplyDetector /
BounceDetector) and to the EmailProvider bundle that ties them together —
never to Gmail or SMTP directly. Adding a new provider (Microsoft 365,
Resend webhooks, IMAP) means implementing what it actually supports and
returning an EmailProvider with the rest set to None.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass
class MessageRef:
    """
    Opaque per-provider reference to a previously-sent message, used by
    detectors to look up replies or bounces. Both ids are optional because
    not every provider returns both (Resend gives message_id, no thread).
    """
    message_id: Optional[str] = None
    thread_id: Optional[str] = None


@dataclass
class BounceEvent:
    """
    A delivery failure surfaced by a BounceDetector. Detectors map provider-
    specific signals (Gmail DSN parse, Resend webhook payload, etc.) onto
    this neutral shape so the caller doesn't care where it came from.
    """
    message_ref: MessageRef
    recipient: str
    hard: bool            # True = permanent (mailbox doesn't exist); False = transient (full / deferred)
    reason: Optional[str] = None
    detected_at: Optional[datetime] = None


@runtime_checkable
class EmailSender(Protocol):
    """
    Vendor-neutral send interface. Implementations:
      GmailSender    — Gmail API (OAuth), personal or Workspace
      SMTPSender     — any SMTP provider (SendGrid, Mailgun, Outlook)
      ResendSender   — Resend transactional API (custom verified domain)
      DryRunSender   — no-op logger, for dev / CI
    """
    rate_limit_ms: int  # minimum gap between consecutive sends on this sender

    async def send(self, email: OutboundEmail) -> SendResult: ...
    async def health_check(self) -> bool: ...


@runtime_checkable
class ReplyDetector(Protocol):
    """
    Reports whether a previously-sent message has received a reply. How that
    is determined is provider-specific (Gmail reads threads, Microsoft Graph
    reads conversations, IMAP polls, Resend would use webhooks). The cadence
    scheduler depends ONLY on this contract and treats `None` (no detector
    available) as "stop-on-reply not supported for this provider".
    """
    async def check_replied(self, ref: MessageRef) -> bool: ...


@runtime_checkable
class BounceDetector(Protocol):
    """
    Reports delivery failures since a given moment. Implementations:
      GmailDSNScanner — scans the sender's inbox for mailer-daemon messages
      ResendBouncePoller / SendGridEvents — webhook-based; ESP-specific
      IMAPBouncePoller — generic SMTP fallback
    """
    async def fetch_bounces(self, since: datetime) -> list[BounceEvent]: ...


@dataclass
class EmailProvider:
    """
    The full integration surface for a single sender account.

    Capability-by-composition: each provider supplies what it can. The
    cadence scheduler asks 'do you have a reply_detector?' rather than
    reaching into provider-specific attributes via getattr.
    """
    sender: EmailSender
    reply_detector: Optional[ReplyDetector] = None
    bounce_detector: Optional[BounceDetector] = None
