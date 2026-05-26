"""
GmailSender — sends via the Gmail API using stored OAuth tokens.

Works for both personal Gmail (500/day) and Google Workspace (2000/day).
Token refresh is transparent: if the access token is within 5 minutes of
expiry the sender refreshes it automatically and writes the new token back
to gmail_tokens before sending.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from backend.config import Config
from backend.infra.email import EmailSender, OutboundEmail, SendResult

logger = logging.getLogger(__name__)


def _load_client_secrets() -> dict:
    """Return client_id / client_secret from the OAuth config (env JSON or file)."""
    data = Config.google_client_config()
    return data.get("web") or data.get("installed") or {}


class GmailSender:
    """
    Sends email via Gmail API (gmail.send scope).
    rate_limit_ms = 200  → 5 sends/sec (safe under personal quota).
    Set to 100 for Workspace accounts if higher throughput is needed.
    """

    rate_limit_ms: int = 200

    def __init__(self, token_row: dict) -> None:
        self._email: str = token_row["email"]
        self._access_token: str = token_row["access_token"]
        self._refresh_token: Optional[str] = token_row.get("refresh_token")
        raw_expiry = token_row.get("token_expiry")
        if isinstance(raw_expiry, str):
            self._token_expiry: Optional[datetime] = datetime.fromisoformat(raw_expiry)
        else:
            self._token_expiry = raw_expiry  # datetime or None

    # ── Token refresh ────────────────────────────────────────────────────────

    def _refresh_sync(self) -> tuple[str, Optional[datetime]]:
        """Blocking token refresh — run via asyncio.to_thread."""
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        secrets = _load_client_secrets()
        creds = Credentials(
            token=self._access_token,
            refresh_token=self._refresh_token,
            token_uri=secrets.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=secrets.get("client_id"),
            client_secret=secrets.get("client_secret"),
        )
        creds.refresh(Request())
        return creds.token, creds.expiry  # expiry is timezone-aware or None

    async def _ensure_fresh_token(self) -> None:
        if not self._token_expiry:
            return
        # Refresh if within 5 minutes of expiry
        cutoff = datetime.now(timezone.utc) + timedelta(minutes=5)
        expiry = self._token_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry > cutoff:
            return

        logger.info(f"[GmailSender] Refreshing token for {self._email}")
        new_token, new_expiry = await asyncio.to_thread(self._refresh_sync)
        self._access_token = new_token
        self._token_expiry = new_expiry

        # Persist new token to DB
        from backend.infra.db.gmail_repo import upsert_gmail_token
        await upsert_gmail_token(
            email=self._email,
            access_token=new_token,
            refresh_token=self._refresh_token,
            token_expiry=new_expiry,
        )

    # ── Send ─────────────────────────────────────────────────────────────────

    def _send_sync(self, email: OutboundEmail, access_token: str) -> SendResult:
        """Blocking Gmail API send — runs in thread pool."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        secrets = _load_client_secrets()
        creds = Credentials(
            token=access_token,
            refresh_token=self._refresh_token,
            token_uri=secrets.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=secrets.get("client_id"),
            client_secret=secrets.get("client_secret"),
        )

        msg = MIMEMultipart("alternative")
        msg["To"] = email.to
        msg["Subject"] = email.subject
        if email.from_name:
            msg["From"] = email.from_name  # Gmail replaces actual address; display name sticks
        if email.reply_to:
            msg["Reply-To"] = email.reply_to
        msg.attach(MIMEText(email.body_html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        try:
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            result = service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            return SendResult(ok=True, message_id=result.get("id"), thread_id=result.get("threadId"))
        except HttpError as e:
            is_rate_limit = e.status_code == 429 or (
                e.status_code == 403 and any(
                    phrase in str(e.reason).lower()
                    for phrase in ("rate limit", "user rate", "quota", "limit exceeded")
                )
            )
            retry_after: Optional[int] = None
            if is_rate_limit:
                try:
                    raw = (e.resp or {}).get("retry-after")
                    if raw:
                        retry_after = int(raw)
                except Exception:
                    pass
            return SendResult(
                ok=False,
                error=f"Gmail API error {e.status_code}: {e.reason}",
                rate_limited=is_rate_limit,
                retry_after_seconds=retry_after,
            )
        except Exception as e:
            return SendResult(ok=False, error=str(e))

    async def send(self, email: OutboundEmail) -> SendResult:
        await self._ensure_fresh_token()
        return await asyncio.to_thread(self._send_sync, email, self._access_token)

    # ── Reply detection ───────────────────────────────────────────────────────

    def _thread_has_reply_sync(self, thread_id: str, access_token: str) -> bool:
        """True if the thread contains a message NOT from this account (i.e. a reply)."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        secrets = _load_client_secrets()
        creds = Credentials(
            token=access_token,
            refresh_token=self._refresh_token,
            token_uri=secrets.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=secrets.get("client_id"),
            client_secret=secrets.get("client_secret"),
        )
        # Let exceptions propagate — the caller (reply poller) decides how to log,
        # so a missing scope is reported once per account, not once per thread.
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["From"],
        ).execute()
        me = (self._email or "").lower()
        for m in thread.get("messages", []):
            headers = (m.get("payload") or {}).get("headers", [])
            frm = next((h["value"] for h in headers if h.get("name") == "From"), "").lower()
            # A message whose From isn't us = a reply from the recipient.
            if me and me not in frm:
                return True
        return False

    async def check_thread_replied(self, thread_id: str) -> bool:
        if not thread_id:
            return False
        await self._ensure_fresh_token()
        return await asyncio.to_thread(self._thread_has_reply_sync, thread_id, self._access_token)

    async def health_check(self) -> bool:
        try:
            await self._ensure_fresh_token()
            return bool(self._access_token)
        except Exception:
            return False


# ── Provider entry point (called by factory.py via importlib) ────────────────

async def build(sender_account=None):
    """Build a GmailSender from a stored OAuth token."""
    from backend.infra.db.gmail_repo import get_gmail_token
    token = await get_gmail_token(sender_account)
    if not token:
        label = sender_account or "any connected account"
        raise ValueError(
            f"No OAuth token found for {label}. "
            "Connect an account via /auth/gmail first."
        )
    return GmailSender(token)
