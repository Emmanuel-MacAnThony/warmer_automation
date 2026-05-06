# Engineering Plan — Phase 1: Contact Intelligence
**Project:** Fundraising Automation Platform
**Scope:** Tasks 1.1–1.7 (Contact Intelligence pipeline)
**Based on:** PRD dated May 2026 + current production codebase

---

## Build Status Overview

| Task | Description | Status | Effort Remaining |
|------|-------------|--------|-----------------|
| 1.1 | LinkedIn Profile Scraping | ✅ Live (upgrade pending) | 3 hrs |
| 1.2 | Crunchbase Enrichment | 🔲 Not started | 5 hrs |
| 1.3 | Press & News Mention Check | 🔲 Not started | 4 hrs |
| 1.4 | Onchain Wealth Verification | 🔲 Not started | 8 hrs |
| 1.5 | Career Trajectory Detection | 🔲 Not started | 4 hrs |
| 1.6 | Warm Path / Mutual Connection Mapping | 🔲 Not started | 16 hrs |
| 1.7 | Wealth Signal Scoring Composite | 🔲 Not started | 4 hrs |

**Total remaining effort: ~44 hours**
**Estimated calendar time at 1 FTE: 5.5 working days**

---

## Task 1.1 — LinkedIn Profile Scraping (Upgrade)

**Status:** Production-live. Upgrade to `harvestapi/linkedin-profile-posts` actor pending.

**What's built:**
- Full Apify actor integration via `backend/clients/linkedin_scraper.py`
- Batch executor, CSV checkpointing, Airtable sync — all running
- 3,696 records processed, 88% enrichment rate

**What needs building:**
- Swap `dev_fusion/linkedin-profile-scraper` → `harvestapi/linkedin-profile-posts` in `linkedin_scraper.py`
- Map new actor output fields (posts array) to existing schema
- Add `recent_posts` field to CRM output and field mapping config

**Effort estimate:** 3 hours
- 1 hr: actor swap + output field remapping
- 1 hr: test run on 10–20 contacts
- 1 hr: Airtable field addition + validation

**Risk:** Low. Drop-in replacement. Same LinkedIn URL input. Core pipeline unchanged.

**Blocker:** None. Proceed immediately.

---

## Task 1.2 — Crunchbase Enrichment

**Status:** Not started. CRM already contains Crunchbase URLs for a subset of contacts.

**What needs building:**
- `backend/clients/crunchbase_client.py` — Crunchbase Pro REST API wrapper
- Batch lookup: read `crunchbase_url` from Airtable records, call `/entities/people/{permalink}`, parse investment and exit data
- New CRM fields: `total_investments`, `notable_exits`, `portfolio_companies`, `co_investors`, `recent_funding_activity`
- Integration into existing `BatchExecutor` pipeline as an optional enrichment module
- Field mapping config additions for Crunchbase output fields

**Effort estimate:** 5 hours
- 1.5 hrs: Crunchbase API client + auth setup
- 1.5 hrs: field parsing + mapping to CRM schema
- 1 hr: batch executor integration (plug in alongside LinkedIn enrichment)
- 1 hr: test on 20 contacts with known Crunchbase presence

**Dependencies:** Crunchbase Pro API subscription required. Confirm credentials before starting.

**Risk:** Medium. ~40% of contacts likely have no Crunchbase URL — graceful null handling required. API rate limits (200 req/min on Pro) need backoff logic.

---

## Task 1.3 — Press and News Mention Check

**Status:** Not started. SerpAPI is already integrated in the platform.

**What needs building:**
- `backend/clients/news_client.py` — SerpAPI query wrapper using existing `SERPAPI_KEY`
- Query pattern: `"{first_name} {last_name}" "{company}"` → Google News results
- Parser: extract article count, outlet names, keyword flags (exit, acquisition, litigation, investment, layoff)
- New CRM fields: `press_count`, `top_outlets`, `press_flags`, `notable_headline`
- Integration into `BatchExecutor` pipeline

**Effort estimate:** 4 hours
- 1 hr: SerpAPI news query pattern + response parsing
- 1 hr: keyword flag extraction logic
- 1 hr: CRM field mapping + Airtable sync
- 1 hr: test on 20 contacts

**Dependencies:** SerpAPI already integrated — no new credentials needed. Re-use `Config.SERPAPI_KEY`.

**Risk:** Low. SerpAPI wrapper pattern already established in codebase. False positives on common names (e.g., "John Smith") — mitigate by requiring company name co-occurrence.

---

## Task 1.4 — Onchain Wealth Verification

**Status:** Not started. Applies only to contacts tagged as crypto-native.

**What needs building:**
- `backend/clients/arkham_client.py` — Arkham Intelligence API wrapper (or Nansen as fallback)
- Name → wallet resolution: query Arkham entity search by full name + company
- Holdings calculation: fetch top token balances, convert to USD via price feed
- New CRM fields: `onchain_wealth_usd`, `top_holdings`, `wallet_age_days`, `transaction_volume_30d`
- Conditional execution: only runs when `contact_type == "crypto"` field is set

**Effort estimate:** 8 hours
- 2 hrs: Arkham API client + entity resolution
- 2 hrs: holdings aggregation + USD conversion
- 1 hr: conditional execution logic in pipeline
- 1.5 hrs: error handling (wallet not found, partial match)
- 1.5 hrs: test on known crypto contacts

**Dependencies:** Arkham Intelligence API access required. Apply for API key before starting. Confirm whether existing contacts have a `contact_type` field or if that needs adding to CRM.

**Risk:** High. Name → wallet resolution is probabilistic — false matches possible. Implement confidence scoring and flag low-confidence matches for manual review. Regulatory note: public wallet data only, no private key exposure.

---

## Task 1.5 — Career Trajectory Pattern Detection

**Status:** Not started. Runs on existing LinkedIn scrape output — no new API calls.

**What needs building:**
- `backend/enrichment/trajectory_classifier.py` — LLM prompt layer over existing `linkedin_data` field
- Prompt: given career history JSON, classify into one of 5 archetypes with a plain-English explanation
- Output: `trajectory_tag` (enum: RSU_beneficiary / early_employee / serial_founder / senior_operator / exited_founder) + `trajectory_signal` (text)
- Integration into `BatchAnalyzer` — runs as part of existing LLM analysis step, not a separate API call

**Effort estimate:** 4 hours
- 1.5 hrs: prompt design + few-shot examples for each archetype
- 1 hr: output parser + enum validation
- 1 hr: integration into `BatchAnalyzer.analyze_profile()`
- 0.5 hr: test on 10 known contacts across archetypes

**Dependencies:** Requires LinkedIn data to be present in CRM record. Run after Task 1.1. No new credentials.

**Risk:** Low. Pure LLM logic on existing data. Main failure mode: ambiguous career histories that don't fit archetypes cleanly — handle with a fallback `unclear` tag.

---

## Task 1.6 — Warm Path / Mutual Connection Mapping

**Status:** Not started. Highest complexity task in Phase 1.

**What needs building:**
- LinkedIn Sales Navigator network export pipeline
  - Export team member connections from Sales Navigator (CSV or API)
  - Parse and deduplicate into a `team_network` graph
- Graph builder: map team network → target prospect list
  - For each prospect, find all team members who are first-degree connected
  - Rank mutual connections by relationship strength (recency, interaction frequency)
- `backend/enrichment/network_mapper.py` — graph traversal + ranking logic
- New CRM fields: `mutual_connections` (list), `top_introducer` (name + relationship context), `intro_strength_score`
- Manual data refresh cadence: Sales Navigator export is not real-time — plan for weekly re-runs

**Effort estimate:** 16 hours
- 3 hrs: Sales Navigator export parsing + deduplication
- 4 hrs: graph builder (team network → prospect adjacency)
- 3 hrs: ranking algorithm + intro strength scoring
- 3 hrs: CRM field integration + Airtable sync
- 2 hrs: test with real team network data + validate against known connections
- 1 hr: documentation for export refresh cadence

**Dependencies:**
- LinkedIn Sales Navigator subscription required (team-level)
- All relevant team members must export their networks
- Network data is PII — define retention policy before storing

**Risk:** Highest in Phase 1. Sales Navigator API access is restricted — may require manual CSV export workflow initially. Graph building at scale (500+ prospects × team network of 1,000+ connections) needs efficiency testing. Treat as a 2-week task with potential scope reduction.

---

## Task 1.7 — Wealth Signal Scoring Composite

**Status:** Not started. Pure aggregation logic — no new API calls.

**What needs building:**
- `backend/enrichment/wealth_scorer.py` — aggregation layer over Tasks 1.1–1.6 outputs
- Scoring rules per signal type:
  - Crunchbase exits/investments → +weight
  - Career trajectory archetype → +weight by type
  - Press flags (exit, acquisition) → +weight
  - Onchain wealth estimate → +weight (crypto contacts only)
  - LinkedIn follower count / board roles → +weight
- Output: `wealth_confidence` (High / Medium / Low) + `signal_trail` (JSON: which fields contributed, with weights)
- Integration: runs last in the enrichment pipeline, after all other tasks complete

**Effort estimate:** 4 hours
- 1.5 hrs: scoring rule design + weight calibration
- 1 hr: aggregator implementation
- 1 hr: CRM field integration
- 0.5 hr: test on 10 contacts across confidence tiers

**Dependencies:** All of Tasks 1.2–1.6 must be complete for full signal coverage. Can be partially implemented (on available signals) before all tasks are done.

**Risk:** Low technically. Main risk is calibration — weights need validation against known high/low confidence contacts. Plan for one round of tuning after first full-pipeline run.

---

## Build Order

Run in this sequence to unblock dependent tasks and ship value incrementally:

```
1.1 upgrade (3 hrs) → posts data available
1.5 (4 hrs)         → depends on 1.1 LinkedIn data, no extra API
1.3 (4 hrs)         → SerpAPI already live, independent
1.2 (5 hrs)         → Crunchbase, independent of others
1.4 (8 hrs)         → crypto contacts, independent but needs credentials
1.7 (4 hrs)         → partial version runnable after 1.2, 1.3, 1.5
1.6 (16 hrs)        → highest complexity, run last, adds to 1.7 scoring
```

**Week 1:** Tasks 1.1 + 1.5 + 1.3 → 11 hours → 3 new signal types live
**Week 2:** Tasks 1.2 + 1.7 (partial) → 9 hours → Crunchbase + composite score live
**Week 3:** Task 1.4 → 8 hours → Crypto contacts fully handled
**Week 4:** Task 1.6 → 16 hours → Warm path live, scoring complete

---

## Infrastructure Notes

**Existing pipeline is reused as-is.** New enrichment tasks plug into `BatchExecutor` and `BatchAnalyzer` without rebuilding the core. Each new client module follows the pattern already established in `backend/clients/`.

**No schema migrations needed for new Airtable fields** — Airtable allows adding fields at any time. New fields are additive, not breaking.

**OpenAI cost impact:** Tasks 1.5 and 1.7 add LLM calls per contact. At current pricing, ~0.5–1K tokens per contact for trajectory + scoring = ~$0.001–0.002 per contact marginal cost. Negligible.

**SerpAPI cost impact (Task 1.3):** ~1 search per contact. At $50/month for 5,000 searches, covering 511 contacts costs ~$5 incremental per run. Acceptable.

---

## Pre-Start Checklist

Before any new task begins, confirm:

- [ ] Crunchbase Pro API key obtained (Task 1.2)
- [ ] Arkham Intelligence API access confirmed (Task 1.4)
- [ ] `contact_type` field exists or added to CRM to gate Task 1.4
- [ ] Sales Navigator team export process defined and tested (Task 1.6)
- [ ] OpenAI project API key is live (currently archived — blocks Tasks 1.5 and 1.7)
- [ ] Batches 12–13 re-run with fresh OpenAI key before any new enrichment begins
