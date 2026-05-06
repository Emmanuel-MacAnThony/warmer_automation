# Batch Enrichment Orchestrator — Implementation Plan

## Architecture Rules
- **Never touch** `linkedin_agent.py`, `output_validator.py`, `matching_agent.py`, `enrichment.py`
- Job is the control unit (▶/⏸) — batches are progress partitions only
- Token pool is the sole Apify rate limiter — all jobs share it
- CSV per batch = written record-by-record during processing, flushed to Airtable once when batch completes

---

## Phase 1 — Infrastructure & Data Layer
**Goal:** Server boots with new config, DB migrations applied, new Airtable methods work. No pipeline code yet.

### Files
| File | Change |
|------|--------|
| `backend/config.py` | Add `APIFY_TOKENS` (List[str]), `APIFY_CONCURRENCY_PER_TOKEN` (int), `BATCH_OUTPUT_DIR` (path) |
| `backend/db/client.py` | Raise pool `max=20`. Add `get_batch()`, `reset_stale_batches()` |
| `backend/clients/airtable_client.py` | Add `get_record(base_id, table_id, record_id)`, `update_record_in_table()`, `batch_update_in_table()` (chunks of 10) |
| `backend/core/server.py` | Startup hook: `reset_stale_batches()`. Add `POST /jobs/{id}/run` (501 stub). Add `PATCH /jobs/{id}/status` |

### Scaling factors
- DB pool `max=20` — handles 30 concurrent jobs doing frequent writes
- `reset_stale_batches()` on startup: batches `running → pending`, **jobs stay `running`**
- ExecutorManager on boot does one DB query for `running` jobs → auto-resumes them (no operator needed)
- No polling loop — executor only wakes on startup scan or direct `submit(job_id)` call from `POST /run`

### Verify
1. `python -m backend.db.init_db` — no errors
2. `GET /health` — server starts clean
3. `PATCH /jobs/{id}/status {status: "paused"}` — 200
4. `POST /jobs/{id}/run` — 200, job status becomes `running`
5. Manually set a job to `running` + batch to `running`, restart server → batch resets to `pending`, job stays `running`, ExecutorManager auto-resumes it

---

## Phase 2 — Core Enrichment Pipeline
**Goal:** A job can be executed end-to-end from a script. CSV written per batch. Airtable updated on batch completion.

### Files
| File | Change |
|------|--------|
| `backend/enrichment/__init__.py` | Create (empty) |
| `backend/enrichment/apify_pool.py` | `ApifyTokenPool` — round-robin semaphores, `async with pool.get_token() as token` |
| `backend/enrichment/batch_analyzer.py` | `BatchAnalyzer` + `BatchOutputValidator` — handles singleSelect/multiSelect with choices, uses field_mapping + schema as context |
| `backend/enrichment/batch_executor.py` | Per-record pipeline + job-level loop |

### Per-record pipeline
```
fetch_record(base_id, table_id, record_id)
  → has linkedin_url?
      NO → SerpClient.search + LLMMatcher.rank → pick highest if >= threshold
           → write linkedin_url back to Airtable immediately
           → if none found: write {record_id, status=skipped} to CSV, continue
  → async with pool.get_token() as token:
        apify_data = await run_in_executor(scrape_with_token, url, token)
  → BatchAnalyzer.analyze(apify_data, schema, field_mapping)
  → BatchOutputValidator.validate(extracted, schema)
  → append row to CSV file (record_id, linkedin_url, status, error, field values...)
```

### Job-level loop
```
for each pending batch (ordered by batch_number):
    check job.status == paused → stop gracefully between batches
    if CSV exists: read already-processed record_ids → skip them (crash recovery)
    process all records concurrently via pool (asyncio.gather + semaphore)
    flush entire CSV → Airtable (batch_update_in_table, chunks of 10)
    batch.status = completed, update hits/misses/failed counts, csv_path
job.status = completed
```

### Scaling factors
- **OpenAI/Serper rate limits**: tenacity retry with exponential backoff + jitter on all external calls
- **LLM concurrency**: semaphore max 5 concurrent OpenAI calls across all jobs
- **Crash recovery**: on resume, read existing CSV to find processed record_ids, skip those records
- **Lazy DB writes**: update `batch.processed` every 10 records, not every record
- **Token pool**: single shared instance across all 30 concurrent jobs — pool is the only Apify governor

### Verify
1. Unit test pool — 2 tokens × 2 concurrency, fire 20 coroutines, confirm max 4 run at once
2. Unit test BatchAnalyzer — known profile + schema with singleSelect choices → values within allowed choices
3. Dry-run script: `DRY_RUN=true`, real batch → inspect CSV, no Airtable writes
4. Live run: 5-record batch, `DRY_RUN=false` → Airtable fields populated, CSV at `csv_path`, batch `completed`
5. Crash recovery: kill mid-batch, re-run → already-processed records skipped

---

## Phase 3 — Server Integration & Extension
**Goal:** Operator starts/pauses jobs from extension UI. Pipeline wired into server.

### Files
| File | Change |
|------|--------|
| `backend/enrichment/executor_manager.py` | Singleton — event-driven, no polling. `submit(job_id)`, active task registry (prevents double-start) |
| `backend/core/server.py` | `POST /jobs/{id}/run` → DB write + `executor_manager.submit()`. Startup: reset_stale_batches → auto-resume running jobs. Shutdown: cancel all tasks |
| `chrome-extension/content.js` | Job row ▶/⏸: pending/paused → `POST /jobs/{id}/run`, running → `PATCH /jobs/{id}/status {paused}` |

### Execution model
- **No polling loop.** ExecutorManager wakes only on: (1) startup scan for `running` jobs, (2) direct `submit(job_id)` call
- `POST /run` → sets `job.status = 'running'` + calls `executor_manager.submit(job_id)` directly
- Crash recovery: batches reset to `pending`, jobs stay `running`, ExecutorManager auto-resumes on boot
- Pause: `PATCH status=paused` → executor checks between batches, exits cleanly

### Scaling factors
- `submit(job_id)` checks registry — returns 409 if already running (idempotent)
- `@app.on_event("shutdown")` cancels all tasks gracefully
- Single uvicorn worker only — token pool is in-process memory, multi-worker breaks pool contract

### Verify
1. ▶ pending job → status `running`, executor picks it up, batches run → `completed`
2. ⏸ mid-run → finishes current batch → stops → status `paused`
3. ▶ paused job → resumes from first non-completed batch
4. Double ▶ → 409
5. Server restart mid-job → batch resets to `pending`, job stays `running`, auto-resumes on boot without operator action

---

## CSV Schema (per batch)
```
record_id, linkedin_url, status, error, <airtable_field_name_1>, <airtable_field_name_2>, ...
rec123,    https://...,  success, ,     John,                    CEO, ...
rec456,    ,             skipped, no_linkedin_found, ,           , ...
rec789,    https://...,  failed,  apify_timeout,     ,           , ...
```
Path: `{BATCH_OUTPUT_DIR}/job_{job_id}_batch_{batch_id}.csv`
