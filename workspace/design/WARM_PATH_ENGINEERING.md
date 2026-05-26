# Warm Path Engineering

## Goal

For each high-value contact (Tier 1/2) in Airtable, surface which other contacts
can make an introduction — and why. Computed post-enrichment, written back to
Airtable as four fields, consumed by the Campaign tab.

---

## Data Source

All career data already lives in Airtable from the original Apify scrape.

`last_three_roles` (multilineText) — written by `extract_career_progression()`:
```
VP Engineering at Stripe (2018–2020)
Senior Engineer at Coinbase (2016–2018)
Software Engineer at Google (2014–2016)
```

Dates came from Apify (`startDate.year` / `endDate.year`). Already stored.
No re-scrape needed. Parse what is there, fall back gracefully where dates
are missing for a given record.

---

## Tier Classification

```
Tier 1 — primary targets
  EXITED_FOUNDER, SERIAL_FOUNDER

Tier 2 — secondary targets
  SENIOR_OPERATOR, RSU_BENEFICIARY

Bridge pool — everyone
  All 3,790 contacts regardless of tier
  A Tier 3 contact can bridge to a Tier 1 target
```

---

## Algorithm

### Step 1 — Load contacts
Pull all contacts from Airtable where `trajectory_tag` is populated.
Fields: `record_id`, `Name`, `trajectory_tag`, `last_three_roles`.

### Step 2 — Parse career records

Regex parse each line of `last_three_roles`:

```
pattern:  ^(.+?) at (.+?) \((\d{4})?[–\-](\d{4}|present)?\)$

"VP Engineering at Stripe (2018–2020)"
→ {title: "VP Engineering", company: "Stripe", start: 2018, end: 2020}

"CEO at Acme (2021–present)"
→ {title: "CEO", company: "Acme", start: 2021, end: None}  ← None = still there

"Founder at Stealth (–present)"  ← start year missing
→ {title: "Founder", company: "Stealth", start: None, end: None}
```

Fallback for lines that don't match the pattern: extract company from
`" at "` split, set both dates to None. Company overlap still scores,
just at base confidence.

### Step 3 — Company normalization

```
normalize(raw: str) -> str

1. Lowercase
2. Strip legal suffixes:
     inc, incorporated, llc, ltd, limited, corp, corporation,
     co, company, plc, group, holdings, technologies, technology,
     tech, services, solutions, systems, ventures, capital,
     partners, management, international, global, foundation
3. Strip punctuation (preserve spaces)
4. Strip leading "the "
5. Collapse whitespace, strip
6. Known aliases (applied after steps 1–5):
     facebook      → meta
     instagram     → meta
     whatsapp      → meta
     google        → alphabet
     youtube       → alphabet
     deepmind      → alphabet
     jp morgan     → jpmorgan
     j p morgan    → jpmorgan
     mckinsey company      → mckinsey
     mckinsey and company  → mckinsey
     booz allen hamilton   → booz allen
     pricewaterhousecoopers → pwc
     price waterhouse      → pwc
     ernst young           → ey
     ernst and young       → ey
     kpmg peat marwick     → kpmg
     deloitte touche       → deloitte
     (extensible — aliases added as false negatives surface)
7. Fuzzy pass — Levenshtein distance <= 1 for strings >= 8 chars
   catches minor variants: "stripe inc" vs "stripe" already handled
   by step 2, but catches typos and encoding differences
```

### Step 4 — Build inverted index

One pass over all contacts, built in memory:

```python
index: Dict[str, List[Entry]] = {}

for contact in all_contacts:
    for role in contact.parsed_roles:
        key = normalize(role.company)
        if not key:
            continue
        index[key].append({
            "contact_id":    contact.record_id,
            "name":          contact.name,
            "title":         role.title,
            "start":         role.start_year,   # int or None
            "end":           role.end_year,     # int or None = present
            "trajectory":    contact.trajectory_tag,
        })
```

Built once, used for all target lookups, discarded after job.

### Step 5 — Find paths

```python
CURRENT_YEAR = 2026

for target in tier_1_and_tier_2_contacts:
    raw_paths = []

    for role in target.parsed_roles:
        key = normalize(role.company)
        candidates = index.get(key, [])

        for c in candidates:
            if c["contact_id"] == target.record_id:
                continue  # skip self

            score, evidence = score_overlap(
                t_start=role.start_year,
                t_end=role.end_year,
                b_start=c["start"],
                b_end=c["end"],
                company=role.company,
                t_title=role.title,
                b_title=c["title"],
            )

            if score > 0:
                raw_paths.append({
                    "bridge_id":   c["contact_id"],
                    "bridge_name": c["name"],
                    "company":     role.company,
                    "score":       score,
                    "evidence":    evidence,
                })

    # if same bridge appears via multiple companies, keep highest score
    paths = deduplicate_by_bridge(raw_paths)
    paths = sorted(paths, key=lambda p: p["score"], reverse=True)[:5]

    results[target.record_id] = paths
```

### Step 6 — Scoring

```
Both dates available:
  overlap = min(t_end, b_end) - max(t_start, b_start)
    where None end = CURRENT_YEAR (still there)
    where None start = treated as partial info, use base

  overlap < 0  → score = 0     (different eras, discard)
  overlap == 0 → score = 35    (same company, barely overlapped)
  overlap >= 1 → score = 55
  overlap >= 2 → score = 70
  overlap >= 3 → score = 80

Modifiers:
  +10  both still at company (both end = None)
  +10  both senior (C-suite / VP / Director / Partner / Principal)
  +15  known small company — not in LARGE_CORP_LIST below
  -15  company in LARGE_CORP_LIST (Google, Meta, Amazon etc.)
        unless overlap >= 2 years (long co-tenure recovers trust)

One or both dates missing:
  score = 45  (company match confirmed, duration unknown)
  no date modifiers applied

Cap: 100

LARGE_CORP_LIST (deprioritize — too many employees, weak signal):
  google, alphabet, meta, amazon, microsoft, apple, netflix,
  salesforce, oracle, ibm, accenture, deloitte, pwc, ey, kpmg,
  mckinsey, bcg, bain, goldman sachs, jpmorgan, morgan stanley,
  blackrock, bank of america, wells fargo, citigroup
```

### Step 7 — Evidence string

```
"Both at Stripe · 2018–2020 · 2yr overlap"
"Both at Stripe · Marcus still there"
"Both at Coinbase · 1yr overlap"
"Both at Stripe · (dates unavailable)"
```

### Step 8 — Write back to Airtable

Four new fields on each TARGET contact record (Tier 1/2 only):

| Field | Type | Example |
|---|---|---|
| `warm_path_top_bridge` | singleLineText | `"Marcus Williams"` |
| `warm_path_evidence` | multilineText | top 3 paths, one per line |
| `warm_path_score` | number | `80` |
| `warm_path_computed_at` | dateTime | ISO timestamp |

Written via batch Airtable update (10 records/request, rate-limited).
Idempotent — overwrites on every run. No stale data accumulates.

---

## Build Layers

```
Layer 1 — Normalizer
  File:  backend/intelligence/warmpath/normalizer.py
  Test:  run against real company names from batch CSVs
  Goal:  zero false negatives on known aliases, no over-collapsing

Layer 2 — Parser
  File:  backend/intelligence/warmpath/parser.py
  Test:  parse last_three_roles samples from Airtable
  Goal:  correct date extraction, graceful fallback on missing dates

Layer 3 — Index + Matcher
  File:  backend/intelligence/warmpath/matcher.py
  Test:  run against full 3,790 contacts, inspect top paths manually
  Goal:  surfaces real connections, no obvious false positives

Layer 4 — Scorer
  Integrated into matcher
  Test:  spot-check scores against known relationships if any exist
  Goal:  HIGH scores feel trustworthy, LOW scores feel appropriately weak

Layer 5 — Airtable Writer
  File:  backend/intelligence/warmpath/writer.py
  Test:  dry-run mode first, inspect fields before live write
  Goal:  correct fields written to correct records, no overwrites of
         non-warm-path fields

Layer 6 — Job Integration
  Trigger after enrichment batch completes
  Manual re-run endpoint for ad-hoc use
```

---

## Open Questions

1. **Education overlap** — LinkedIn education not currently in `last_three_roles`.
   Not in scope until career_json structured field is added.

2. **Large company false positives** — Phase 1 may surface "Both at Google"
   paths with no date data. LARGE_CORP_LIST penalty handles this but
   manual review of first run output will tune the list.

3. **Campaign tab** — how paths are presented and actioned is a separate
   design decision. This doc covers computation only.
