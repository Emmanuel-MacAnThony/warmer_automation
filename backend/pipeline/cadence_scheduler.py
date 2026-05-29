"""
Cadence scheduler.

A single background loop that, every TICK_SECONDS, finds enrollments whose next
step is due and sends it — reusing the same variable resolution + EmailSender as
the batch runner. State lives entirely in the DB (sequence_enrollments), so the
loop is stateless and restart-safe: after any crash/sleep/deploy the next tick
simply re-queries due rows and catches up.

Started from the FastAPI lifespan; stopped on shutdown.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Optional

from backend.infra.db import sequence_repo as seq_repo
from backend.infra.db.campaign_repo import (
    get_campaign_template_by_id, send_contact, sync_campaign_sent_count,
)
from backend.infra.email import OutboundEmail
from backend.infra.email.factory import build_sender
from backend.outreach.variable_resolver import resolve_contact

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
REPLY_POLL_SECONDS = 120   # reply detection poll cadence (Gmail API; rate-limited)
REPLY_BATCH_SIZE = 250     # enrollments checked per poll; rotated by last_reply_check_at
_task: Optional[asyncio.Task] = None
_reply_task: Optional[asyncio.Task] = None
_lock = asyncio.Lock()        # ensure send-ticks never overlap
_reply_lock = asyncio.Lock()  # ensure reply-polls never overlap


async def _send_one(sender, due: dict, template: dict, test_recipient: Optional[str]) -> tuple[bool, Optional[str], Optional[str]]:
    """Resolve + send a single step. Returns (ok, message_id, thread_id)."""
    resolved = resolve_contact(template["subject"], template["body"], due)
    snap = due.get("contact_snapshot") or {}
    name = snap.get("name", "") or snap.get("email", "")

    if test_recipient:
        to_email = test_recipient
        subject = f"[TEST → {name}] {resolved['rendered_subject']}"
    else:
        to_email = (snap.get("email") or "").strip()
        subject = resolved["rendered_subject"]

    if not to_email:
        return False, None, None  # caller stops the enrollment (nothing to send to)

    result = await sender.send(OutboundEmail(
        to=to_email, subject=subject, body_html=resolved["rendered_body"],
    ))
    return bool(result.ok), getattr(result, "message_id", None), getattr(result, "thread_id", None)


async def tick() -> int:
    """Process one batch of due enrollments. Returns number of steps sent."""
    due = await seq_repo.get_due_enrollments(limit=200)
    if not due:
        return 0

    # Group by sequence so we build a sender + load steps once per sequence.
    by_seq: dict[int, list[dict]] = defaultdict(list)
    for d in due:
        by_seq[d["sequence_id"]].append(d)

    sent_total = 0
    touched_campaigns: set[int] = set()

    for seq_id, enrollments in by_seq.items():
        seq = await seq_repo.get_sequence(seq_id)
        if not seq or seq["status"] != "active":
            continue

        steps = await seq_repo.get_sequence_steps(seq_id)
        steps_by_num = {s["step_number"]: s for s in steps}
        max_step = max(steps_by_num) if steps_by_num else 0

        sender_emails = seq.get("sender_emails") or []
        test_recipient = seq.get("test_recipient") or None
        try:
            sender = await build_sender(sender_emails[0] if sender_emails else None)
        except Exception as e:
            logger.warning(f"[cadence seq={seq_id}] no sender available: {e}")
            continue

        for d in enrollments:
            step = steps_by_num.get(d["current_step"])
            if not step:
                await seq_repo.finish_enrollment(d["enrollment_id"], "completed")
                continue

            template = await get_campaign_template_by_id(step["template_id"])
            if not template:
                logger.warning(f"[cadence seq={seq_id}] step {d['current_step']} template missing — stopping enrollment {d['enrollment_id']}")
                await seq_repo.finish_enrollment(d["enrollment_id"], "stopped")
                continue

            try:
                ok, message_id, thread_id = await _send_one(sender, d, template, test_recipient)
            except Exception as e:
                logger.warning(f"[cadence seq={seq_id}] send error on enrollment {d['enrollment_id']}: {e}")
                continue  # leave active → retried next tick

            if not ok:
                # No deliverable address → can't ever send; stop it.
                await seq_repo.finish_enrollment(d["enrollment_id"], "stopped")
                continue

            # Mark the contact reached (first real send) + remember the draft.
            if not test_recipient:
                try:
                    await send_contact(d["campaign_contact_id"], resolve_contact(
                        template["subject"], template["body"], d)["rendered_body"])
                except Exception:
                    pass

            sent_total += 1
            touched_campaigns.add(d["campaign_id"])

            next_step = d["current_step"] + 1
            if next_step > max_step:
                await seq_repo.finish_enrollment(d["enrollment_id"], "completed", message_id=message_id, thread_id=thread_id)
            else:
                delay = steps_by_num[next_step]["delay_days"]
                await seq_repo.advance_enrollment(d["enrollment_id"], next_step, delay, message_id=message_id, thread_id=thread_id)

            # Per-sender rate limit
            await asyncio.sleep(getattr(sender, "rate_limit_ms", 200) / 1000)

        # Sequence is done when no enrollments are still 'active' (all completed,
        # replied, stopped, or bounced). Flip the badge so the UI reflects reality
        # instead of forever showing 'active' for an empty sequence.
        try:
            if await seq_repo.count_active_enrollments(seq_id) == 0:
                await seq_repo.set_sequence_status(seq_id, "completed")
                logger.info(f"[cadence seq={seq_id}] all enrollments done — sequence marked completed")
        except Exception as e:
            logger.warning(f"[cadence seq={seq_id}] could not auto-complete: {e}")

    for cid in touched_campaigns:
        try:
            await sync_campaign_sent_count(cid)
        except Exception:
            pass

    if sent_total:
        logger.info(f"[cadence] tick sent {sent_total} step(s)")
    return sent_total


async def poll_replies() -> int:
    """
    Reply detection: for active enrollments that have sent an email, check their
    Gmail thread for a reply. On reply → stop the sequence for that contact.
    Only works for the Gmail provider (smtp/resend have no thread reading).
    Returns the number of enrollments stopped for replying.
    """
    # Rotating batch: ordered by last_reply_check_at (oldest first), so over
    # successive cycles every active enrollment is covered fairly — no stuck window,
    # bounded Gmail API usage even with thousands of live enrollments.
    candidates = await seq_repo.get_enrollments_awaiting_reply(limit=REPLY_BATCH_SIZE)
    if not candidates:
        return 0

    # Group by sequence so we build one Gmail sender per sequence's account.
    by_seq: dict[int, list[dict]] = defaultdict(list)
    for c in candidates:
        by_seq[c["sequence_id"]].append(c)

    checked_ids: list[int] = []
    replied_total = 0
    for seq_id, rows in by_seq.items():
        sender_emails = rows[0].get("sender_emails") or []
        try:
            sender = await build_sender(sender_emails[0] if sender_emails else None)
        except Exception:
            continue
        # Only Gmail supports thread-based reply detection.
        check = getattr(sender, "check_thread_replied", None)
        if not check:
            continue

        for r in rows:
            try:
                if await check(r["last_thread_id"]):
                    await seq_repo.finish_enrollment(r["enrollment_id"], "replied")
                    replied_total += 1
                    logger.info(f"[cadence] enrollment {r['enrollment_id']} replied — sequence stopped")
                checked_ids.append(r["enrollment_id"])
            except Exception as e:
                msg = str(e)
                if "insufficientPermissions" in msg or "insufficient authentication scopes" in msg:
                    # Token lacks the read scope — every thread on this account will fail.
                    # Log once and stop checking this account this cycle (don't stamp,
                    # so they're retried after the account is reconnected).
                    acct = (rows[0].get("sender_emails") or ["?"])[0]
                    logger.warning(
                        f"[cadence] reply detection disabled for {acct}: account needs the Gmail read "
                        f"scope. Reconnect Gmail (disconnect + reconnect) to enable stop-on-reply."
                    )
                    break
                logger.debug(f"[cadence] reply check error on enrollment {r['enrollment_id']}: {e}")
                checked_ids.append(r["enrollment_id"])  # rotate it back anyway
            await asyncio.sleep(0.1)  # gentle on the Gmail API

    # Rotate everyone we touched to the back of the queue.
    await seq_repo.mark_reply_checked(checked_ids)

    if replied_total:
        logger.info(f"[cadence] reply poll stopped {replied_total} enrollment(s)")
    return replied_total


async def _reply_loop() -> None:
    logger.info("Cadence reply-poll started")
    while True:
        try:
            async with _reply_lock:
                await poll_replies()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Reply poll failed (non-fatal): {e}", exc_info=True)
        await asyncio.sleep(REPLY_POLL_SECONDS)


async def _loop() -> None:
    logger.info("Cadence scheduler started")
    while True:
        try:
            async with _lock:
                await tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Cadence tick failed (non-fatal): {e}", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)


def start() -> None:
    global _task, _reply_task
    if not (_task and not _task.done()):
        _task = asyncio.create_task(_loop(), name="cadence-scheduler")
    if not (_reply_task and not _reply_task.done()):
        _reply_task = asyncio.create_task(_reply_loop(), name="cadence-reply-poll")


async def stop() -> None:
    global _task, _reply_task
    for t in (_task, _reply_task):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    _task = None
    _reply_task = None
