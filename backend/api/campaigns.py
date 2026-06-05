"""
Outreach campaign endpoints — campaigns, contacts, templates, batch send jobs.
"""
import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["campaigns"])


class CreateCampaignRequest(BaseModel):
    base_id: str
    table_id: str
    goal: str = Field(..., min_length=10)
    mapping_id: Optional[int] = None
    # Optional pitch page. When set, every email sent for this campaign gets a
    # tracked CTA appended pointing here, so we can measure click engagement.
    pitch_page_url: Optional[str] = None
    pitch_page_label: Optional[str] = None


class SendContactRequest(BaseModel):
    sent_draft: str = Field(..., min_length=1)


class SaveTemplateRequest(BaseModel):
    subject: str = ''
    body: str = ''
    variables: list[str] = Field(default_factory=list)
    tier_summary: Optional[str] = None
    template_id: Optional[int] = None


class PreviewRequest(BaseModel):
    subject: str = ''
    body: str = ''
    count: int = Field(default=5, ge=1, le=10)


class GenerateRequest(BaseModel):
    guidance: str = ''
    current_subject: str = ''
    current_body: str = ''
    template_id: Optional[int] = None
    guidance_history: list[str] = []
    airtable_fields: list[str] = []


class BatchSendRequest(BaseModel):
    scope: str = Field(default="unsent", pattern="^(unsent|everyone)$")
    template_id: Optional[int] = None
    sender_emails: list[str] = Field(default_factory=list)
    test_recipient: Optional[str] = None


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.post("/campaigns")
async def create_campaign(request: CreateCampaignRequest):
    """
    Create a campaign and immediately start the segmentation pipeline.

    Returns the full campaign row so the frontend doesn't need a follow-up
    GET — eliminates one round-trip on what was a 3-call create flow.
    """
    try:
        from backend.infra.db.campaign_repo import (
            create_campaign as db_create_campaign,
            get_campaign as db_get_campaign,
        )
        from backend.agents.segmentation import run_segmentation, register

        campaign_id = await db_create_campaign(
            base_id=request.base_id,
            table_id=request.table_id,
            goal=request.goal,
            mapping_id=request.mapping_id,
            pitch_page_url=(request.pitch_page_url or "").strip() or None,
            pitch_page_label=(request.pitch_page_label or "").strip() or None,
        )
        register(campaign_id)
        asyncio.create_task(
            run_segmentation(
                campaign_id=campaign_id,
                base_id=request.base_id,
                table_id=request.table_id,
                goal=request.goal,
                mapping_id=request.mapping_id,
            ),
            name=f"segment-{campaign_id}",
        )
        # Fetch the full row so the response is ready-to-use on the frontend.
        # Single SELECT against the row we just inserted — fast, same pool.
        campaign = await db_get_campaign(campaign_id)
        logger.info(f"Campaign {campaign_id}: created and segmentation started")
        return {
            "campaign_id": campaign_id,
            "status": "segmenting",
            "campaign": campaign,
        }
    except Exception as e:
        logger.error(f"Failed to create campaign: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/events")
async def campaign_events(campaign_id: int):
    """SSE stream of segmentation progress events."""
    from backend.infra.db.campaign_repo import get_campaign
    from backend.agents.segmentation import get_queue, unregister, SENTINEL
    import json

    async def _stream():
        q = get_queue(campaign_id)
        if q is None:
            campaign = await get_campaign(campaign_id)
            if campaign:
                event = {
                    "type": "complete" if campaign["status"] == "ready" else campaign["status"],
                    "message": f"Campaign is {campaign['status']}",
                    "tier_counts": {
                        "tier_1": campaign.get("tier_1_count", 0),
                        "tier_2": campaign.get("tier_2_count", 0),
                        "tier_3": campaign.get("tier_3_count", 0),
                    },
                }
            else:
                event = {"type": "error", "message": "Campaign not found"}
            yield f"data: {json.dumps(event)}\n\n"
            return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if event is SENTINEL:
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break

                yield f"data: {json.dumps(event)}\n\n"

                if event.get("type") in ("complete", "error"):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
        finally:
            unregister(campaign_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/campaigns")
async def list_campaigns(base_id: str, table_id: str):
    try:
        from backend.infra.db.campaign_repo import list_campaigns as db_list_campaigns
        campaigns = await db_list_campaigns(base_id, table_id)
        return {"campaigns": campaigns}
    except Exception as e:
        logger.error(f"Failed to list campaigns: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int):
    try:
        from backend.infra.db.campaign_repo import get_campaign as db_get_campaign
        campaign = await db_get_campaign(campaign_id)
        if not campaign:
            return JSONResponse(status_code=404, content={"error": "Campaign not found"})
        return {"campaign": campaign}
    except Exception as e:
        logger.error(f"Failed to get campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int):
    try:
        from backend.infra.db.campaign_repo import delete_campaign as db_delete_campaign
        deleted = await db_delete_campaign(campaign_id)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": "Campaign not found"})
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/queue/{tier}")
async def get_campaign_queue(campaign_id: int, tier: str, offset: int = 0, limit: int = 50):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import count_queue, get_queue
        total, contacts = await asyncio.gather(
            count_queue(campaign_id, tier),
            get_queue(campaign_id, tier, offset=offset, limit=limit),
        )
        return {"contacts": contacts, "count": total, "has_more": offset + limit < total}
    except Exception as e:
        logger.error(f"Failed to get queue for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: int):
    try:
        from backend.infra.db.campaign_repo import get_campaign_stats as db_get_stats
        stats = await db_get_stats(campaign_id)
        return {"stats": stats}
    except Exception as e:
        logger.error(f"Failed to get stats for campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/contacts/{contact_id}/send")
async def send_contact(campaign_id: int, contact_id: int, body: SendContactRequest):
    try:
        from backend.infra.db.campaign_repo import send_contact as db_send, increment_campaign_counter
        await db_send(contact_id, body.sent_draft)
        await increment_campaign_counter(campaign_id, "sent_count")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to mark contact {contact_id} as sent: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/contacts/{contact_id}/skip")
async def skip_contact(campaign_id: int, contact_id: int):
    try:
        from backend.infra.db.campaign_repo import skip_contact as db_skip, increment_campaign_counter
        await db_skip(contact_id)
        await increment_campaign_counter(campaign_id, "skipped_count")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to skip contact {contact_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/contacts/{contact_id}/later")
async def park_contact(campaign_id: int, contact_id: int):
    try:
        from backend.infra.db.campaign_repo import get_campaign_contact, park_contact_later
        contact = await get_campaign_contact(contact_id)
        if not contact:
            return JSONResponse(status_code=404, content={"error": "Contact not found"})
        await park_contact_later(contact_id, campaign_id, contact["tier"])
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to park contact {contact_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/templates/by-id/{template_id}")
async def get_template_by_id(campaign_id: int, template_id: int):
    try:
        from backend.infra.db.campaign_repo import get_campaign_template_by_id
        template = await get_campaign_template_by_id(template_id)
        if not template:
            return JSONResponse(status_code=404, content={"error": "Template not found"})
        return {"template": template}
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/templates/{tier}/signal-scan")
async def signal_scan(campaign_id: int, tier: str):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.outreach.signal_scanner import scan_tier_signals
        scan = await scan_tier_signals(campaign_id, tier)
        return {"scan": scan}
    except Exception as e:
        logger.error(f"Signal scan failed for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/templates/{tier}")
async def get_campaign_template(campaign_id: int, tier: str):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import get_campaign_template as db_get_template
        template = await db_get_template(campaign_id, tier)
        if not template:
            return JSONResponse(status_code=404, content={"error": "No template yet"})
        return {"template": template}
    except Exception as e:
        logger.error(f"Failed to get template for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/templates/{tier}/new")
async def create_new_template(campaign_id: int, tier: str):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import create_campaign_template
        template = await create_campaign_template(campaign_id, tier)
        return {"template": template}
    except Exception as e:
        logger.error(f"Failed to create template for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.put("/campaigns/{campaign_id}/templates/{tier}")
async def save_campaign_template(campaign_id: int, tier: str, request: SaveTemplateRequest):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import (
            create_campaign_template, update_campaign_template_by_id
        )
        if request.template_id:
            template = await update_campaign_template_by_id(
                request.template_id, request.subject, request.body,
                request.variables, request.tier_summary,
            )
            if not template:
                return JSONResponse(status_code=404, content={"error": "Template not found"})
        else:
            tpl = await create_campaign_template(campaign_id, tier)
            template = await update_campaign_template_by_id(
                tpl["id"], request.subject, request.body,
                request.variables, request.tier_summary,
            )
        return {"template": template}
    except Exception as e:
        logger.error(f"Failed to save template for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/parse-file")
async def parse_template_file(campaign_id: int, file: UploadFile):
    try:
        from backend.outreach.file_parser import parse_file
        data = await file.read()
        result = parse_file(file.filename or 'upload.txt', data)
        return result
    except Exception as e:
        logger.error(f"File parse failed for campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/deck")
async def upload_campaign_deck(campaign_id: int, file: UploadFile):
    """
    Optional: attach a campaign deck/brief (PDF/DOCX/TXT). Parsed and stored so
    the email copilot can ground generated emails in the real campaign messaging.
    Campaigns work fine with no deck — this only adds context when present.
    """
    try:
        from backend.outreach.file_parser import parse_file
        from backend.infra.db.campaign_repo import create_campaign_file

        filename = file.filename or 'deck.txt'
        data = await file.read()
        parsed = parse_file(filename, data)
        text = (parsed.get('text') or '').strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "Could not extract any text from this file"})

        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
        file_type = ext if ext in ('csv', 'xlsx', 'pdf', 'docx', 'txt') else 'txt'

        file_id = await create_campaign_file(
            campaign_id=campaign_id,
            filename=filename,
            file_type=file_type,
            parsed_content=text,
        )
        return {"id": file_id, "filename": filename, "chars": len(text)}
    except Exception as e:
        logger.error(f"Deck upload failed for campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/templates/{tier}/approve")
async def approve_campaign_template(campaign_id: int, tier: str):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import approve_campaign_template as db_approve
        updated = await db_approve(campaign_id, tier)
        if not updated:
            return JSONResponse(status_code=404, content={"error": "Template not found"})
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to approve template for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/templates/{tier}/preview")
async def preview_campaign_template(campaign_id: int, tier: str, request: PreviewRequest):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import get_campaign, sample_queue
        from backend.outreach.link_rewriter import render_with_tracking
        from backend.outreach.variable_resolver import resolve

        # Pull the campaign once so the preview can show the auto-appended CTA
        # exactly as it'll go out at send time.
        camp = await get_campaign(campaign_id)
        pitch_page_url   = camp.get("pitch_page_url")   if camp else None
        pitch_page_label = camp.get("pitch_page_label") if camp else None

        contacts = await sample_queue(campaign_id, tier, request.count)
        results = []
        for c in contacts:
            snap     = c.get("contact_snapshot") or {}
            score    = c.get("score_breakdown") or {}
            wp       = c.get("warm_path_data")
            subj, rs = resolve(request.subject, snap, score, wp, tier)
            body, rb = resolve(request.body,    snap, score, wp, tier)
            # Apply the same link-rewriter + pitch-page-CTA append used at send
            # time, so the fundraiser sees the exact body that will go out and
            # can click-test the tracked CTA before approving. Preview clicks
            # log without enrollment attribution (eid=0 in the URL).
            body = render_with_tracking(
                body,
                enrollment_id=None,
                pitch_page_url=pitch_page_url,
                pitch_page_label=pitch_page_label,
            )
            results.append({
                "contact_id":       c["id"],
                "contact_name":     snap.get("name", "Unknown"),
                "rendered_subject": subj,
                "rendered_body":    body,
                "resolved_vars":    list(set(rs["resolved"] + rb["resolved"])),
                "fallback_vars":    list(set(rs["fallback"] + rb["fallback"])),
                "omitted_vars":     list(set(rs["omitted"]  + rb["omitted"])),
            })
        return {"previews": results}
    except Exception as e:
        logger.error(f"Preview failed for campaign {campaign_id} tier {tier}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/templates/{tier}/scope-counts")
async def get_scope_counts(campaign_id: int, tier: str):
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import count_scope_contacts
        unsent   = await count_scope_contacts(campaign_id, tier, "unsent")
        everyone = await count_scope_contacts(campaign_id, tier, "everyone")
        return {"unsent": unsent, "everyone": everyone}
    except Exception as e:
        logger.error(f"Scope count failed for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/templates/{tier}/send")
async def create_batch_send(campaign_id: int, tier: str, body: BatchSendRequest):
    """Queue a batch send job for a campaign tier."""
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})
    try:
        from backend.infra.db.campaign_repo import (
            get_campaign_template_by_id, get_campaign_template,
            count_scope_contacts, create_batch_send_job, get_batch_send_job,
        )
        if body.template_id:
            template = await get_campaign_template_by_id(body.template_id)
        else:
            template = await get_campaign_template(campaign_id, tier)
        if not template:
            return JSONResponse(status_code=404, content={"error": "No template found — save one first"})
        total  = await count_scope_contacts(campaign_id, tier, body.scope)
        job_id = await create_batch_send_job(
            campaign_id=campaign_id, template_id=template["id"],
            tier=tier, total=total, scope=body.scope,
            sender_emails=body.sender_emails,
            test_recipient=body.test_recipient or None,
        )
        job = await get_batch_send_job(job_id)

        # Register SSE queue and start runner as background task
        from backend.pipeline import batch_sender
        batch_sender.register(job_id)
        asyncio.create_task(
            batch_sender.run(job_id),
            name=f"batch-send-{job_id}",
        )
        logger.info(f"Campaign {campaign_id} tier {tier}: batch send job {job_id} started")
        return {"job": job}
    except Exception as e:
        logger.error(f"Failed to create batch send job for campaign {campaign_id} tier {tier}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/templates/{tier}/generate")
async def generate_campaign_template(campaign_id: int, tier: str, gen_req: GenerateRequest):
    """Generate a new email template via LLM — streams SSE events."""
    if tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {tier}"})

    import json as _json
    from backend.infra.db.campaign_repo import (
        get_campaign, get_queue, update_campaign_template_by_id, upsert_campaign_template
    )
    from backend.outreach.signal_scanner import scan_tier_signals
    from backend.agents.outreach import generate_streaming

    async def event_stream():
        try:
            campaign = await get_campaign(campaign_id)
            if not campaign:
                yield f'data: {_json.dumps({"type":"error","message":"Campaign not found"})}\n\n'
                return

            from backend.infra.db.campaign_repo import get_campaign_source_material
            samples, scan, source_material = await asyncio.gather(
                get_queue(campaign_id, tier, include_later=True, offset=0, limit=20),
                scan_tier_signals(campaign_id, tier),
                get_campaign_source_material(campaign_id),
            )

            tier_insight = campaign.get(f"{tier}_insight") or ''

            async for event in generate_streaming(
                campaign["goal"], tier, scan, samples,
                guidance=gen_req.guidance,
                existing_subject=gen_req.current_subject,
                existing_body=gen_req.current_body,
                guidance_history=gen_req.guidance_history,
                airtable_fields=gen_req.airtable_fields,
                tier_insight=tier_insight,
                source_material=source_material,
            ):
                if event["type"] == "complete":
                    result = event["result"]
                    if gen_req.template_id:
                        template = await update_campaign_template_by_id(
                            gen_req.template_id,
                            subject=result["subject"], body=result["body"],
                            variables=result["variables"], tier_summary=result["tier_summary"],
                        )
                    else:
                        template = await upsert_campaign_template(
                            campaign_id=campaign_id, tier=tier,
                            subject=result["subject"], body=result["body"],
                            variables=result["variables"], tier_summary=result["tier_summary"],
                        )
                    yield f'data: {_json.dumps({"type":"complete","template":template,"score":result.get("final_score")})}\n\n'
                else:
                    yield f'data: {_json.dumps(event)}\n\n'
        except Exception as e:
            logger.error(f"Template generation stream failed: {e}", exc_info=True)
            yield f'data: {_json.dumps({"type":"error","message":"Something went wrong generating the template"})}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Batch Send Jobs (top-level and per-campaign)
# ---------------------------------------------------------------------------

@router.get("/batch-jobs")
async def list_all_batch_jobs(base_id: str, table_id: str):
    try:
        from backend.infra.db.campaign_repo import list_all_batch_send_jobs_for_table
        jobs = await list_all_batch_send_jobs_for_table(base_id, table_id)
        return {"jobs": jobs}
    except Exception as e:
        logger.error(f"Failed to list all batch jobs: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/batch-jobs/{job_id}")
async def get_batch_job_detail(job_id: int):
    """Single batch job — used by the batch-job detail page. Joins the campaign goal
    + pitch page so the detail view doesn't need a second roundtrip, and computes
    quota_resets_at (when Gmail's rolling 24h window opens up) when the job is
    paused so the UI can show the user an actual time to retry."""
    try:
        from backend.infra.db.campaign_repo import (
            count_sent_contacts_for_scope, estimate_quota_reset_for_job,
            get_batch_send_job, get_campaign, update_batch_send_job,
        )
        job = await get_batch_send_job(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": "Batch job not found"})

        # Self-heal stale sent counts. A buggy earlier resume could have written
        # sent=0 even though contacts went out. We treat campaign_contacts as
        # the source of truth and write the corrected count back so the next
        # read is fast and consistent.
        stored_sent = int(job.get("sent") or 0)
        true_sent = await count_sent_contacts_for_scope(job["campaign_id"], job["tier"])
        if true_sent > stored_sent:
            await update_batch_send_job(job_id, sent=true_sent)
            job["sent"] = true_sent
            logger.info(
                f"[batch_send job={job_id}] healed stored sent {stored_sent} -> {true_sent}"
            )

        camp = await get_campaign(job["campaign_id"])
        if camp:
            job["campaign_goal"] = camp.get("goal")
            job["pitch_page_url"] = camp.get("pitch_page_url")
            job["pitch_page_label"] = camp.get("pitch_page_label")
        # Only useful when paused; harmless to compute always. None if no recent
        # send activity to estimate from.
        job["quota_resets_at"] = await estimate_quota_reset_for_job(job_id)
        return job
    except Exception as e:
        logger.error(f"Failed to get batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/batch-jobs/{job_id}/clicks")
async def get_batch_job_clicks(job_id: int):
    """Contacts who clicked any link in this batch job — strongest engagement signal."""
    try:
        from backend.infra.db import engagement_repo
        return {"clicks": await engagement_repo.list_click_contacts_for_batch_job(job_id)}
    except Exception as e:
        logger.error(f"Failed to fetch clicks for batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/batch-jobs/{job_id}/bounces")
async def get_batch_job_bounces(job_id: int, limit: int = 200):
    """Bounces detected against contacts in this batch job — joined with contact
    snapshot so the UI can show who bounced + why."""
    try:
        from backend.infra.db.client import get_pool
        import json as _json
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cc.contact_snapshot,
                       eb.reason       AS bounce_reason,
                       eb.smtp_status  AS bounce_status,
                       eb.detected_at  AS bounce_detected_at,
                       eb.hard         AS bounce_hard,
                       eb.email        AS bounce_email
                FROM email_bounces eb
                LEFT JOIN campaign_contacts cc
                       ON LOWER(cc.contact_snapshot->>'email') = eb.email
                WHERE eb.batch_job_id = $1
                ORDER BY eb.detected_at DESC
                LIMIT $2
                """,
                job_id, limit,
            )
        out = []
        for r in rows:
            snap = r["contact_snapshot"]
            if isinstance(snap, str):
                snap = _json.loads(snap)
            snap = snap or {}
            out.append({
                "name":         snap.get("name") or "Unknown",
                "email":        snap.get("email") or r["bounce_email"] or "",
                "title":        snap.get("title") or "",
                "company":      snap.get("company") or "",
                "reason":       r["bounce_reason"],
                "smtp_status":  r["bounce_status"],
                "hard":         r["bounce_hard"],
                "detected_at":  r["bounce_detected_at"].isoformat() if r["bounce_detected_at"] else None,
            })
        return {"bounces": out}
    except Exception as e:
        logger.error(f"Failed to fetch bounces for batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/batch-jobs")
async def list_batch_jobs(campaign_id: int, tier: Optional[str] = None):
    try:
        from backend.infra.db.campaign_repo import list_batch_send_jobs
        jobs = await list_batch_send_jobs(campaign_id, tier)
        return {"jobs": jobs}
    except Exception as e:
        logger.error(f"Failed to list batch jobs for campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.delete("/campaigns/{campaign_id}/batch-jobs/{job_id}")
async def delete_batch_job(campaign_id: int, job_id: int):
    try:
        from backend.infra.db.campaign_repo import cancel_or_delete_batch_send_job
        await cancel_or_delete_batch_send_job(job_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/batch-jobs/{job_id}/pause")
async def pause_batch_job(campaign_id: int, job_id: int):
    """
    Signal the runner to pause at the next chunk boundary.
    Emails in the current in-flight chunk are still sent before the runner stops.
    """
    try:
        from backend.infra.db.campaign_repo import pause_batch_send_job as db_pause
        updated = await db_pause(job_id)
        return {"success": updated}
    except Exception as e:
        logger.error(f"Failed to pause batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/batch-jobs/{job_id}/resume")
async def resume_batch_job(campaign_id: int, job_id: int):
    """
    Resume a paused job. Sets status back to running and spawns a fresh runner
    task which picks up the remaining pending contacts automatically.
    """
    try:
        from backend.infra.db.campaign_repo import resume_batch_send_job as db_resume
        from backend.pipeline import batch_sender
        updated = await db_resume(job_id)
        if updated:
            batch_sender.register(job_id)
            asyncio.create_task(
                batch_sender.run(job_id),
                name=f"batch-send-{job_id}",
            )
        return {"success": updated}
    except Exception as e:
        logger.error(f"Failed to resume batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/campaigns/{campaign_id}/batch-jobs/{job_id}/cancel")
async def cancel_batch_job(campaign_id: int, job_id: int):
    """
    Gracefully cancel a running or pending batch send job.
    The runner checks the cancelled flag at each chunk boundary and exits cleanly.
    Emails already sent are not recalled.
    """
    try:
        from backend.infra.db.campaign_repo import cancel_batch_send_job as db_cancel
        updated = await db_cancel(job_id)
        return {"success": updated}
    except Exception as e:
        logger.error(f"Failed to cancel batch job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/batch-jobs/{job_id}/events")
async def batch_job_events(campaign_id: int, job_id: int):
    """
    SSE stream of real-time progress events for a batch send job.

    Events:
      { type: 'start',    total, sent, failed }
      { type: 'progress', total, sent, failed, current }
      { type: 'complete', total, sent, failed, duration_seconds }
      { type: 'cancelled', total, sent, failed }
      { type: 'error',    error }

    If the job is already finished (completed/failed/cancelled), returns
    its last recorded state as a synthetic final event and closes.
    """
    import json as _json
    from backend.pipeline import batch_sender
    from backend.infra.db.campaign_repo import get_batch_send_job as db_get_job

    async def _stream():
        # If runner is already finished and queue is gone, synthesize a final event
        q = batch_sender.get_queue(job_id)
        if q is None:
            job = await db_get_job(job_id)
            if job:
                event_type = (
                    "complete"   if job["status"] == "completed"
                    else "cancelled" if job["status"] == "cancelled"
                    else "paused"    if job["status"] == "paused"
                    else "error"     if job["status"] == "failed"
                    else job["status"]
                )
                event = {
                    "type": event_type,
                    "sent": job.get("sent", 0),
                    "failed": job.get("failed", 0),
                    "total": job.get("total", 0),
                    "error": job.get("error"),
                }
                yield f"data: {_json.dumps(event)}\n\n"
            return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if event is batch_sender.SENTINEL:
                    break

                yield f"data: {_json.dumps(event)}\n\n"

                if event.get("type") in ("complete", "cancelled", "paused", "error"):
                    break
        finally:
            batch_sender.unregister(job_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
