"""
EmailSender factory — provider-agnostic dispatch via module registry.

Open/Closed: adding a new provider means creating a new module that exports
`build(sender_account)` and adding one entry to _PROVIDER_MODULES below.
The factory dispatch logic never changes.

Current providers:
  gmail  → backend.infra.email.gmail   (OAuth token from DB)
  smtp   → backend.infra.email.smtp    (SMTP_HOST/PORT/USER/PASS from env)

To add SendGrid:
  1. Create backend/infra/email/sendgrid.py with async def build(sender_account)
  2. Add "sendgrid": "backend.infra.email.sendgrid" below. Done.
"""
from __future__ import annotations

import importlib
import logging
from typing import Optional

from backend.infra.email import EmailSender

logger = logging.getLogger(__name__)

_PROVIDER_MODULES: dict[str, str] = {
    "gmail":  "backend.infra.email.gmail",
    "smtp":   "backend.infra.email.smtp",
    "resend": "backend.infra.email.resend",
}


async def build_sender(sender_account: Optional[str] = None) -> EmailSender:
    """
    Build an EmailSender for the configured provider.

    sender_account is provider-specific:
      - Gmail: email address stored in gmail_tokens
      - SMTP:  ignored (credentials come from env)
    """
    from backend.config import Config

    if Config.EMAIL_DRY_RUN:
        from backend.infra.email.dry_run import DryRunSender
        logger.debug("[EmailFactory] DryRunSender (EMAIL_DRY_RUN=true)")
        return DryRunSender()

    provider = (Config.EMAIL_PROVIDER or "gmail").lower()
    module_path = _PROVIDER_MODULES.get(provider)
    if not module_path:
        raise ValueError(
            f"Unknown email provider '{provider}'. "
            f"Supported: {', '.join(_PROVIDER_MODULES)}"
        )

    mod = importlib.import_module(module_path)
    logger.debug(f"[EmailFactory] Building sender via {module_path}")
    return await mod.build(sender_account)
