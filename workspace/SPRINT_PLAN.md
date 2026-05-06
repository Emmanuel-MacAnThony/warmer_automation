# Phase 1 Sprint Plan — Contact Intelligence
**3 Sprints | ~44 hours total | Goal: 511 contacts fully qualified in under 1 minute**

---

## The Bigger Picture

Every sprint delivers signals that feed the final wealth scoring composite (Task 1.7).
The pipeline shape is:

```
LinkedIn Profile + Posts (1.1)
        ↓
Career Trajectory (1.5) ─────────────────────┐
Press & News (1.3)       ─────────────────────┤
Crunchbase (1.2)         ─────────────────────┤──→ Wealth Score (1.7) → Ranked Outreach List
Onchain Wealth (1.4)     ─────────────────────┤
Warm Path (1.6)          ─────────────────────┘
```

Nothing in Sprint 2 or 3 starts before Sprint 1 is validated.

---

## Sprint 1 — Signal Layer (Zero New Credentials)
**Duration:** 1 week | **Effort:** ~11 hours
**Theme:** Squeeze maximum signal from infrastructure already live

### What We're Building
1. **Upgrade LinkedIn scraper** to `harvestapi` actor → adds post data at 5x lower cost
2. **Career Trajectory Classifier** → LLM tag over existing LinkedIn data
3. **Press & News Check** → SerpAPI queries already wired up, just new query pattern

### Why Sprint 1 First
- Tasks 1.5 and 1.3 have zero new credentials, zero new dependencies — they can ship immediately
- Post data from Task 1.1 upgrade unlocks richer trajectory signals in Task 1.5
- Each of these 3 tasks is additive — they enrich contacts the pipeline has already processed
- Delivers measurable new CRM columns within the first week

### Contribution to Bigger Goal
Sprint 1 adds 3 of the 6 signal types the wealth scorer needs. By end of Sprint 1, every contact in the 511 shortlist has: career archetype, news flags, and a richer LinkedIn profile with posts. That alone transforms a raw name into a research-ready record.

---

### Task 1.1 Upgrade — Swap LinkedIn Actor + Add Posts

**File:** `backend/clients/linkedin_scraper.py`

```
CURRENT ACTOR: dev_fusion/linkedin-profile-scraper
NEW ACTOR:     harvestapi/linkedin-profile-posts

INPUT:  linkedin_url (same as before)
OUTPUT: all existing profile fields + posts[]

CHANGE:
  1. Update ACTOR_ID constant
  2. Map new response shape to existing ProfileData schema
  3. Add new field: recent_posts → list of { text, date, likes, comments }
  4. Add recent_posts to FIELD_MAPPING config and Airtable output

SCHEMA ADDITION (Airtable):
  - recent_posts_raw        (multilineText)  — top 3 posts joined as text
  - recent_posts_count      (number)         — how many posts scraped
  - last_post_date          (singleLineText) — ISO date of most recent post

VALIDATION:
  Run on 10 known contacts
  Compare output fields vs existing schema — confirm no regressions
  Confirm cost: $2/1k records vs current $10/1k
```

---

### Task 1.5 — Career Trajectory Classifier

**File:** `backend/enrichment/trajectory_classifier.py`

```
INPUT:  contact record with linkedin_data (career history JSON already in CRM)

ARCHETYPES:
  RSU_BENEFICIARY     — long tenure at public company (4+ yrs, senior IC or manager)
  EARLY_EMPLOYEE      — joined pre-IPO/pre-acquisition, left after event
  SERIAL_FOUNDER      — 2+ founding roles in career history
  SENIOR_OPERATOR     — C-suite or VP, not founder, tenure across multiple orgs
  EXITED_FOUNDER      — founded once, exited, now in advisory/board/soft role

PSEUDOCODE:

  function classify_trajectory(linkedin_data):

    career_history = linkedin_data["experience"]  # list of roles

    prompt = """
      Given this career history, classify this person into exactly one of:
      RSU_BENEFICIARY, EARLY_EMPLOYEE, SERIAL_FOUNDER, SENIOR_OPERATOR, EXITED_FOUNDER

      Rules:
      - RSU_BENEFICIARY: 4+ years at a post-IPO tech company in senior IC/manager role
      - EARLY_EMPLOYEE: joined pre-IPO startup, short tenure, left after liquidity event
      - SERIAL_FOUNDER: "founder", "co-founder" appears 2+ times across roles
      - SENIOR_OPERATOR: C-suite or VP title, never founder, multiple companies
      - EXITED_FOUNDER: founder once, current role is board/advisor/investor/soft

      Also include: recent_posts (if available) as supporting context.

      Return JSON: { "tag": "<archetype>", "signal": "<1 sentence plain English explanation>" }
    """

    response = openai.chat(prompt + json(career_history) + json(recent_posts))
    parsed = parse_json(response)

    return {
      "trajectory_tag":    parsed["tag"],       # enum value
      "trajectory_signal": parsed["signal"]     # plain English
    }

INTEGRATION:
  Add classify_trajectory() call inside BatchAnalyzer.analyze_profile()
  Runs on same OpenAI call batch — no extra API round trip needed
  Output fields added to FIELD_MAPPING config

AIRTABLE FIELDS:
  - trajectory_tag    (singleSelect)   — one of 5 enum values
  - trajectory_signal (multilineText)  — plain English explanation
```

---

### Task 1.3 — Press & News Mention Check

**File:** `backend/clients/news_client.py`

```
INPUT:  first_name, last_name, current_company

SERPAPI QUERY:
  query = f'"{first_name} {last_name}" "{company}" news'
  params = { engine: "google", tbm: "nws", num: 10 }
  — reuse existing Config.SERPAPI_KEY

PSEUDOCODE:

  function check_press_mentions(name, company):

    results = serpapi.search(query=f'"{name}" "{company}"', news=True, limit=10)

    articles = results["news_results"]  # list of { title, source, date, link }

    # Count and deduplicate outlets
    outlets = deduplicate([a["source"] for a in articles])
    press_count = len(articles)

    # Keyword flagging — scan titles for signal words
    FLAG_KEYWORDS = {
      "exit":        ["acquired", "acquisition", "merger", "sold"],
      "investment":  ["invested", "funding", "raised", "led round"],
      "litigation":  ["lawsuit", "sued", "settlement", "SEC", "fraud"],
      "leadership":  ["appointed", "named CEO", "joins board", "promoted"]
    }

    flags = []
    notable_headline = ""
    for article in articles:
      title = article["title"].lower()
      for flag, keywords in FLAG_KEYWORDS.items():
        if any(kw in title for kw in keywords):
          flags.append(flag)
      if not notable_headline and any flag triggered:
        notable_headline = article["title"]

    return {
      "press_count":       press_count,
      "top_outlets":       ", ".join(outlets[:3]),
      "press_flags":       list(set(flags)),       # deduplicated
      "notable_headline":  notable_headline
    }

INTEGRATION:
  Add news_client call inside BatchExecutor._run_batch()
  Runs in parallel with LinkedIn scrape (async gather)
  Graceful null return if SerpAPI returns no results

AIRTABLE FIELDS:
  - press_count       (number)
  - top_outlets       (singleLineText)
  - press_flags       (multipleSelects)  — exit, investment, litigation, leadership
  - notable_headline  (multilineText)
```

---

## Sprint 2 — Wealth Signal Expansion (New Data Sources)
**Duration:** 1.5 weeks | **Effort:** ~17 hours
**Theme:** Pull in financial and investment data that proves net worth

### What We're Building
1. **Crunchbase Enrichment** → investment history, portfolio companies, exits
2. **Onchain Wealth Verification** → wallet holdings for crypto contacts
3. **Wealth Score Composite (v1)** → first composite score from all signals gathered so far

### Why Sprint 2 Second
- Sprint 1 gives career and press signals — useful but not conclusive for wealth
- Crunchbase and onchain data are the strongest quantitative wealth indicators
- Wealth Score v1 ships at end of Sprint 2 on available signals — doesn't wait for warm path
- Crypto contacts are currently taking 37 min manual; this sprint eliminates that entirely

### Contribution to Bigger Goal
After Sprint 2, every contact has a preliminary wealth confidence rating. The fundraising team can start prioritising outreach on the top-rated contacts while Sprint 3 completes. This de-risks the timeline — Phase 1 delivers value before it's 100% done.

---

### Task 1.2 — Crunchbase Enrichment

**File:** `backend/clients/crunchbase_client.py`

```
INPUT:  crunchbase_url (already stored in CRM for ~40% of contacts)
        fallback: full_name + company for API search

CRUNCHBASE PRO API:
  Base URL: https://api.crunchbase.com/api/v4
  Auth:     ?user_key=CRUNCHBASE_API_KEY
  Endpoint: /entities/people/{permalink}
            /searches/people  (for name-based fallback)

PSEUDOCODE:

  function enrich_crunchbase(crunchbase_url=None, name=None, company=None):

    if crunchbase_url:
      permalink = extract_permalink(crunchbase_url)  # last segment of URL
      data = GET /entities/people/{permalink}?field_ids=investments,exits,board_roles
    else:
      # Fallback: search by name
      data = POST /searches/people  body={ name: name, org: company, limit: 1 }
      if no results: return null

    investments = data["investments"]  # list of { company, amount, date, stage }
    exits       = data["exits"]        # list of { company, exit_type, date, amount }

    return {
      "crunchbase_total_investments": len(investments),
      "crunchbase_notable_exits":     format_exits(exits[:3]),
      "crunchbase_portfolio":         comma_join([i["company"] for i in investments[:5]]),
      "crunchbase_last_investment":   investments[0]["date"] if investments else null
    }

  function format_exits(exits):
    # "Acme Corp (Acquired, $50M, 2022), Beta Inc (IPO, 2021)"
    return comma_join([f'{e["company"]} ({e["exit_type"]}, {e["date"]})' for e in exits])

INTEGRATION:
  Add as optional enrichment step in BatchExecutor._run_batch()
  Skip gracefully if no crunchbase_url AND name search returns no match
  Rate limit: 200 req/min — add 0.3s sleep between calls in batch loop

AIRTABLE FIELDS:
  - crunchbase_total_investments  (number)
  - crunchbase_notable_exits      (multilineText)
  - crunchbase_portfolio          (multilineText)
  - crunchbase_last_investment    (singleLineText)

BLOCKER: Crunchbase Pro API key required before starting.
```

---

### Task 1.4 — Onchain Wealth Verification

**File:** `backend/clients/arkham_client.py`
**Runs only when:** `contact_type == "crypto"` in CRM

```
INPUT:  full_name, company (for entity resolution)
        optional: known_wallet_address (if already in CRM)

ARKHAM API:
  Base URL: https://api.arkhamintelligence.com
  Auth:     API-Key header
  Endpoints:
    GET /intelligence/entities?name={name}   — entity search
    GET /intelligence/address/{address}/portfolio  — holdings
    GET /intelligence/address/{address}/transactions?period=30d  — tx volume

PSEUDOCODE:

  function verify_onchain_wealth(name, company, known_wallet=None):

    if known_wallet:
      address = known_wallet
    else:
      # Resolve name → entity → wallet
      entities = GET /intelligence/entities?name=name&type=person
      best_match = find_best_entity(entities, name, company)
        # score by: name similarity + company match
        # reject if confidence < 0.8 (flag for manual review)
      if no confident match: return { onchain_verified: false }
      address = best_match["addresses"][0]

    holdings  = GET /intelligence/address/{address}/portfolio
    tx_data   = GET /intelligence/address/{address}/transactions?period=30d

    total_usd     = sum([h["usd_value"] for h in holdings])
    top_tokens    = top_3_by_value(holdings)
    tx_volume_30d = sum([t["usd_value"] for t in tx_data])
    wallet_age    = days_since(holdings["first_transaction_date"])

    return {
      "onchain_wealth_usd":     round(total_usd),
      "onchain_top_holdings":   format_holdings(top_tokens),
      "onchain_tx_volume_30d":  round(tx_volume_30d),
      "onchain_wallet_age_days": wallet_age,
      "onchain_verified":       True
    }

  function find_best_entity(entities, name, company):
    for entity in entities:
      name_score    = fuzzy_match(entity["name"], name)
      company_score = fuzzy_match(entity["organization"], company)
      if name_score > 0.9 and company_score > 0.7:
        return entity
    return None  # no confident match

INTEGRATION:
  Add conditional check at top of _run_batch():
    if record["contact_type"] == "crypto": run arkham enrichment
  Confidence threshold rejects low-match entities — never write wrong wallet to CRM

AIRTABLE FIELDS:
  - onchain_wealth_usd      (number)
  - onchain_top_holdings    (multilineText)
  - onchain_tx_volume_30d   (number)
  - onchain_wallet_age_days (number)
  - onchain_verified        (checkbox)

BLOCKER: Arkham API access + contact_type field in CRM required before starting.
```

---

### Task 1.7 — Wealth Score Composite (v1)

**File:** `backend/enrichment/wealth_scorer.py`
**Note:** Ships end of Sprint 2 on available signals. Updated end of Sprint 3 when warm path data is added.

```
INPUT:  fully enriched contact record (all fields from Tasks 1.1–1.5 + 1.2 if available)

SCORING MODEL:

  MAX SCORE: 100 points

  Signal                          | Points | Condition
  --------------------------------|--------|----------
  Crunchbase exits (1+)           |   25   | at least one exit on record
  Career archetype = EXITED_FOUNDER|  20   | trajectory_tag match
  Career archetype = EARLY_EMPLOYEE|  15   | trajectory_tag match
  Career archetype = SERIAL_FOUNDER|  15   | trajectory_tag match
  Press flag = exit or investment |   15   | press_flags contains either
  Onchain wealth > $1M            |   20   | crypto contacts only
  Onchain wealth > $10M           |   30   | crypto contacts only (replaces above)
  Press count > 5                 |    5   | high media presence
  LinkedIn follower count > 5000  |    5   | public reach signal
  Warm connection (Sprint 3)      |   10   | added in Sprint 3

PSEUDOCODE:

  function score_contact(record):

    score = 0
    signals = []

    # Investment/exit signals
    if record["crunchbase_total_investments"] > 0:
      score += 25
      signals.append("Crunchbase exits confirmed")

    # Career archetype signals
    archetype_scores = {
      "EXITED_FOUNDER": 20,
      "EARLY_EMPLOYEE": 15,
      "SERIAL_FOUNDER": 15,
      "SENIOR_OPERATOR": 10,
      "RSU_BENEFICIARY": 10
    }
    if record["trajectory_tag"] in archetype_scores:
      points = archetype_scores[record["trajectory_tag"]]
      score += points
      signals.append(f'Career: {record["trajectory_signal"]}')

    # Press signals
    if "exit" in record["press_flags"] or "investment" in record["press_flags"]:
      score += 15
      signals.append(f'Press: {record["notable_headline"]}')

    # Onchain signals (crypto contacts)
    if record["onchain_verified"]:
      if record["onchain_wealth_usd"] >= 10_000_000:
        score += 30
        signals.append(f'Onchain: ${record["onchain_wealth_usd"]:,} verified')
      elif record["onchain_wealth_usd"] >= 1_000_000:
        score += 20
        signals.append(f'Onchain: ${record["onchain_wealth_usd"]:,} verified')

    # Reach signals
    if record.get("follower_count", 0) > 5000:
      score += 5
      signals.append("LinkedIn reach: 5k+ followers")

    # Derive confidence tier
    if score >= 60:   confidence = "High"
    elif score >= 35: confidence = "Medium"
    else:             confidence = "Low"

    return {
      "wealth_confidence":    confidence,
      "wealth_score":         score,
      "wealth_signal_trail":  " | ".join(signals)
    }

INTEGRATION:
  Runs last in BatchAnalyzer.analyze_profile() after all enrichment steps
  Re-runs automatically when warm path data is added in Sprint 3

AIRTABLE FIELDS:
  - wealth_confidence    (singleSelect)   — High / Medium / Low
  - wealth_score         (number)
  - wealth_signal_trail  (multilineText)  — pipe-separated signal explanations
```

---

## Sprint 3 — Network Intelligence (Highest Complexity)
**Duration:** 1.5 weeks | **Effort:** ~16 hours
**Theme:** Map who on the team already knows each prospect — and who can open the door

### What We're Building
1. **Posts-Based Warm Signal Layer** — use Sprint 1 posts data to find team engagement on prospect content
2. **LinkedIn Network Graph** — export team connections, build adjacency map to prospects
3. **Mutual Connection Ranker** — surface the best intro path per prospect
4. **Wealth Score v2** — add warm path signal to composite scoring

### Why Sprint 3 Last
- Highest complexity, highest data dependency (requires all team members to export Sales Navigator data)
- Warm path data is the difference between a cold outreach and a warm intro — directly increases close rate
- Runs after the rest of the pipeline is validated so network data augments an already-rich profile

### Contribution to Bigger Goal
A warm intro from the right person is worth more than any wealth signal. Sprint 3 turns the prospect list from "qualified" to "ready to close" — it tells the team not just who to call, but who should make the introduction and why.

---

### Task 1.6a — Posts Engagement Layer (Warm Signal from Sprint 1 Data)

**File:** `backend/enrichment/posts_engagement.py`
**Runs on:** `recent_posts` field already populated from Task 1.1 upgrade

```
INPUT:  prospect's recent_posts (from Sprint 1)
        team_profiles — list of team LinkedIn profile URLs/names

PSEUDOCODE:

  function detect_team_engagement(recent_posts, team_profiles):

    warm_signals = []

    for post in recent_posts:
      # Check likers and commenters against team member list
      likers    = post.get("likers", [])     # names/profiles who liked
      commenters= post.get("commenters", []) # names/profiles who commented

      for member in team_profiles:
        if member["name"] in likers:
          warm_signals.append({
            "member": member["name"],
            "type":   "liked",
            "post_snippet": post["text"][:100],
            "date":   post["date"]
          })
        if member["name"] in commenters:
          warm_signals.append({
            "member": member["name"],
            "type":   "commented",           # stronger signal than like
            "post_snippet": post["text"][:100],
            "date":   post["date"]
          })

    # Rank: commented > liked, recent > old
    warm_signals.sort(key=lambda x: (x["type"] == "commented", x["date"]), reverse=True)

    return {
      "post_warm_signal":   warm_signals[0]["member"] if warm_signals else null,
      "post_warm_context":  format_signal(warm_signals[0]) if warm_signals else null
    }

  function format_signal(signal):
    # "Bradford commented on their post about DeFi liquidity (Mar 2026)"
    return f'{signal["member"]} {signal["type"]} on their post about "{signal["post_snippet"]}" ({signal["date"]})'
```

---

### Task 1.6b — LinkedIn Network Graph

**File:** `backend/enrichment/network_graph.py`

```
INPUT:  team_network.csv  — exported from LinkedIn Sales Navigator by each team member
        prospect_list     — all 511 shortlisted contacts with LinkedIn URLs

DATA PREP (one-time, manual step):
  Each team member exports their 1st-degree connections from Sales Navigator
  Files merged and deduplicated into: data/team_network.csv
  Schema: { team_member, connection_name, connection_linkedin_url, connection_title, connection_company }

PSEUDOCODE:

  function build_network_graph(team_network_csv):

    graph = {}  # { linkedin_url: [{ team_member, relationship_strength }] }

    for row in team_network_csv:
      url = row["connection_linkedin_url"]
      if url not in graph:
        graph[url] = []
      graph[url].append({
        "team_member": row["team_member"],
        "strength":    1  # base score; upgraded in rank step
      })

    return graph


  function find_mutual_connections(prospect_linkedin_url, graph):

    if prospect_linkedin_url not in graph:
      return { "mutual_connections": [], "top_introducer": null }

    connections = graph[prospect_linkedin_url]

    # Rank by strength (future: factor in recency of interaction)
    ranked = sort_by(connections, key="strength", descending=True)

    top = ranked[0]
    return {
      "mutual_connections":      [c["team_member"] for c in ranked],
      "mutual_connection_count": len(ranked),
      "top_introducer":          top["team_member"],
      "intro_context":           f'Direct connection via {top["team_member"]}\'s LinkedIn network'
    }

INTEGRATION:
  graph = build_network_graph("data/team_network.csv")  — load once at startup
  Call find_mutual_connections(record["linkedin_url"], graph) per contact in batch
  Zero API calls — pure in-memory graph traversal

AIRTABLE FIELDS:
  - mutual_connections       (multilineText)  — comma-separated team members
  - mutual_connection_count  (number)
  - top_introducer           (singleLineText) — name of best intro path
  - intro_context            (multilineText)  — plain English intro context
  - post_warm_signal         (singleLineText) — team member who engaged with posts
  - post_warm_context        (multilineText)  — what the engagement was

BLOCKER: All team members must export Sales Navigator connections before this task starts.
```

---

### Task 1.7 Update — Wealth Score v2 (Add Warm Path Signal)

```
CHANGE TO wealth_scorer.py:

  # Add after existing scoring logic:

  # Warm path signal
  if record.get("top_introducer"):
    score += 10
    signals.append(f'Warm path: intro via {record["top_introducer"]}')

  if record.get("post_warm_signal"):
    score += 5
    signals.append(f'Post engagement: {record["post_warm_context"]}')

  # Re-derive confidence tier with updated score
  # (same thresholds: High ≥ 60, Medium ≥ 35, Low < 35)
```

---

## Sprint Summary

| Sprint | Theme | Effort | Key Output |
|--------|-------|--------|-----------|
| 1 | Signal Layer (no new credentials) | ~11 hrs | Posts, career archetype, press flags in CRM |
| 2 | Wealth Signals (new data sources) | ~17 hrs | Crunchbase + onchain + first composite score |
| 3 | Network Intelligence | ~16 hrs | Warm intros ranked, wealth score finalised |
| **Total** | | **~44 hrs** | **511 contacts fully qualified** |

## Immediate Next Actions (Before Sprint 1 Starts)

- [ ] Fix OpenAI API key (archived project — blocks 1.5 and 1.7)
- [ ] Re-run batches 12–13 (~353 records still unenriched)
- [ ] Obtain Crunchbase Pro API key (needed for Sprint 2)
- [ ] Apply for Arkham Intelligence API access (needed for Sprint 2, can take days)
- [ ] Confirm `contact_type` field exists in Airtable for crypto gating (Task 1.4)
- [ ] Schedule Sales Navigator export with all team members (needed for Sprint 3)
