# Scaling Plan — Fundraising Automations Pipeline

**Target:** 1,000 concurrent jobs, each with 6,000+ records across many onboarded companies.

---

## Current Architecture (What We Have Today)

```
Browser → FastAPI server → runs job directly inside itself
```

All jobs run as `asyncio.Task` objects inside a single Python process on a single event loop.

### Key numbers that break at scale

| Limit | Current value | Problem at 1,000 jobs |
|-------|--------------|----------------------|
| Apify concurrency | 2 (1 token × 2) | 2 scrapes globally while 1,000 jobs need work |
| Chunk size | 5 records per job | 5,000 concurrent coroutines in one loop |
| DB pool | 20 connections | ~200 writes/sec from stat updates, pool saturates |
| CSV checkpoints | Local disk | Cannot share across workers, slow to parse on retry |
| Job queue | In-process asyncio tasks | Lost on server restart, no priority, no horizontal scale |

---

## Bottlenecks in Priority Order

### 1. Single process — everything shares one event loop

**The root problem.** You cannot run 1,000 long-running I/O-heavy jobs inside one FastAPI process. The event loop congests, thread pool saturates, and API latency degrades.

**Fix:** ARQ task queue — separate the API server from the worker processes entirely.

---

### 2. Apify token pool is global — one company's 403 affects everyone

All jobs share one `ApifyTokenPool` singleton. A company exhausting their credits pauses the entire platform.

**Fix:** Per-company token pools keyed to `base_id`, stored in a `companies` table.

---

### 3. CSV checkpoints live on local disk

Recovery reads the entire CSV file. Can't be shared across worker machines. With 6,000-record batches, CSV parsing becomes a bottleneck.

**Fix:** `batch_records` DB table — upsert per record, query on resume.

---

### 4. DB stat writes after every 5-record chunk

At 1,000 jobs × one `UPDATE enrichment_batches` per chunk = ~200 DB writes/sec on a 20-connection pool.

**Fix:** Buffer stats in worker memory, flush every 10 chunks or every 5 seconds.

---

### 5. No job priority — free tier starves paying customers

All jobs compete equally for workers.

**Fix:** Named ARQ queues (`queue:high`, `queue:normal`, `queue:low`) with workers assigned per tier.

---

### 6. Warm path and embedding compete with enrichment

CPU-bound warm path index building and OpenAI embedding calls run in the same process as enrichment.

**Fix:** Separate ARQ worker pools per workload type.

---

## The Solution: ARQ Task Queue

### What ARQ is

ARQ (Async Redis Queue) is a Python task queue built on asyncio and Redis. It fits this codebase with minimal changes because the executor is already fully async.

### Architecture after migration

```
Browser
  ↓
FastAPI (thin — HTTP only, enqueues work)
  ↓
Redis (job queue — just stores job IDs, tiny footprint)
  ↓
┌─────────────────────────────────────┐
│  ARQ Enrichment Workers (x8–16)     │  ← scale by adding machines
│  ARQ Warm Path Workers  (x2–4)      │  ← CPU-isolated
│  ARQ Embedding Workers  (x2–4)      │  ← OpenAI rate-limit optimised
└─────────────────────────────────────┘
  ↓
PostgreSQL (single source of truth)
```

### What changes in the code

The executor logic is **unchanged**. The only change is how jobs are submitted:

```python
# Today (manager.py)
task = asyncio.create_task(executor.run_job(job_id))

# With ARQ
async def run_enrichment_job(ctx, job_id: int):
    await BatchExecutor().run_job(job_id)  # same function, untouched
```

Start workers with:
```bash
arq backend.workers.WorkerSettings
```

That's the core migration. Everything else is additive.

### How to run multiple workers on one machine

```
Machine (single box):
  ├── uvicorn (FastAPI)     ← handles HTTP only, very lightweight
  ├── arq worker 1          ← enrichment
  ├── arq worker 2          ← enrichment
  ├── arq worker 3          ← warm path
  └── redis                 ← queue (tiny)
```

### How to scale horizontally

```
Machine 1:  uvicorn + redis
Machine 2:  arq enrichment workers × 4
Machine 3:  arq enrichment workers × 4
Machine 4:  arq enrichment workers × 4
Machine 5:  arq warmpath + embedding workers × 4
```

Add machines when you add customers. No code changes. No API redeploy.

---

## Implementation Roadmap

### Phase 1 — ARQ migration (unlocks everything else)

**Effort:** Medium (2–3 days)

1. Add `arq` and `redis` to dependencies
2. Create `backend/workers.py` with `WorkerSettings` and task functions wrapping existing executors
3. Replace `ExecutorManager.submit()` with `await arq_pool.enqueue_job('run_enrichment_job', job_id)`
4. Replace `_trigger_post_enrichment` fire-and-forget tasks with enqueue calls to warm path / embedding queues
5. Update `run_py312.bat` / startup scripts to also start workers

**Result:** Jobs survive server restarts. Workers are independently scalable. API stays fast under load.

---

### Phase 2 — Per-company Apify token isolation

**Effort:** Low–Medium (1 day)

1. Add `apify_tokens` column to a `companies` table (or `enrichment_jobs` table as a quick start)
2. Change `ApifyTokenPool` from a global singleton to a per-job instance: `get_company_apify_pool(base_id)`
3. One company hitting 403 pauses their jobs only

**Result:** Complete tenant isolation for external API credentials. No shared blast radius.

---

### Phase 3 — Replace CSV checkpoints with `batch_records` table

**Effort:** Medium (1–2 days)

Schema:
```sql
CREATE TABLE batch_records (
  id            SERIAL PRIMARY KEY,
  batch_id      INTEGER REFERENCES enrichment_batches(id),
  record_id     TEXT NOT NULL,
  status        TEXT NOT NULL,  -- success | skipped | failed | apify_403
  error         TEXT,
  processed_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (batch_id, record_id)
);
```

Replace in `executor.py`:
- `_write_csv_row()` → `INSERT ... ON CONFLICT DO UPDATE`
- `_read_processed_stats()` → `SELECT record_id, status FROM batch_records WHERE batch_id = $1`
- `_flush_csv_to_airtable_sync()` → reads from DB instead of CSV

**Result:** Any worker can pick up any batch. No shared filesystem needed. Faster resume on large batches.

---

### Phase 4 — Buffer DB stat writes

**Effort:** Low (hours)

```python
# Instead of writing after every chunk:
stats_buffer[batch_id] = {'processed': x, 'hits': y, ...}

# Flush every 10 chunks or every 5 seconds
if chunk_count % 10 == 0 or time.monotonic() - last_flush > 5:
    await db.update_batch(batch_id, **stats_buffer[batch_id])
```

Also increase `asyncpg` pool `max_size` from 20 → 50–100 on a proper Postgres instance.

**Result:** ~10× reduction in DB write pressure. Frees connections for query load.

---

### Phase 5 — Priority queues by company tier

**Effort:** Low (hours, after Phase 1)

```python
# ARQ supports named queues natively
await arq_pool.enqueue_job('run_enrichment_job', job_id, _queue_name='arq:queue:high')

# WorkerSettings assigns workers to queues
class EnterpriseWorkerSettings(WorkerSettings):
    queue_name = 'arq:queue:high'

class SharedWorkerSettings(WorkerSettings):
    queue_name = 'arq:queue:normal'
```

**Result:** Enterprise customers never wait behind free-tier bulk jobs.

---

## Infrastructure at Target Scale

At 1,000 jobs × 6,000 records = 6 million records, 12 million Apify calls:

| Component | Count | Notes |
|-----------|-------|-------|
| FastAPI instances | 2 | Load balanced, stateless |
| Redis | 1 | Single instance sufficient (< 100MB for 1k jobs) |
| ARQ enrichment workers | 8–16 | Each handles ~62–125 concurrent jobs |
| ARQ warm path workers | 2–4 | CPU-isolated, multiprocessing internally |
| ARQ embedding workers | 2–4 | Optimised for OpenAI batch throughput |
| PostgreSQL | 1 primary + 1 replica | Read replica for stats queries |
| Apify tokens (per company) | 2–5 | Customer-provided, isolated per tenant |

With 16 enrichment workers × CHUNK_SIZE=5 = 80 concurrent Apify scrapes at minimum (more with multiple tokens per company). Throughput scales linearly with workers.

---

## What Does NOT Need to Change

- `BatchExecutor.run_job()` — untouched
- `_process_record()` — untouched  
- `WarmPathExecutor` and `EmbeddingExecutor` — untouched
- The entire DB schema (except adding `batch_records` and `companies.apify_tokens`)
- All API endpoints
- The frontend

The queue is infrastructure, not logic. The logic already works.

---

---

## Batch Send Runner — Scale Path

### Current state (Phase 1, what we're building now)

```
Browser → POST /send → FastAPI creates job row → asyncio.create_task(runner)
Browser → GET  /events → SSE reads from in-memory asyncio.Queue
```

The runner lives inside the FastAPI process. SSE events flow through an in-process `asyncio.Queue` keyed by `job_id`. Works perfectly for a single server, single process.

**Breaks when:**
- You deploy two FastAPI instances (load balancer can route the SSE request to a different server than the one running the job — queue is in-process, unreachable)
- 10+ simultaneous batch jobs saturate the FastAPI event loop alongside regular API traffic

---

### Phase 2 — Redis pub/sub for SSE

Replace the in-process `asyncio.Queue` with a Redis channel. Every runner publishes events to `batch_send:{job_id}`. Every SSE endpoint subscribes to that channel. Server affinity doesn't matter.

```python
# Runner publishes
await redis.publish(f"batch_send:{job_id}", json.dumps(event))

# SSE endpoint subscribes
async with redis.pubsub() as ps:
    await ps.subscribe(f"batch_send:{job_id}")
    async for message in ps.listen():
        yield f"data: {message['data']}\n\n"
```

**Cost:** Add `redis[hiredis]` and `aioredis` to dependencies. Change two functions in `batch_sender.py` (`_emit`, SSE endpoint reader). Runner logic is untouched.

---

### Phase 3 — ARQ workers for the runner

Same pattern as the enrichment pipeline. The POST `/send` endpoint enqueues a job instead of spawning a task. A separate ARQ worker process picks it up.

```python
# API (thin)
await arq_pool.enqueue_job('run_batch_send', job_id)

# Worker (same runner, different entry point)
async def run_batch_send(ctx, job_id: int):
    await batch_sender.run(job_id)
```

**What doesn't change:** The runner loop, variable resolver, checkpoint logic, rate limiting — all untouched. Just the dispatch mechanism changes.

---

### Phase 4 — Switch to SendGrid / Mailgun

The `EmailSender` Protocol means this is a one-line factory change:

```python
# factory.py — swap GmailSender for SMTPSender
async def build_sender(sender_email=None) -> EmailSender:
    if Config.EMAIL_PROVIDER == "sendgrid":
        return SMTPSender(
            host="smtp.sendgrid.net", port=587,
            username="apikey", password=Config.SENDGRID_API_KEY,
            from_email=Config.SENDGRID_FROM_EMAIL,
        )
    # else Gmail ...
```

SendGrid free tier: 100/day. Essentials: 50k/day starting at ~$20/month. No per-account limits.

**Runner doesn't change at all.** It calls `sender.send(email)` — doesn't know or care what's behind it.

---

### Multi-account round-robin (built in from day one)

`batch_send_jobs.sender_emails` is a JSON array. The runner builds one `GmailSender` per connected account and cycles through them:

```
Contact 1 → account_a@gmail.com  (rate: 200ms)
Contact 2 → account_b@gmail.com  (rate: 200ms, independent)
Contact 3 → account_a@gmail.com  (rate: 200ms from last send on A)
...
```

Each sender has its own last-sent timestamp. Two accounts = effective 100ms average rate = ~36,000/hour theoretical ceiling, capped by Gmail's 2,000/day per account.

| Connected accounts | Effective daily cap |
|---|---|
| 1 personal Gmail | 500 |
| 2 personal Gmail | 1,000 |
| 1 Workspace | 2,000 |
| 2 Workspace | 4,000 |
| SendGrid Essentials | 50,000+ |

---

*Last updated: 2026-05-24*
