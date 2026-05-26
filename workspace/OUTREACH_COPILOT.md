# Outreach Copilot

## What It Is

An AI-powered outreach layer built on top of the enrichment and warm path pipeline. The copilot takes a fundraiser's goal, segments their entire contact list intelligently, drafts personalised emails for every contact, and presents them one at a time for human review and send.

It is not an autonomous email sender. It is a drafting and workflow tool that eliminates the blank page problem at scale — giving a 3-person development team the output of a 10-person team.

---

## Why It Has Value

Fundraising teams are chronically understaffed. A development team managing 5,000 donor relationships rarely has time to personally reach every contact who should be hearing from them. Strategy is not the bottleneck — capacity is.

The ROI math is simple:
- Tool costs $X/month
- One re-engaged lapsed donor gives multiples of that back
- Pays for itself immediately

The wedge is not AI novelty. It is selling capacity.

---

## Core Principles

**Human-final, always.** Every single email is reviewed and sent by a person. No batch auto-sends without template review. Fundraising is built on multi-year relationships — one wrong email to a major donor costs more than the whole campaign is worth.

**AI drafts, human sends.** The AI does research, segmentation, and drafting. The fundraiser reads, edits if needed, and hits send. Fast, but never blind.

**Mode matches the tier.** Tier 1 (warm intros, high-value) gets individual one-at-a-time review. Tiers 2 and 3 (direct, re-engagement) get batch template mode — one template reviewed, hundreds sent. The depth of human review scales with the stakes.

**Airtable stays clean.** Campaign logic, drafts, and AI reasoning live in this app. Only outcomes write back to Airtable — three fields maximum.

---

## How It Works

### 1. Campaign Intent

Fundraiser types a goal in plain language:

> "Raise $500k for the cancer research fund by Q3"

The system reads the full enriched dataset and warm path graph, then segments every contact into tiers. No manual sorting required.

### 2. Campaign Overview — Tier Cards

The fundraiser lands on a simple card grid. One card per tier, nothing else:

```
┌───────────────────┐  ┌───────────────────┐  ┌──────────────────┐
│  Warm Intro       │  │  Direct           │  │  Re-engagement   │
│  52 contacts      │  │  187 contacts     │  │  73 contacts     │
│  0 sent           │  │  0 sent           │  │  0 sent          │
└───────────────────┘  └───────────────────┘  └──────────────────┘
```

Click a card to enter that tier's review queue. Work tiers in any order. Come back to others when ready. No scheduling noise, no toggles, no forced sequencing.

Each tier card offers two entry points:
- **Review Queue** — individual one-at-a-time mode (default for Tier 1)
- **Batch Mode** — template-based send for the whole tier (default for Tiers 2/3)

### 3. The Review Queue (Individual Mode)

One contact at a time. Full context always visible — who the person is, why they were chosen, the warm path if one exists, and the AI-drafted email.

**Draft generation is on-demand, one at a time.** When the fundraiser lands on a contact, the draft is generated at that moment using the contact's enriched data, warm path, and campaign goal. Nothing is pre-generated, nothing is saved until send. If the fundraiser skips or closes — the draft is gone, no storage waste, no token burn on contacts that will never be reviewed.

```
┌──────────────┬──────────────────────────────────────────┐
│ 47 / 52      │  David Kim                               │
│              │  VP Research · Memorial Health           │
│ ○ David Kim  │                                          │
│ ○ Sarah Wu   │  PATH  You → Sarah Chen → David Kim      │
│ ○ James Obi  │                                          │
│   ...        │  CONTEXT                                 │
│              │  Joined Memorial Health 3 months ago.    │
│              │  Sarah introduced him at the Hopkins     │
│              │  gala last year.                         │
│              │                                          │
│              │  ┌────────────────────────────────────┐  │
│              │  │ Hi Sarah,                          │  │
│              │  │                                    │  │
│              │  │ Would you be open to introducing   │  │
│              │  │ me to David Kim? Given his new     │  │
│              │  │ role at Memorial Health...         │  │
│              │  └────────────────────────────────────┘  │
│              │                                          │
│              │  [ Send ]  [ Edit ]  [ Skip ]  [ Later ] │
└──────────────┴──────────────────────────────────────────┘
```

**Four actions:**
- **Send** — email goes, contact marked Contacted in Airtable
- **Edit** — draft becomes editable inline
- **Skip** — marks contact as skipped in this campaign. They remain in the contact list and can be revisited. Skip does not remove them from the campaign — it moves them to a skipped state visible in campaign stats.
- **Later** — returns to bottom of queue

**Keyboard shortcuts:** S to send, E to edit, N for next. A focused fundraiser can work through 50 drafts in 30 minutes.

Progress saves automatically. Close the tab, come back tomorrow, pick up where you left off.

### 4. AI-Directed Editing

When the draft needs changing, the fundraiser tells the AI what to change rather than rewriting manually:

```
┌──────────────────────────────────┐
│ make it shorter, more casual...  │  [ ↑ ]
└──────────────────────────────────┘
[ Keep ]  [ Undo ]  [ Original ]
```

The AI streams the rewrite in real time. It has full context — warm path, enriched data, campaign goal, donor tier — so it revises intelligently. If the result is wrong, one click back to the original. Ask again as many times as needed.

Natural language instructions work: *"more formal"*, *"lead with the Hopkins connection"*, *"she's a close friend, make it warmer"*, *"cut to two sentences"*.

### 5. Draft Lifecycle (Individual Mode)

```
Contact loads in queue
→ Generate draft on demand (no pre-generation)
→ Draft lives in memory only
→ Fundraiser reviews, edits if needed
→ On Send → save rendered draft to DB + write three fields to Airtable
→ On Skip / Close → draft discarded, nothing saved
```

**On Airtable write-back:** The rendered email already lives in the fundraiser's Gmail sent folder. Airtable write-back exists purely for team visibility — so colleagues can filter `Outreach_Stage = Contacted` without opening this tool. It writes three fields only. If the team does not use Airtable as a shared CRM view, write-back can be toggled off per campaign.

This keeps token usage proportional to actual sends, not total contacts. A campaign with 300 contacts where 180 get sent costs tokens for 180 drafts, not 300.

### 6. Batch Template Mode (Tiers 2 and 3)

For mid and lower tiers where individual review of every draft is impractical, the fundraiser reviews one AI-generated template and sends it to the entire tier with per-contact variable substitution at send time.

**Cost:** One LLM call to generate the template. Zero LLM calls at send time — all variable rendering is pattern-based.

**Workflow:**

```
Fundraiser clicks "Batch" in queue header (Tier 2 / Tier 3)
    ↓
Two paths:
  A) Upload a draft file (Word doc, PDF, TXT) → LLM refines it, injects {{variable}} slots
  B) No file → LLM generates template from signal profile + campaign goal
    ↓
Split-pane editor opens:
  Left:  editable template with {{variable}} slots highlighted
  Right: live preview rendering real contacts from the tier
    ↓
Variables discovered from LLM output — never from the raw file itself
Signal scanner shows coverage before generation so LLM knows which slots are worth using
    ↓
Fundraiser edits prose, runs copilot instructions ("make it shorter"), preview updates live
    ↓
Approve → batch send job queued
    ↓
Sends asynchronously, progress bar in real time
Each contact gets their rendered draft stored in DB
```

**UI Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Tier 2 — Direct Outreach  ·  187 contacts  ·  Batch Mode       │
├──────────────────────────────┬──────────────────────────────────┤
│  TEMPLATE                    │  PREVIEW                         │
│                              │                                  │
│  Subject:                    │  Contact 3 of 5   ◀  ▶           │
│  ┌────────────────────────┐  │  Sarah Chen · Acme Corp          │
│  │ Supporting [campaign]  │  │                                  │
│  └────────────────────────┘  │  Subject: Supporting cancer...   │
│                              │                                  │
│  Body:                       │  Hi Sarah,                       │
│  ┌────────────────────────┐  │                                  │
│  │ Hi {{first_name}},     │  │  Given your interest in          │
│  │                        │  │  medical research, I wanted      │
│  │ {{topic_hook}} I        │  │  to reach out about our...      │
│  │ wanted to reach out    │  │                                  │
│  │ about our campaign...  │  │  A leadership-level gift         │
│  │                        │  │  would make a real...            │
│  │ {{capacity_close}}     │  │                                  │
│  └────────────────────────┘  │                                  │
│                              │                                  │
│  Variables in use:           │  ✓ topic_hook resolved           │
│  ● first_name                │  ✓ capacity_close resolved       │
│  ● topic_hook                │  ✗ 12 contacts missing topic     │
│  ● capacity_close            │    → will use fallback phrase    │
│                              │                                  │
│  [ Regenerate ]              │                                  │
├──────────────────────────────┴──────────────────────────────────┤
│                    [ Approve & Send 187 emails ]                 │
└─────────────────────────────────────────────────────────────────┘
```

**Variable slots and how they resolve:**

| Variable | Resolution | Fallback |
|---|---|---|
| `{{first_name}}` | contact_snapshot.name (first word) | "there" |
| `{{company}}` | contact_snapshot.company | omitted |
| `{{title}}` | contact_snapshot.title | omitted |
| `{{topic_hook}}` | "given your interest in [topic]" from enrichment | "" (omitted gracefully) |
| `{{giving_reference}}` | "your past support of [cause]" from giving signal | "your commitment to this work" |
| `{{capacity_close}}` | "a leadership-level gift" / "a significant contribution" / "a gift at any level" based on tier | "a contribution at any level" |
| `{{warm_opener}}` | "I was speaking with [connector] recently and" | "" (Tier 1 only) |

All variables resolve without LLM calls — they are pattern-rendered from the contact's signals already stored in `contact_snapshot` and `score_breakdown`. The preview panel shows resolution status so the fundraiser can see before sending how many contacts hit fallbacks.

**When to use each mode:**

| Mode | Tier | Why |
|---|---|---|
| Individual review | Tier 1 — Warm Intro | High-value asks, connector relationships, never templated |
| Batch template | Tier 2 — Direct | Personalised at variable level, template reviewed once |
| Batch template | Tier 3 — Re-engagement | Broader reach, efficiency matters, lower stakes per contact |

### 7. Airtable Write-Back (On Send Only)

Three fields update automatically when an email is sent, regardless of mode:

```
Outreach_Stage    →  "Contacted"
Last_Touch_Date   →  date sent
Last_Touch_Type   →  "Warm Intro" / "Direct" / "Re-engagement"
```

Team filters `Outreach_Stage = Contacted` in Airtable to see exactly who's been reached. No draft emails, no AI reasoning, no sequence steps cluttering contact records.

---

## Data Model

### Existing Tables (already built)

`outreach_campaigns` — one row per campaign, tracks status, tier counts, sent/skipped progress.

`campaign_contacts` — one row per (campaign, contact). Stores tier, composite score, score breakdown, warm path data, contact snapshot, queue status, and sent draft on send.

### New Tables Required

#### `campaign_templates`
One row per (campaign, tier). Created when the fundraiser enters Batch Mode.

```sql
CREATE TABLE campaign_templates (
    id              SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    tier            TEXT NOT NULL CHECK (tier IN ('tier_1', 'tier_2', 'tier_3')),
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,          -- template prose with {{variable}} slots
    variables       JSONB NOT NULL,         -- ["first_name", "topic_hook", ...]
    tier_summary    TEXT,                   -- AI-generated signal summary used to write template
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, tier)
);
```

#### `batch_send_jobs`
One row per send operation. A tier can only have one active job at a time.

```sql
CREATE TABLE batch_send_jobs (
    id              SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    template_id     INT NOT NULL REFERENCES campaign_templates(id),
    tier            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    total           INT NOT NULL DEFAULT 0,
    sent            INT NOT NULL DEFAULT 0,
    failed          INT NOT NULL DEFAULT 0,
    error           TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, tier) WHERE status IN ('pending', 'running')
);
```

### Schema Notes

- `campaign_contacts.sent_draft` stores the fully rendered per-contact email body on send (both modes)
- `campaign_contacts.status` covers both modes: `pending → sent | skipped | later`
- No new column needed on `campaign_contacts` for batch vs individual — the send action is the same

---

## API Design

### Individual Review Queue (existing)
- `GET /api/campaigns/{id}/queue/{tier}?offset=0&limit=50` — paginated queue
- `POST /api/campaigns/{id}/contacts/{contact_id}/send` — mark sent, store draft
- `POST /api/campaigns/{id}/contacts/{contact_id}/skip` — mark skipped (stays in campaign)
- `POST /api/campaigns/{id}/contacts/{contact_id}/later` — bump to end of queue

### Batch Template Mode (new)

```
POST   /api/campaigns/{id}/templates/{tier}/generate
       → Samples tier signals, generates template via LLM
       → Returns { subject, body, variables, tier_summary }

GET    /api/campaigns/{id}/templates/{tier}
       → Fetch saved template

PUT    /api/campaigns/{id}/templates/{tier}
       → Save edits { subject, body }

POST   /api/campaigns/{id}/templates/{tier}/preview
       → Render N random contacts from tier against template
       → Returns [{ contact_name, rendered_subject, rendered_body, resolved_vars, fallbacks }]
       → No LLM — pure variable substitution

POST   /api/campaigns/{id}/templates/{tier}/approve
       → Sets status = 'approved'

POST   /api/campaigns/{id}/templates/{tier}/send
       → Creates batch_send_job, starts async send
       → Returns job_id for SSE polling

GET    /api/campaigns/{id}/batch-jobs/{job_id}/events
       → SSE stream: { sent: N, total: M, status, current_contact }
```

### Draft Generation (Phase 2)
```
POST   /api/campaigns/{id}/contacts/{contact_id}/draft
       → On-demand, streams response
       → Context: contact signals, warm path, campaign goal, tier

POST   /api/campaigns/{id}/contacts/{contact_id}/revise
       → Streams rewrite given instruction + current draft
```

---

## Tier Definitions

| Tier | Logic | Send Mode | Email Type |
|---|---|---|---|
| Warm Intro | Warm path exists in graph | Individual queue | Email to the connector, not the target |
| Direct | No warm path, high/mid signal | Batch template | Personalised cold outreach to target |
| Re-engagement | Lapsed donor, previous giving history | Batch template | Reactivation referencing prior relationship |

Tiers are AI-suggested but the fundraiser can move contacts between tiers before generating drafts.

---

## What Makes This Different From B2B SDR Tools

Every existing product — Clay, Apollo, Artisan, 11x — is built for cold B2B sales. High volume, low relationship stakes, spray and pray. 50-70% annual churn on those tools because the model doesn't hold up.

This is built specifically for fundraising:

- **Warm paths are first-class.** No generic tool has network graph data baked into the outreach layer. The system already computed `You → Sarah → Target Donor`. The connector ask is drafted automatically — a fundamentally different and more effective class of outreach.
- **Fundraising context is native.** The AI understands the difference between cultivating a major gift prospect and reactivating a lapsed $500 donor. Tone, ask size, relationship stage — all inform the draft.
- **Human-final by design.** Not a limitation — a feature. The sales pitch is "your judgment, at scale" not "let the AI handle it."
- **Mode-aware.** High-value contacts get individual human review. Mid and lower tiers get template-based batch send. The system doesn't force one mode on every contact.
- **Airtable-native.** No new CRM. No new workflow. The team keeps working exactly where they already work.

---

## Build Phases

### Phase 1 — Foundation (Build First)
The core loop. Everything else depends on this working well.

- [ ] Campaign creation — natural language goal input
- [ ] AI contact segmentation into tiers (Warm Intro / Direct / Re-engagement)
- [ ] Tier card UI — campaign overview page with dual entry points (Review / Batch)
- [ ] Review queue — one contact at a time, context panel + draft
- [ ] On-demand draft generation — generate for current contact only, lives in memory
- [ ] Send action — saves draft to DB, writes to Airtable (Outreach_Stage, Last_Touch_Date, Last_Touch_Type)
- [ ] Skip — marks contact as skipped, stays in campaign, visible in stats
- [ ] Later — returns contact to bottom of queue
- [ ] Progress persistence — resume where you left off

**Definition of done:** A fundraiser can go from goal input to sending their first email end to end. Token cost is proportional to emails sent, not contacts in the campaign.

---

### Phase 2 — AI Editing (High Leverage, Low Complexity)
Adds significant value with relatively contained scope.

- [ ] AI revision bar in the review queue
- [ ] Streaming rewrite output (character by character)
- [ ] Keep / Undo / Original controls
- [ ] AI revision is context-aware (knows tier, warm path, enriched data, campaign goal)
- [ ] Revision history per contact (can see previous versions)

**Definition of done:** Fundraiser can revise any draft with a plain language instruction and see it rewrite in real time.

---

### Phase 3 — Campaign Intelligence (Meaningful Differentiator)
Makes the segmentation smarter and the campaign more strategic.

- [ ] Confidence scoring — AI grades its own drafts, surfaces low-confidence ones
- [ ] Outlier review — show the worst-scored drafts first, not random samples
- [ ] Cluster-based review — group similar contacts, review one representative per cluster
- [ ] Missing variable report — show which contacts had fallback phrases used
- [ ] Move contacts between tiers before generating drafts
- [ ] Campaign-level stats — sent, pending, skipped per tier

**Definition of done:** Fundraiser can understand draft quality across 300+ contacts in under 5 minutes without reading every email.

---

### Phase 4 — Donor Intelligence (Long-Term Differentiator)rm
Deepens the fundraising-specific context over time.

- [ ] Donor lifecycle stage detection (first-time, mid-level, major gift, lapsed)
- [ ] Cultivation vs. solicitation mode — stewardship drafts separate from ask drafts
- [ ] Gift capacity signal integration into tier logic
- [ ] Pull last 3 correspondences as generation context — draft continues a real conversation, not a cold first touch
- [ ] Response tracking — log replies back from email, update Airtable accordingly
- [ ] Follow-up drafts — system detects no response after N days, queues a follow-up draft
- [ ] Campaign performance view — which tiers, which message angles are generating responses

**Definition of done:** The system understands where each donor is in their lifecycle and adjusts outreach strategy accordingly without manual configuration. Drafts feel like continuations of real relationships, not templated first touches.

---

### Phase 5 — Batch Template Send (Scale Without Sacrificing Quality)
Enables mid and lower tiers to be worked at 10x speed with a single template review.

Each step ships backend + frontend together. Nothing is built in isolation.

---

#### Step 1 — Database Foundation
- [ ] **DB** `campaign_templates` table — one row per (campaign, tier), stores subject/body/variables/status
- [ ] **DB** `batch_send_jobs` table — one row per send operation, tracks sent/total/failed/status
- [ ] **DB** `campaign_files` table — uploaded files per campaign, stores filename/type/parsed_content
- [ ] **DB** Run migrations, verify tables exist
- [ ] **API** `GET /campaigns/{id}/templates/{tier}` — fetch saved template (returns null if none yet)
- [ ] **Frontend** Batch Mode entry point on tier row in campaign card — "Batch" button visible for Tier 2 and Tier 3. Clicking opens the batch editor view.

---

#### Step 2 — Signal Scanner
Runs before template generation. Tells the LLM (and the fundraiser) exactly how much signal the tier has before writing anything.

- [ ] **Backend** `signal_scanner.py` — reads all `campaign_contacts` for a (campaign, tier), returns per-variable coverage counts:
  ```
  { first_name: 98%, company: 89%, title: 74%, topic_hook: 68%,
    giving_reference: 31%, capacity_close: 45% }
  ```
- [ ] **API** `GET /campaigns/{id}/templates/{tier}/signal-scan` — returns coverage report
- [ ] **Frontend** Signal coverage panel shown at top of batch editor before template exists:
  ```
  Name 98%  ·  Company 89%  ·  Topics 68%  ·  Giving history 31%
  ```
  Low-coverage signals shown in amber so fundraiser knows to expect fallbacks.

---

#### Step 3 — Variable Resolver
Pure Python, zero LLM. The engine that renders `{{variable}}` slots against a real contact's data at preview and send time.

- [ ] **Backend** `variable_resolver.py` — resolves each slot from `contact_snapshot` + `score_breakdown`:

  | Variable | Source | Fallback |
  |---|---|---|
  | `{{first_name}}` | `contact_snapshot.name` first word | "there" |
  | `{{company}}` | `contact_snapshot.company` | omitted |
  | `{{title}}` | `contact_snapshot.title` | omitted |
  | `{{topic_hook}}` | `signals.topics` → "given your interest in X" | omit whole clause |
  | `{{giving_reference}}` | `signals.giving` → "your past support of X" | "your commitment to this work" |
  | `{{capacity_close}}` | `signals.capacity` + tier → "a leadership-level gift" / "a significant contribution" / "a gift at any level" | "a contribution at any level" |
  | `{{warm_opener}}` | `warm_path_data.connector` → "I was speaking with X recently and" | omit (Tier 1 only) |

- [ ] **Backend** Two-layer slot format: `{{variable | fallback: "phrase"}}` — resolver uses primary if signal exists, fallback if not, omits clause if fallback is `""`
- [ ] **Backend** Unit tests for resolver covering all variables and fallback paths

---

#### Step 4 — Template Generation
One LLM call per tier. The LLM receives the signal coverage profile so it writes prose that degrades gracefully when signals are missing.

- [ ] **API** `POST /campaigns/{id}/templates/{tier}/generate` — samples up to 20 contacts from tier, runs signal scan, passes coverage + contact samples + campaign goal to LLM, returns `{ subject, body, variables, tier_summary }`
- [ ] **API** `PUT /campaigns/{id}/templates/{tier}` — save manual edits `{ subject, body }`
- [ ] **API** `POST /campaigns/{id}/templates/{tier}/approve` — set status = 'approved', lock template
- [ ] **Frontend** Batch editor left pane: editable subject + body fields. `{{variable}}` slots highlighted in a distinct colour. "Generate" button triggers LLM call with loading state. "Regenerate" clears and re-runs.
- [ ] **Frontend** Template locked visually when approved — fields become read-only, "Unlock to edit" button appears.

---

#### Step 5 — Live Preview Panel
Renders real contacts against the template with no LLM. Shows the fundraiser exactly what each email will look like, including which variables resolved and which hit fallbacks.

- [ ] **API** `POST /campaigns/{id}/templates/{tier}/preview` — takes current `{ subject, body }` + optional `contact_ids` (defaults to 5 random pending contacts from tier), runs resolver on each, returns:
  ```json
  [{ contact_name, rendered_subject, rendered_body, resolved_vars, fallback_vars, missing_vars }]
  ```
- [ ] **Frontend** Right pane shows rendered email for one contact at a time. ◀ ▶ to cycle through the 5 samples.
- [ ] **Frontend** Resolution status below preview:
  ```
  ✓ topic_hook resolved   ✓ first_name resolved   ✗ giving_reference → fallback used
  ```
- [ ] **Frontend** Tier-wide resolution summary: "Of 187 contacts — 128 resolve topic_hook, 59 will use fallback phrase"
- [ ] **Frontend** Preview auto-refreshes as the fundraiser edits the template (debounced 800ms)

---

#### Step 6 — File Upload Copilot

**Primary use case: the file IS the template starter.**

The fundraiser may already have a draft email — a Word doc, PDF, or plain text they wrote offline. They upload it and the LLM's job is to *refine* it, not generate from scratch. The split panel shows their existing prose on the left and the LLM layers in `{{variable}}` slots and optionally tightens the copy.

**Variable discovery for file-uploaded templates:** Variables always come from the LLM's output, not the file itself. The LLM reads the draft prose + signal availability map → decides where personalisation slots fit naturally → writes the refined version with `{{variable | fallback}}` markers. If the draft already says "Dear [Name]", the LLM converts it to `{{first_name}}`. If a paragraph references the recipient's organisation, it wraps it in `{{company}}`. The signal scanner (Step 2) tells the LLM which variables are worth using before it touches the draft.

**Two modes, same split panel:**
- **Refine mode** — file uploaded, LLM works from the fundraiser's draft
- **Generate mode** — no file, LLM writes from scratch using campaign goal + signal profile

In both cases the output is the same: a template body with `{{variable}}` slots, previewed live on the right.

**Secondary use cases for non-prose files:**
- **CSV/XLSX** — cross-reference rows with tier contacts by name/email to fill missing signals (giving history, event attendance, capacity notes not in Airtable). After parse, re-run signal scan to show coverage improvement.
- **PDF/DOCX without a draft** — case for support, talking points, campaign brief. Passed as LLM context for richer language. Does not define variables.

---

- [ ] **API** `POST /campaigns/{id}/files` — upload file, parse it, store in `campaign_files`. For CSV/XLSX: fuzzy-match rows to `campaign_contacts` by name/email, merge new signal values without overwriting enrichment data. For prose files (PDF/DOCX/TXT): extract raw text and store as `parsed_content`.
- [ ] **Backend** File parsers: `pandas` for CSV/XLSX, `pypdf` for PDF, `python-docx` for DOCX, plain read for TXT
- [ ] **Backend** CSV cross-reference logic: fuzzy-name + email match, merge signals, never overwrite existing enrichment
- [ ] **API** After CSV upload: re-run signal scan, return updated coverage diff
- [ ] **API** `POST /campaigns/{id}/templates/{tier}/generate` — accepts optional `file_id`. If the file is a prose draft (PDF/DOCX/TXT): pass raw text as the template starter — LLM refines and injects slots. If CSV: use patched signal data only. If no file: generate from scratch.
- [ ] **Frontend** File upload zone in batch editor — drag and drop or click. After upload: shows filename, file type badge, "Remove". If CSV: shows "↑ X more signals available" after re-scan.
- [ ] **Frontend** After CSV upload: signal coverage panel updates — "giving_reference: 31% → 67%"
- [ ] **Frontend** Copilot instruction bar at bottom of left pane (visible in both refine and generate mode):
  ```
  [ make it shorter, lead with the Hopkins connection... ]  [ ↑ ]
  ```
  LLM revises the current template body in context of the uploaded file. "Undo" reverts. Instructions are additive — the LLM always works from the current draft state, not the original.
- [ ] **Frontend** Preview panel updates resolution counts automatically after any file upload or instruction

---

#### Step 7 — Gmail OAuth
Send from the fundraiser's own Gmail account, not a bulk sender. Emails land in their Sent folder, threads reply naturally.

- [ ] **DB** `gmail_tokens` table — stores access_token, refresh_token, expiry, email per user
- [ ] **Backend** Uncomment `GOOGLE_CREDENTIALS_JSON` in `.env`
- [ ] **API** `GET /auth/gmail` — starts OAuth flow, redirects to Google consent screen (scope: `gmail.send`, `gmail.readonly`)
- [ ] **API** `GET /auth/gmail/callback` — exchanges code for tokens, stores in `gmail_tokens`, redirects to app
- [ ] **API** `GET /auth/gmail/status` — returns `{ connected: bool, email: str }`
- [ ] **Backend** Token refresh logic — auto-refresh access token using refresh token before each send
- [ ] **Frontend** Gmail connection status shown in outreach page header. "Connect Gmail" button if not connected. Shows connected email address if connected.
- [ ] **Frontend** Approve & Send button disabled with tooltip "Connect Gmail to send" if not connected.

---

#### Step 8 — Batch Send Runner
Async job that renders each contact's email and sends it via Gmail API. Rate-limited to respect Gmail's 2000/day limit.

- [ ] **Backend** `batch_sender.py` — async worker: for each pending contact in tier, run resolver → render subject + body → send via Gmail API → mark `campaign_contacts.status = 'sent'`, store rendered email in `sent_draft`, write three fields to Airtable
- [ ] **Backend** Rate limiting: 1 email per 200ms (stays well under Gmail limits), configurable
- [ ] **Backend** Per-contact error handling — failed sends logged, don't stop the job, retried once
- [ ] **API** `POST /campaigns/{id}/templates/{tier}/send` — creates `batch_send_job`, starts async runner, returns `{ job_id }`
- [ ] **API** `GET /campaigns/{id}/batch-jobs/{job_id}/events` — SSE stream: `{ sent: N, total: M, status, current_contact_name }`
- [ ] **API** `POST /campaigns/{id}/batch-jobs/{job_id}/cancel` — gracefully stops runner
- [ ] **Frontend** "Approve & Send N emails" button — confirms then starts job
- [ ] **Frontend** Progress view replaces editor after send starts: real-time counter, current contact name, cancel button
- [ ] **Frontend** On complete: summary — sent / failed / fallbacks used. Option to view fallback report.

---

#### Step 9 — Fallback Report
After a batch send, shows which contacts received fallback phrases so the fundraiser knows where enrichment would help most in the next campaign.

- [ ] **API** `GET /campaigns/{id}/batch-jobs/{job_id}/fallback-report` — lists contacts + which variables used fallbacks
- [ ] **Frontend** Post-send screen shows fallback summary. Downloadable as CSV for re-enrichment targeting.

---

**Definition of done:** Fundraiser uploads a campaign brief, reviews a generated template against 5 live contacts, sees signal coverage across the tier, approves, and sends 200 personalised emails from their own Gmail in under 10 minutes. Each contact receives a rendered email. Zero LLM calls at send time. Fallback phrases are visible before and after send.

**Token economics:**
- Individual mode: 1 draft generation call per email sent
- Batch mode: 1 template generation call per tier (+ optional revision calls), regardless of tier size
- A campaign with Tier 1 (50 sent individually) + Tier 2 (200 batch) = ~51 LLM calls total, not 250
