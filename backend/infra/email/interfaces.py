"""
Email integration boundary — Ports & Adapters style.

Three ABCs defining what the application needs from any email provider:

  EmailSender    — outbound delivery
  ReplyDetector  — "did this previously-sent message receive a reply?"
  BounceDetector — "what delivery failures have happened since X?"

Concrete adapters live in ``backend.infra.email.adapters.*`` and inherit
explicitly from these ABCs. The application code (cadence scheduler, batch
sender, future bounce poller) depends on these abstractions, never on a
specific provider module.

EmailProvider bundles the three capabilities for a single sender account.
reply_detector and bounce_detector are Optional — a provider supplies what
it can (e.g. Gmail has reply detection but no bounce detector yet; SMTP has
neither until an IMAP poller is added).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from backend.infra.email.types import (
    BounceEvent,
    MessageRef,
    OutboundEmail,
    SendResult,
)


class EmailSender(ABC):
    """Sends one email. Per-sender rate limiting is the caller's job."""

    rate_limit_ms: int = 0  # minimum gap (ms) between consecutive sends on this instance

    @abstractmethod
    async def send(self, email: OutboundEmail) -> SendResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...


class ReplyDetector(ABC):
    """
    Reports whether a previously-sent message has received a reply.

    How that is determined is provider-specific (Gmail reads threads,
    Microsoft Graph reads conversations, IMAP polls inboxes, Resend would
    use webhooks). The cadence scheduler treats a missing detector as
    "stop-on-reply not supported" and skips the account cleanly.
    """

    @abstractmethod
    async def check_replied(self, ref: MessageRef) -> bool: ...


class BounceDetector(ABC):
    """
    Reports delivery failures (bounces) since a given moment.

    Concrete impls expected:
      GmailDSNScanner       — scans the sender's inbox for mailer-daemon DSNs
      ResendBouncePoller    — reads Resend webhook events
      IMAPBouncePoller      — generic SMTP fallback
    """

    @abstractmethod
    async def fetch_bounces(self, since: datetime) -> list[BounceEvent]: ...


@dataclass
class EmailProvider:
    """
    Full integration surface for one sender account: a sender, plus whichever
    detectors that provider supports. Capability-by-composition — callers ask
    'is reply_detector set?' instead of poking attributes via getattr.
    """
    sender: EmailSender
    reply_detector: Optional[ReplyDetector] = None
    bounce_detector: Optional[BounceDetector] = None
