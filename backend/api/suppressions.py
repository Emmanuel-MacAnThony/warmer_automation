"""
Suppressions endpoints.

The "dead-list" admin surface: view who's suppressed, why, when, and from
which source (sequence / batch / MX preflight / DSN scan). Plus a manual
unsuppress action for false positives.

Bounces themselves are recorded in email_bounces (audit log); suppressions
live in email_suppressions (active dead-list). These endpoints query both.
"""
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["suppressions"])


class UnsuppressRequest(BaseModel):
    email: str


@router.get("/suppressions")
async def list_suppressions(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
):
    """
    Paged list of suppressed emails. ?search=<substr> for an ILIKE match.
    Returns a `count` of currently-active suppressions for the summary label.
    """
    try:
        from backend.infra.db import suppression_repo as sup_repo
        rows = await sup_repo.list_suppressions(limit=limit, offset=offset, search=search)
        active = await sup_repo.count_active_suppressions()
        return {"suppressions": rows, "active_count": active}
    except Exception as e:
        logger.error(f"Failed to list suppressions: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/suppressions/{email}/bounces")
async def get_bounces_for_email(email: str, limit: int = 50):
    """Audit history for one email — the expand row on the suppressions page."""
    try:
        from backend.infra.db import suppression_repo as sup_repo
        return {"bounces": await sup_repo.list_bounces_for_email(email, limit=limit)}
    except Exception as e:
        logger.error(f"Failed to fetch bounce history for {email}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/suppressions/unsuppress")
async def unsuppress(req: UnsuppressRequest):
    """
    Remove an email from the suppression list (manual override for false
    positives). The address can be re-enrolled in future sequences and
    appear in batch contact selection again.
    """
    try:
        from backend.infra.db import suppression_repo as sup_repo
        removed = await sup_repo.unsuppress(req.email)
        return {"removed": removed}
    except Exception as e:
        logger.error(f"Failed to unsuppress {req.email!r}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
