"""
Value objects that cross the email-adapter boundary.

These are deliberately neutral — no provider-specific fields. Adapters map
their native payloads onto these shapes; the runner only sees these.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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
    A delivery failure surfaced by a BounceDetector. Adapters map provider-
    specific signals (Gmail DSN parse, Resend webhook payload, etc.) onto
    this neutral shape so the caller doesn't care where it came from.

    event_id is the provider's own identifier for this bounce event — the
    Gmail DSN message id, or a Resend webhook event id. Used by the caller
    purely for idempotency when persisting (so a poller restart cannot
    insert the same bounce twice).
    """
    message_ref: MessageRef
    recipient: str
    hard: bool            # True = permanent (mailbox doesn't exist); False = transient (full / deferred)
    reason: Optional[str] = None
    detected_at: Optional[datetime] = None
    event_id: Optional[str] = None
    smtp_status: Optional[str] = None  # e.g. "5.1.1" — for the audit row
