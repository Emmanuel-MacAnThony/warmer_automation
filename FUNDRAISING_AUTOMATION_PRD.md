# Fundraising Automation Platform — Product Requirements Document

**Prepared by:** Engineering
**Input from:** Precious (Fundraising Operations Roadmap) + Bradford feedback
**Date:** May 2026
**Status:** Phase 1 in active development

---

## Problem Statement

Manually qualifying one fundraising contact end-to-end takes 25 minutes (37 minutes for crypto contacts). At current pace, qualifying the full 511-contact Likely + High Confidence HNW shortlist requires **213 hours — 5.5 weeks of full-time work** for one person. That time is entirely consumed by research and data entry, leaving no bandwidth for actual outreach and relationship-building.

The goal of this platform is to compress that 213 hours down to approximately **8.5 hours of automated processing**, freeing the fundraising team to focus entirely on conversations and closes.

---

## Success Metric

**One contact fully qualified in under 1 minute.** Every engineering task is evaluated against this target.

---

## Phase 1: Contact Intelligence — PRIORITY

> Turn a raw name in the database into a fully classified, research-ready profile ready for outreach. Nothing in Phase 2 or 3 starts until Phase 1 is producing qualified contacts.

### Current State (What's Already Built)

LinkedIn profile scraping and Airtable sync are live in production. 3,696 records enriched at 88% hit rate. Task 1.1 is effectively done — it needs an upgrade to include post data (swap to harvestapi actor) but the core pipeline is running.

---

### Task 1.1 — LinkedIn Profile Scraping ✅ Live

**Manual baseline:** 4 min per contact
**Automated target:** 5 sec per contact
**Time saved:** 3 min 55 sec per contact

**What it produces:**
- Career history with dates
- Education and board roles
- Follower count and "Open to Work" status
- Full About text and work history
- Recent posts (upgrade to harvestapi actor)

**Status:** Built and validated in production. Upgrade pending (harvestapi swap for posts + 5x cost reduction).

---

### Task 1.2 — Crunchbase Enrichment

**Manual baseline:** 3 min per contact
**Automated target:** 2 sec per contact
**Time saved:** ~3 min per contact

**What it produces:**
- Total investments made and notable exits
- Co-investor network
- Recent funding activity
- Portfolio companies

**Tooling:** Crunchbase Pro API — batch lookup against existing Crunchbase URLs already in CRM.

---

### Task 1.3 — Press and News Mention Check

**Manual baseline:** 4 min per contact
**Automated target:** 10 sec per contact
**Time saved:** ~4 min per contact

**What it produces:**
- Recent press count and top outlets
- Exit / investment / litigation flags
- Public statement highlights

**Tooling:** SerpAPI (already integrated in the platform) — new query pattern per contact name.

---

### Task 1.4 — Onchain Wealth Verification *(crypto contacts only)*

**Manual baseline:** 12 min per contact
**Automated target:** 30 sec per contact
**Time saved:** ~11.5 min per contact

**What it produces:**
- On-chain wealth estimate in USD
- Top token holdings
- Transaction volume and wallet age patterns

**Tooling:** Arkham Intelligence API or Nansen API — name → wallet resolution → holdings calculation.

---

### Task 1.5 — Career Trajectory Pattern Detection

**Manual baseline:** 6 min per contact
**Automated target:** 1 sec per contact (runs on already-scraped LinkedIn data, no extra API call)
**Time saved:** ~6 min per contact

**What it produces:**
A single trajectory tag per contact with a plain-English signal explanation. Five archetypes:
1. Long-tenure RSU beneficiary
2. Early employee at a winner (pre-IPO / pre-acquisition)
3. Serial founder
4. Prior senior operator (C-suite, not founder)
5. Exited founder now in soft role

**Tooling:** LLM logic layer running on existing LinkedIn scrape output — no new data source required.

---

### Task 1.6 — Warm Path / Mutual Connection Mapping

**Manual baseline:** 7 min per contact
**Automated target:** 30 sec per contact
**Time saved:** ~6.5 min per contact

**What it produces:**
- Ranked list of mutual connections per target
- "Who could intro" surfaced automatically with relationship context

**Tooling:** LinkedIn Sales Navigator network export + graph builder mapping the team's combined network to target contacts. Highest complexity task in Phase 1.

---

### Task 1.7 — Wealth Signal Scoring Composite

**Manual baseline:** 3 min per contact (the synthesis step)
**Automated target:** Instant
**Time saved:** ~3 min per contact

**What it produces:**
- Final wealth confidence rating per contact (High / Medium / Low)
- Full signal trail: which data points contributed and how
- Single ranked output ready for outreach prioritisation

**Tooling:** Aggregation layer on top of outputs from Tasks 1.1–1.6. No new APIs — pure logic.

---

### Phase 1 Total Impact

| Metric | Value |
|--------|-------|
| Manual time per contact (non-crypto) | 25 min |
| Manual time per contact (crypto) | 37 min |
| Automated time per contact | ~1 min |
| Time saved per contact | 24–36 min |
| Contacts on shortlist | 511 |
| Total hours saved | ~213 hours |
| Weeks of work reclaimed | 5.5 weeks |

---

## Phase 2: Outreach Operations *(scope preview — sized after Phase 1 ships)*

Picks up where Phase 1 ends. Once a contact is classified and research-ready, Phase 2 covers everything between "ready to message" and "in active conversation."

- **Personalized outreach message drafting** — LLM draft from Phase 1 data, replacing 10–15 min of manual writing
- **Follow-up sequencing and reminders** — automated drip cadence, replacing ~5 min per follow-up cycle
- **Meeting prep brief generation** — auto-generated one-pager the morning of each meeting, replacing 20–30 min of manual prep
- **Response tracking and routing** — automatic CRM stage progression from email and calendar signals

---

## Phase 3: Pipeline Operations & Strategic Layer *(scope preview — sized after Phase 2 ships)*

Underlying infrastructure keeping the system healthy and producing decision-grade visibility.

- CRM data hygiene and deduplication (~2 hrs/week reclaimed)
- Automated re-classification on data refresh
- New contact auto-ingestion (referrals and exports through Phase 1 automatically)
- Live pipeline reporting dashboard
- Anchor LP composite scoring
- Geographic clustering for travel planning
- Stale pipeline detection and auto-flagging
