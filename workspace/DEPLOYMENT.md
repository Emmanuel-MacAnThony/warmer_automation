# Deployment Guide — Fundraising Automations → Render

A complete, step-by-step guide to deploy this system to production on
[Render](https://render.com), from creating accounts to pushing code.

**Architecture we're deploying:**

- **Backend** — FastAPI (Python 3.12), runs as a single always-on Render Web Service.
- **Frontend** — React/Vite, served as a Render Static Site.
- **Database** — Neon (managed Postgres + pgvector). External, not on Render.
- **Email** — Gmail OAuth (requires a public callback URL).

> **Why a single backend instance?** The backend keeps state in memory — the
> SSE event queues for batch sending and the executor task registry. These are
> not shared across processes, so the backend **must run as exactly one
> always-on instance**. No autoscaling, and **not** Render's free tier (free
> services sleep after 15 min of inactivity and would kill running batch jobs).

---

## 0. Prerequisites — accounts you need

Create these first (all have free signups):

1. **GitHub** — https://github.com (code hosting; Render deploys from it)
2. **Render** — https://render.com → "Get Started" → sign up with GitHub (easiest;
   it links your repos automatically)
3. **Neon** — https://neon.tech → sign up (you likely already have this)
4. **Google Cloud Console** — https://console.cloud.google.com (for Gmail OAuth;
   only if you use the Gmail sending feature)

You also need these secrets ready (from your local `backend/.env`):

- `OPENAI_API_KEY`
- `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_TABLE_NAME`
- `APIFY_API_TOKEN` (or `APIFY_TOKENS`), `SERPAPI_API_KEY`
- `GOOGLE_CREDENTIALS_JSON`, and your Gmail OAuth client details
- Your Neon `DATABASE_URL`

---

## 1. One required code change (frontend API base)

In production the frontend and backend live on different URLs, so the client
needs to know where the API is.

Edit `client/src/shared/api/client.ts`, line 1:

```ts
// before
const BASE = '/api'

// after
const BASE = import.meta.env.VITE_API_URL ?? '/api'
```

- **Local dev** is unchanged — `/api` still routes through the Vite proxy.
- **Production** sets `VITE_API_URL` to the backend's URL (Step 5). Because the
  backend has no `/api` route prefix, paths like `${BASE}/campaigns/...` resolve
  correctly in both modes.

Commit this change (we push everything in Step 3).

---

## 2. Put the code on GitHub

If the project isn't on GitHub yet:

1. Create an empty repo at https://github.com/new (e.g. `fundraising-automations`).
   Do **not** add a README/license (the repo already has files).
2. In your project folder, initialise and push:

```bash
# from c:\Users\USER\twolions\fundraising_automations
git init                       # skip if already a git repo
git add .
git commit -m "Prepare for Render deployment"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/fundraising-automations.git
git push -u origin main
```

3. **Confirm `backend/.env` is NOT pushed.** It must be in `.gitignore`.
   Verify with `git status` — `.env` should never appear. Secrets go into
   Render's env-var UI, never into git.

> Already using git with a remote? Just commit the Step 1 change and
> `git push`. Render redeploys automatically on every push to `main`.

---

## 3. Set up the database (Neon)

1. In the Neon console, open your project → **Connection Details**.
2. Copy the connection string. It looks like:
   `postgresql://user:pass@ep-xxx.neon.tech/dbname?sslmode=require`
   - The **pooled** string is fine — our pool sets `statement_cache_size=0`,
     which avoids the usual pgBouncer/asyncpg prepared-statement problem.
   - Make sure it ends with `?sslmode=require`.
3. Save this as your `DATABASE_URL`. We'll paste it into Render next.

> pgvector (used for contact embeddings) is enabled automatically — the schema
> script runs `CREATE EXTENSION IF NOT EXISTS vector` for you in Step 6.

---

## 4. Deploy the backend (Render Web Service)

1. Render Dashboard → **New → Web Service** → connect your GitHub repo.
2. Configure:
   - **Name:** `twolions-api` (or your choice)
   - **Region:** closest to your users
   - **Branch:** `main`
   - **Root Directory:** leave blank (repo root)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.core.server:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** **Starter** or higher (NOT Free — must stay always-on)
3. **Advanced → Pre-Deploy Command** (this is the database migration step —
   idempotent, safe to run on every deploy):
   ```
   python -m backend.infra.db.init_db
   ```
4. **Advanced → Health Check Path:** `/health`
5. **Scaling:** keep **1 instance**. Do not enable autoscaling.
6. **Environment Variables** — add each of these (Add Environment Variable):

   | Key | Value |
   |-----|-------|
   | `PYTHON_VERSION` | `3.12.10` |
   | `DATABASE_URL` | your Neon string from Step 3 |
   | `OPENAI_API_KEY` | … |
   | `OPENAI_MODEL` | `gpt-4o-mini` |
   | `OPENAI_GENERATION_MODEL` | `gpt-4o` |
   | `AIRTABLE_API_KEY` | … |
   | `AIRTABLE_BASE_ID` | … |
   | `AIRTABLE_TABLE_NAME` | `Contacts` (or yours) |
   | `APIFY_API_TOKEN` | … (or `APIFY_TOKENS`) |
   | `SERPAPI_API_KEY` | … |
   | `EMAIL_PROVIDER` | `gmail` (or `smtp` / `resend` — see §11) |
   | `GOOGLE_CREDENTIALS_JSON` | **the OAuth client JSON content itself, on one line** (not a file path) |
   | `GMAIL_REDIRECT_URI` | `https://twolions-api.onrender.com/auth/gmail/callback` |
   | `LOG_LEVEL` | `INFO` |

   (Add any cost-control flags you use: `ENRICH_TWITTER`, `ENRICH_NEWS`, etc.)

   > **Google credentials — do NOT ship the file.** `backend/google_credentials.json`
   > is gitignored and never deployed. In production, paste the **contents** of that
   > JSON file as the `GOOGLE_CREDENTIALS_JSON` env-var value (open the file, copy the
   > single-line JSON, paste it). The code accepts either inline JSON (production) or a
   > file path (local dev). Keep the file local-only.

7. Click **Create Web Service**. Wait for the build + deploy to finish.
8. **Copy the service URL**, e.g. `https://twolions-api.onrender.com`. You need
   it for the frontend and for Gmail OAuth.

---

## 5. Deploy the frontend (Render Static Site)

1. Render Dashboard → **New → Static Site** → same GitHub repo.
2. Configure:
   - **Name:** `twolions-app`
   - **Branch:** `main`
   - **Root Directory:** `client`
   - **Build Command:** `npm install && npm run build`
   - **Publish Directory:** `client/dist`
3. **Environment Variables:**

   | Key | Value |
   |-----|-------|
   | `VITE_API_URL` | `https://twolions-api.onrender.com` (Step 4 URL, no trailing slash, no `/api`) |

4. **Redirects/Rewrites** (so client-side routing works) — add a rule:
   - **Source:** `/*`
   - **Destination:** `/index.html`
   - **Action:** Rewrite
5. Click **Create Static Site**. Copy its URL, e.g.
   `https://twolions-app.onrender.com`.

---

## 6. Database schema / migrations

There is **no Alembic**. The schema is managed by an idempotent script,
`backend/infra/db/init_db.py`, which uses `CREATE TABLE IF NOT EXISTS` and
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. This **is** the migration system.

- It runs automatically as the **Pre-Deploy Command** (Step 4.3) on every deploy.
- To change the schema later: add a new `ALTER TABLE ... IF NOT EXISTS` line to
  the `DDL` block in `init_db.py`, commit, and it applies on the next deploy.
- To run it manually against Neon from your machine:
  ```bash
  # DATABASE_URL must point at Neon
  python -m backend.infra.db.init_db
  ```

> Consider adopting Alembic later only if you need rollbacks or destructive
> migrations. For an additive single-database schema, the current approach is
> sufficient.

---

## 7. Gmail OAuth (if using email sending)

1. Google Cloud Console → **APIs & Services → Credentials** → your OAuth 2.0
   Client ID.
2. Under **Authorized redirect URIs**, add (must match `GMAIL_REDIRECT_URI`
   exactly):
   ```
   https://twolions-api.onrender.com/auth/gmail/callback
   ```
3. Under **Authorized JavaScript origins**, add your frontend origin:
   ```
   https://twolions-app.onrender.com
   ```
4. Save. Allow a minute for Google to propagate.

---

## 8. Verify the deployment

1. **Backend health:** open `https://twolions-api.onrender.com/health` → should
   return OK.
2. **Frontend loads:** open `https://twolions-app.onrender.com`. Open the
   browser **Network** tab and confirm API calls (`/campaigns/...`,
   `/jobs/...`) hit the backend URL and return 200.
3. **Database:** create a small enrichment job or campaign; confirm it persists.
4. **Segmentation:** run segmentation on a small table; watch the live progress.
5. **Email (test mode):** queue a batch send in **Test mode** (all copies go to
   `macanthonyemmanuel9@gmail.com`) and confirm delivery.
6. **Gmail connect:** click Connect Gmail; confirm the OAuth round-trip succeeds
   through the production callback.

---

## 9. Operational notes & gotchas

- **Ephemeral filesystem.** Render wipes the disk on every deploy/restart.
  - `backend.log` is fine to lose.
  - Enrichment CSVs (`BATCH_OUTPUT_DIR=./data/batches`) will NOT survive
    restarts. If you need them persisted, attach a **Render Disk** mounted at
    `/opt/render/project/src/data` and set `BATCH_OUTPUT_DIR` accordingly.
  - Job state survives anyway: on startup the backend resets stale batches and
    auto-resumes in-progress jobs (see `backend/core/server.py` lifespan).
- **Single instance is mandatory** — SSE queues and the executor task registry
  are in-memory. Scaling to 2+ instances breaks live progress and job tracking.
- **Free tier sleeps after 15 min idle** — see §12 for how to run on it safely.
- **CORS** is currently `allow_origins=["*"]`. Fine for now (no credentials are
  sent). To tighten, set it to your frontend origin in `backend/core/server.py`.
- **Neon cold start:** the free Neon tier auto-suspends after inactivity; the
  first query after idle has ~0.5s lag. Harmless.
- **Deploys are automatic:** every `git push` to `main` triggers a rebuild on
  both services. Use a separate branch for WIP if you don't want that.
- **Build filters (monorepo optimization):** by default a push rebuilds *both*
  services. To rebuild only what changed, set Build Filters on each Render service:
  - Backend service → **Included Paths:** `backend/**`, `requirements.txt`
  - Frontend service → **Included Paths:** `client/**`
  Then a backend-only change won't rebuild the frontend, and vice versa.

---

## 10. Future: collapse to a single service (Docker)

Once stable, you can bundle frontend + backend into one Render service with a
multi-stage `Dockerfile`:

1. **Stage 1 (Node):** `npm install && npm run build` → produces `client/dist`.
2. **Stage 2 (Python):** install requirements, copy `client/dist`, serve it via
   FastAPI `StaticFiles`, and add an `/api` router prefix.

This gives one origin (no CORS), one deploy, and one always-on instance. It's
not necessary for the first customer deploy — the two-service setup above is
simpler to reason about and ship.

---

## 11. Email sending: choosing a provider

Set `EMAIL_PROVIDER` to one of `gmail` | `smtp` | `resend`. The runner is
provider-agnostic; only env vars change.

**The deliverability rule that decides everything:** a transactional service
(Resend, SendGrid, SES, Brevo…) can only send "from" a **domain you verify**
with DKIM/SPF. You **cannot** send as an `@gmail.com` address through them —
Gmail's DMARC policy makes receivers reject/spam-fold that mail. So:

| Your "from" address | Best free option | Why |
|---------------------|------------------|-----|
| **Personal Gmail** (`you@gmail.com`) | `EMAIL_PROVIDER=gmail` | The Gmail API sends through your real Google account. ~500 recipients/day free. No transactional service can send as gmail.com. |
| **Google Workspace** (`you@yourorg.com`) | `gmail` (simplest) **or** `resend` (more volume/tracking) **or** `smtp` relay | Gmail API: ~2,000/day, best deliverability. Resend: 3,000/mo free once your domain is verified. Workspace SMTP relay (`smtp-relay.gmail.com`): up to ~10k/day. |
| **Any custom domain, no Workspace** | `resend` | Verify the domain in Resend (add DKIM/SPF DNS records), then send. |

**Gmail (default)** — already wired. Users click "Connect Gmail"; tokens are
stored in the DB. Requires the Google OAuth setup in §7. Free, best
deliverability, sends as the real account.

**Resend (free transactional, opt-in)** — for a custom/Workspace domain:
1. Create a Resend account, add your domain, and add the DKIM/SPF DNS records it
   gives you. Wait for "Verified".
2. Set env vars on the backend:
   - `EMAIL_PROVIDER=resend`
   - `RESEND_API_KEY=re_...`
   - `RESEND_FROM_EMAIL=outreach@yourdomain.com` (must be on the verified domain)
   - `RESEND_FROM_NAME=Your Name` (optional)
3. Redeploy. The batch runner uses it automatically — same rate-limit and
   checkpoint handling as the other providers.

**SMTP / Workspace relay** — set `EMAIL_PROVIDER=smtp` with `SMTP_HOST` etc.
For Workspace, `smtp-relay.gmail.com:587` sends as your domain at higher volume.

> **Recommendation:** ship with `gmail` for the first customer (zero extra
> setup, best deliverability). Switch to `resend` only if they have a custom
> domain and need higher volume or open/click analytics.

---

## 12. Running on the free tier (keep-alive)

Render's free web service **spins down after 15 minutes with no inbound HTTP
traffic**, killing the process. For this app that means background work
(enrichment, batch email sends) stops. To run on free tier you must keep the
instance awake and rely on startup recovery.

### Keep it awake with an external ping
Set up a free uptime pinger to hit the health endpoint every ~10 minutes so the
instance never idles long enough to sleep:

1. Sign up at **cron-job.org** (free) or **UptimeRobot** (free).
2. Create a monitor / cron job:
   - **URL:** `https://twolions-api.onrender.com/health`
   - **Method:** GET
   - **Interval:** every 10 minutes (must be < 15)
3. Save. The instance now stays alive, so background jobs keep running.

Notes:
- Render free gives **750 instance-hours/month**. One always-on backend ≈ 730
  hrs, so a single kept-alive service fits within the cap. (The frontend is a
  Static Site — free, never sleeps, doesn't count toward this.)
- The pinger is a safety wire, not a guarantee. If a ping is missed and the
  instance sleeps mid-send, that's where startup recovery comes in ↓.

### Startup recovery (already built — survives sleep, crashes, and deploys)
On every boot the backend reconciles interrupted work, so a restart never loses
jobs (`backend/core/server.py` lifespan):
- **Enrichment jobs** left "running" are auto-resumed from their last checkpoint.
- **Batch email sends** are recovered by `batch_sender.recover()`:
  - `unsent`-scope sends (and any send that hadn't sent anything yet) re-launch
    and continue with the remaining contacts — already-sent contacts are skipped,
    so nobody is emailed twice.
  - `everyone`-scope sends that had already sent some are set to **paused**
    instead of auto-resuming (re-sending would duplicate the already-contacted
    portion), so you resume them manually when you choose.

This recovery runs regardless of tier — it also protects you on the paid tier,
since **every deploy restarts the server** mid-job.

> **Bottom line for free tier:** add the keep-alive ping so jobs keep running,
> and trust startup recovery to pick up anything stranded by an occasional sleep
> or a deploy. If sends ever feel unreliable, the $7/mo Starter tier removes the
> sleep entirely.

---

## Quick reference

| Item | Value |
|------|-------|
| Backend start | `uvicorn backend.core.server:app --host 0.0.0.0 --port $PORT` |
| Backend build | `pip install -r requirements.txt` |
| Migration (pre-deploy) | `python -m backend.infra.db.init_db` |
| Health check | `/health` |
| Frontend build | `npm install && npm run build` |
| Frontend publish dir | `client/dist` |
| Frontend env | `VITE_API_URL=https://<backend>.onrender.com` |
| Backend instances | 1 (always-on, Starter+) |
| Python version | 3.12.10 |
