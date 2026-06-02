"""
Email package — public surface.

Code that needs email should import from this module (not from interfaces /
types / adapters directly):

    from backend.infra.email import (
        EmailSender, ReplyDetector, BounceDetector, EmailProvider,
        OutboundEmail, SendResult, MessageRef, BounceEvent,
    )
    from backend.infra.email.factory import build_provider, build_sender

Concrete adapters live in ``backend.infra.email.adapters.*`` and are reached
only via the factory (which dispatches by EMAIL_PROVIDER env var).
"""
from backend.infra.email.interfaces import (
    BounceDetector,
    EmailProvider,
    EmailSender,
    ReplyDetector,
)
from backend.infra.email.types import (
    BounceEvent,
    MessageRef,
    OutboundEmail,
    SendResult,
)

__all__ = [
    # Interfaces
    "EmailSender",
    "ReplyDetector",
    "BounceDetector",
    "EmailProvider",
    # Value objects
    "OutboundEmail",
    "SendResult",
    "MessageRef",
    "BounceEvent",
]
