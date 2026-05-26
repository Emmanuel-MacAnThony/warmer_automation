"""
Cadence (multi-touch sequence) endpoints.

A sequence = ordered steps (each a template + delay) for a campaign tier.
Create → launch (enroll pending contacts) → the cadence scheduler runs it.
"""
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sequences"])


class StepIn(BaseModel):
    delay_days: int = 0
    template_id: int


class CreateSequenceRequest(BaseModel):
    tier: str
    name: str = "Sequence"
    steps: list[StepIn]
    sender_emails: list[str] = []
    test_recipient: Optional[str] = None


@router.post("/campaigns/{campaign_id}/sequences")
async def create_sequence(campaign_id: int, req: CreateSequenceRequest):
    """Create a sequence with its steps (each step references an existing template)."""
    if req.tier not in ("tier_1", "tier_2", "tier_3"):
        return JSONResponse(status_code=400, content={"error": f"Invalid tier: {req.tier}"})
    if not req.steps:
        return JSONResponse(status_code=400, content={"error": "A sequence needs at least one step"})
    try:
        from backend.infra.db import sequence_repo as seq_repo
        seq_id = await seq_repo.create_sequence(
            campaign_id, req.tier, req.name, req.sender_emails, req.test_recipient,
        )
        for i, step in enumerate(req.steps, start=1):
            # Step 1 always fires immediately; later steps wait delay_days.
            delay = 0 if i == 1 else max(0, step.delay_days)
            await seq_repo.add_sequence_step(seq_id, i, delay, step.template_id)
        return {"id": seq_id}
    except Exception as e:
        logger.error(f"Failed to create sequence for campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/sequences/{sequence_id}/launch")
async def launch_sequence(sequence_id: int, scope: str = "everyone"):
    """
    Enroll the tier's contacts and set the sequence active.
    scope='everyone' (default) enrolls all tier contacts; 'unsent' only those not yet contacted.
    """
    scope = scope if scope in ("everyone", "unsent") else "everyone"
    try:
        from backend.infra.db import sequence_repo as seq_repo
        seq = await seq_repo.get_sequence(sequence_id)
        if not seq:
            return JSONResponse(status_code=404, content={"error": "Sequence not found"})
        enrolled = await seq_repo.enroll_tier(sequence_id, seq["campaign_id"], seq["tier"], scope)
        await seq_repo.set_sequence_status(sequence_id, "active")
        return {"enrolled": enrolled}
    except Exception as e:
        logger.error(f"Failed to launch sequence {sequence_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/sequences/{sequence_id}/pause")
async def pause_sequence(sequence_id: int):
    try:
        from backend.infra.db import sequence_repo as seq_repo
        await seq_repo.set_sequence_status(sequence_id, "paused")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to pause sequence {sequence_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/sequences/{sequence_id}/resume")
async def resume_sequence(sequence_id: int):
    try:
        from backend.infra.db import sequence_repo as seq_repo
        await seq_repo.set_sequence_status(sequence_id, "active")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to resume sequence {sequence_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/sequences")
async def list_all_sequences(base_id: str, table_id: str):
    """All sequences for a base/table with live stats — the monitoring tab."""
    try:
        from backend.infra.db import sequence_repo as seq_repo
        seqs = await seq_repo.list_all_sequences_for_table(base_id, table_id)
        for s in seqs:
            s["stats"] = await seq_repo.get_sequence_stats(s["id"])
            s["step_previews"] = await seq_repo.get_sequence_steps_detail(s["id"])
        return {"sequences": seqs}
    except Exception as e:
        logger.error(f"Failed to list sequences for {base_id}/{table_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/sequences/{sequence_id}/replies")
async def get_sequence_replies(sequence_id: int):
    """Contacts who replied to this sequence (hot leads)."""
    try:
        from backend.infra.db import sequence_repo as seq_repo
        return {"replies": await seq_repo.get_replied_contacts(sequence_id)}
    except Exception as e:
        logger.error(f"Failed to get replies for sequence {sequence_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.delete("/sequences/{sequence_id}")
async def delete_sequence(sequence_id: int):
    """Delete a sequence (and its steps + enrollments)."""
    try:
        from backend.infra.db import sequence_repo as seq_repo
        ok = await seq_repo.delete_sequence(sequence_id)
        return {"success": ok}
    except Exception as e:
        logger.error(f"Failed to delete sequence {sequence_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/sequences/{sequence_id}")
async def get_sequence(sequence_id: int):
    """Sequence + steps + live enrollment stats (powers the monitoring view)."""
    try:
        from backend.infra.db import sequence_repo as seq_repo
        seq = await seq_repo.get_sequence(sequence_id)
        if not seq:
            return JSONResponse(status_code=404, content={"error": "Sequence not found"})
        seq["steps"] = await seq_repo.get_sequence_steps(sequence_id)
        seq["stats"] = await seq_repo.get_sequence_stats(sequence_id)
        return seq
    except Exception as e:
        logger.error(f"Failed to get sequence {sequence_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/campaigns/{campaign_id}/sequences")
async def list_sequences(campaign_id: int, tier: Optional[str] = None):
    """List sequences for a campaign, each with live stats — the Sequences tab."""
    try:
        from backend.infra.db import sequence_repo as seq_repo
        seqs = await seq_repo.list_sequences(campaign_id, tier)
        for s in seqs:
            s["stats"] = await seq_repo.get_sequence_stats(s["id"])
        return {"sequences": seqs}
    except Exception as e:
        logger.error(f"Failed to list sequences for campaign {campaign_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
