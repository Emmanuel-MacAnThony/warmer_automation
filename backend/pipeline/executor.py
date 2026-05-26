"""
Batch Executor — per-record pipeline + job-level loop.

BatchExecutor.run_job(job)
    for each pending batch → run_batch()
        asyncio.gather all records → _process_record()
            fetch record → find/search linkedin_url → scrape → analyze → write CSV row
        flush CSV → Airtable
        mark batch completed

Sync helpers run in thread executor (run_in_executor) because pyairtable,
apify_client, and requests are all synchronous libraries.
"""

import asyncio
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential, wait_random

from backend.config import Config
from backend.infra.crm.airtable import AirtableClient
from backend.infra.scrapers import LinkedInScraper, TweetScraper
from backend.infra.scrapers.apify import ApifyCreditsError, check_apify_403, get_pool
from backend.infra.scrapers.apify.linkedin import ApifyLinkedInScraper
from backend.infra.scrapers.apify.twitter import ApifyTweetScraper
from backend.infra.scrapers.apify.linkedin import normalize_profile as preserve_apify_data
from backend.infra.scrapers.apify.twitter import normalize_tweet
from backend.pipeline.resolvers.linkedin import LinkedInFinder
from backend.infra.search.serper import SerperNewsClient as NewsClient
from backend.agents.enrichment.matcher import LLMMatcher
from backend.infra.db import client as db
from backend.intelligence.linkedin.analyzer import (
    BatchAnalyzer, BatchOutputValidator,
    FIXED_LLM_OUTPUT_FIELDS, PROFILE_SIGNAL_FIELDS, POST_SIGNAL_FIELDS,
    extract_career_progression, extract_post_signals, extract_personalization_hook,
)
from backend.intelligence.news.analyzer import parse_news_results, NEWS_SIGNAL_FIELDS
from backend.intelligence.twitter.analyzer import extract_tweet_signals, TWEET_SIGNAL_FIELDS
# from backend.intelligence.crunchbase.scraper import scrape_crunchbase_profile  # Week 2

logger = logging.getLogger(__name__)

# Semaphore for SERP calls — max 5 concurrent search requests
_serp_semaphore = asyncio.Semaphore(5)

# ---------------------------------------------------------------------------
# Lazy singletons — created once, shared across all concurrent jobs
# ---------------------------------------------------------------------------

_airtable: Optional[AirtableClient] = None
_finder: Optional[LinkedInFinder] = None
_news_client: Optional[NewsClient] = None
_matcher: Optional[LLMMatcher] = None
_analyzer: Optional[BatchAnalyzer] = None
_validator: Optional[BatchOutputValidator] = None


def _get_airtable() -> AirtableClient:
    global _airtable
    if _airtable is None:
        _airtable = AirtableClient()
    return _airtable


def _get_finder() -> LinkedInFinder:
    global _finder
    if _finder is None:
        _finder = LinkedInFinder()
    return _finder


def _get_news_client() -> NewsClient:
    global _news_client
    if _news_client is None:
        _news_client = NewsClient()
    return _news_client


def _get_matcher() -> LLMMatcher:
    global _matcher
    if _matcher is None:
        _matcher = LLMMatcher()
    return _matcher


def _get_analyzer() -> BatchAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = BatchAnalyzer()
    return _analyzer


def _get_validator() -> BatchOutputValidator:
    global _validator
    if _validator is None:
        _validator = BatchOutputValidator()
    return _validator


# ---------------------------------------------------------------------------
# Sync helpers (called via run_in_executor)
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 2),
    retry=retry_if_not_exception_type(ApifyCreditsError),
    reraise=True,
)
def _scrape_profile_sync(profile_url: str, scraper: LinkedInScraper) -> Dict[str, Any]:
    """Scrape one LinkedIn profile. Returns normalised profile dict."""
    try:
        raw = scraper.scrape_raw_profile(profile_url)
        return preserve_apify_data(raw, profile_url) if raw else {}
    except ApifyCreditsError:
        raise
    except Exception as e:
        check_apify_403(e)
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 2),
    retry=retry_if_not_exception_type(ApifyCreditsError),
    reraise=True,
)
def _scrape_posts_sync(profile_url: str, scraper: LinkedInScraper) -> List[Dict]:
    """Scrape recent posts for one LinkedIn profile. Returns raw post list."""
    try:
        return scraper.scrape_raw_posts(profile_url)
    except ApifyCreditsError:
        raise
    except Exception as e:
        check_apify_403(e)
        raise


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=15) + wait_random(0, 2),
    reraise=True,
)
def _scrape_tweets_sync(handle: str, scraper: TweetScraper) -> List[Dict]:
    """Scrape recent tweets for a Twitter handle. Returns normalised tweet list."""
    raw_tweets = scraper.scrape_raw_user_tweets(handle, max_tweets=30)
    return [normalize_tweet(t) for t in raw_tweets]


def _extract_twitter_handle(apify_data: Dict, fields: Dict) -> Optional[str]:
    """
    Extract a Twitter handle from:
      1. LinkedIn profile data (apify_data['twitter'] — populated by linkedin_scraper)
      2. Fixed "Twitter" Airtable field on the record
    Returns a clean handle string (no @ or URL prefix), or None.
    """
    # 1. From LinkedIn profile
    twitter_raw = apify_data.get("twitter") or ""
    if twitter_raw:
        handle = twitter_raw.rstrip("/").split("/")[-1].lstrip("@").strip()
        if handle:
            return handle

    # 2. From fixed Twitter field
    val = (fields.get("Twitter") or "").strip()
    if val:
        handle = val.rstrip("/").split("/")[-1].lstrip("@").strip()
        if handle:
            return handle

    return None


async def _pool_scrape(loop, fn, profile_url: str, factory) -> Any:
    """
    Acquire a pool token, instantiate the scraper for that token, run sync fn in executor.
    factory: callable(token: str) -> LinkedInScraper
    """
    pool = get_pool()
    async with pool.get_token() as token:
        scraper = factory(token)
        return await loop.run_in_executor(None, fn, profile_url, scraper)


async def _news_search_async(name: str, company: str, loop) -> Dict:
    """Search Google News and parse results. Respects the shared SERP semaphore."""
    if not name:
        return {"press_count": 0}
    async with _serp_semaphore:
        results = await loop.run_in_executor(None, _get_news_client().search_news, name, company)
    return parse_news_results(results, name)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 2),
    reraise=True,
)
def _search_sync(contact: Dict) -> List[Dict]:
    return _get_finder().search_linkedin_profiles(contact, num_results=10)


def _rank_sync(contact: Dict, candidates: List[Dict]):
    return _get_matcher().rank_linkedin_profiles(contact, candidates, max_results=1)


def _sanitize_for_airtable(fields: Dict, type_map: Dict[str, str]) -> Dict:
    """Final type coercion before writing to Airtable.
    Ensures values conform to their Airtable field type regardless of what was stored in CSV.
    """
    sanitized = {}
    for name, value in fields.items():
        field_type = type_map.get(name, "singleLineText")
        if value is None:
            continue
        if field_type == "multipleSelects":
            sanitized[name] = value if isinstance(value, list) else [str(value)]
        elif field_type in ("singleLineText", "multilineText", "url", "email", "phoneNumber", "singleSelect"):
            if isinstance(value, dict):
                import json as _j; value = _j.dumps(value)
            elif isinstance(value, list):
                # list-of-dicts means it was a JSON blob stored in a text field — re-serialize
                if value and isinstance(value[0], dict):
                    import json as _j; value = _j.dumps(value)
                elif len(value) == 1:
                    value = value[0]
                else:
                    value = ", ".join(str(v) for v in value)
            sanitized[name] = str(value).strip()
        elif field_type == "number":
            try:
                sanitized[name] = float(value)
            except (ValueError, TypeError):
                pass
        elif field_type == "checkbox":
            if isinstance(value, bool):
                sanitized[name] = value
            elif isinstance(value, str):
                sanitized[name] = value.lower() in ("true", "yes", "1")
        else:
            sanitized[name] = value
    return sanitized


def _flush_csv_to_airtable_sync(
    base_id: str, table_id: str, csv_path: Path, field_names: List[str],
) -> int:
    """Read completed CSV and batch-update Airtable. Returns updated count."""
    if not csv_path.exists():
        return 0

    import json as _json

    # Build airtable_name → airtable_type lookup for sanitization.
    type_map: Dict[str, str] = {
        **{f["name"]: f["type"] for f in FIXED_LLM_OUTPUT_FIELDS},
        **PROFILE_SIGNAL_FIELDS,
        **POST_SIGNAL_FIELDS,
        **NEWS_SIGNAL_FIELDS,
        **TWEET_SIGNAL_FIELDS,
    }

    def _decode(v: str):
        """JSON-decode values that were serialized as lists/dicts on write."""
        try:
            parsed = _json.loads(v)
            return parsed if isinstance(parsed, (list, dict)) else v
        except (ValueError, TypeError):
            return v

    # Last-write-wins: later rows overwrite earlier ones (handles retry duplicates)
    latest_rows: Dict[str, Dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "success" and row.get("record_id"):
                latest_rows[row["record_id"]] = row

    records = []
    for row in latest_rows.values():
        fields = {k: _decode(v) for k, v in row.items() if k in field_names and v}
        if fields:
            fields = _sanitize_for_airtable(fields, type_map)
        if fields:
            records.append({"id": row["record_id"], "fields": fields})

    if not records:
        return 0
    return _get_airtable().batch_update_in_table(base_id, table_id, records)


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _csv_path(job_id: int, batch_id: int) -> Path:
    output_dir = Path(Config.BATCH_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"job_{job_id}_batch_{batch_id}.csv"


def _csv_field_names() -> List[str]:
    """Return fixed Airtable output field names (used as CSV column headers)."""
    return [f["name"] for f in FIXED_LLM_OUTPUT_FIELDS]


def _friendly_reason(error: str) -> str:
    """Map a raw CSV error code to a human-readable reason for the UI."""
    e = (error or "").strip()
    if not e:
        return "Unknown error"
    base = e.split(":", 1)[0]
    detail = e.split(":", 1)[1] if ":" in e else ""
    mapping = {
        "record_not_found":      "Record not found in Airtable (deleted or moved)",
        "apify_no_profile_data": "No usable profile data (private profile or bad LinkedIn URL)",
        "apify_403":             "Apify access blocked (credits exhausted / 403)",
        "no_linkedin_found":     "No LinkedIn profile found",
        "apify_error":           f"Scrape failed ({detail})" if detail else "Scrape failed",
        "analysis_error":        f"AI analysis failed ({detail})" if detail else "AI analysis failed",
        "unexpected":            f"Unexpected error ({detail})" if detail else "Unexpected error",
    }
    return mapping.get(base, e)


def _batch_failures_from_csv(csv_path: Path) -> list[dict]:
    """Extract failed records from one batch CSV (last-write-wins per record)."""
    if not csv_path.exists():
        return []
    latest: Dict[str, Dict[str, str]] = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rid = row.get("record_id")
                if rid:
                    latest[rid] = row
    except Exception as e:
        logger.warning(f"_batch_failures_from_csv: could not read {csv_path}: {e}")
        return []
    return [
        {"record_id": r.get("record_id", ""), "linkedin_url": r.get("linkedin_url", ""), "error": r.get("error", "")}
        for r in latest.values()
        if r.get("status") == "failed"
    ]


def read_job_failures(batches: list[dict], limit: int = 200) -> dict:
    """
    Aggregate per-record failure reasons for a job.

    Prefers the durable DB-persisted `failures` on each batch (survives restarts);
    falls back to reading the batch CSV when the DB column is empty (in-progress or
    legacy batches). Returns grouped reason counts + a capped record list.
    """
    failed: list[dict] = []
    for b in batches:
        stored = b.get("failures") or []
        if stored:
            failed.extend(stored)
        else:
            path = b.get("csv_path")
            if path:
                failed.extend(_batch_failures_from_csv(Path(path)))

    reason_counts: Dict[str, int] = {}
    records: list[dict] = []
    for r in failed:
        reason = _friendly_reason(r.get("error", ""))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if len(records) < limit:
            records.append({
                "record_id":    r.get("record_id", ""),
                "linkedin_url": r.get("linkedin_url", ""),
                "reason":       reason,
                "error":        r.get("error", ""),
            })

    reasons = sorted(
        ({"reason": k, "count": v} for k, v in reason_counts.items()),
        key=lambda x: -x["count"],
    )
    return {
        "total_failed": len(failed),
        "reasons":      reasons,
        "records":      records,
        "truncated":    len(failed) > len(records),
    }


def _read_processed_stats(csv_path: Path):
    """Crash recovery — read already-written record_ids AND stats from an existing CSV.
    Returns (skip_ids, failed_ids, hits, misses, failed).

    skip_ids:   records with success/skipped status — will not be re-processed.
    failed_ids: records that failed — will be retried but already counted in `failed`
                so that the initial processed baseline is correct.
    Uses the LAST row per record_id (last-write-wins across retries).
    """
    if not csv_path.exists():
        return set(), set(), 0, 0, 0
    try:
        latest: Dict[str, str] = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rid = row.get("record_id")
                if rid:
                    latest[rid] = row.get("status", "")

        skip_ids: Set[str] = set()
        failed_ids: Set[str] = set()
        hits = misses = failed = 0
        for rid, status in latest.items():
            if status == "success":
                skip_ids.add(rid)
                hits += 1
            elif status == "skipped":
                skip_ids.add(rid)
                misses += 1
            else:
                failed_ids.add(rid)
                failed += 1

        return skip_ids, failed_ids, hits, misses, failed
    except Exception as e:
        logger.warning(f"Could not read existing CSV {csv_path}: {e}")
        return set(), set(), 0, 0, 0


def _write_csv_row(csv_path: Path, headers: List[str], row: Dict) -> None:
    """Append one row. Creates with header row if file is new.
    List values (multipleSelects, etc.) are JSON-encoded so they survive the
    CSV round-trip and can be decoded back to proper lists on flush.

    If the file exists but is missing columns present in headers (e.g. a new
    signal field was added after this CSV was created), the file is rewritten
    in-place with the new columns added (empty for existing rows) before
    appending.  This prevents new column values from silently dropping due to
    DictWriter's extrasaction="ignore" + DictReader reading stale header rows.
    """
    import json as _json

    serialized = {
        k: _json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()
    }

    if not csv_path.exists():
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerow(serialized)
        return

    # Read existing header row to check for missing columns.
    with open(csv_path, newline="", encoding="utf-8") as f:
        existing_headers = next(csv.reader(f), None)

    missing = [h for h in headers if h not in (existing_headers or [])]
    if missing and existing_headers:
        # Rewrite the file with the new columns appended (empty for old rows).
        import tempfile, os
        merged_headers = existing_headers + missing
        tmp = csv_path.with_suffix(".tmp")
        with open(csv_path, newline="", encoding="utf-8") as src, \
             open(tmp, "w", newline="", encoding="utf-8") as dst:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dst, fieldnames=merged_headers, extrasaction="ignore")
            writer.writeheader()
            for old_row in reader:
                writer.writerow(old_row)  # missing cols written as empty strings
        os.replace(tmp, csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writerow(serialized)


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------


def _find_linkedin_field(field_mapping: Dict) -> Optional[str]:
    """
    Return the Airtable column name that holds LinkedIn URLs.
    New format: field_mapping = {"linkedin_url_field": "LinkedIn", "name_field": "Name"}
    Legacy format: keyed by field_id, each value has canonical_key/airtable_name.
    """
    if "linkedin_url_field" in field_mapping:
        return field_mapping["linkedin_url_field"]
    # Legacy: scan by canonical_key
    for cfg in field_mapping.values():
        if isinstance(cfg, dict) and cfg.get("canonical_key") == "linkedin_url":
            return cfg.get("airtable_name")
    return None


def _build_contact(fields: Dict, name_field: str = "Name") -> Dict:
    """Extract name/company/title/location from raw Airtable record fields."""
    return {
        "name": fields.get(name_field) or fields.get("Name") or fields.get("Full Name") or "",
        "company": fields.get("Realtime company name") or fields.get("Company Name") or fields.get("Company") or "",
        "job_title": fields.get("Realtime role") or fields.get("Job Title") or fields.get("Title") or "",
        "location": fields.get("Realtime location") or fields.get("Location") or "",
    }


# ---------------------------------------------------------------------------
# BatchExecutor
# ---------------------------------------------------------------------------


class BatchExecutor:
    """
    Executes a job end-to-end:
      run_job → for each pending batch → run_batch → concurrent process_record

    linkedin_scraper_factory: (token: str) -> LinkedInScraper
        Defaults to ApifyLinkedInScraper. Override in tests with a fake.
    tweet_scraper_factory: (token: str) -> TweetScraper
        Defaults to ApifyTweetScraper. Override in tests with a fake.
    """

    def __init__(self, linkedin_scraper_factory=None, tweet_scraper_factory=None):
        self._li_factory = linkedin_scraper_factory or (lambda token: ApifyLinkedInScraper(token))
        self._tw_factory = tweet_scraper_factory or (lambda token: ApifyTweetScraper(token))

    async def run_job(self, job: Dict) -> None:
        job_id = job["id"]
        base_id = job["base_id"]
        table_id = job["table_id"]
        field_mapping = job["field_mapping"]

        logger.info(f"Job {job_id}: starting ({base_id}/{table_id})")

        # Ensure all output columns exist in the user's Airtable table.
        # Creates missing fields non-destructively; existing ones are untouched.
        try:
            loop = asyncio.get_event_loop()
            all_output_fields = (
                [{"name": f["name"], "type": f["type"]} for f in FIXED_LLM_OUTPUT_FIELDS]
                + [{"name": k, "type": v} for k, v in PROFILE_SIGNAL_FIELDS.items()]
                + [{"name": k, "type": v} for k, v in POST_SIGNAL_FIELDS.items()]
                + [{"name": k, "type": v} for k, v in NEWS_SIGNAL_FIELDS.items()]
                + [{"name": k, "type": v} for k, v in TWEET_SIGNAL_FIELDS.items()]
            )
            await loop.run_in_executor(
                None, _get_airtable().ensure_table_fields, base_id, table_id, all_output_fields
            )
        except Exception as _e:
            logger.warning(f"Job {job_id}: could not ensure output fields (non-fatal): {_e}")

        # Run dedup before enrichment — only on the first run, not on resume after pause.
        existing_dedup = await db.get_dedup_run_by_job(job_id)
        if existing_dedup and existing_dedup["status"] == "completed":
            logger.info(f"Job {job_id}: skipping dedup (already completed run {existing_dedup['id']})")
        else:
            try:
                from backend.pipeline.dedup_executor import run as run_dedup
                await asyncio.wait_for(
                    run_dedup(
                        base_id=base_id,
                        table_id=table_id,
                        field_mapping=field_mapping,
                        triggered_by="auto",
                        enrichment_job_id=job_id,
                    ),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Job {job_id}: dedup timed out (90 s), proceeding anyway")
            except Exception as _e:
                logger.warning(f"Job {job_id}: dedup failed (non-fatal): {_e}")

        batches = await db.get_batches(job_id)
        pending = [b for b in batches if b["status"] in ("pending", "running", "paused")]

        for batch in pending:
            # Check for pause/delete signal between batches
            fresh = await db.get_job(job_id)
            if not fresh:
                logger.info(f"Job {job_id}: deleted — stopping executor")
                return
            if fresh["status"] == "paused":
                logger.info(f"Job {job_id}: paused before batch {batch['id']}")
                return

            await self._run_batch(batch, job_id, base_id, table_id, field_mapping)

        await db.update_job_status(job_id, "completed")
        logger.info(f"Job {job_id}: completed")

    async def _run_batch(
        self,
        batch: Dict,
        job_id: int,
        base_id: str,
        table_id: str,
        field_mapping: Dict,
    ) -> None:
        batch_id = batch["id"]
        record_ids: List[str] = batch["record_ids"]

        await db.update_batch(
            batch_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        csv_path = _csv_path(job_id, batch_id)
        already_done, previously_failed_ids, recovered_hits, recovered_misses, recovered_failed = (
            _read_processed_stats(csv_path)
        )
        if already_done or previously_failed_ids:
            logger.info(
                f"Batch {batch_id}: skipping {len(already_done)} completed, "
                f"retrying {len(previously_failed_ids)} failed "
                f"(recovered: ✓{recovered_hits} —{recovered_misses} ✗{recovered_failed})"
            )

        field_cols          = _csv_field_names()
        post_cols           = list(POST_SIGNAL_FIELDS.keys())
        profile_signal_cols = list(PROFILE_SIGNAL_FIELDS.keys())
        news_cols           = list(NEWS_SIGNAL_FIELDS.keys())
        tweet_cols          = list(TWEET_SIGNAL_FIELDS.keys())
        # crunchbase_cols   = list(CRUNCHBASE_SIGNAL_FIELDS.keys())  # Week 2
        csv_headers = (
            ["record_id", "linkedin_url", "status", "error"]
            + field_cols
            + profile_signal_cols
            + post_cols
            + news_cols
            + tweet_cols
        )

        pending_ids = [r for r in record_ids if r not in already_done]

        # Process in small concurrent chunks so we can:
        #   • check for pause signals between chunks
        #   • write live hits/misses/failed stats after each chunk
        CHUNK_SIZE = 5
        hits = recovered_hits
        misses = recovered_misses
        failed = recovered_failed
        # processed counts unique records attempted. Retries don't add to this total —
        # they adjust hits/failed in-place. Only truly new records increment it.
        processed_count = 0
        initial_processed = len(already_done) + recovered_failed
        paused = False
        consecutive_403s = 0

        for chunk_start in range(0, len(pending_ids), CHUNK_SIZE):
            # Pause/delete check before each chunk
            fresh = await db.get_job(job_id)
            if not fresh:
                logger.info(f"Job {job_id}: deleted mid-batch {batch_id} — stopping")
                paused = True
                break
            if fresh["status"] == "paused":
                logger.info(
                    f"Job {job_id}: pause detected mid-batch {batch_id}, stopping after {processed_count} records"
                )
                paused = True
                break

            chunk_record_ids = pending_ids[chunk_start : chunk_start + CHUNK_SIZE]
            chunk = [
                self._process_record(
                    record_id, base_id, table_id, field_mapping, csv_path, csv_headers
                )
                for record_id in chunk_record_ids
            ]
            chunk_results = await asyncio.gather(*chunk, return_exceptions=True)

            for record_id, result in zip(chunk_record_ids, chunk_results):
                is_retry = record_id in previously_failed_ids
                if not is_retry:
                    processed_count += 1

                if result == "apify_403":
                    consecutive_403s += 1
                    if not is_retry:
                        failed += 1
                    if consecutive_403s >= 3:
                        logger.warning(
                            f"Job {job_id}: {consecutive_403s} consecutive Apify 403s — auto-pausing"
                        )
                        await db.update_job_status(job_id, "paused", pause_reason="rate_limited")
                        paused = True
                elif isinstance(result, Exception):
                    consecutive_403s = 0
                    logger.error(
                        f"Batch {batch_id}: unhandled error on record: {result}"
                    )
                    if not is_retry:
                        failed += 1
                elif result == "success":
                    consecutive_403s = 0
                    hits += 1
                    if is_retry:
                        failed -= 1
                elif result == "skipped":
                    consecutive_403s = 0
                    misses += 1
                    if is_retry:
                        failed -= 1
                else:
                    if not is_retry:
                        failed += 1

            # Live stats update after every chunk
            await db.update_batch(
                batch_id,
                processed=initial_processed + processed_count,
                hits=hits,
                misses=misses,
                failed=failed,
            )

            if paused:
                break

        total_processed = initial_processed + processed_count

        if paused:
            await db.update_batch(
                batch_id,
                status="paused",
                processed=total_processed,
                hits=hits,
                misses=misses,
                failed=failed,
            )
            await db.save_batch_failures(batch_id, _batch_failures_from_csv(csv_path))
            logger.info(
                f"Batch {batch_id}: paused at {processed_count}/{len(pending_ids)} pending records "
                f"(✓{hits} —{misses} ✗{failed})"
            )
            return

        # Flush CSV → Airtable
        updated = 0
        if not Config.DRY_RUN:
            loop = asyncio.get_event_loop()
            try:
                updated = await loop.run_in_executor(
                    None,
                    _flush_csv_to_airtable_sync,
                    base_id,
                    table_id,
                    csv_path,
                    field_cols + profile_signal_cols + post_cols + news_cols + tweet_cols,
                )
            except Exception as e:
                logger.error(f"Batch {batch_id}: Airtable flush failed: {e}")

        # Mark completed only if we finished all records (not paused)
        await db.update_batch(
            batch_id,
            status="completed",
            processed=total_processed,
            hits=hits,
            misses=misses,
            failed=failed,
            csv_path=str(csv_path),
            completed_at=datetime.now(timezone.utc),
        )
        await db.save_batch_failures(batch_id, _batch_failures_from_csv(csv_path))
        logger.info(
            f"Batch {batch_id}: done — {hits} hits, {misses} skipped, "
            f"{failed} failed, {updated} Airtable records updated"
        )

    async def _process_record(
        self,
        record_id: str,
        base_id: str,
        table_id: str,
        field_mapping: Dict,
        csv_path: Path,
        csv_headers: List[str],
    ) -> str:
        """Pipeline for one record. Returns 'success' | 'skipped' | 'failed'."""
        loop = asyncio.get_event_loop()
        linkedin_field = _find_linkedin_field(field_mapping)
        name_field = field_mapping.get("name_field", "Name") if isinstance(field_mapping.get("name_field"), str) else "Name"

        def write_row(status: str, error: str = "", **extra):
            _write_csv_row(
                csv_path,
                csv_headers,
                {
                    "record_id": record_id,
                    "linkedin_url": extra.get("linkedin_url", ""),
                    "status": status,
                    "error": error,
                    **extra,
                },
            )

        try:
            # 1. Fetch record from Airtable
            record = await loop.run_in_executor(
                None, _get_airtable().get_record, base_id, table_id, record_id
            )
            if not record:
                logger.warning(f"Record {record_id}: not found in Airtable (deleted or moved) — marking failed")
                write_row("failed", "record_not_found")
                return "failed"

            fields = record.get("fields", {})

            # 1b. Skip already-enriched contacts (saves Apify + LLM credits on re-runs)
            if Config.SKIP_ALREADY_ENRICHED and fields.get("trajectory_tag"):
                logger.info(f"Record {record_id}: already enriched (trajectory_tag set) — skipping")
                write_row("skipped", "already_enriched")
                return "skipped"

            # 2. Get LinkedIn URL from record (or search for it)
            linkedin_url = ""
            if linkedin_field:
                raw_url = (fields.get(linkedin_field) or "").strip()
                # Validate it's actually a LinkedIn URL, not placeholder text like "N/A"
                if raw_url and "linkedin.com" in raw_url.lower():
                    # Normalize: add https:// if missing
                    if not raw_url.startswith(("http://", "https://")):
                        linkedin_url = f"https://{raw_url}"
                    else:
                        linkedin_url = raw_url

            if not linkedin_url:
                linkedin_url = await self._find_linkedin_url(
                    record_id, fields, base_id, table_id, linkedin_field, loop, name_field
                )
                if not linkedin_url:
                    write_row("skipped", "no_linkedin_found")
                    return "skipped"

            # 3. Scrape profile + posts concurrently; news is optional (uses Serper credits)
            contact = _build_contact(fields, name_field)
            try:
                if Config.ENRICH_NEWS:
                    apify_data, raw_posts, news_signals = await asyncio.gather(
                        _pool_scrape(loop, _scrape_profile_sync, linkedin_url, self._li_factory),
                        _pool_scrape(loop, _scrape_posts_sync, linkedin_url, self._li_factory),
                        _news_search_async(contact["name"], contact.get("company", ""), loop),
                    )
                else:
                    apify_data, raw_posts = await asyncio.gather(
                        _pool_scrape(loop, _scrape_profile_sync, linkedin_url, self._li_factory),
                        _pool_scrape(loop, _scrape_posts_sync, linkedin_url, self._li_factory),
                    )
                    news_signals = {}
            except ApifyCreditsError as e:
                logger.warning(f"Record {record_id}: Apify 403 (credits exhausted): {e}")
                write_row("failed", "apify_403", linkedin_url=linkedin_url)
                return "apify_403"
            except Exception as e:
                # Fallback 403 detection — catches cases where ApifyCreditsError wasn't raised
                # (e.g. Apify client wraps the error without preserving message text)
                _status = getattr(e, "status_code", None) or getattr(e, "status", None)
                _msg = str(e).lower()
                if _status == 403 or "403" in _msg or "forbidden" in _msg:
                    logger.warning(f"Record {record_id}: Apify 403 detected via fallback: {e}")
                    write_row("failed", "apify_403", linkedin_url=linkedin_url)
                    return "apify_403"
                logger.error(f"Record {record_id}: scrape failed: {e}")
                write_row("failed", f"apify_error:{type(e).__name__}", linkedin_url=linkedin_url)
                return "failed"

            # Merge posts into profile dict before passing to profile analyzer
            apify_data["posts"]       = raw_posts or []
            apify_data["posts_count"] = len(raw_posts or [])

            # Validate we got actual profile data
            if not apify_data or (
                not apify_data.get("full_name")
                and not apify_data.get("headline")
                and not (apify_data.get("raw_data") or {}).get("experience")
                and not (apify_data.get("raw_data") or {}).get("experiences")
            ):
                logger.warning(
                    f"Record {record_id}: scrape returned no usable profile data "
                    f"(private profile, bad URL, or Apify miss) — {linkedin_url}"
                )
                write_row("failed", "apify_no_profile_data", linkedin_url=linkedin_url)
                return "failed"

            # 4. Twitter scrape — opt-in only (extra Apify call per contact)
            raw_tweets: List[Dict] = []
            if Config.ENRICH_TWITTER:
                twitter_handle = _extract_twitter_handle(apify_data, fields)
                if twitter_handle:
                    try:
                        tweet_scraper = self._tw_factory(Config.APIFY_API_TOKEN)
                        raw_tweets = await loop.run_in_executor(
                            None, _scrape_tweets_sync, twitter_handle, tweet_scraper
                        )
                        logger.info(f"Record {record_id}: scraped {len(raw_tweets)} tweets for @{twitter_handle}")
                    except Exception as e:
                        logger.warning(f"Record {record_id}: Twitter scrape failed (non-fatal): {e}")

            # Crunchbase enrichment — deferred to Week 2
            # crunchbase_url = _extract_crunchbase_url(fields, field_mapping)
            # if crunchbase_url:
            #     crunchbase_data = await loop.run_in_executor(None, _scrape_crunchbase_sync, crunchbase_url)

            # 5. Profile LLM analysis + posts signal extraction + tweet signals +
            #    personalization hook — all run concurrently (no added wall-time)
            try:
                extracted, post_signals, tweet_signals, hook_signals = await asyncio.gather(
                    _get_analyzer().analyze(apify_data),
                    extract_post_signals(raw_posts or []),
                    extract_tweet_signals(raw_tweets or []),
                    extract_personalization_hook(apify_data),
                )
            except Exception as e:
                logger.error(f"Record {record_id}: analysis failed ({type(e).__name__}): {e}")
                write_row("failed", f"analysis_error:{type(e).__name__}", linkedin_url=linkedin_url)
                return "failed"

            # 6. Peel trajectory fields out of LLM response before validation —
            #    they are not in field_mapping so the validator would reject them as unknown
            trajectory_signals = {
                k: extracted.pop(k)
                for k in ("trajectory_tag", "trajectory_signal")
                if k in extracted
            }

            # 7. Validate remaining profile fields against fixed schema
            validated, errors = _get_validator().validate(extracted)
            if errors:
                logger.debug(f"Record {record_id}: validation notes: {errors}")

            # 8. Derive career progression directly from experience data (no LLM)
            career_signals = extract_career_progression(apify_data)

            # 9. Write CSV row — all signal types merged
            write_row(
                "success",
                linkedin_url=linkedin_url,
                **validated,
                **career_signals,
                **trajectory_signals,
                **post_signals,
                **hook_signals,
                **news_signals,
                **tweet_signals,
            )
            return "success"

        except Exception as e:
            logger.error(f"Record {record_id}: unexpected error: {e}", exc_info=True)
            try:
                write_row("failed", f"unexpected:{type(e).__name__}")
            except Exception:
                pass
            return "failed"

    async def _find_linkedin_url(
        self,
        record_id: str,
        fields: Dict,
        base_id: str,
        table_id: str,
        linkedin_field: Optional[str],
        loop,
        name_field: str = "Name",
    ) -> Optional[str]:
        """Search for LinkedIn URL via SERP + LLM ranking."""
        contact = _build_contact(fields, name_field)
        if not contact["name"]:
            logger.warning(f"Record {record_id}: no name, cannot search")
            return None

        try:
            async with _serp_semaphore:
                candidates = await loop.run_in_executor(None, _search_sync, contact)
        except Exception as e:
            logger.error(f"Record {record_id}: SERP failed: {e}")
            return None

        if not candidates:
            return None

        try:
            urls, confidence = await loop.run_in_executor(
                None, _rank_sync, contact, candidates
            )
        except Exception as e:
            logger.error(f"Record {record_id}: LLM ranking failed: {e}")
            return None

        if not urls or confidence < Config.MATCH_CONFIDENCE_THRESHOLD:
            logger.info(
                f"Record {record_id}: no confident match (confidence={confidence:.2f})"
            )
            return None

        linkedin_url = urls[0]

        # Normalize: ensure URL has https:// prefix (SERP may return without protocol)
        if linkedin_url and not linkedin_url.startswith(("http://", "https://")):
            linkedin_url = f"https://{linkedin_url}"

        # Write URL back to Airtable immediately so it's not lost if we crash
        if linkedin_field and not Config.DRY_RUN:
            try:
                await loop.run_in_executor(
                    None,
                    _get_airtable().update_record_in_table,
                    base_id,
                    table_id,
                    record_id,
                    {linkedin_field: linkedin_url},
                )
            except Exception as e:
                logger.warning(
                    f"Record {record_id}: failed to write linkedin_url back: {e}"
                )

        return linkedin_url
