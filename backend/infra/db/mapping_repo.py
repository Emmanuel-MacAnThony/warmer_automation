"""
Field mapping repository.
Implements domain/interfaces/repos.py::MappingRepo.
"""
import json
import logging
from typing import Any, Optional

from backend.infra.db.pool import get_pool

logger = logging.getLogger(__name__)


async def save_field_mapping(base_id: str, table_id: str, name: str, mappings: dict) -> int:
    """Insert a new named field mapping for a table. Returns the new mapping id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO field_mappings (base_id, table_id, name, mappings)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id
            """,
            base_id, table_id, name, json.dumps(mappings)
        )
    mapping_id = row["id"]
    logger.info(f"Saved mapping '{name}' (id={mapping_id}) for {base_id}/{table_id}")
    return mapping_id


async def get_field_mappings(base_id: str, table_id: str) -> list[dict[str, Any]]:
    """Fetch all saved mappings for a table, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, mappings, created_at
            FROM field_mappings
            WHERE base_id=$1 AND table_id=$2
            ORDER BY created_at DESC
            """,
            base_id, table_id
        )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "mappings": json.loads(r["mappings"]) if isinstance(r["mappings"], str) else r["mappings"],
            "created_at": r["created_at"].isoformat()
        }
        for r in rows
    ]


async def get_field_mapping_by_id(mapping_id: int) -> Optional[dict[str, Any]]:
    """Fetch a single mapping by id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, mappings, created_at FROM field_mappings WHERE id=$1",
            mapping_id
        )
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "mappings": json.loads(row["mappings"]) if isinstance(row["mappings"], str) else row["mappings"],
        "created_at": row["created_at"].isoformat()
    }


async def update_field_mapping(mapping_id: int, name: str, mappings: dict) -> bool:
    """Update name and field mappings for an existing mapping. Returns True if updated."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE field_mappings SET name=$1, mappings=$2::jsonb WHERE id=$3",
            name, json.dumps(mappings), mapping_id
        )
    return result == "UPDATE 1"


async def delete_field_mapping(mapping_id: int) -> bool:
    """Delete a mapping by id. Returns True if deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM field_mappings WHERE id=$1", mapping_id
        )
    return result == "DELETE 1"
