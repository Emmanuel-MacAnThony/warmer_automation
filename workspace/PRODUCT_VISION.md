# Product Vision

## What We Are Building

Fundraising intelligence automation for teams managing high-net-worth prospect pipelines.
The product enriches a contact list with career, financial, and behavioural signals automatically,
surfaces ranked prospects, and (Phase 2) generates warm outreach recommendations — all without
the team leaving their existing CRM workflow.

---

## Where This Is Going: Web Dashboard

The Chrome extension is the current testing vehicle. The end product is a standalone web app.

### Why

The extension was the right MVP. As the product grows into outreach recommendations,
live pipeline reporting, composite scoring, and team collaboration, a browser sidebar
is the wrong home. A web dashboard gives each feature the space it needs and makes
onboarding self-serve.

### What It Looks Like

```
Login → Connect Airtable (OAuth) → Select Base → Map Fields
                                         ↓
                   Dashboard
                   ├── Jobs         — trigger runs, watch live batch progress
                   ├── Prospects    — enriched contact list, filter by signal
                   ├── Intelligence — wealth tier breakdown, giving signals, top picks
                   ├── Outreach     — Phase 2: ranked recs, draft emails
                   └── Automation   — Phase 3: hygiene runs, stale alerts, reports
```

### How Airtable Connection Works

Airtable has OAuth 2.0. User clicks Connect, selects which bases to share, token stored.
No extension required, no manual API key copy-paste. Works for any team member after
one org-level authorization.

### What Changes vs. Now

- Frontend: new React web app (replaces extension as primary UI)
- Backend: add JWT auth + Airtable OAuth flow; pipeline and agents unchanged
- Chrome extension: kept as lightweight companion — one button that deep-links
  into the web app for the contact currently open in Airtable

---

## Current Build (Phase 1 Testing)

Continuing with FastAPI backend + lightweight Chrome extension while core intelligence
pipeline is validated. The extension tests the full enrichment loop cheaply before
investing in the web app frontend.

**Decision point:** start web app frontend once Phase 1 pipeline is stable and
Apify credits are topped up (currently at monthly limit).

---

## Distribution

- Primary: direct to fundraising teams at impact orgs, family offices, nonprofit endowments
- Secondary: Airtable Extensions Marketplace listing (requires Airtable review)
- Pricing: TBD — likely per seat or per contacts-enriched tier

## Open Questions for the Boss

1. Who is the exact buyer — nonprofit fundraisers, VC/family office, or both?
2. Standalone product or Airtable Marketplace app first?
3. Pricing model — per seat, per enrichment, or flat monthly?
