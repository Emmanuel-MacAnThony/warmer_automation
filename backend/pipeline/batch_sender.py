"""
Batch Send Runner.

Picks up a batch_send_job from the DB, resolves template variables for each
pending contact, sends via the configured EmailSender, and checkpoints
progress every CHECKPOINT_SIZE contacts.

SSE events are pushed to an in-process asyncio.Queue keyed by job_id.
The GET /batch-jobs/{job_id}/events endpoint drains that queue.

Scale path: replace the asyncio.Queue with Redis pub/sub (batch_send:{job_id})
when running multiple server processes. Runner logic is untouched.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from backend.infra.db import suppression_repo as sup_repo
from backend.infra.db.campaign_repo import (
    bulk_mark_sent_contacts,
    get_batch_send_job,
    get_campaign_template_by_id,
    get_pending_contacts_for_job,
    sync_campaign_sent_count,
    update_batch_send_job,
)
from backend.infra.email import EmailSender, OutboundEmail
from backend.infra.email.factory import build_sender
from backend.outreach.email_validator import has_valid_mx, is_recipient_rejection
from backend.outreach.variable_resolver import resolve_contact

logger = logging.getLogger(__name__)

CHECKPOINT_SIZE = 25

# ── SSE event registry ───────────────────────────────────────────────────────

_queues: dict[int, asyncio.Queue] = {}
SENTINEL = object()


def register(job_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _queues[job_id] = q
    return q


def get_queue(job_id: int) -> Optional[asyncio.Queue]:
    return _queues.get(job_id)


def unregister(job_id: int) -> None:
    _queues.pop(job_id, None)


async def _emit(job_id: int, event: Any) -> None:
    q = _queues.get(job_id)
    if q:
        await q.put(event)


# ── Domain types ─────────────────────────────────────────────────────────────

@dataclass
class ContactSendResult:
    contact_id: int
    status: str          # 'sent' | 'failed'
    rendered_body: str


# ── Runner ───────────────────────────────────────────────────────────────────

async def recover() -> int:
    """
    Startup recovery — re-launch batch sends stranded by a deploy, crash, or sleep.

    Resume safety:
      - scope='unsent' (or fresh jobs with nothing sent): re-launch the runner.
        Already-sent contacts are status='sent', so the runner naturally skips them
        and continues with the remainder — no duplicate emails.
      - scope='everyone' that already sent some: PAUSE instead of resuming.
        Re-sending would re-email the already-contacted portion (we don't track
        which contacts this job already sent), so a human decides.
    Returns the number of jobs re-launched.
    """
    from backend.infra.db.campaign_repo import (
        get_running_batch_send_jobs, update_batch_send_job,
    )

    jobs = await get_running_batch_send_jobs()
    resumed = 0
    for job in jobs:
        jid = job["id"]
        scope = job.get("scope") or "unsent"
        already_sent = job.get("sent") or 0

        if scope == "everyone" and already_sent > 0:
            await update_batch_send_job(jid, status="paused")
            logger.info(
                f"[batch_send recover] job={jid}: scope=everyone, {already_sent} already sent "
                f"— paused to avoid duplicate sends (resume manually)"
            )
            continue

        register(jid)
        asyncio.create_task(run(jid), name=f"batch-send-{jid}")
        resumed += 1
        logger.info(f"[batch_send recover] job={jid}: resuming (scope={scope}, {already_sent} already sent)")

    return resumed


async def run(job_id: int) -> None:
    """
    Execute a batch send job end-to-end.

    Algorithm:
      1. Load job, template, and pending contacts from DB
      2. Build one EmailSender per sender_email (round-robin if multiple)
      3. For each chunk of CHECKPOINT_SIZE contacts:
           a. Check cancellation flag
           b. Resolve variables → build OutboundEmail → send → retry once on fail
           c. Rate-limit between sends (per-sender, independent)
           d. Checkpoint: bulk-mark sent in DB + update job counters
           e. Emit SSE progress event
      4. Mark job complete

    Crash recovery: contacts stay 'pending' until marked 'sent'. Re-running
    the job (or starting a new one with scope='unsent') resumes automatically.
    """
    start = time.monotonic()

    try:
        job = await get_batch_send_job(job_id)
        if not job:
            logger.error(f"[batch_send job={job_id}] Not found")
            return

        template = await get_campaign_template_by_id(job["template_id"])
        if not template:
            await update_batch_send_job(
                job_id, status="failed", error="Template not found"
            )
            await _emit(job_id, {"type": "error", "error": "Template not found"})
            return

        # ── Build senders ────────────────────────────────────────────────────
        sender_emails: list[str] = job.get("sender_emails") or []
        senders: list[EmailSender] = []

        for acct in sender_emails:
            try:
                senders.append(await build_sender(acct))
            except Exception as e:
                logger.warning(f"[batch_send job={job_id}] Skipping {acct}: {e}")

        if not senders:
            # Fall back to default configured sender
            try:
                senders.append(await build_sender())
            except Exception as e:
                msg = f"No email sender available: {e}"
                await update_batch_send_job(job_id, status="failed", error=msg)
                await _emit(job_id, {"type": "error", "error": msg})
                return

        # Mutable rotation — rate-limited senders are dropped mid-run
        active_senders: list[EmailSender] = list(senders)
        sender_idx = 0
        # Track last-send timestamp per sender object for independent rate limiting
        last_sent: dict[int, float] = {id(s): 0.0 for s in senders}
        # Largest retry_after hint seen across all rate-limited senders this run
        max_retry_after: Optional[int] = None

        # ── Test-mode recipient override ─────────────────────────────────────
        test_recipient: str | None = job.get("test_recipient") or None
        if test_recipient:
            logger.info(f"[batch_send job={job_id}] TEST MODE — all emails → {test_recipient}")

        # ── Load contacts ────────────────────────────────────────────────────
        contacts = await get_pending_contacts_for_job(
            campaign_id=job["campaign_id"],
            tier=job["tier"],
            scope=job.get("scope", "unsent"),
        )
        total = len(contacts)

        await update_batch_send_job(
            job_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            total=total,
        )
        await _emit(job_id, {"type": "start", "total": total, "sent": 0, "failed": 0})
        logger.info(f"[batch_send job={job_id}] Starting: {total} contacts, {len(senders)} sender(s)")

        total_sent = 0
        total_failed = 0

        # ── Main send loop ───────────────────────────────────────────────────
        for chunk_start in range(0, total, CHECKPOINT_SIZE):
            # Status check — re-read at each chunk boundary for cancel or pause
            current = await get_batch_send_job(job_id)
            if current and current["status"] == "cancelled":
                logger.info(f"[batch_send job={job_id}] Cancelled at contact {chunk_start}")
                await _emit(job_id, {
                    "type": "cancelled",
                    "sent": total_sent,
                    "failed": total_failed,
                    "total": total,
                })
                return
            if current and current["status"] == "paused":
                logger.info(f"[batch_send job={job_id}] Paused at contact {chunk_start}")
                await _emit(job_id, {
                    "type": "paused",
                    "sent": total_sent,
                    "failed": total_failed,
                    "total": total,
                })
                return

            chunk = contacts[chunk_start : chunk_start + CHECKPOINT_SIZE]
            chunk_results: list[ContactSendResult] = []
            all_rate_limited = False

            for contact in chunk:
                if not active_senders:
                    all_rate_limited = True
                    break

                # Variable resolution (done once per contact, reused across sender retries)
                resolved = resolve_contact(
                    template_subject=template["subject"],
                    template_body=template["body"],
                    contact=contact,
                )

                snap = contact.get("contact_snapshot") or {}
                contact_name = snap.get("name", "") or snap.get("email", "") or f"#{contact['id']}"

                if test_recipient:
                    to_email = test_recipient
                    subject_line = f"[TEST → {contact_name}] {resolved['rendered_subject']}"
                else:
                    to_email = snap.get("email", "").strip()
                    subject_line = resolved["rendered_subject"]

                if not test_recipient and not to_email:
                    logger.warning(
                        f"[batch_send job={job_id}] Contact {contact['id']} has no email — skipping"
                    )
                    total_failed += 1
                    chunk_results.append(
                        ContactSendResult(contact["id"], "failed", resolved["rendered_body"])
                    )
                    continue

                # ── Layer 1: MX preflight (production sends only) ─────────────
                # Catch domain-level dead addresses before we burn a send attempt.
                # The suppression makes them silent for every future job.
                if not test_recipient:
                    try:
                        mx_ok = await has_valid_mx(to_email)
                    except Exception as e:
                        logger.warning(f"[batch_send job={job_id}] MX preflight raised for {to_email}: {e}")
                        mx_ok = True  # defensive: don't false-flag on transient DNS
                    if not mx_ok:
                        await sup_repo.upsert_suppression(
                            to_email, reason="mx_invalid",
                            reason_text="Domain has no MX or A records",
                        )
                        await sup_repo.record_bounce(
                            email=to_email, source="batch", hard=True,
                            reason="mx_invalid: domain has no MX/A records",
                            batch_job_id=job_id,
                        )
                        logger.info(
                            f"[batch_send job={job_id}] MX preflight failed for {to_email} — suppressed"
                        )
                        total_failed += 1
                        chunk_results.append(
                            ContactSendResult(contact["id"], "failed", resolved["rendered_body"])
                        )
                        continue

                outbound = OutboundEmail(
                    to=to_email,
                    subject=subject_line,
                    body_html=resolved["rendered_body"],
                )

                # Try each active sender; drop rate-limited ones and fall through to the next
                result = None
                for _ in range(len(active_senders) + 1):
                    if not active_senders:
                        break

                    sender = active_senders[sender_idx % len(active_senders)]

                    elapsed_ms = (time.monotonic() - last_sent[id(sender)]) * 1000
                    wait_ms = max(0.0, sender.rate_limit_ms - elapsed_ms)
                    if wait_ms > 0:
                        await asyncio.sleep(wait_ms / 1000)

                    result = await sender.send(outbound)
                    last_sent[id(sender)] = time.monotonic()

                    if result.rate_limited:
                        acct = getattr(sender, "account_email", "?")
                        if result.retry_after_seconds is not None:
                            if max_retry_after is None or result.retry_after_seconds > max_retry_after:
                                max_retry_after = result.retry_after_seconds
                        active_senders.remove(sender)
                        remaining = len(active_senders)
                        logger.warning(
                            f"[batch_send job={job_id}] {acct} rate limited — "
                            f"dropped from rotation ({remaining} sender(s) remaining)"
                        )
                        # Don't advance idx — next sender slides into this position
                        continue

                    # Single retry on transient (non-rate-limit) failure
                    if not result.ok:
                        await asyncio.sleep(2)
                        result = await sender.send(outbound)
                        last_sent[id(sender)] = time.monotonic()

                    # Advance round-robin to next sender
                    if active_senders:
                        sender_idx = (sender_idx + 1) % len(active_senders)
                    break

                if not active_senders or result is None:
                    all_rate_limited = True
                    break

                if result.ok:
                    total_sent += 1
                    chunk_results.append(
                        ContactSendResult(contact["id"], "sent", resolved["rendered_body"])
                    )
                else:
                    # Layer 2: sync-error map. Gmail's response string matches a
                    # permanent recipient-rejection pattern → suppress + audit so
                    # this address is dead across every future sequence and batch.
                    if not test_recipient and is_recipient_rejection(result.error):
                        await sup_repo.upsert_suppression(
                            to_email, reason="sync_rejected",
                            reason_text=(result.error or "")[:300],
                        )
                        await sup_repo.record_bounce(
                            email=to_email, source="batch", hard=True,
                            reason=(result.error or "")[:300],
                            batch_job_id=job_id,
                        )
                        logger.info(
                            f"[batch_send job={job_id}] sync-rejection on {to_email} — suppressed: {result.error}"
                        )
                    total_failed += 1
                    chunk_results.append(
                        ContactSendResult(contact["id"], "failed", resolved["rendered_body"])
                    )
                    logger.warning(
                        f"[batch_send job={job_id}] Failed → {to_email}: {result.error}"
                    )

            # ── Checkpoint ───────────────────────────────────────────────────
            await bulk_mark_sent_contacts(chunk_results)
            await update_batch_send_job(job_id, sent=total_sent, failed=total_failed)
            await sync_campaign_sent_count(job["campaign_id"])

            if all_rate_limited:
                logger.warning(f"[batch_send job={job_id}] All senders rate limited — auto-pausing")
                retry_at_iso: Optional[str] = None
                if max_retry_after is not None:
                    retry_at_iso = (
                        datetime.now(timezone.utc) + timedelta(seconds=max_retry_after)
                    ).isoformat()
                await update_batch_send_job(
                    job_id, status="paused", sent=total_sent, failed=total_failed,
                    **({"retry_after": retry_at_iso} if retry_at_iso else {}),
                )
                await _emit(job_id, {
                    "type": "paused",
                    "reason": "rate_limited",
                    "retry_at": retry_at_iso,
                    "sent": total_sent,
                    "failed": total_failed,
                    "total": total,
                })
                return

            current_name = ""
            if chunk:
                current_name = (chunk[-1].get("contact_snapshot") or {}).get("name", "")

            await _emit(job_id, {
                "type": "progress",
                "sent": total_sent,
                "failed": total_failed,
                "total": total,
                "current": current_name,
            })
            logger.debug(
                f"[batch_send job={job_id}] Checkpoint: {total_sent}/{total} sent, {total_failed} failed"
            )

        # ── Complete ─────────────────────────────────────────────────────────
        duration = round(time.monotonic() - start, 1)
        await update_batch_send_job(
            job_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            sent=total_sent,
            failed=total_failed,
        )
        await sync_campaign_sent_count(job["campaign_id"])
        await _emit(job_id, {
            "type": "complete",
            "sent": total_sent,
            "failed": total_failed,
            "total": total,
            "duration_seconds": duration,
        })
        logger.info(
            f"[batch_send job={job_id}] Done: {total_sent} sent, {total_failed} failed, {duration}s"
        )

    except Exception as e:
        logger.error(f"[batch_send job={job_id}] Runner crashed: {e}", exc_info=True)
        await update_batch_send_job(job_id, status="failed", error=str(e))
        await _emit(job_id, {"type": "error", "error": str(e)})

    finally:
        await _emit(job_id, SENTINEL)
