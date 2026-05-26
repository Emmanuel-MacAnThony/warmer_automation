# Batch Send Runner — Use Case Specification

## What It Does

Executes an approved batch send job: resolves template variables for each pending
contact in a tier, sends each rendered email via the connected email account, and
checkpoints progress to the database. The runner does not generate content — the
template was already approved before this runs.

---

## Input Data

```
job_id: int
  └── resolves to:
      campaign_id:  int
      tier:         'tier_1' | 'tier_2' | 'tier_3'
      template_id:  int
        └── subject:   str                  # with {{variable}} slots
            body:      str                  # with {{variable}} slots
            variables: list[str]            # ["first_name", "topic_hook", ...]
      sender_id:    int                     # which connected account to send from
      pending_contacts: list[CampaignContact]
        └── contact_id:       int
            contact_snapshot: dict          # name, company, title, signals {...}
            warm_path_data:   dict | None   # connector, evidence
            tier:             str
```

`contact_snapshot.signals` is the only data the variable resolver reads.
`score_breakdown` is not needed here — it informed tier assignment upstream,
not variable resolution.

---

## Dependencies — All Behind Interfaces

### EmailSender (Protocol)

The runner never knows which email backend it is talking to.

```python
@dataclass
class OutboundEmail:
    to:         str
    subject:    str
    body_html:  str
    from_name:  str | None = None
    reply_to:   str | None = None

@dataclass
class SendResult:
    ok:         bool
    message_id: str | None = None   # provider message ID if available
    error:      str | None = None

class EmailSender(Protocol):
    async def send(self, email: OutboundEmail) -> SendResult: ...
    async def health_check(self) -> bool: ...
```

**Implementations:**

| Class | Backend | When used |
|---|---|---|
| `GmailSender` | Gmail API (OAuth) | Personal Gmail, single user |
| `WorkspaceSender` | Gmail API (OAuth) | Google Workspace account |
| `SMTPSender` | Generic SMTP | Any provider (Outlook, custom) |
| `MailtrapSender` | Mailtrap SMTP | Testing — accepts sends, never delivers |
| `DryRunSender` | No-op | Dev / CI — logs only, marks sent in DB |

`GmailSender` and `WorkspaceSender` are the same OAuth flow with different scopes
and quota ceilings. They can share implementation; which one is instantiated
depends on the account type stored at auth time.

`sender_id` is the authenticated account record. The factory reads its `provider`
field and instantiates the right implementation. The runner receives the interface
and never inspects the concrete type.

**Multi-account:** if multiple fundraisers send simultaneously, each job carries
its own `sender_id`. The runner is stateless — two jobs run concurrently, each
with its own sender instance, each rate-limited independently.

---

### JobStore (DB)

```python
class JobStore(Protocol):
    async def get_job(self, job_id: int) -> BatchSendJob: ...
    async def get_pending_contacts(self, job_id: int) -> list[CampaignContact]: ...
    async def get_template(self, template_id: int) -> CampaignTemplate: ...
    async def bulk_mark_sent(
        self,
        job_id: int,
        results: list[ContactSendResult],   # contact_id, status, rendered_body
    ) -> None: ...
    async def update_job_progress(
        self,
        job_id: int,
        sent: int,
        failed: int,
    ) -> None: ...
    async def complete_job(
        self,
        job_id: int,
        status: Literal['completed', 'failed', 'cancelled'],
        summary: BatchSendSummary,
    ) -> None: ...
```

---

### ProgressEmitter

Pushes real-time events to the SSE connection held by the frontend.
In-process pub/sub for now; swap to Redis pub/sub when multi-process.

```python
class ProgressEmitter(Protocol):
    async def emit(self, job_id: int, event: ProgressEvent) -> None: ...
```

---

### CRMClient (optional, deferred)

Airtable write-back. Not in the send hot path — fired as a background task
after job completion or via a manual "sync" action. Skipped entirely for now.

---

## Side Effects

**Irreversible:**
- Emails delivered to recipient inboxes

**DB writes (checkpointed every 25 contacts):**
- `campaign_contacts.status` → `'sent'` | `'failed'`
- `campaign_contacts.sent_draft` → rendered subject + body stored
- `batch_send_jobs.sent`, `.failed` incremented at each checkpoint
- `batch_send_jobs.status` → `'running'` → `'completed'` | `'failed'`

**SSE events emitted during run:**
```json
{ "sent": 25, "total": 187, "status": "running", "current": "Sarah Chen" }
{ "sent": 50, "total": 187, "status": "running", "current": "David Kim" }
{ "sent": 187, "total": 187, "status": "completed" }
```

**Not a side effect of the runner:**
- Airtable write-back (deferred, separate action)
- Template generation (happened before this runs)
- Variable resolution failure — handled inline, never throws

---

## Algorithm

```
START
  job         = JobStore.get_job(job_id)
  template    = JobStore.get_template(job.template_id)
  contacts    = JobStore.get_pending_contacts(job_id)
  sender      = EmailSenderFactory.build(job.sender_id)

  CHECKPOINT_SIZE = 25
  total_sent = 0
  total_failed = 0

  FOR chunk IN batches(contacts, size=CHECKPOINT_SIZE):

    chunk_results = []

    FOR contact IN chunk:
      rendered = VariableResolver.resolve(template, contact)
      email    = OutboundEmail(
                   to=contact.email,
                   subject=rendered.subject,
                   body_html=rendered.body,
                   from_name=job.sender_display_name,
                 )
      result   = await sender.send(email)

      IF result.ok:
        total_sent += 1
        chunk_results.append(ContactSendResult(contact.id, 'sent', rendered.body))
      ELSE:
        # retry once after 2s
        result = await retry_once(sender.send, email)
        status = 'sent' if result.ok else 'failed'
        if status == 'sent': total_sent += 1
        else: total_failed += 1
        chunk_results.append(ContactSendResult(contact.id, status, rendered.body))

      await rate_limiter.wait()   # respects sender.rate_limit (e.g. 200ms for Gmail)

    # checkpoint — one DB round-trip per 25 contacts
    await JobStore.bulk_mark_sent(job_id, chunk_results)
    await JobStore.update_job_progress(job_id, total_sent, total_failed)
    await ProgressEmitter.emit(job_id, { sent: total_sent, total: len(contacts) })

  await JobStore.complete_job(job_id, 'completed', summary)
  await ProgressEmitter.emit(job_id, { status: 'completed', sent, failed })

END
```

**Crash recovery:** on restart, `get_pending_contacts` only returns contacts
where `status = 'pending'`. Already-checkpointed contacts are invisible to the
runner. Resume is automatic with no extra logic.

**Cancellation:** runner checks a `cancelled` flag (set via the cancel API)
at the top of each chunk loop. Exits cleanly after the current chunk finishes.

---

## Output Data

```python
@dataclass
class BatchSendSummary:
    job_id:           int
    sent:             int
    failed:           int
    duration_seconds: float
    fallback_report:  list[FallbackEntry]

@dataclass
class FallbackEntry:
    contact_id:   int
    contact_name: str
    fallbacks:    list[str]   # variable names that hit fallback phrases
    missing:      list[str]   # variable names that were omitted entirely
```

The fallback report is built inline as the resolver runs — zero extra queries.

---

## Rate Limiting Per Sender

The `EmailSender` implementation owns its own rate limit. The runner calls
`rate_limiter.wait()` which asks the sender for its delay. Switching backends
does not require changing the runner.

| Sender | Rate |
|---|---|
| GmailSender | 200ms between sends (5/sec, safe under quota) |
| WorkspaceSender | 100ms between sends (10/sec) |
| SMTPSender | configurable, default 100ms |
| MailtrapSender | no delay |
| DryRunSender | no delay |

---

## What This Does Not Own

- Template generation (agents/outreach)
- Variable resolver logic (outreach/variable_resolver.py)
- Gmail OAuth token management (infra/email/gmail.py)
- Airtable write-back (infra/crm/airtable.py, fired separately)
- SSE connection management (API layer)
