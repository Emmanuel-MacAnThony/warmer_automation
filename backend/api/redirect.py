"""
Click-tracking redirect endpoint.

  GET /r?eid=<enrollment>&u=<base64 destination>&s=<hmac>

Flow:
  1. Recompute the HMAC of (eid|u) using LINK_TRACKING_SECRET.
     If it doesn't match the supplied `s` → 400. This stops anyone tampering
     with the URL or using us as an open-redirector for phishing.
  2. Decode `u` back to the destination URL.
  3. Record a click event (best-effort; failures don't block the redirect —
     we never want a logging hiccup to break a recipient's click).
  4. 302 to the destination.

Performance: the click endpoint is in the recipient's hot path. Keep work
minimal and fire-and-forget the DB insert when reasonable; here we just
await it directly because asyncpg + Neon is fast enough that an extra ~5ms
on a click is invisible.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, PlainTextResponse

from backend.infra.db import engagement_repo
from backend.infra.db import sequence_repo as seq_repo
from backend.outreach.link_rewriter import decode_tracked_url, verify_signature

logger = logging.getLogger(__name__)
router = APIRouter(tags=["click-tracking"])


@router.get("/r", include_in_schema=False)
async def click_redirect(
    request: Request,
    eid: str = "",
    u: str = "",
    s: str = "",
    bjid: str = "",
):
    if not eid or not u or not s:
        return PlainTextResponse("bad request", status_code=400)

    # The signature payload uses "0" when no batch attribution is present —
    # the URL just omits the query param in that case, so normalise here.
    bjid_for_sig = bjid or "0"
    if not verify_signature(eid, u, s, bjid_for_sig):
        # Tampered or forged URL. Don't log to events (it isn't a real click)
        # and don't reveal anything about the destination.
        logger.warning(f"[/r] signature mismatch eid={eid!r} bjid={bjid!r}")
        return PlainTextResponse("invalid signature", status_code=400)

    dest = decode_tracked_url(u)
    if not dest:
        return PlainTextResponse("invalid destination", status_code=400)

    # Resolve enrollment context for the audit row. Each send carries exactly
    # one attribution id; the other comes back None.
    enrollment_id: int | None = None
    batch_job_id: int | None = None
    campaign_contact_id: int | None = None
    try:
        enrollment_id = int(eid)
        if enrollment_id <= 0:
            enrollment_id = None
    except ValueError:
        enrollment_id = None
    try:
        if bjid:
            batch_job_id = int(bjid)
            if batch_job_id <= 0:
                batch_job_id = None
    except ValueError:
        batch_job_id = None

    if enrollment_id is not None:
        try:
            row = await seq_repo.get_enrollment_contact_id(enrollment_id)
            if row is not None:
                campaign_contact_id = row
        except Exception as e:
            logger.debug(f"[/r] could not resolve contact for enrollment {enrollment_id}: {e}")

    try:
        await engagement_repo.record_click(
            sequence_enrollment_id=enrollment_id,
            batch_job_id=batch_job_id,
            campaign_contact_id=campaign_contact_id,
            link_url=dest,
            user_agent=request.headers.get("user-agent"),
            ip=(request.client.host if request.client else None),
        )
    except Exception as e:
        # Never fail the redirect on a logging error.
        logger.warning(f"[/r] click log failed (continuing to redirect): {e}")

    # 302 (temporary) is correct here — the destination URL is the canonical
    # one; the /r URL exists only as a logging hop. We don't want browsers /
    # caches to memoise the tracked URL as a permanent redirect target.
    return RedirectResponse(url=dest, status_code=302)
