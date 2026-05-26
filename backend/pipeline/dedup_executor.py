"""
Airtable duplicate record health-check.

Groups records by normalized name, then for each duplicate group keeps the
record with the most filled fields and deletes the rest.

The job's field_mapping is the source of truth for which columns hold the
contact name (canonical keys: full_name, first_name, last_name). Falls back
to auto-detecting name-like column keys from the Airtable response.

Runs as an async background task with DB-tracked status so the UI can poll
even after the user navigates away.  Pipeline order: dedup → enrichment →
warm-path → embedding.
"""
import asyncio
import logging
import queue as _queue
import re
import threading
import unicodedata
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    return re.sub(r"\s+", " ", text)


def _name_field_map(field_mapping: dict) -> dict:
    """
    Extract name column(s) from a job's field_mapping.
    New format: {"name_field": "Name", "linkedin_url_field": "LinkedIn"}
    Legacy format: keyed by field_id, each value has canonical_key/airtable_name.
    Returns e.g. {'full': 'Name', 'first': 'First Name', 'last': 'Last Name'}
    """
    # New simplified format
    if "name_field" in field_mapping:
        name_col = field_mapping["name_field"]
        return {"full": name_col} if name_col else {}

    # Legacy format: scan by canonical_key
    result: dict = {}
    for cfg in field_mapping.values():
        if not isinstance(cfg, dict):
            continue
        ck    = cfg.get("canonical_key", "")
        aname = cfg.get("airtable_name")
        if not aname:
            continue
        if ck == "full_name":
            result["full"] = aname
        elif ck == "first_name":
            result["first"] = aname
        elif ck == "last_name":
            result["last"] = aname
    return result


def _extract_name(fields: dict, name_cols: dict) -> Optional[str]:
    """
    Extract a normalized display name.

    Priority:
      1. Mapping-derived full_name column
      2. Mapping-derived first_name + last_name
      3. Auto-detect: key exactly equals 'name' or 'full name'
      4. Auto-detect: first key containing 'name' (excluding company/domain keys)
    """
    if name_cols.get("full"):
        val = fields.get(name_cols["full"], "")
        if val and isinstance(val, str):
            return _normalize(val)

    first = fields.get(name_cols.get("first", ""), "") or ""
    last  = fields.get(name_cols.get("last",  ""), "") or ""
    combined = f"{first} {last}".strip()
    if combined:
        return _normalize(combined)

    fallback: Optional[str] = None
    for key, val in fields.items():
        if not isinstance(val, str) or not val.strip():
            continue
        k = key.lower()
        if k in ("name", "full name", "contact name"):
            return _normalize(val)
        if "name" in k and "company" not in k and "domain" not in k and fallback is None:
            fallback = _normalize(val)

    return fallback


def _score(record: dict) -> int:
    return sum(
        1 for v in record["fields"].values()
        if v is not None and v != "" and v != []
    )


# ---------------------------------------------------------------------------
# Async page iterator (wraps pyairtable's sync generator without blocking loop)
# ---------------------------------------------------------------------------

async def _iter_pages(table, fetch_fields):
    q: _queue.Queue = _queue.Queue()

    def _producer():
        try:
            kwargs = {"fields": fetch_fields} if fetch_fields else {}
            for page in table.iterate(**kwargs):
                q.put(("page", page))
            q.put(("done", None))
        except Exception as exc:
            q.put(("error", exc))

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        try:
            kind, data = q.get_nowait()
        except _queue.Empty:
            await asyncio.sleep(0.05)
            continue
        if kind == "done":
            break
        if kind == "error":
            raise data
        yield data


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run(
    base_id: str,
    table_id: str,
    field_mapping: Optional[dict] = None,
    triggered_by: str = "auto",
    enrichment_job_id: Optional[int] = None,
) -> None:
    """
    Background async task: scan for duplicates, delete losers, update DB run record.
    """
    from pyairtable import Api
    from backend.config import Config
    from backend.infra.db.client import create_dedup_run, update_dedup_run

    run_id = await create_dedup_run(
        base_id=base_id,
        table_id=table_id,
        triggered_by=triggered_by,
        enrichment_job_id=enrichment_job_id,
    )

    try:
        await update_dedup_run(run_id, status="running")

        api_client = Api(Config.AIRTABLE_API_KEY)
        table      = api_client.table(base_id, table_id)

        name_cols = _name_field_map(field_mapping or {})

        # Slim fetch — only name columns if mapping provides them
        if name_cols:
            fetch_fields = list({name_cols.get("full"), name_cols.get("first"), name_cols.get("last")} - {None})
        else:
            fetch_fields = None

        # Page-by-page scan so we can flush progress to DB and unblock the event loop
        groups: dict[str, list[str]] = defaultdict(list)
        records_checked = 0

        async for page in _iter_pages(table, fetch_fields):
            for r in page:
                name = _extract_name(r["fields"], name_cols)
                if name:
                    groups[name].append(r["id"])
                records_checked += 1
            # flush live count after every page (~100 records)
            groups_so_far = sum(1 for ids in groups.values() if len(ids) > 1)
            await update_dedup_run(
                run_id, status="running",
                records_checked=records_checked,
                groups_found=groups_so_far,
            )

        duplicate_groups = {n: ids for n, ids in groups.items() if len(ids) > 1}

        groups_found    = len(duplicate_groups)
        records_deleted = 0

        if not duplicate_groups:
            logger.info(f"Dedup run {run_id}: {records_checked} checked — no duplicates")
            await update_dedup_run(
                run_id, status="completed",
                records_checked=records_checked,
                groups_found=0,
                records_deleted=0,
            )
            return

        # Fetch full records for each duplicate group and resolve
        for name, record_ids in duplicate_groups.items():
            full: list[dict] = []
            for rid in record_ids:
                try:
                    r = await asyncio.to_thread(table.get, rid)
                    full.append(r)
                except Exception as e:
                    logger.warning(f"Dedup run {run_id}: could not fetch {rid}: {e}")

            if len(full) < 2:
                continue

            full.sort(key=_score, reverse=True)
            winner = full[0]
            losers = full[1:]

            logger.info(
                f"Dedup run {run_id}: '{name}' — keeping {winner['id']} "
                f"({_score(winner)} fields), deleting {[l['id'] for l in losers]}"
            )

            for loser in losers:
                try:
                    await asyncio.to_thread(table.delete, loser["id"])
                    records_deleted += 1
                    await update_dedup_run(run_id, status="running", records_deleted=records_deleted)
                except Exception as e:
                    logger.warning(f"Dedup run {run_id}: failed to delete {loser['id']}: {e}")

        logger.info(
            f"Dedup run {run_id} complete — {records_checked} checked, "
            f"{groups_found} groups, {records_deleted} deleted"
        )
        await update_dedup_run(
            run_id, status="completed",
            records_checked=records_checked,
            groups_found=groups_found,
            records_deleted=records_deleted,
        )

    except Exception as e:
        logger.error(f"Dedup run {run_id} failed: {e}")
        await update_dedup_run(run_id, status="failed", error=str(e))
        raise
