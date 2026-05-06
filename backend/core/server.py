"""
FastAPI Server - Production-ready backend for Chrome extension
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from backend.core.agent import get_agent
from backend.agents.hitl.core import hitl_core
from backend.config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("backend.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Server lifecycle handler.
    Startup:
      - Reset stale batch state (running → pending). Jobs stay running so
        ExecutorManager can auto-resume them — no operator action needed after a crash.
      - (Phase 3) ExecutorManager initialised here, picks up running jobs automatically.
    Shutdown:
      - (Phase 3) ExecutorManager graceful cancel of active tasks.
    """
    # --- startup ---
    try:
        from backend.db.client import reset_stale_batches

        count = await reset_stale_batches()
        if count:
            logger.info(
                f"Startup: {count} stale batches reset to pending, jobs auto-resuming"
            )
    except Exception as e:
        logger.warning(f"Startup recovery failed (non-fatal): {e}")

    try:
        from backend.enrichment.executor_manager import get_manager

        resumed = await get_manager().auto_resume()
        if resumed:
            logger.info(f"Startup: ExecutorManager resumed {resumed} job(s)")
    except Exception as e:
        logger.warning(f"ExecutorManager auto-resume failed (non-fatal): {e}")

    yield  # server is running

    # --- shutdown ---
    try:
        from backend.enrichment.executor_manager import get_manager

        await get_manager().shutdown()
    except Exception as e:
        logger.warning(f"ExecutorManager shutdown error: {e}")


# Initialize FastAPI
app = FastAPI(
    title="LinkedIn Enrichment API",
    description="AI-powered LinkedIn profile enrichment for Airtable CRM",
    version="1.0.0",
    lifespan=lifespan,
)

# In-memory store for interrupted workflows (for HITL)
# Maps user_id -> {thread_id, approval_data, timestamp}
_interrupted_workflows: Dict[str, Dict[str, Any]] = {}

# CORS configuration for Chrome extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Middleware to handle Chrome's Private Network Access
@app.middleware("http")
async def add_private_network_access_headers(request: Request, call_next):
    # Handle preflight requests for Private Network Access
    if request.method == "OPTIONS":
        response = JSONResponse(content={}, status_code=200)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    # Process normal requests
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# Request/Response models
class AirtableContext(BaseModel):
    """Context from Chrome extension"""

    url: str
    baseId: Optional[str] = None
    tableName: Optional[str] = None
    viewId: Optional[str] = None
    recordId: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat message from user"""

    message: str = Field(..., min_length=1, description="User message")
    context: Optional[AirtableContext] = None
    history: Optional[List[Dict[str, str]]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Chat response"""

    response: str
    success: bool = True
    error: Optional[str] = None
    show_panel: Optional[Dict[str, Any]] = None
    approval_needed: Optional[bool] = None
    approval_data: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


class ScrapeRequest(BaseModel):
    """Scrape profile request"""

    context: AirtableContext


class BatchRequest(BaseModel):
    """Batch enrichment request"""

    limit: Optional[int] = None


class HITLResponse(BaseModel):
    """HITL panel response from user"""

    agent_id: str
    response: Dict[str, Any]


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Internal server error: {str(exc)}"},
    )


@app.get("/canonical-schema")
async def get_canonical_schema():
    """Return the canonical LinkedIn profile schema for field mapping UI."""
    import json

    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "schema",
        "canonical_profile.json",
    )
    with open(schema_path, "r") as f:
        return json.load(f)


@app.get("/schema")
async def get_schema(base_id: str, table_id: str):
    """
    Return field definitions for a given Airtable base + table.
    Called by the extension Jobs tab to populate the schema preview.
    """
    try:
        from backend.clients.airtable_client import AirtableClient

        client = AirtableClient()
        schema = client.get_table_schema(base_id, table_id)
        return schema
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Schema fetch failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Field Mapping endpoints
# ---------------------------------------------------------------------------


class SaveMappingRequest(BaseModel):
    base_id: str
    table_id: str
    name: str
    mappings: Dict[str, Any]  # { airtable_field_id: canonical_key }


@app.post("/mappings")
async def save_mapping(request: SaveMappingRequest):
    """Save a new named field mapping for a table."""
    from backend.db.client import save_field_mapping

    try:
        mapping_id = await save_field_mapping(
            request.base_id, request.table_id, request.name, request.mappings
        )
        return {"success": True, "id": mapping_id}
    except Exception as e:
        logger.error(f"Failed to save mapping: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/mappings")
async def list_mappings(base_id: str, table_id: str):
    """List all saved mappings for a table."""
    from backend.db.client import get_field_mappings

    try:
        results = await get_field_mappings(base_id, table_id)
        return {"mappings": results}
    except Exception as e:
        logger.error(f"Failed to list mappings: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/mappings/{mapping_id}")
async def get_mapping(mapping_id: int):
    """Fetch a single mapping by id."""
    from backend.db.client import get_field_mapping_by_id

    try:
        result = await get_field_mapping_by_id(mapping_id)
        if result is None:
            return JSONResponse(status_code=404, content={"error": "Mapping not found"})
        return result
    except Exception as e:
        logger.error(f"Failed to get mapping {mapping_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/mappings/{mapping_id}")
async def delete_mapping(mapping_id: int):
    """Delete a mapping by id."""
    from backend.db.client import delete_field_mapping

    try:
        deleted = await delete_field_mapping(mapping_id)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": "Mapping not found"})
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete mapping {mapping_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Jobs endpoints
# ---------------------------------------------------------------------------


class JobPreflightRequest(BaseModel):
    base_id: str
    table_id: str
    view_id: str
    batch_size: int = 100


class JobCreateRequest(BaseModel):
    base_id: str
    table_id: str
    view_id: str
    mapping_id: int
    batch_size: int = 100


@app.post("/jobs/preflight")
async def jobs_preflight(request: JobPreflightRequest):
    """
    Fetch record count for a view and compute batch breakdown.
    Returns preview info for the confirmation step — does NOT create anything in DB.
    """
    try:
        from backend.clients.airtable_client import AirtableClient
        import math

        client = AirtableClient()
        record_ids = client.get_view_record_ids(
            request.base_id, request.table_id, request.view_id
        )
        record_count = len(record_ids)
        batch_count = (
            math.ceil(record_count / request.batch_size) if record_count > 0 else 0
        )
        return {
            "record_count": record_count,
            "batch_count": batch_count,
            "batch_size": request.batch_size,
        }
    except Exception as e:
        logger.error(f"Preflight failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/jobs/create")
async def jobs_create(request: JobCreateRequest):
    """
    Fetch all record IDs from the view, create enrichment_job + enrichment_batches in DB.
    Returns the created job with its batches.
    """
    try:
        import math
        from backend.clients.airtable_client import AirtableClient
        from backend.db.client import (
            get_field_mapping_by_id,
            get_active_job,
            create_job,
            create_batches,
            get_batches,
        )

        # Check for existing active job
        active = await get_active_job(request.base_id, request.table_id)
        if active:
            return JSONResponse(
                status_code=409,
                content={
                    "error": f"A job is already active for this table (id={active['id']}, status={active['status']})"
                },
            )

        # Load mapping snapshot
        mapping = await get_field_mapping_by_id(request.mapping_id)
        if not mapping:
            return JSONResponse(status_code=404, content={"error": "Mapping not found"})

        # Fetch all record IDs from view
        client = AirtableClient()
        record_ids = client.get_view_record_ids(
            request.base_id, request.table_id, request.view_id
        )
        record_count = len(record_ids)
        if record_count == 0:
            return JSONResponse(
                status_code=400, content={"error": "No records found in this view"}
            )

        # Chunk record IDs into batches
        batch_size = request.batch_size
        chunks = [
            record_ids[i : i + batch_size] for i in range(0, record_count, batch_size)
        ]
        total_batches = len(chunks)

        # Persist job + batches
        job_id = await create_job(
            base_id=request.base_id,
            table_id=request.table_id,
            field_mapping=mapping["mappings"],
            batch_size=batch_size,
            total_records=record_count,
            total_batches=total_batches,
        )
        await create_batches(job_id, chunks)
        batches = await get_batches(job_id)

        logger.info(
            f"Created job {job_id}: {record_count} records, {total_batches} batches"
        )
        return {
            "job_id": job_id,
            "record_count": record_count,
            "total_batches": total_batches,
            "batch_size": batch_size,
            "batches": batches,
        }
    except Exception as e:
        logger.error(f"Job create failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/jobs")
async def list_jobs(base_id: str, table_id: str):
    """List recent jobs for a table."""
    from backend.db.client import get_jobs

    try:
        jobs = await get_jobs(base_id, table_id)
        return {"jobs": jobs}
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/jobs/{job_id}/batches")
async def list_job_batches(job_id: int):
    """List all batches for a job. Lazily backfills stats from CSV for pre-stat-tracking batches."""
    from backend.db.client import get_batches, update_batch
    from backend.enrichment.batch_executor import _csv_path, _read_processed_stats

    try:
        batches = await get_batches(job_id)

        # Backfill stats from CSV for any batch with a mismatch between processed and stats.
        # If hits + misses + failed < processed, the batch has legacy records without stats.
        for b in batches:
            processed = b.get("processed") or 0
            hits = b.get("hits") or 0
            misses = b.get("misses") or 0
            failed = b.get("failed") or 0

            if processed > 0 and (hits + misses + failed) < processed:
                csv = _csv_path(job_id, b["id"])
                _, csv_hits, csv_misses, csv_failed = _read_processed_stats(csv)
                if csv_hits or csv_misses or csv_failed:
                    await update_batch(
                        b["id"], hits=csv_hits, misses=csv_misses, failed=csv_failed
                    )
                    b["hits"] = csv_hits
                    b["misses"] = csv_misses
                    b["failed"] = csv_failed

        return {"batches": batches}
    except Exception as e:
        logger.error(f"Failed to list batches for job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/jobs/{job_id}/run")
async def run_job(job_id: int):
    """
    Start or resume a job. Sets job status to 'running' and submits it to the
    ExecutorManager (wired in Phase 3). Returns 409 if already running.
    """
    from backend.db.client import get_job, update_job_status

    try:
        job = await get_job(job_id)
        if not job:
            return JSONResponse(
                status_code=404, content={"error": f"Job {job_id} not found"}
            )

        if job["status"] == "running":
            return JSONResponse(
                status_code=409, content={"error": "Job is already running"}
            )

        if job["status"] == "completed":
            return JSONResponse(
                status_code=409, content={"error": "Job is already completed"}
            )

        await update_job_status(job_id, "running")

        from backend.enrichment.executor_manager import get_manager

        await get_manager().submit(job_id)

        logger.info(f"Job {job_id}: submitted to ExecutorManager")
        return {"success": True, "job_id": job_id, "status": "running"}

    except Exception as e:
        logger.error(f"Failed to run job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.patch("/jobs/{job_id}/status")
async def update_job_status_endpoint(job_id: int, body: Dict[str, Any]):
    """
    Update job status. Used to pause a running job.
    Executor checks this between batches and exits cleanly on 'paused'.
    """
    from backend.db.client import get_job, update_job_status

    try:
        status = body.get("status")
        if status not in ("paused", "pending", "cancelled"):
            return JSONResponse(
                status_code=400, content={"error": f"Invalid status '{status}'"}
            )

        job = await get_job(job_id)
        if not job:
            return JSONResponse(
                status_code=404, content={"error": f"Job {job_id} not found"}
            )

        await update_job_status(job_id, status)
        logger.info(f"Job {job_id} status updated to {status}")
        return {"success": True, "job_id": job_id, "status": status}

    except Exception as e:
        logger.error(f"Failed to update job {job_id} status: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.patch("/jobs/{job_id}/batches/{batch_id}/status")
async def update_batch_status(job_id: int, batch_id: int, body: Dict[str, Any]):
    """Update a batch status (pending/running/paused/completed/failed)."""
    from backend.db.client import update_batch

    try:
        status = body.get("status")
        if status not in ("pending", "running", "paused", "completed", "failed"):
            return JSONResponse(status_code=400, content={"error": "Invalid status"})
        await update_batch(batch_id, status=status)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to update batch {batch_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/jobs/{job_id}/reset-incomplete-batches")
async def reset_incomplete_batches(job_id: int):
    """
    Reset batches that are marked completed/paused but haven't finished processing all records.
    Used to recover from the old pause bug that incorrectly marked batches as completed.
    """
    from backend.db.client import get_pool

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Reset batches where status is completed/paused but processed < total
            result = await conn.execute(
                """
                UPDATE enrichment_batches
                SET status = 'pending', completed_at = NULL
                WHERE job_id = $1
                  AND status IN ('completed', 'paused')
                  AND processed < total
                """,
                job_id,
            )

        count = int(result.split()[-1])
        logger.info(f"Job {job_id}: reset {count} incomplete batch(es) to pending")
        return {"success": True, "reset_count": count}

    except Exception as e:
        logger.error(f"Failed to reset incomplete batches for job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Validate configuration
        Config.validate()

        return {
            "status": "healthy",
            "version": "1.0.0",
            "services": {
                "openai": bool(Config.OPENAI_API_KEY),
                "airtable": bool(Config.AIRTABLE_API_KEY),
                "apify": bool(Config.APIFY_API_TOKEN),
                "serper": bool(Config.SERPAPI_API_KEY),
            },
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint for natural language interaction

    The agent will:
    - Understand user intent
    - Use appropriate tools
    - Return conversational responses
    """
    try:
        logger.info(f"Chat request: {request.message[:100]}...")

        # Build context
        from backend.agents.react_agent import get_react_agent
        from backend.agents.context import (
            build_thread_config,
            build_message_history,
            build_airtable_context,
        )

        thread_id, config = build_thread_config(prefix="chat")
        messages = build_message_history(request.history, request.message)
        airtable_context = build_airtable_context(request.context)

        # Run ReAct agent
        agent = get_react_agent()
        result = await agent.run(
            messages=messages,
            context=airtable_context,
            config=config,
            user_id=airtable_context.get("record_id"),
        )

        # Check if guardrails blocked the request
        if result.get("blocked"):
            logger.warning(f"Request blocked by guardrails: {result.get('response')}")
            return ChatResponse(
                response=result.get("response"),
                success=False,
                error="Request blocked by security guardrails",
            )

        # Check if workflow was interrupted for HITL
        from backend.agents.context import (
            detect_hitl_interrupt,
            store_interrupted_workflow,
        )

        interrupt_data = detect_hitl_interrupt(result, airtable_context)
        if interrupt_data:
            # Store workflow for resumption
            store_interrupted_workflow(
                _interrupted_workflows, interrupt_data["workflow_data"]
            )

            # Return HITL response
            return ChatResponse(**interrupt_data["response_data"])

        # Check for errors
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Agent error: {error_msg}")
            return ChatResponse(
                response=result.get(
                    "response", "I encountered an error processing your request."
                ),
                success=False,
                error=error_msg,
            )

        # Success - return agent response
        response_text = result.get("response", "I completed your request.")

        logger.info(
            f"Chat response: {response_text[:100] if len(response_text) > 100 else response_text}..."
        )

        return ChatResponse(response=response_text, success=True)

    except Exception as e:
        # Log full error internally (for debugging)
        logger.error(f"[INTERNAL] Chat error: {e}", exc_info=True)

        # Return sanitized user-friendly message (NO internal details)
        return ChatResponse(
            response="I encountered an error processing your request. Please try again or contact support if this continues.",
            success=False,
            error="internal_error",  # Generic error code, not the actual error
        )


class ApprovalRequest(BaseModel):
    """Request to approve/reject HITL workflow"""

    record_id: str = Field(description="Record ID that initiated the workflow")
    approved: bool = Field(description="Whether user approved the changes")
    modified_fields: Optional[Dict[str, Any]] = Field(
        default=None, description="User-modified fields (if they changed anything)"
    )


@app.post("/resume")
async def resume_workflow(request: ApprovalRequest):
    """
    Resume an interrupted workflow after user approval/rejection.

    This endpoint handles HITL (Human-in-the-Loop) workflow resumption:
    1. Retrieves the paused workflow by record_id
    2. Updates workflow state with user's approval decision
    3. Resumes workflow execution
    4. Returns final result
    """
    try:
        user_id = request.record_id

        logger.info(f"RESUME_REQUEST: Looking for workflow for user_id={user_id}")
        logger.info(
            f"RESUME_REQUEST: Available workflows: {list(_interrupted_workflows.keys())}"
        )

        # Get interrupted workflow
        if user_id not in _interrupted_workflows:
            logger.error(f"RESUME_ERROR: No interrupted workflow found for {user_id}")
            logger.error(
                f"RESUME_ERROR: Available workflows are: {list(_interrupted_workflows.keys())}"
            )
            return ChatResponse(
                response="No pending approval found. The workflow may have expired or already been completed.",
                success=False,
                error="no_pending_workflow",
            )

        workflow_data = _interrupted_workflows[user_id]
        workflow_thread_id = workflow_data["thread_id"]

        logger.info(
            f"RESUME: Resuming workflow {workflow_thread_id} - approved={request.approved}"
        )

        # Get the enrichment workflow instance
        from backend.agents.workflows.enrichment import get_enrichment_workflow

        workflow = get_enrichment_workflow()
        config = {"configurable": {"thread_id": workflow_thread_id}}

        # Get current state
        current_state = workflow.graph.get_state(config)

        # Update state with approval decision
        state_update = {
            "hitl_approved": request.approved,
        }

        # If user modified fields, use those instead
        if request.modified_fields:
            state_update["validated_fields"] = request.modified_fields

        workflow.graph.update_state(config, state_update)

        # Resume workflow (pass None, not new input!)
        result = await workflow.graph.ainvoke(None, config=config)

        # Get final state to extract report (generated after update)
        final_state = workflow.graph.get_state(config)
        final_values = final_state.values if final_state else {}

        # DEBUG: Check what's in final state
        logger.info(f"DEBUG RESUME: final_state exists = {final_state is not None}")
        logger.info(
            f"DEBUG RESUME: final_state.next = {final_state.next if final_state else 'N/A'}"
        )
        logger.info(
            f"DEBUG RESUME: final_values keys = {list(final_values.keys()) if final_values else 'None'}"
        )
        logger.info(
            f"DEBUG RESUME: workflow_status in result = {result.get('workflow_status')}"
        )
        logger.info(
            f"DEBUG RESUME: similar_profiles_report in final_values = {'similar_profiles_report' in final_values}"
        )
        logger.info(
            f"DEBUG RESUME: similar_profiles_report value = {final_values.get('similar_profiles_report')}"
        )

        # Clean up stored workflow
        del _interrupted_workflows[user_id]

        # Return result
        if result.get("workflow_status") == "completed":
            validated_fields = final_values.get(
                "validated_fields", result.get("validated_fields", {})
            )
            linkedin_data = final_values.get(
                "linkedin_data", result.get("linkedin_data", {})
            )
            similar_report = final_values.get("similar_profiles_report")

            logger.info(
                f"RESUME_SUCCESS: Workflow completed, updated {len(validated_fields)} fields"
            )
            if similar_report:
                logger.info(
                    f"RESUME_SUCCESS: Report available with {similar_report.get('count', 0)} profiles"
                )
            else:
                logger.warning(
                    f"RESUME_WARNING: No similar_profiles_report in final state"
                )

            # Build success message
            success_msg = f"✅ Successfully updated {len(validated_fields)} fields for {linkedin_data.get('full_name', 'contact')}!"

            return ChatResponse(
                response=success_msg,
                success=True,
                similar_profiles_report=similar_report,  # Include report for frontend
            )
        else:
            # Workflow cancelled or failed
            error_msg = result.get("error_message", "Workflow was cancelled")
            logger.info(f"RESUME_CANCELLED: {error_msg}")

            return ChatResponse(
                response="Enrichment cancelled - no changes were made.", success=True
            )

    except Exception as e:
        logger.error(f"[INTERNAL] Resume error: {e}", exc_info=True)
        return ChatResponse(
            response="I encountered an error processing your approval. Please try again.",
            success=False,
            error="internal_error",
        )


@app.post("/agent/invoke")
async def invoke_agent(request: ChatRequest):
    """
    Unified agent entry point - the orchestrator decides what to do.

    This is the main endpoint that uses the multi-agent architecture:
    1. Orchestrator classifies intent (enrichment, search, outreach, etc.)
    2. Routes to appropriate workflow (EnrichmentWorkflow, SearchWorkflow, etc.)
    3. Workflow may interrupt for HITL approval
    4. Returns results or HITL approval UI

    Args:
        request: Message and context from frontend

    Returns:
        - If workflow completes: success response
        - If workflow interrupts: HITL approval UI with thread_id
    """
    try:
        import uuid
        from backend.agents.orchestrator import get_orchestrator

        logger.info(f"Agent invoke request: {request.message[:100]}...")

        # Generate thread ID for this workflow
        thread_id = f"agent-{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"=== AGENT INVOKE: Created thread_id: {thread_id} ===")

        # Build orchestrator state
        airtable_context = {}
        if request.context:
            airtable_context = {
                "record_id": request.context.recordId,
                "base_id": request.context.baseId,
                "table_name": request.context.tableName,
                "linkedin_url": None,  # Orchestrator will extract from message or record
                "fields": [],  # Will be fetched by workflow
            }

        orchestrator_state = {
            "messages": [HumanMessage(content=request.message)],
            "airtable_context": airtable_context,
            "status": "pending",
            "needs_approval": False,
        }

        # Run orchestrator - it will classify intent and route
        orchestrator = get_orchestrator()
        result = await orchestrator.run(orchestrator_state, config=config)

        # Check if workflow was interrupted for HITL
        if result.get("needs_approval"):
            logger.info(f"Workflow interrupted for HITL - thread_id: {thread_id}")
            approval_data = result.get("approval_data", {})

            return {
                "needs_approval": True,
                "thread_id": thread_id,
                "show_panel": {"panel_type": "inline_approval", "data": approval_data},
            }

        # Check for errors
        if result.get("status") == "failed":
            error_msg = result.get("error_message", "Unknown error")
            logger.error(f"Workflow failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        # Workflow completed successfully
        workflow_result = result.get("workflow_result", {})
        intent = result.get("intent", "unknown")

        logger.info(f"Workflow completed successfully - intent: {intent}")

        return {
            "success": True,
            "message": f"Successfully completed {intent} workflow",
            "result": workflow_result,
            "intent": intent,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log detailed error for debugging
        logger.error(f"Agent invoke error: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback available in logs")

        # Return user-friendly error message
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again or contact support if the issue persists.",
        )


@app.post("/scrape")
async def scrape_profile(request: ScrapeRequest):
    """
    Direct enrichment endpoint using LangGraph interrupt for HITL.

    Flow:
    1. Start enrichment workflow with thread_id
    2. If interrupted (HITL needed), return approval UI data with thread_id
    3. Frontend shows approval panel
    4. User approves via /hitl/response with thread_id
    5. Workflow resumes and completes
    """
    try:
        if not request.context.recordId:
            raise HTTPException(
                status_code=400,
                detail="No record selected. Please open a record first.",
            )

        import uuid
        from backend.agents.workflows.enrichment import get_enrichment_workflow
        from backend.clients.airtable_client import AirtableClient
        from backend.agents.tools.langchain_tools import get_airtable_schema

        record_id = request.context.recordId
        base_id = request.context.baseId or Config.AIRTABLE_BASE_ID
        table_name = request.context.tableName or Config.AIRTABLE_TABLE_NAME

        logger.info(f"Starting enrichment workflow for record: {record_id}")

        # Create unique thread_id for this enrichment instance
        thread_id = f"enrichment-{record_id}-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}

        # Get record data
        airtable = AirtableClient()
        record = airtable.fetch_record_by_id(record_id)

        if not record:
            raise HTTPException(status_code=404, detail=f"Record {record_id} not found")

        fields = record.get("fields", {})
        linkedin_url = fields.get(
            Config.AIRTABLE_FIELDS.get("linkedin_url", "LinkedIn URL")
        )

        if not linkedin_url:
            raise HTTPException(
                status_code=400, detail="No LinkedIn URL found in record"
            )

        # Get table schema
        schema_result = get_airtable_schema(base_id, table_name)
        if not schema_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to fetch table schema")

        # Build initial state
        initial_state = {
            "linkedin_url": linkedin_url,
            "airtable_record_id": record_id,
            "airtable_fields": schema_result["fields"],
            "workflow_status": "pending",
        }

        # Start workflow (will pause at interrupt)
        workflow = get_enrichment_workflow()
        result = await workflow.graph.ainvoke(initial_state, config=config)

        # Check if workflow was interrupted (HITL)
        if result is None:
            # Get current state to extract HITL data
            state = workflow.graph.get_state(config)
            hitl_data = state.values.get("hitl_data", {})

            logger.info(f"Workflow interrupted for approval - thread_id: {thread_id}")

            # Return approval UI data to frontend
            return {
                "success": True,
                "needs_approval": True,
                "thread_id": thread_id,
                "show_panel": {
                    "panel_type": "inline_approval",
                    "agent_id": thread_id,
                    "data": hitl_data,
                },
            }

        # Workflow completed without interrupt
        logger.info(f"Enrichment completed: {result.get('workflow_status')}")

        return {
            "success": result.get("workflow_status") == "completed",
            "response": (
                result.get("error_message")
                if result.get("workflow_status") == "failed"
                else "Enrichment completed"
            ),
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log full error internally
        logger.error(f"[INTERNAL] Scrape error: {e}", exc_info=True)
        # Return sanitized error
        raise HTTPException(
            status_code=500,
            detail="Enrichment failed. Please try again or contact support.",
        )


@app.post("/batch-enrich")
async def batch_enrich(request: BatchRequest):
    """
    Batch enrichment endpoint
    """
    try:
        logger.info(f"Starting batch enrichment (limit: {request.limit})")

        from backend.agents.tools.langchain_tools import batch_enrich_airtable_tool

        result = batch_enrich_airtable_tool.invoke({"limit": request.limit})

        if result.get("success"):
            return {
                "success": True,
                "response": result.get("message"),
                "stats": result.get("stats"),
            }
        else:
            return {
                "success": False,
                "response": f"Batch enrichment failed: {result.get('error')}",
                "error": result.get("error"),
            }

    except Exception as e:
        # Log full error internally
        logger.error(f"[INTERNAL] Batch enrichment error: {e}", exc_info=True)
        # Return sanitized error
        raise HTTPException(
            status_code=500,
            detail="Batch enrichment failed. Please try again or contact support.",
        )


@app.post("/hitl/response")
async def hitl_response(request: HITLResponse):
    """
    Resume workflow after HITL approval using LangGraph native interrupt.

    Receives:
    - agent_id (thread_id): Unique workflow instance identifier
    - response: User's approval/rejection with optional edits

    Resumes the interrupted workflow and returns final result.
    """
    try:
        thread_id = request.agent_id
        user_response = request.response

        logger.info(f"=== HITL RESPONSE: Received thread_id: {thread_id} ===")
        logger.info(f"User response status: {user_response.get('status')}")

        # Resume workflow with thread_id
        from backend.agents.workflows.enrichment import get_enrichment_workflow

        config = {"configurable": {"thread_id": thread_id}}
        logger.info(f"Looking up state with config: {config}")

        # Resume from checkpoint
        workflow = get_enrichment_workflow()
        logger.info(f"Got workflow instance: {id(workflow)}")
        logger.info(f"Workflow checkpointer type: {type(workflow.graph.checkpointer)}")

        # Get current state from checkpointer to preserve existing data
        current_state = workflow.graph.get_state(config)
        logger.info(f"get_state returned: {current_state}")

        if not current_state or not current_state.values:
            logger.error(f"No saved state found for thread_id: {thread_id}")
            raise HTTPException(
                status_code=404, detail="Workflow session not found. Please start over."
            )

        logger.info(f"Retrieved state for thread {thread_id}")
        logger.info(f"  Next node: {current_state.next}")
        logger.info(f"  State keys: {list(current_state.values.keys())}")
        logger.info(f"  Has linkedin_url: {'linkedin_url' in current_state.values}")

        # Update the state with processed user response fields
        # This merges into existing state without replacing linkedin_url, etc.
        approved = user_response.get("status") == "approved"
        edited_fields = user_response.get("edited_fields")

        state_update = {
            "hitl_approved": approved,
            "validated_fields": (
                edited_fields
                if edited_fields
                else current_state.values.get("validated_fields")
            ),
        }

        logger.info(f"Updating state with: {list(state_update.keys())}")
        workflow.graph.update_state(config, state_update)

        # Resume execution - invoke with None to continue from checkpoint
        logger.info("Resuming workflow execution")
        result = await workflow.graph.ainvoke(None, config=config)

        # Check result
        if result and result.get("workflow_status") == "completed":
            logger.info(f"Workflow {thread_id} completed successfully")

            # Get stats for completion message
            validated_fields = result.get("validated_fields", {})
            field_count = len(validated_fields)
            record_name = result.get("linkedin_data", {}).get("full_name", "Contact")
            similar_profiles_report = result.get("similar_profiles_report")

            response_data = {
                "success": True,
                "message": f"✅ Successfully updated {field_count} fields for {record_name}",
                "stats": {
                    "fields_updated": field_count,
                    "record_name": record_name,
                    "fields": list(validated_fields.keys()),
                },
                "toast": {
                    "type": "success",
                    "message": f"Enrichment complete! Updated {field_count} fields.",
                    "duration": 5000,
                },
            }

            # Add similar profiles report if available
            if similar_profiles_report and similar_profiles_report.get("available"):
                response_data["similar_profiles"] = {
                    "count": similar_profiles_report.get("count", 0),
                    "download_url": f"/download/report/{os.path.basename(similar_profiles_report.get('file_path', ''))}",
                    "filename": similar_profiles_report.get("filename"),
                }
                # Update toast to mention the report
                response_data["toast"][
                    "message"
                ] = f"Enrichment complete! Updated {field_count} fields. {similar_profiles_report.get('count', 0)} similar profiles found."

            return response_data
        elif result and result.get("workflow_status") == "failed":
            logger.error(f"Workflow {thread_id} failed: {result.get('error_message')}")
            return {
                "success": False,
                "message": f"❌ Enrichment failed: {result.get('error_message')}",
                "toast": {
                    "type": "error",
                    "message": "Enrichment failed. Please try again.",
                    "duration": 5000,
                },
            }
        else:
            # User rejected
            logger.info(f"User rejected workflow {thread_id}")
            return {
                "success": False,
                "message": "Enrichment cancelled by user",
                "toast": {
                    "type": "info",
                    "message": "Enrichment cancelled",
                    "duration": 3000,
                },
            }

    except Exception as e:
        # Log detailed error for debugging
        logger.error(f"HITL response error: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")

        # Return user-friendly error message
        raise HTTPException(
            status_code=500,
            detail="Failed to process approval. Please try again or contact support.",
        )


@app.get("/download/report/{filename}")
async def download_report(filename: str, background_tasks: BackgroundTasks):
    """
    Download a generated report file (e.g., similar profiles report)
    Automatically deletes the file after download
    """
    try:
        import os
        import tempfile
        from fastapi.responses import FileResponse

        # Security: only allow specific filename patterns
        if not filename.startswith("similar_profiles_") or not filename.endswith(
            ".txt"
        ):
            raise HTTPException(status_code=400, detail="Invalid filename")

        # Get file from temp directory
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, filename)

        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Report not found")

        # Delete file after response is sent
        def cleanup_file():
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted report file: {filename}")
            except Exception as e:
                logger.warning(f"Could not delete report file {filename}: {e}")

        background_tasks.add_task(cleanup_file)

        return FileResponse(path=file_path, filename=filename, media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        # Log full error internally
        logger.error(f"[INTERNAL] Download error: {e}", exc_info=True)
        # Return sanitized error
        raise HTTPException(
            status_code=500,
            detail="File download failed. Please try again or contact support.",
        )


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("LinkedIn Enrichment API - Starting Server")
    print("=" * 60)
    print(f"Backend running at: http://localhost:8000")
    print(f"API docs: http://localhost:8000/docs")
    print(f"Health check: http://localhost:8000/health")
    print("=" * 60)

    uvicorn.run(
        "backend.core.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disabled reload to prevent constant reloading
        log_level="info",
    )
