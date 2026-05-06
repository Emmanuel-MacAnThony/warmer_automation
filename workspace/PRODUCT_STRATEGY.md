# Product Strategy — Fundraising Enrichment Platform

## Vision
A clean, hosted enrichment platform that fundraising teams use to keep their prospect databases live, accurate, and actionable — delivered on two surfaces: a standalone web app and an Airtable Native App.

---

## Phase 1 — Web App (Ship First)

### What It Is
A standalone web application at a custom domain. Teams sign up, connect their Airtable via OAuth, and run enrichment jobs from a dashboard. No Chrome extension. No local setup. Nothing to install.

### Core User Flow
1. **Sign up** — team creates an account
2. **Connect** — OAuth to their Airtable base (one click, no API keys to configure)
3. **Map** — select table, map their columns to LinkedIn fields (existing mapping logic)
4. **Run** — kick off a job, watch real-time progress
5. **Done** — enriched data appears in their Airtable automatically

Target time from signup to first enriched record: **under 10 minutes.**

### What Gets Built
- Auth system (sign up, login, team workspaces)
- Cloud deployment of existing FastAPI backend (Render / Railway / Fly.io)
- Web dashboard (job creation, progress, history, field mappings)
- Airtable OAuth integration (replace hardcoded API keys with per-team credentials)
- Credits system (purchase and track enrichment credits per team)
- Data privacy layer (no prospect data stored on our servers beyond job metadata)

### Business Model — Credits
Teams buy enrichment credits. You absorb API costs (Apify + OpenAI) and charge per enriched record.

| Tier | Credits | Price | Cost per Record |
|------|---------|-------|----------------|
| Starter | 500 records | $49 | $0.098 |
| Growth | 2,500 records | $199 | $0.080 |
| Scale | 10,000 records | $599 | $0.060 |
| Enterprise | Custom | Custom | Negotiated |

Estimated API cost per record: ~$1.50–2.00 (Apify scrape + OpenAI analysis).
Adjust pricing accordingly to maintain margin — these are illustrative figures.

### Why Web App First
- Fastest path to a paying customer
- Full control over UX and onboarding
- No marketplace approval process
- Easier to iterate and update
- Works for any team regardless of Airtable plan tier

---

## Phase 2 — Airtable Native App (Marketplace)

### What It Is
An official Airtable App built using Airtable's Extensions SDK. Lives inside Airtable natively — teams install it from the Airtable Marketplace in one click. No external website needed, no tab switching. The enrichment panel appears directly inside their Airtable base.

### Why Airtable Native App
- First-class Airtable integration (not a Chrome extension hack)
- Distribution through Airtable Marketplace — built-in discovery
- Trusted by enterprise procurement (officially sanctioned integration)
- Teams never leave Airtable
- Signals product maturity to buyers

### What Changes from Phase 1
- Frontend rebuilt as an Airtable Extension (React-based SDK)
- Backend remains the same FastAPI cloud service
- Auth handled via Airtable's identity (teams already logged in)
- Marketplace listing drives inbound — reduces sales effort

### Airtable Marketplace Requirements (to plan for)
- Airtable developer account and app review process
- Privacy policy and data handling documentation
- Security review for apps handling external data
- SOC 2 roadmap for enterprise tier (not required at launch, required to close enterprise deals)

---

## Platforms Summary

| | Web App | Airtable Native App |
|--|---------|-------------------|
| **Timeline** | Phase 1 — ship first | Phase 2 — after web app validated |
| **Discovery** | Direct / outbound | Airtable Marketplace inbound |
| **Onboarding** | Sign up → OAuth → run | Install from marketplace → run |
| **Auth** | Email / Google SSO | Airtable identity |
| **Distribution** | Self-managed | Marketplace listing |
| **Approval needed** | None | Airtable review process |
| **Best for** | Early customers, iteration | Scale, enterprise, inbound |

---

## Onboarding Requirements (Both Platforms)

To close deals with serious fundraising orgs:

- **Privacy policy** — explicit statement that prospect data is not stored on our servers
- **Security page** — how data is handled, encrypted, and deleted
- **SOC 2 roadmap** — not required at launch, required for enterprise procurement
- **Data processing agreement (DPA)** — for EU/GDPR customers

---

## Go-To-Market

**First 3 customers:** Direct outreach to fundraising teams at mid-size nonprofits and university development offices. Offer free credits for feedback. Goal is 3 paying teams before building anything new.

**Growth:** Airtable Marketplace listing drives inbound once Phase 2 is live. Teams searching for enrichment tools find the product organically.

**Pricing signal to test:** $49 starter pack. Low enough that a fundraising manager can expense it without approval. High enough to signal it is a real product.

---

## What Does Not Change

The core enrichment pipeline — batch executor, LinkedIn scraper, LLM analyzer, Airtable sync — is already built and validated in production (3,696 records, 88% enrichment rate). The product work is entirely in the delivery layer and onboarding experience, not in rebuilding what already works.
