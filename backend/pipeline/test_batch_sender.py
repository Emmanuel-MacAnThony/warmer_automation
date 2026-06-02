"""
Tests for the batch send runner — observable behavior only.

We mock all I/O (DB, email) and verify what the runner emits and calls
under each branch condition:

  Runner lifecycle
    - Happy path: all contacts sent, correct SSE events, counts, status
    - Pause signal at chunk boundary: 'paused' event, no 'complete', clean exit
    - Pause carries already-sent count from prior chunk
    - Cancel signal at chunk boundary: 'cancelled' event, clean exit

  Sender selection
    - Round-robin across two senders: each gets half the contacts
    - Fallback to default sender when sender_emails is empty

  Retry logic
    - First attempt fails, second succeeds → contact counted as sent
    - Both attempts fail → contact counted as failed

  Edge cases
    - Contact with no email address → failed, no send call made
    - Template not found → job marked failed, error event emitted
    - build_sender raises → job marked failed

  Checkpointing
    - bulk_mark_sent_contacts called once per chunk

  SSE registry
    - register / emit / unregister lifecycle
    - Emitting to an unregistered job is a no-op

  Email infrastructure
    - DryRunSender always returns ok=True, no I/O
    - DryRunSender satisfies the EmailSender Protocol (isinstance)
    - Factory returns DryRunSender when EMAIL_DRY_RUN=true
    - Factory raises ValueError for unknown provider
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from backend.infra.email import OutboundEmail, SendResult
from backend.pipeline import batch_sender


# ── Shared helpers ────────────────────────────────────────────────────────────

def _job(job_id=1, status="pending", total=0, sent=0, failed=0,
         sender_emails=None, template_id=10, campaign_id=1,
         tier="tier_1", scope="unsent"):
    return {
        "id": job_id, "campaign_id": campaign_id, "template_id": template_id,
        "tier": tier, "scope": scope, "status": status,
        "total": total, "sent": sent, "failed": failed,
        "sender_emails": sender_emails or [],
    }


def _template(tid=10):
    return {"id": tid, "subject": "Hi [first_name]", "body": "<p>Body</p>"}


def _contact(cid, name="Alice", email="alice@example.com"):
    return {
        "id": cid,
        "contact_snapshot": {"name": name, "email": email},
        "tier": "tier_1",
    }


def _resolved():
    return {
        "rendered_subject": "Hi Alice",
        "rendered_body": "<p>Body</p>",
        "resolved_vars": ["first_name"],
        "fallback_vars": [],
        "omitted_vars": [],
    }


class MockSender:
    """Controllable in-memory sender — no I/O. Cycles through supplied results."""
    rate_limit_ms = 0

    def __init__(self, results=None):
        self._results = results or []
        self._idx = 0
        self.sent_to: list[str] = []

    async def send(self, email: OutboundEmail) -> SendResult:
        self.sent_to.append(email.to)
        if self._results:
            r = self._results[self._idx % len(self._results)]
            self._idx += 1
            return r
        return SendResult(ok=True, message_id="msg-1")

    async def health_check(self) -> bool:
        return True


async def _run_and_drain(job_id: int = 1) -> list[dict]:
    """Run the batch sender, await completion, return all SSE events (no SENTINEL)."""
    q = batch_sender.register(job_id)
    await batch_sender.run(job_id)
    events = []
    while not q.empty():
        item = q.get_nowait()
        if item is not batch_sender.SENTINEL:
            events.append(item)
    return events


def _patch_runner(
    *,
    job_seq,                    # list of dicts returned by get_batch_send_job on successive calls
    contacts,
    sender,
    template=None,
    update_mock=None,
    bulk_mock=None,
    checkpoint_size=None,
):
    """Return a context-manager stack for a full runner mock."""
    from contextlib import ExitStack
    from unittest.mock import patch

    patches = [
        patch(
            "backend.pipeline.batch_sender.get_batch_send_job",
            AsyncMock(side_effect=job_seq),
        ),
        patch(
            "backend.pipeline.batch_sender.get_campaign_template_by_id",
            AsyncMock(return_value=template or _template()),
        ),
        patch(
            "backend.pipeline.batch_sender.get_pending_contacts_for_job",
            AsyncMock(return_value=contacts),
        ),
        patch(
            "backend.pipeline.batch_sender.update_batch_send_job",
            update_mock or AsyncMock(),
        ),
        patch(
            "backend.pipeline.batch_sender.bulk_mark_sent_contacts",
            bulk_mock or AsyncMock(),
        ),
        patch(
            "backend.pipeline.batch_sender.build_sender",
            AsyncMock(return_value=sender),
        ),
        patch(
            "backend.pipeline.batch_sender.resolve_contact",
            return_value=_resolved(),
        ),
        patch("asyncio.sleep", AsyncMock()),
    ]
    if checkpoint_size is not None:
        patches.append(
            patch("backend.pipeline.batch_sender.CHECKPOINT_SIZE", checkpoint_size)
        )

    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ── Runner lifecycle ──────────────────────────────────────────────────────────

async def test_happy_path_completes_all_contacts():
    """All 3 contacts sent → complete event with correct counts, no errors."""
    contacts = [_contact(i) for i in range(3)]
    sender = MockSender()

    with _patch_runner(
        job_seq=[_job(total=3), _job(status="running")],
        contacts=contacts,
        sender=sender,
    ):
        events = await _run_and_drain()

    types = [e["type"] for e in events]
    assert "start" in types
    assert "progress" in types
    assert "complete" in types
    assert "error" not in types

    complete = next(e for e in events if e["type"] == "complete")
    assert complete["sent"] == 3
    assert complete["failed"] == 0
    assert len(sender.sent_to) == 3


async def test_start_event_carries_total():
    """Start event includes the correct total contact count."""
    contacts = [_contact(i) for i in range(2)]
    with _patch_runner(
        job_seq=[_job(total=2), _job(status="running")],
        contacts=contacts,
        sender=MockSender(),
    ):
        events = await _run_and_drain()

    start = next(e for e in events if e["type"] == "start")
    assert start["total"] == 2
    assert start["sent"] == 0


async def test_update_batch_send_job_called_with_completed():
    """update_batch_send_job is called with status='completed' at the end."""
    update_mock = AsyncMock()
    contacts = [_contact(1)]

    with _patch_runner(
        job_seq=[_job(total=1), _job(status="running")],
        contacts=contacts,
        sender=MockSender(),
        update_mock=update_mock,
    ):
        await _run_and_drain()

    call_kwargs = [str(c) for c in update_mock.call_args_list]
    assert any("completed" in kw for kw in call_kwargs)


# ── Pause ─────────────────────────────────────────────────────────────────────

async def test_pause_at_chunk_boundary_emits_paused_not_complete():
    """'paused' status at boundary → 'paused' event emitted, 'complete' never."""
    with _patch_runner(
        job_seq=[_job(total=1), _job(status="paused")],
        contacts=[_contact(1)],
        sender=MockSender(),
    ):
        events = await _run_and_drain()

    types = [e["type"] for e in events]
    assert "paused" in types
    assert "complete" not in types


async def test_pause_event_includes_progress_from_prior_chunk():
    """Paused event reflects contacts sent before the pause signal arrived."""
    # CHECKPOINT_SIZE=1 so chunk 0 processes contact 0, checkpoint fires,
    # then chunk 1 hits the boundary and sees 'paused'.
    contacts = [_contact(0), _contact(1)]

    with _patch_runner(
        job_seq=[
            _job(total=2),           # initial load
            _job(status="running"),  # chunk 0 boundary — proceed
            _job(status="paused"),   # chunk 1 boundary — pause
        ],
        contacts=contacts,
        sender=MockSender(),
        checkpoint_size=1,
    ):
        events = await _run_and_drain()

    paused = next(e for e in events if e["type"] == "paused")
    assert paused["sent"] == 1


# ── Cancel ────────────────────────────────────────────────────────────────────

async def test_cancel_at_chunk_boundary_emits_cancelled_not_complete():
    """'cancelled' status at boundary → 'cancelled' event, 'complete' never."""
    with _patch_runner(
        job_seq=[_job(total=1), _job(status="cancelled")],
        contacts=[_contact(1)],
        sender=MockSender(),
    ):
        events = await _run_and_drain()

    types = [e["type"] for e in events]
    assert "cancelled" in types
    assert "complete" not in types
    assert "paused" not in types


# ── Multi-sender round-robin ──────────────────────────────────────────────────

async def test_round_robin_two_senders_split_contacts_evenly():
    """Four contacts with two senders → each sender gets exactly two sends."""
    contacts = [_contact(i) for i in range(4)]
    sender_a = MockSender()
    sender_b = MockSender()

    with (
        patch(
            "backend.pipeline.batch_sender.get_batch_send_job",
            AsyncMock(side_effect=[
                _job(total=4, sender_emails=["a@x.com", "b@x.com"]),
                _job(status="running"),
            ]),
        ),
        patch(
            "backend.pipeline.batch_sender.get_campaign_template_by_id",
            AsyncMock(return_value=_template()),
        ),
        patch(
            "backend.pipeline.batch_sender.get_pending_contacts_for_job",
            AsyncMock(return_value=contacts),
        ),
        patch("backend.pipeline.batch_sender.update_batch_send_job", AsyncMock()),
        patch("backend.pipeline.batch_sender.bulk_mark_sent_contacts", AsyncMock()),
        patch(
            "backend.pipeline.batch_sender.build_sender",
            AsyncMock(side_effect=[sender_a, sender_b]),
        ),
        patch("backend.pipeline.batch_sender.resolve_contact", return_value=_resolved()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        await _run_and_drain()

    assert len(sender_a.sent_to) == 2
    assert len(sender_b.sent_to) == 2


async def test_falls_back_to_default_sender_when_no_accounts_specified():
    """Empty sender_emails → build_sender() called once with no account arg."""
    build_mock = AsyncMock(return_value=MockSender())

    with (
        patch(
            "backend.pipeline.batch_sender.get_batch_send_job",
            AsyncMock(side_effect=[_job(total=1, sender_emails=[]), _job(status="running")]),
        ),
        patch(
            "backend.pipeline.batch_sender.get_campaign_template_by_id",
            AsyncMock(return_value=_template()),
        ),
        patch(
            "backend.pipeline.batch_sender.get_pending_contacts_for_job",
            AsyncMock(return_value=[_contact(1)]),
        ),
        patch("backend.pipeline.batch_sender.update_batch_send_job", AsyncMock()),
        patch("backend.pipeline.batch_sender.bulk_mark_sent_contacts", AsyncMock()),
        patch("backend.pipeline.batch_sender.build_sender", build_mock),
        patch("backend.pipeline.batch_sender.resolve_contact", return_value=_resolved()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        await _run_and_drain()

    # Called once with no positional sender_account
    build_mock.assert_called_once_with()


# ── Retry logic ───────────────────────────────────────────────────────────────

async def test_retry_on_first_failure_counts_as_sent():
    """First send fails, retry succeeds → contact counted as sent not failed."""
    sender = MockSender(results=[
        SendResult(ok=False, error="timeout"),
        SendResult(ok=True, message_id="msg-retry"),
    ])

    with _patch_runner(
        job_seq=[_job(total=1), _job(status="running")],
        contacts=[_contact(1)],
        sender=sender,
    ):
        events = await _run_and_drain()

    assert len(sender.sent_to) == 2  # two attempts
    complete = next(e for e in events if e["type"] == "complete")
    assert complete["sent"] == 1
    assert complete["failed"] == 0


async def test_both_attempts_fail_counts_as_failed():
    """Both attempts fail → contact counted as failed."""
    sender = MockSender(results=[
        SendResult(ok=False, error="refused"),
        SendResult(ok=False, error="refused"),
    ])

    with _patch_runner(
        job_seq=[_job(total=1), _job(status="running")],
        contacts=[_contact(1)],
        sender=sender,
    ):
        events = await _run_and_drain()

    complete = next(e for e in events if e["type"] == "complete")
    assert complete["failed"] == 1
    assert complete["sent"] == 0


# ── Missing email ─────────────────────────────────────────────────────────────

async def test_contact_with_no_email_skipped_no_send_call():
    """Contact with empty email → counted as failed, send() never called."""
    sender = MockSender()

    with _patch_runner(
        job_seq=[_job(total=1), _job(status="running")],
        contacts=[_contact(1, email="")],
        sender=sender,
    ):
        events = await _run_and_drain()

    assert len(sender.sent_to) == 0
    complete = next(e for e in events if e["type"] == "complete")
    assert complete["failed"] == 1
    assert complete["sent"] == 0


# ── Error paths ───────────────────────────────────────────────────────────────

async def test_template_not_found_marks_job_failed():
    """No template → update called with status='failed', error event emitted."""
    update_mock = AsyncMock()

    with (
        patch(
            "backend.pipeline.batch_sender.get_batch_send_job",
            AsyncMock(return_value=_job()),
        ),
        patch(
            "backend.pipeline.batch_sender.get_campaign_template_by_id",
            AsyncMock(return_value=None),
        ),
        patch("backend.pipeline.batch_sender.update_batch_send_job", update_mock),
    ):
        events = await _run_and_drain()

    assert any(e["type"] == "error" for e in events)
    update_mock.assert_called_once_with(1, status="failed", error="Template not found")


async def test_no_sender_available_marks_job_failed():
    """build_sender raises for all accounts → error event emitted."""
    with (
        patch(
            "backend.pipeline.batch_sender.get_batch_send_job",
            AsyncMock(return_value=_job()),
        ),
        patch(
            "backend.pipeline.batch_sender.get_campaign_template_by_id",
            AsyncMock(return_value=_template()),
        ),
        patch(
            "backend.pipeline.batch_sender.get_pending_contacts_for_job",
            AsyncMock(return_value=[_contact(1)]),
        ),
        patch("backend.pipeline.batch_sender.update_batch_send_job", AsyncMock()),
        patch(
            "backend.pipeline.batch_sender.build_sender",
            AsyncMock(side_effect=RuntimeError("No credentials")),
        ),
    ):
        events = await _run_and_drain()

    assert any(e["type"] == "error" for e in events)


# ── Checkpointing ─────────────────────────────────────────────────────────────

async def test_checkpoint_called_once_per_chunk():
    """bulk_mark_sent_contacts is called exactly once per CHECKPOINT_SIZE chunk."""
    contacts = [_contact(i) for i in range(5)]
    bulk_mock = AsyncMock()

    with _patch_runner(
        job_seq=[
            _job(total=5),
            _job(status="running"),   # chunk [0,1]
            _job(status="running"),   # chunk [2,3]
            _job(status="running"),   # chunk [4]
        ],
        contacts=contacts,
        sender=MockSender(),
        bulk_mock=bulk_mock,
        checkpoint_size=2,
    ):
        await _run_and_drain()

    assert bulk_mock.call_count == 3  # ceil(5/2)


# ── SSE registry ──────────────────────────────────────────────────────────────

async def test_sse_register_emit_unregister_lifecycle():
    """register creates queue; _emit enqueues; unregister removes."""
    job_id = 777
    q = batch_sender.register(job_id)
    assert batch_sender.get_queue(job_id) is q

    await batch_sender._emit(job_id, {"type": "ping"})
    item = q.get_nowait()
    assert item == {"type": "ping"}

    batch_sender.unregister(job_id)
    assert batch_sender.get_queue(job_id) is None


async def test_sse_emit_to_unregistered_job_is_noop():
    """Emitting to an unregistered job silently does nothing."""
    await batch_sender._emit(99999, {"type": "ghost"})


async def test_sentinel_placed_in_queue_after_run():
    """SENTINEL is always placed in the SSE queue after run() finishes."""
    q = batch_sender.register(2)

    with (
        patch(
            "backend.pipeline.batch_sender.get_batch_send_job",
            AsyncMock(return_value=None),  # job not found → runner exits early
        ),
    ):
        await batch_sender.run(2)

    found_sentinel = False
    while not q.empty():
        if q.get_nowait() is batch_sender.SENTINEL:
            found_sentinel = True
            break
    assert found_sentinel


# ── DryRunSender ─────────────────────────────────────────────────────────────

async def test_dry_run_sender_always_returns_ok():
    """DryRunSender.send always succeeds without any network I/O."""
    from backend.infra.email.adapters.dry_run import DryRunSender
    sender = DryRunSender()
    result = await sender.send(OutboundEmail(
        to="alice@example.com",
        subject="Test",
        body_html="<p>Hello</p>",
    ))
    assert result.ok is True
    assert result.message_id == "dry-run"


async def test_dry_run_sender_health_check_returns_true():
    from backend.infra.email.adapters.dry_run import DryRunSender
    assert await DryRunSender().health_check() is True


def test_dry_run_sender_satisfies_email_sender_protocol():
    """DryRunSender passes runtime isinstance check against EmailSender Protocol."""
    from backend.infra.email import EmailSender
    from backend.infra.email.adapters.dry_run import DryRunSender
    assert isinstance(DryRunSender(), EmailSender)


def test_dry_run_sender_has_zero_rate_limit():
    from backend.infra.email.adapters.dry_run import DryRunSender
    assert DryRunSender.rate_limit_ms == 0


# ── Factory ───────────────────────────────────────────────────────────────────

async def test_factory_dry_run_flag_returns_dry_run_sender():
    """EMAIL_DRY_RUN=true → factory returns DryRunSender regardless of provider."""
    from backend.infra.email.adapters.dry_run import DryRunSender
    from backend.infra.email.factory import build_sender

    # Config is imported locally inside build_sender, so patch the source module
    with patch("backend.config.Config") as cfg:
        cfg.EMAIL_DRY_RUN = True
        result = await build_sender()

    assert isinstance(result, DryRunSender)


async def test_factory_raises_for_unknown_provider():
    """Unknown EMAIL_PROVIDER → ValueError, not a silent failure."""
    from backend.infra.email.factory import build_sender

    with patch("backend.config.Config") as cfg:
        cfg.EMAIL_DRY_RUN = False
        cfg.EMAIL_PROVIDER = "carrier-pigeon"
        with pytest.raises(ValueError, match="carrier-pigeon"):
            await build_sender()
