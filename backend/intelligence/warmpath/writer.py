"""
Warm path writer — Layer 5.

Writes warm path results back to Airtable as four fields on each target record.

Fields written (auto-created if missing):
  warm_path_top_bridge  singleLineText  — name of best bridge contact
  warm_path_evidence    multilineText   — top N paths, one per line
  warm_path_score       number          — best score (0-100)
  warm_path_computed_at singleLineText  — ISO timestamp of last run

Usage:
  from backend.intelligence.warmpath.writer import write, ensure_fields
  ensure_fields(crm, base_id, table_id)
  written, errors = write(results, crm, base_id, table_id)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.intelligence.warmpath.matcher import Path

logger = logging.getLogger(__name__)

_FIELDS = [
    {"name": "warm_path_top_bridge",  "type": "singleLineText"},
    {"name": "warm_path_evidence",    "type": "multilineText"},
    {"name": "warm_path_score",       "type": "number", "options": {"precision": 0}},
    {"name": "warm_path_computed_at", "type": "singleLineText"},
]


def ensure_fields(crm, base_id: str, table_id: str) -> None:
    """Create warm path fields in Airtable if they don't already exist."""
    crm.ensure_table_fields(base_id, table_id, _FIELDS)


def _format_record(
    record_id: str,
    paths: list[Path],
    top_n: int = 3,
    computed_at: Optional[str] = None,
) -> dict:
    ts   = computed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    top  = paths[0]
    shown = paths[:top_n]
    evidence_lines = [
        f"{i}. {p.bridge_name} [{p.score}] | {p.evidence}"
        for i, p in enumerate(shown, 1)
    ]
    return {
        "id": record_id,
        "fields": {
            "warm_path_top_bridge":  top.bridge_name,
            "warm_path_evidence":    "\n".join(evidence_lines),
            "warm_path_score":       top.score,
            "warm_path_computed_at": ts,
        },
    }


def write(
    results: dict[str, list[Path]],
    crm,
    base_id: str,
    table_id: str,
    dry_run: bool = False,
    top_n: int = 3,
) -> tuple[int, int]:
    """
    Write warm path results to Airtable.

    results:  dict mapping target record_id → list of Path objects
    crm:      AirtableClient instance
    Returns:  (written_count, error_count)
    """
    if not results:
        logger.info("No warm path results to write")
        return 0, 0

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = [
        _format_record(record_id, paths, top_n=top_n, computed_at=ts)
        for record_id, paths in results.items()
        if paths
    ]

    if dry_run:
        logger.info("[DRY RUN] Would write %d records", len(records))
        for r in records[:5]:
            f = r["fields"]
            logger.info(
                "  %s  top_bridge=%s  score=%s\n    %s",
                r["id"], f["warm_path_top_bridge"],
                f["warm_path_score"],
                f["warm_path_evidence"].replace("\n", " / "),
            )
        if len(records) > 5:
            logger.info("  ... and %d more", len(records) - 5)
        return len(records), 0

    written = crm.batch_update_in_table(base_id, table_id, records)
    errors  = len(records) - written
    return written, errors
