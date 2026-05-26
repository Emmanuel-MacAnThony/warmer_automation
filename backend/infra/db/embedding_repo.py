"""
Contact embedding repository — pgvector-backed RAG scoring and indexing.
Implements the embedding slice of domain/interfaces/repos.py.
"""
import logging
from typing import Any

from backend.infra.db.pool import get_pool

logger = logging.getLogger(__name__)


async def get_rag_scores(
    base_id: str,
    table_id: str,
    goal_vector: str,
) -> dict[str, float]:
    """
    Bulk cosine-similarity query against a campaign goal embedding.
    Returns {airtable_record_id: similarity_score [0,1]} for every indexed contact.

    Uses pgvector's <=> operator (cosine distance); similarity = 1 - distance.
    Contacts not yet indexed won't appear — callers default missing ids to 0.0.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT airtable_record_id,
                   CAST(1.0 - (embedding <=> $1::vector) AS FLOAT) AS similarity
            FROM contact_embeddings
            WHERE base_id = $2 AND table_id = $3
            """,
            goal_vector, base_id, table_id,
        )
    return {r["airtable_record_id"]: float(r["similarity"]) for r in rows}


async def get_existing_hashes(base_id: str, table_id: str) -> dict[str, str]:
    """Return {record_id: content_hash} for every contact already indexed."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT airtable_record_id, content_hash FROM contact_embeddings WHERE base_id=$1 AND table_id=$2",
            base_id, table_id,
        )
    return {r["airtable_record_id"]: r["content_hash"] for r in rows}


async def upsert_contact_embedding(
    airtable_record_id: str,
    base_id: str,
    table_id: str,
    embedding: list[float],
    content_hash: str,
) -> bool:
    """
    Upsert a contact's embedding. Skips the write if content_hash is unchanged.
    Returns True if inserted/updated, False if skipped (no change).
    """
    pool = await get_pool()
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO contact_embeddings
                (airtable_record_id, base_id, table_id, embedding, content_hash, embedded_at)
            VALUES ($1, $2, $3, $4::vector, $5, now())
            ON CONFLICT (airtable_record_id)
            DO UPDATE SET
                embedding    = EXCLUDED.embedding,
                content_hash = EXCLUDED.content_hash,
                embedded_at  = now()
            WHERE contact_embeddings.content_hash != EXCLUDED.content_hash
            """,
            airtable_record_id, base_id, table_id, vector_str, content_hash,
        )
    return result not in ("INSERT 0 0", "UPDATE 0")
