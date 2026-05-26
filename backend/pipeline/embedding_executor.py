"""
EmbeddingExecutor — indexes enriched Airtable contacts into pgvector.

Called automatically after an enrichment job completes, or manually
via the API endpoint.

run(base_id, table_id, enrichment_job_id, triggered_by) -> run_id

Each contact is converted to a text blob from its Airtable fields,
hashed, and upserted — existing records are only re-embedded when
their content has actually changed.
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import Optional

from backend.infra.crm.airtable import AirtableClient
from backend.infra.db import client as db

logger = logging.getLogger(__name__)

# Fields to skip entirely — noisy, structural, or not semantically useful
_EXCLUDE_FIELDS = {
    "id", "createdTime", "Created", "Created Time",
    "Last Modified", "Last Modified Time",
    # Raw link dumps — too noisy for semantic search
    "post_analyzed_links", "LinkedIn URL", "Website",
}

# Fields that carry strong philanthropic / capacity signal — placed at top of text block
_HIGH_SIGNAL_FIELDS = [
    "post_giving_signal",
    "post_wealth_signal",
    "trajectory_signal",
    "Wealthy Capacity/Networth",
    "post_topic_themes",
    "post_personality_type",
    "post_engagement_tier",
]

# Fields that are JSON-encoded arrays stored as strings in Airtable
_JSON_ARRAY_FIELDS = {
    "post_topic_themes",
    "post_analyzed_links",
}


def _coerce_value(key: str, value) -> str | None:
    """Return a clean string representation of a field value, or None to skip."""
    if value is None or value == "" or value is False:
        return None

    # Native list (Airtable multi-select / linked records)
    if isinstance(value, list):
        items = [str(v).strip() for v in value if v]
        return ", ".join(items) if items else None

    if isinstance(value, (int, float)):
        return str(value)

    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    # JSON-string arrays → clean comma list
    if key in _JSON_ARRAY_FIELDS or (raw.startswith("[") and raw.endswith("]")):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items = [str(v).strip() for v in parsed if v]
                return ", ".join(items) if items else None
        except (json.JSONDecodeError, ValueError):
            pass

    # Strip bare URLs that add noise (http lines on their own)
    if re.match(r'^https?://\S+$', raw):
        return None

    return raw


def _build_contact_text(record: dict) -> str:
    """
    Convert an Airtable record into a semantically rich embeddable string.

    High-signal fields (giving intent, wealth, topics) come first so the
    embedding captures philanthropic context prominently. Remaining fields
    follow in original order. JSON array strings are decoded to clean text.
    """
    fields = record.get("fields", {})
    parts: list[str] = []
    seen: set[str] = set()

    def _add(key: str, value) -> None:
        if key in seen or key in _EXCLUDE_FIELDS:
            return
        text = _coerce_value(key, value)
        if text:
            parts.append(f"{key}: {text}")
            seen.add(key)

    # High-signal fields first
    for key in _HIGH_SIGNAL_FIELDS:
        if key in fields:
            _add(key, fields[key])

    # All remaining fields
    for key, value in fields.items():
        _add(key, value)

    return "\n".join(parts)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts. Blocking."""
    from backend.infra.llm.factory import get_llm_provider
    client = get_llm_provider().sync_client
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


async def _upsert_batch(
    rows: list[tuple[str, str, list[float]]],  # (record_id, content_hash, vector)
    base_id: str,
    table_id: str,
) -> tuple[int, int, int]:
    """
    Upsert a batch of embeddings using executemany — one DB round-trip for the
    whole batch instead of N individual execute() calls.

    All rows passed here are pre-filtered (hash changed or new), so they're all
    expected to be indexed. Returns (indexed, skipped=0, failed).
    """
    # Build vector strings before acquiring the connection — CPU work,
    # but kept here since it's fast (~5ms for 50 vectors).
    params = [
        (record_id, base_id, table_id,
         "[" + ",".join(str(x) for x in vector) + "]",
         content_hash)
        for record_id, content_hash, vector in rows
    ]

    pool = await db.get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO contact_embeddings
                    (airtable_record_id, base_id, table_id, embedding, content_hash, embedded_at)
                VALUES ($1, $2, $3, $4::vector, $5, now())
                ON CONFLICT (airtable_record_id)
                DO UPDATE SET
                    embedding    = EXCLUDED.embedding,
                    content_hash = EXCLUDED.content_hash,
                    embedded_at  = now()
                """,
                params,
            )
        return len(rows), 0, 0
    except Exception as e:
        logger.error(f"_upsert_batch failed: {e}")
        return 0, 0, len(rows)


async def run(
    base_id: str,
    table_id: str,
    enrichment_job_id: Optional[int] = None,
    triggered_by: str = "auto",
) -> int:
    """
    Index all contacts for a table into pgvector.

      1. Create embedding_runs record (status: running)
      2. Fetch all records from Airtable          [thread pool]
      3. For each record: build text + hash
      4. Skip records whose hash hasn't changed
      5. Embed changed records in batches of 100  [thread pool]
      6. Upsert embeddings into contact_embeddings
      7. Update embedding_runs (completed)

    Returns the embedding_runs run_id.
    """
    loop = asyncio.get_event_loop()

    run_id = await db.create_embedding_run(
        base_id=base_id,
        table_id=table_id,
        triggered_by=triggered_by,
        enrichment_job_id=enrichment_job_id,
    )
    await db.update_embedding_run(run_id, status="running")

    try:
        crm = AirtableClient()
        table = crm.api.table(base_id, table_id)

        # ── Fetch all records (blocking Airtable HTTP) ─────────────────────
        logger.info(f"[embedding run={run_id}] Fetching all records from {base_id}/{table_id}")
        records = await loop.run_in_executor(None, table.all)
        total = len(records)
        logger.info(f"[embedding run={run_id}] {total} records fetched")

        await db.update_embedding_run(run_id, status="running", total_contacts=total)

        # ── Build texts ────────────────────────────────────────────────────
        candidates = []  # (record_id, text, content_hash)
        skipped = 0      # empty-text contacts

        for record in records:
            record_id = record["id"]
            text = _build_contact_text(record)
            if not text.strip():
                skipped += 1
                continue
            candidates.append((record_id, text, _hash(text)))

        # ── Pre-filter: skip contacts whose hash hasn't changed ────────────
        # Fetch all existing hashes in one query — avoids redundant OpenAI
        # calls for contacts that were already embedded with the same content.
        existing_hashes = await db.get_existing_hashes(base_id, table_id)
        to_embed = [(rid, text, h) for rid, text, h in candidates if existing_hashes.get(rid) != h]
        already_current = len(candidates) - len(to_embed)
        skipped += already_current

        logger.info(
            f"[embedding run={run_id}] {len(to_embed)} to embed, "
            f"{already_current} already up to date, {skipped} skipped total"
        )

        # Persist immediately so the UI shows accurate "up to date" count
        # instead of staying at 0 / total for a long time.
        await db.update_embedding_run(
            run_id, status="running",
            indexed=0, skipped=skipped, failed=0,
        )

        # ── Embed in batches of 50 ─────────────────────────────────────────
        BATCH = 50
        indexed = 0
        failed = 0

        for i in range(0, len(to_embed), BATCH):
            batch = to_embed[i : i + BATCH]
            texts = [t for _, t, _ in batch]

            try:
                vectors = await loop.run_in_executor(None, _embed_texts, texts)
            except Exception as e:
                logger.error(f"[embedding run={run_id}] Embed batch {i//BATCH+1} failed: {e}")
                failed += len(batch)
                continue

            # Batch upsert — one pool acquire for the whole batch of 100
            batch_indexed, batch_skipped, batch_failed = await _upsert_batch(
                [(record_id, content_hash, vector)
                 for (record_id, _, content_hash), vector in zip(batch, vectors)],
                base_id, table_id,
            )
            indexed += batch_indexed
            skipped += batch_skipped
            failed  += batch_failed

            total_batches = (len(to_embed) + BATCH - 1) // BATCH
            logger.info(
                f"[embedding run={run_id}] Batch {i//BATCH+1}/{total_batches} done — "
                f"indexed={indexed} skipped={skipped} failed={failed}"
            )

            # Persist incremental progress so the UI can poll and show live counts
            await db.update_embedding_run(
                run_id,
                status="running",
                indexed=indexed,
                skipped=skipped,
                failed=failed,
            )

        # ── Complete ───────────────────────────────────────────────────────
        await db.update_embedding_run(
            run_id,
            status="completed",
            total_contacts=total,
            indexed=indexed,
            skipped=skipped,
            failed=failed,
        )
        logger.info(
            f"[embedding run={run_id}] Completed — "
            f"indexed={indexed} skipped={skipped} failed={failed}"
        )

    except Exception as e:
        logger.error(f"[embedding run={run_id}] Failed: {e}", exc_info=True)
        await db.update_embedding_run(run_id, status="failed", error=str(e))
        raise

    return run_id
