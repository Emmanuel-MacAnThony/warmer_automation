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
from backend.infra.email.interfaces import (
    BounceDetector,
    EmailProvider,
    EmailSender,
    ReplyDetector,
)
from backend.infra.email.types import BounceEvent, MessageRef, OutboundEmail, SendResult

logger = logging.getLogger(__name__)


def _load_client_secrets() -> dict:
    """Return client_id / client_secret from the OAuth config (env JSON or file)."""
    data = Config.google_client_config()
    return data.get("web") or data.get("installed") or {}


class GmailSender(EmailSender):
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


class GmailReplyDetector(ReplyDetector):
    """
    ReplyDetector adapter over a GmailSender. Shares the sender's OAuth
    state (token, refresh, DB persistence) — no duplication.

    Reads MessageRef.thread_id to query the Gmail thread API. Returns False
    if no thread id is present.
    """

    def __init__(self, sender: "GmailSender") -> None:
        self._sender = sender

    async def check_replied(self, ref: MessageRef) -> bool:
        if not ref.thread_id:
            return False
        return await self._sender.check_thread_replied(ref.thread_id)


class GmailDSNScanner(BounceDetector):
    """
    BounceDetector adapter for Gmail OAuth accounts (Phase A layer 3).

    Reads the sender's own inbox for DSN (Delivery Status Notification)
    messages from mailer-daemon@/postmaster@, parses each per RFC 3464 to
    extract the dead recipient + SMTP status + the original Message-ID,
    and returns them as neutral BounceEvent rows.

    Incremental: the Gmail history-list cursor lives on gmail_tokens
    .last_dsn_history_id. After each successful poll we advance the cursor
    so the next call processes ONLY new DSNs — not the whole inbox.

    First-run / cursor-expired path falls back to messages.list since the
    given `since` timestamp (Gmail's history retention is ~7 days).
    """

    def __init__(self, sender: "GmailSender") -> None:
        self._sender = sender

    async def fetch_bounces(self, since: datetime) -> list[BounceEvent]:
        from backend.infra.db.gmail_repo import get_dsn_cursor, update_dsn_cursor

        await self._sender._ensure_fresh_token()
        cursor = await get_dsn_cursor(self._sender._email)

        events, new_cursor = await asyncio.to_thread(
            self._fetch_sync,
            self._sender._access_token,
            self._sender._refresh_token,
            cursor,
            since,
        )
        if new_cursor:
            await update_dsn_cursor(self._sender._email, new_cursor)
        return events

    # ── Sync work (Gmail API + RFC 3464 parse) ──────────────────────────────

    def _fetch_sync(
        self,
        access_token: str,
        refresh_token: Optional[str],
        cursor: Optional[str],
        since: datetime,
    ) -> tuple[list[BounceEvent], Optional[str]]:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        secrets = _load_client_secrets()
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=secrets.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=secrets.get("client_id"),
            client_secret=secrets.get("client_secret"),
        )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        msg_ids: list[str] = []
        new_cursor: Optional[str] = None

        # ── Incremental path: history.list since the saved cursor ────────────
        if cursor:
            try:
                hist = service.users().history().list(
                    userId="me", startHistoryId=cursor,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                ).execute()
                for h in hist.get("history", []):
                    for m in h.get("messagesAdded", []):
                        mid = m.get("message", {}).get("id")
                        if mid:
                            msg_ids.append(mid)
                new_cursor = hist.get("historyId")
            except HttpError as e:
                # 404 = cursor expired (Gmail history retention ~7 days).
                # Drop to the bootstrap path so we scan recent DSNs by query.
                if e.status_code == 404:
                    logger.info(f"[GmailDSNScanner] cursor {cursor!r} expired — falling back to messages.list")
                    cursor = None
                else:
                    raise

        # ── Bootstrap path: messages.list filtered to recent DSN-like mail ───
        if not cursor:
            since_unix = int(since.timestamp())
            query = f"from:(mailer-daemon OR postmaster) after:{since_unix}"
            try:
                listed = service.users().messages().list(
                    userId="me", q=query, maxResults=100,
                ).execute()
                msg_ids = [m["id"] for m in listed.get("messages", []) if "id" in m]
            except HttpError as e:
                logger.warning(f"[GmailDSNScanner] messages.list failed: {e}")
                msg_ids = []
            # Seed the cursor from the current historyId so the next call is incremental.
            try:
                profile = service.users().getProfile(userId="me").execute()
                new_cursor = profile.get("historyId")
            except HttpError as e:
                logger.warning(f"[GmailDSNScanner] getProfile failed: {e}")

        # ── Fetch + parse each candidate ─────────────────────────────────────
        events: list[BounceEvent] = []
        for mid in msg_ids:
            try:
                msg = service.users().messages().get(
                    userId="me", id=mid, format="raw",
                ).execute()
                ev = self._parse_dsn(msg.get("raw", ""), mid)
                if ev:
                    events.append(ev)
            except Exception as e:
                logger.warning(f"[GmailDSNScanner] parse failed on {mid}: {e}")
                continue

        return events, new_cursor

    @staticmethod
    def _parse_dsn(raw_b64: str, gmail_msg_id: str) -> Optional[BounceEvent]:
        """
        Parse a Gmail raw message (urlsafe-b64) into a BounceEvent.

        Returns None if the message isn't a recognisable DSN (mailer-daemon
        notification with a message/delivery-status part). RFC 3464:
            multipart/report; report-type=delivery-status
              ├── text/plain                  (human notice)
              ├── message/delivery-status     (machine fields we want)
              └── message/rfc822(-headers)    (the original message headers)
        """
        if not raw_b64:
            return None
        try:
            import base64
            from email import message_from_bytes
            from email.policy import default as default_policy
            raw_bytes = base64.urlsafe_b64decode(raw_b64)
            parsed = message_from_bytes(raw_bytes, policy=default_policy)
        except Exception:
            return None

        sender = (parsed.get("From") or "").lower()
        if "mailer-daemon" not in sender and "postmaster" not in sender:
            return None

        recipient: Optional[str] = None
        status_code: Optional[str] = None
        diagnostic: Optional[str] = None
        original_msg_id: Optional[str] = None

        for part in parsed.walk():
            ctype = part.get_content_type()
            if ctype == "message/delivery-status":
                payload = part.get_payload()
                if isinstance(payload, list):
                    # Skip the per-message block (index 0) — we want the per-recipient ones.
                    for block in payload:
                        fr = block.get("Final-Recipient") or block.get("Original-Recipient")
                        if fr and not recipient:
                            # "rfc822; alice@dead.com"
                            recipient = fr.split(";", 1)[-1].strip().lower()
                        st = block.get("Status")
                        if st and not status_code:
                            status_code = st.strip()
                        dc = block.get("Diagnostic-Code")
                        if dc and not diagnostic:
                            diagnostic = dc.strip()
            elif ctype in ("message/rfc822", "message/rfc822-headers"):
                payload = part.get_payload()
                if isinstance(payload, list) and payload:
                    orig = payload[0]
                    mid = orig.get("Message-ID") or orig.get("Message-Id")
                    if mid:
                        original_msg_id = mid.strip().strip("<>")

        if not recipient or not status_code:
            return None

        return BounceEvent(
            message_ref=MessageRef(message_id=original_msg_id),
            recipient=recipient,
            hard=status_code.startswith("5"),
            reason=diagnostic or status_code,
            detected_at=datetime.now(timezone.utc),
            event_id=gmail_msg_id,
            smtp_status=status_code,
        )


# ── Provider entry point (called by factory.py via importlib) ────────────────

async def build(sender_account=None) -> EmailProvider:
    """
    Build an EmailProvider for a stored Gmail OAuth token.

    Gmail supports all three capabilities: send + reply detection (thread
    reading via gmail.metadata scope) + bounce detection (DSN scanning via
    the same scope, since DSNs land in the sender's own inbox).
    """
    from backend.infra.db.gmail_repo import get_gmail_token
    token = await get_gmail_token(sender_account)
    if not token:
        label = sender_account or "any connected account"
        raise ValueError(
            f"No OAuth token found for {label}. "
            "Connect an account via /auth/gmail first."
        )
    sender = GmailSender(token)
    return EmailProvider(
        sender=sender,
        reply_detector=GmailReplyDetector(sender),
        bounce_detector=GmailDSNScanner(sender),
    )
