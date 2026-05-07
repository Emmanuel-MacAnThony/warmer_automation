# Scalability Issues

Document for tracking scale problems and potential solutions.

---

## Issue #1: Conversation History Bloat

**Problem**: Frontend sends full conversation history on every request with no pruning. History grows indefinitely until page refresh.

**Impact**: Will eventually hit LLM context limits (200k tokens for Claude) and degrade performance. Each request becomes slower and more expensive.

**Solution**: Implement sliding window (keep last 10-20 messages) or token-based truncation (max 10k tokens). Consider summarizing old context.

---

## Issue #2: Scraper Scalability Across Multiple Teams

### Problem 1: Apify credit limits per account
Single Apify account runs everything. One team with a large list burns the monthly
budget and all other teams stop. Already hit this on 2026-05-07 during Job 2.

**Solution A — BYOK (Bring Your Own Key):** Each customer provides their own Apify
API key during onboarding. They control their budget, we control the processing.
Marginal scraping cost drops to zero for us. Cleanest B2B model.

**Solution B — Token pool per org:** The existing `ApifyTokenPool` is global.
Scope it per org so one team's heavy job cannot starve another's concurrency slots.

Both should be combined at scale.

---

### Problem 2: Actor fragility and LinkedIn blocks
LinkedIn actively detects scrapers. When an actor returns 403s, the pipeline retries
the same broken actor three times and then fails. One actor outage halts everything.

**Solution — Actor fallback chain:** Maintain a registry of `[primary, fallback_1, fallback_2]`
per data type. On 403 or rate-limit, rotate to the next actor instead of retrying
the same one. Actor outages become invisible to the pipeline.

```python
LINKEDIN_PROFILE_ACTORS = [
    "harvestapi/linkedin-profile-scraper",
    "dev_fusion/linkedin-profile-scraper",  # fallback
]
```

Apply the same pattern for posts and tweets scrapers.

---

### Problem 3: Job queue lives inside the API process
Enrichment jobs run as asyncio background tasks inside FastAPI. Server restart
mid-job means the task is gone and requires manual re-trigger. CSV recovery
handles data but not job resumption.

**Solution — Redis + RQ or Celery:** Separate worker processes from the API.
Jobs survive restarts, workers scale horizontally, fair-scheduling across orgs
is straightforward. The existing `ExecutorManager` already has the right shape —
it just needs a persistent queue behind it instead of asyncio tasks.

---

### Problem 4: Redundant re-scraping
Every enrichment re-run burns Apify credits on contacts scraped days ago.
No cache layer means first run and tenth run cost the same.

**Solution — `enriched_at` TTL cache:** Store `enriched_at` timestamp per contact
in the DB. Before scraping: if `enriched_at < 30 days` serve cached data, skip
Apify call entirely. First enrichment pass is expensive; steady-state is cheap.

---

### Rollout order

| Now | Phase 1 stable | Serving 3+ teams |
|---|---|---|
| Actor fallback chain | BYOK key per customer | Redis job queue |
| Rate limit between chunks | Token pool scoped per org | Separate worker process |
| | `enriched_at` TTL cache | Fair-queue across orgs |

Actor fallback chain is the highest priority — fixes the most common failure
(actor going down) with no infrastructure change required.

---

## Issue #3: HITL Workflow Storage (In-Memory Dict)

**Problem**: `_interrupted_workflows` dict (server.py:37) stores HITL workflows in memory. Lost on restart, can't scale across multiple servers, no expiration.

**Impact**: Workflows lost on server restart/crash. Can't load balance. Memory grows indefinitely. Users lose pending approvals.

**Solution**: Replace with Redis. Use TTL (1 hour expiration). Enables multi-server deployment and persistence. Key: `hitl:workflow:{record_id}`.

---
