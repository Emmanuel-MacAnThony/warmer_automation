# Product Feature Roadmap

## The Core Workflow
Every feature serves this loop:

**Enrich → Segment → Draft → Send → Track → Re-enrich**

---

## Phase 1 — Complete the Workflow
*Goal: Give the team a usable end-to-end pipeline*

### Campaign Builder
Natural language → Airtable filtered subset.
- User types: *"Create a campaign of tech executives in New York not yet contacted"*
- Chat routes to Airtable, creates a named filtered view automatically
- Campaigns are named, saved, and reusable
- Built on existing chat interface + Airtable client + outreach workflow stub

### Gmail Draft Generation per Campaign
- Select a campaign, hit generate
- For each contact, a personalized Gmail draft is created using enriched data — current role, company, career context
- Fundraiser reviews and sends directly from Gmail — no new sending infrastructure needed
- Drafts reference specific profile details, not generic templates

### Airtable Automation Triggers
- When enrichment completes, fire a configurable webhook
- Triggers whatever Airtable automation the team has configured
- Examples: update a status field, create a linked task, move record to a new view, send a Slack notification
- Direct answer to CEO's request for Airtable automations

---

## Phase 2 — Intelligence Layer
*Goal: Make the database self-maintaining and actionable*

### Diff / Re-enrichment Alerts
- Schedule periodic re-enrichment runs on a cadence (weekly, monthly)
- Compare new enrichment data against the last snapshot
- Surface material changes: job promotion, company change, new role, location change
- Alert delivered via Slack message or email with context: what changed, why it matters
- Strongest retention feature — keeps the product valuable monthly, not just once

### Data Health Score
- Per-record completeness score visible in the sidebar
- Per-table dashboard: *"Your database is 67% complete. 340 records missing phone, 210 missing LinkedIn URL"*
- Highlights which fields have the worst coverage across the dataset
- Fundraising managers obsess over data quality — high perceived value, simple to build

### Auto-tagging
- After enrichment, automatically suggest Airtable tags based on profile data
- Examples: *"Tech Executive", "Education Sector", "West Coast", "10+ Years Experience", "Open to Work"*
- LLM categorizes at scale using enriched fields
- Makes campaign segmentation faster — classification work is already done before the fundraiser opens Airtable

---

## Phase 3 — Close the Feedback Loop
*Goal: Turn one-way data pipeline into a learning system*

### Reply Tracking Back to Airtable
- Connect Gmail via OAuth
- When a contact replies to a campaign email, automatically update their Airtable record
- Updates: last contacted date, reply received flag, status change, response sentiment
- Closes the loop — reply data currently lives in Gmail and never makes it back to the CRM

### Warm Signal Detection
- Scan the fundraiser's Gmail history for past conversations with contacts in the database
- If a prior email exchange is found, flag that record as warm
- Example: *"You emailed Sarah Chen 8 months ago about the gala — she's currently marked as cold in your database"*
- Surfaces hidden relationship context that would otherwise be missed

### Campaign Scoring
- After a campaign, pull open rates and reply rates from Gmail
- Surface which segments of the database are most responsive
- Feeds directly into better future segmentation criteria
- Turns the product from a one-way data tool into something that learns over time

---

## Flagship Feature — Next Best Action

Every enriched contact gets a suggested action generated from their profile + last contact date + campaign history:

- *"Call this week — just got promoted at Stripe"*
- *"Add to tech campaign — strong industry match"*
- *"Re-enrich — data is 7 months old"*
- *"Flag for board outreach — prior email exchange detected"*
- *"High capacity prospect — career trajectory trending up"*

This is the decision layer that makes raw enrichment data actionable. It answers the question fundraisers actually have: **who do I call today and why?**

---

## Build Order

| Priority | Feature | Complexity | Impact |
|----------|---------|------------|--------|
| 1 | Campaign Builder | Medium | High |
| 2 | Gmail Draft Generation | Medium | High |
| 3 | Airtable Automation Triggers | Low | High |
| 4 | Diff / Re-enrichment Alerts | Medium | High |
| 5 | Data Health Score | Low | Medium |
| 6 | Auto-tagging | Low | Medium |
| 7 | Reply Tracking | Medium | High |
| 8 | Warm Signal Detection | High | High |
| 9 | Campaign Scoring | Medium | Medium |
| 10 | Next Best Action | High | Very High |
