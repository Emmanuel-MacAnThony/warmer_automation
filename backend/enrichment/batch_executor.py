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

from apify_client import ApifyClient
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.config import Config
from backend.clients.airtable_client import AirtableClient
from backend.clients.linkedin_scraper import preserve_apify_data
from backend.clients.serp_client import SerpClient
from backend.agents.subagents.matching_agent import LLMMatcher
from backend.db import client as db
from backend.enrichment.apify_pool import get_pool
from backend.enrichment.batch_analyzer import (
    BatchAnalyzer, BatchOutputValidator,
    PROFILE_SIGNAL_FIELDS, extract_career_progression,
)
from backend.enrichment.posts_analyzer import extract_post_signals, POST_SIGNAL_FIELDS
from backend.enrichment.news_analyzer import parse_news_results, NEWS_SIGNAL_FIELDS
from backend.enrichment.twitter_analyzer import extract_tweet_signals, TWEET_SIGNAL_FIELDS
# from backend.clients.crunchbase_scraper import scrape_crunchbase_profile  # Week 2

logger = logging.getLogger(__name__)

# Semaphore for SERP calls — max 5 concurrent search requests
_serp_semaphore = asyncio.Semaphore(5)

# ---------------------------------------------------------------------------
# Lazy singletons — created once, shared across all concurrent jobs
# ---------------------------------------------------------------------------

_airtable: Optional[AirtableClient] = None
_serp: Optional[SerpClient] = None
_matcher: Optional[LLMMatcher] = None
_analyzer: Optional[BatchAnalyzer] = None
_validator: Optional[BatchOutputValidator] = None


def _get_airtable() -> AirtableClient:
    global _airtable
    if _airtable is None:
        _airtable = AirtableClient()
    return _airtable


def _get_serp() -> SerpClient:
    global _serp
    if _serp is None:
        _serp = SerpClient()
    return _serp


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
    reraise=True,
)
def _scrape_profile_sync(profile_url: str, token: str) -> Dict[str, Any]:
    """Scrape one LinkedIn profile using harvestapi. Returns normalised profile dict."""
    client = ApifyClient(token)
    run = client.actor("harvestapi/linkedin-profile-scraper").call(
        run_input={
            "urls": [profile_url],
            "profileScraperMode": "Profile details no email ($4 per 1k)",
        }
    )
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        return preserve_apify_data(item, profile_url)
    return {}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 2),
    reraise=True,
)
def _scrape_posts_sync(profile_url: str, token: str) -> List[Dict]:
    """Scrape recent posts for one LinkedIn profile using harvestapi. Returns raw post list."""
    client = ApifyClient(token)
    run = client.actor("harvestapi/linkedin-profile-posts").call(
        run_input={"profileUrls": [profile_url], "resultsLimit": 20}
    )
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=15) + wait_random(0, 2),
    reraise=True,
)
def _scrape_tweets_sync(handle: str) -> List[Dict]:
    """Scrape recent tweets for a Twitter handle. Returns raw tweet list."""
    from backend.clients.twitter_scraper import scrape_user_tweets
    return scrape_user_tweets(handle, max_tweets=30)


def _extract_twitter_handle(apify_data: Dict, fields: Dict, field_mapping: Dict) -> Optional[str]:
    """
    Extract a Twitter handle from:
      1. LinkedIn profile data (apify_data['twitter'] — populated by linkedin_scraper)
      2. Airtable record fields via any mapping entry with 'twitter' in canonical_key
    Returns a clean handle string (no @ or URL prefix), or None.
    """
    # 1. From LinkedIn profile
    twitter_raw = apify_data.get("twitter") or ""
    if twitter_raw:
        handle = twitter_raw.rstrip("/").split("/")[-1].lstrip("@").strip()
        if handle:
            return handle

    # 2. From field mapping
    for cfg in field_mapping.values():
        key = (cfg.get("canonical_key") or "").lower()
        if "twitter" in key:
            airtable_name = cfg.get("airtable_name", "")
            val = (fields.get(airtable_name) or "").strip()
            if val:
                handle = val.rstrip("/").split("/")[-1].lstrip("@").strip()
                if handle:
                    return handle

    return None


async def _pool_scrape(loop, fn, profile_url: str) -> Any:
    """Acquire one pool token, run a sync scrape function in executor, release token."""
    pool = get_pool()
    async with pool.get_token() as token:
        return await loop.run_in_executor(None, fn, profile_url, token)


async def _news_search_async(name: str, company: str, loop) -> Dict:
    """Search Google News and parse results. Respects the shared SERP semaphore."""
    if not name:
        return {"press_count": 0}
    async with _serp_semaphore:
        results = await loop.run_in_executor(None, _get_serp().search_news, name, company)
    return parse_news_results(results, name)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 2),
    reraise=True,
)
def _search_sync(contact: Dict) -> List[Dict]:
    return _get_serp().search_linkedin_profiles(contact, num_results=10)


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
            if isinstance(value, list):
                value = value[0] if len(value) == 1 else ", ".join(str(v) for v in value)
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
    field_mapping: Optional[Dict] = None,
) -> int:
    """Read completed CSV and batch-update Airtable. Returns updated count."""
    if not csv_path.exists():
        return 0

    import json as _json

    # Build airtable_name → airtable_type lookup for sanitization.
    # Seed with all static fields (profile signals + post signals), then overlay job mapping.
    type_map: Dict[str, str] = {**PROFILE_SIGNAL_FIELDS, **POST_SIGNAL_FIELDS, **NEWS_SIGNAL_FIELDS, **TWEET_SIGNAL_FIELDS}
    if field_mapping:
        for cfg in field_mapping.values():
            name = cfg.get("airtable_name")
            ftype = cfg.get("airtable_type")
            if name and ftype:
                type_map[name] = ftype

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


def _csv_field_names(field_mapping: Dict) -> List[str]:
    """Return airtable_name values from the mapping (used as CSV column names)."""
    return [
        cfg["airtable_name"]
        for cfg in field_mapping.values()
        if cfg.get("airtable_name")
    ]


def _read_processed_stats(csv_path: Path):
    """Crash recovery — read already-written record_ids AND stats from an existing CSV.
    Returns (processed_ids: Set[str], hits: int, misses: int, failed: int).

    Uses the LAST row per record_id so a successful retry overwrites an earlier
    failure in both the skip-set and the stats counts.
    Only success/skipped are added to processed_ids — failed/pending are retried.
    """
    if not csv_path.exists():
        return set(), 0, 0, 0
    try:
        # Last-write-wins: later rows for the same record_id overwrite earlier ones
        latest: Dict[str, str] = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rid = row.get("record_id")
                if rid:
                    latest[rid] = row.get("status", "")

        processed_ids: Set[str] = set()
        hits = misses = failed = 0
        for rid, status in latest.items():
            if status == "success":
                processed_ids.add(rid)
                hits += 1
            elif status == "skipped":
                processed_ids.add(rid)
                misses += 1
            else:
                failed += 1

        return processed_ids, hits, misses, failed
    except Exception as e:
        logger.warning(f"Could not read existing CSV {csv_path}: {e}")
        return set(), 0, 0, 0


def _write_csv_row(csv_path: Path, headers: List[str], row: Dict) -> None:
    """Append one row. Creates with header row if file is new.
    List values (multipleSelects, etc.) are JSON-encoded so they survive the
    CSV round-trip and can be decoded back to proper lists on flush.
    """
    import json as _json

    serialized = {
        k: _json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()
    }
    new_file = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(serialized)


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------


def _find_linkedin_field(field_mapping: Dict) -> Optional[str]:
    """Return the airtable_name of the field with canonical_key == 'linkedin_url'."""
    for cfg in field_mapping.values():
        if cfg.get("canonical_key") == "linkedin_url":
            return cfg.get("airtable_name")
    return None


def _build_contact(fields: Dict) -> Dict:
    """Extract name/company/title/location from raw Airtable record fields."""
    return {
        "name": fields.get("Name") or fields.get("Full Name") or "",
        "company": fields.get("Company") or fields.get("Company Name") or "",
        "job_title": fields.get("Job Title") or fields.get("Title") or "",
        "location": fields.get("Location") or fields.get("Realtime location") or "",
    }


# ---------------------------------------------------------------------------
# BatchExecutor
# ---------------------------------------------------------------------------


class BatchExecutor:
    """
    Executes a job end-to-end:
      run_job → for each pending batch → run_batch → concurrent process_record
    """

    async def run_job(self, job: Dict) -> None:
        job_id = job["id"]
        base_id = job["base_id"]
        table_id = job["table_id"]
        field_mapping = job["field_mapping"]

        logger.info(f"Job {job_id}: starting ({base_id}/{table_id})")

        batches = await db.get_batches(job_id)
        pending = [b for b in batches if b["status"] in ("pending", "running")]

        for batch in pending:
            # Check for pause signal between batches
            fresh = await db.get_job(job_id)
            if fresh and fresh["status"] == "paused":
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
        already_done, recovered_hits, recovered_misses, recovered_failed = (
            _read_processed_stats(csv_path)
        )
        if already_done:
            logger.info(
                f"Batch {batch_id}: skipping {len(already_done)} already-processed records "
                f"(recovered: ✓{recovered_hits} —{recovered_misses} ✗{recovered_failed})"
            )

        field_cols          = _csv_field_names(field_mapping)
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
        processed_count = 0
        paused = False

        for chunk_start in range(0, len(pending_ids), CHUNK_SIZE):
            # Pause check before each chunk
            fresh = await db.get_job(job_id)
            if fresh and fresh["status"] == "paused":
                logger.info(
                    f"Job {job_id}: pause detected mid-batch {batch_id}, stopping after {processed_count} records"
                )
                paused = True
                break

            chunk = [
                self._process_record(
                    record_id, base_id, table_id, field_mapping, csv_path, csv_headers
                )
                for record_id in pending_ids[chunk_start : chunk_start + CHUNK_SIZE]
            ]
            chunk_results = await asyncio.gather(*chunk, return_exceptions=True)

            for result in chunk_results:
                processed_count += 1
                if isinstance(result, Exception):
                    logger.error(
                        f"Batch {batch_id}: unhandled error on record: {result}"
                    )
                    failed += 1
                elif result == "success":
                    hits += 1
                elif result == "skipped":
                    misses += 1
                else:
                    failed += 1

            # Live stats update after every chunk
            await db.update_batch(
                batch_id,
                processed=len(already_done) + processed_count,
                hits=hits,
                misses=misses,
                failed=failed,
            )

        total_processed = len(already_done) + processed_count

        # If paused mid-batch, leave status as "running" so it resumes on next run
        if paused:
            await db.update_batch(
                batch_id,
                processed=total_processed,
                hits=hits,
                misses=misses,
                failed=failed,
            )
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
                    field_mapping,
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

                write_row("failed", "record_not_found")
                return "failed"

            fields = record.get("fields", {})

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
                    record_id, fields, base_id, table_id, linkedin_field, loop
                )
                if not linkedin_url:
                    write_row("skipped", "no_linkedin_found")
                    return "skipped"

            # 3. Scrape profile + posts + news concurrently
            contact = _build_contact(fields)
            try:
                apify_data, raw_posts, news_signals = await asyncio.gather(
                    _pool_scrape(loop, _scrape_profile_sync, linkedin_url),
                    _pool_scrape(loop, _scrape_posts_sync, linkedin_url),
                    _news_search_async(contact["name"], contact.get("company", ""), loop),
                )
            except Exception as e:
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
                write_row("failed", "apify_no_profile_data", linkedin_url=linkedin_url)
                return "failed"

            # 4. Twitter scrape — non-fatal, runs alongside profile analysis
            twitter_handle = _extract_twitter_handle(apify_data, fields, field_mapping)
            raw_tweets: List[Dict] = []
            if twitter_handle:
                try:
                    raw_tweets = await loop.run_in_executor(None, _scrape_tweets_sync, twitter_handle)
                    logger.info(f"Record {record_id}: scraped {len(raw_tweets)} tweets for @{twitter_handle}")
                except Exception as e:
                    logger.warning(f"Record {record_id}: Twitter scrape failed (non-fatal): {e}")

            # Crunchbase enrichment — deferred to Week 2
            # crunchbase_url = _extract_crunchbase_url(fields, field_mapping)
            # if crunchbase_url:
            #     crunchbase_data = await loop.run_in_executor(None, _scrape_crunchbase_sync, crunchbase_url)

            # 5. Profile LLM analysis + posts signal extraction + tweet signals — run concurrently
            try:
                extracted, post_signals, tweet_signals = await asyncio.gather(
                    _get_analyzer().analyze(apify_data, field_mapping),
                    extract_post_signals(raw_posts or [], llm=_get_analyzer()._llm),
                    extract_tweet_signals(raw_tweets or []),
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

            # 7. Validate remaining profile fields against field_mapping
            validated, errors = _get_validator().validate(extracted, field_mapping)
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
    ) -> Optional[str]:
        """Search for LinkedIn URL via SERP + LLM ranking."""
        contact = _build_contact(fields)
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
