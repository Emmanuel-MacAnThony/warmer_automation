"""
EmailProvider factory — provider-agnostic dispatch via module registry.

Open/Closed: adding a new provider means creating a new module that exports
`async def build(sender_account) -> EmailProvider` and adding one entry to
_PROVIDER_MODULES below. The factory dispatch logic never changes.

Current providers:
  gmail   → backend.infra.email.gmail   (OAuth token from DB; reply detection wired)
  smtp    → backend.infra.email.smtp    (SMTP_HOST/PORT/USER/PASS from env)
  resend  → backend.infra.email.resend  (RESEND_API_KEY + verified domain)
  dry_run → backend.infra.email.dry_run (logger-only; activated by EMAIL_DRY_RUN)

To add Microsoft 365 (Graph):
  1. Create backend/infra/email/microsoft.py with `async def build(sender_account) -> EmailProvider`
     returning a Graph-backed sender + GraphReplyDetector + GraphBounceDetector.
  2. Add "microsoft": "backend.infra.email.microsoft" below. Done.
"""
from __future__ import annotations

import importlib
import logging
from typing import Optional

from backend.infra.email.interfaces import EmailProvider, EmailSender

logger = logging.getLogger(__name__)

_PROVIDER_MODULES: dict[str, str] = {
    "gmail":   "backend.infra.email.adapters.gmail",
    "smtp":    "backend.infra.email.adapters.smtp",
    "resend":  "backend.infra.email.adapters.resend",
    "dry_run": "backend.infra.email.adapters.dry_run",
}


async def build_provider(sender_account: Optional[str] = None) -> EmailProvider:
    """
    Build an EmailProvider (sender + optional reply/bounce detectors) for the
    configured provider. This is the canonical entry point for code that needs
    post-send signals (cadence scheduler, future bounce poller).

    sender_account is provider-specific:
      - Gmail: email address stored in gmail_tokens
      - SMTP / Resend: ignored (credentials come from env)
    """
    from backend.config import Config

    if Config.EMAIL_DRY_RUN:
        provider_key = "dry_run"
    else:
        provider_key = (Config.EMAIL_PROVIDER or "gmail").lower()

    module_path = _PROVIDER_MODULES.get(provider_key)
    if not module_path:
        raise ValueError(
            f"Unknown email provider '{provider_key}'. "
            f"Supported: {', '.join(_PROVIDER_MODULES)}"
        )

    mod = importlib.import_module(module_path)
    logger.debug(f"[EmailFactory] Building provider via {module_path}")
    return await mod.build(sender_account)


async def build_sender(sender_account: Optional[str] = None) -> EmailSender:
    """
    Send-only convenience wrapper over build_provider().

    For callers (batch sender, anything that purely emits) that don't need
    reply or bounce signals. Discards the detectors so the caller doesn't
    have to think about them.
    """
    provider = await build_provider(sender_account)
    return provider.sender
