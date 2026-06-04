"""
FastAPI application entry point.

Responsibilities:
  - App creation, CORS, and middleware
  - Startup / shutdown lifespan hook (DB recovery + ExecutorManager resume)
  - Global exception handler
  - Router mounting

All route handlers live in backend/api/*.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import Config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("backend.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

async def _run_migrations_in_background() -> None:
    """
    Idempotent schema migration runner spawned as a background task in lifespan.

    Doing this in the background instead of awaiting lets uvicorn bind the
    port and start accepting requests immediately — important on Render,
    where the port-scan timeout (~90s) fires from process start, not from
    lifespan completion. Cold-start asyncpg + DDL roundtrips can otherwise
    push total startup past that window even when the migrations themselves
    are no-ops on an existing schema.

    On Render the pre-deploy hook already applies the migrations before the
    web service boots, so this background run is normally an all-no-op
    safety net. Locally it's the only thing that applies new schema changes
    without remembering to run `python -m backend.infra.db.init_db`.
    """
    try:
        from backend.infra.db.init_db import apply_migrations
        await apply_migrations()
        logger.info("Startup: schema migrations applied")
    except Exception as e:
        logger.error(f"Startup: schema migrations failed (continuing): {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # --- startup ---

    # Kick off migrations without blocking — see _run_migrations_in_background.
    asyncio.create_task(_run_migrations_in_background())

    try:
        from backend.infra.db.job_repo import reset_stale_batches, reset_stale_pipeline_runs, reset_stale_dedup_runs

        count = await reset_stale_batches()
        if count:
            logger.info(f"Startup: {count} stale batches reset to pending")

        emb, wp = await reset_stale_pipeline_runs()
        if emb or wp:
            logger.info(f"Startup: {emb} stale embedding run(s), {wp} warm-path run(s) reset to failed")

        dup_count = await reset_stale_dedup_runs()
        if dup_count:
            logger.info(f"Startup: {dup_count} stale dedup run(s) reset to failed")
    except Exception as e:
        logger.warning(f"Startup recovery failed (non-fatal): {e}")

    try:
        from backend.pipeline.manager import get_manager
        resumed = await get_manager().auto_resume()
        if resumed:
            logger.info(f"Startup: ExecutorManager resumed {resumed} job(s)")
    except Exception as e:
        logger.warning(f"ExecutorManager auto-resume failed (non-fatal): {e}")

    try:
        from backend.pipeline import batch_sender
        resumed_sends = await batch_sender.recover()
        if resumed_sends:
            logger.info(f"Startup: resumed {resumed_sends} batch send job(s)")
    except Exception as e:
        logger.warning(f"Batch send recovery failed (non-fatal): {e}")

    try:
        from backend.pipeline import cadence_scheduler
        cadence_scheduler.start()
    except Exception as e:
        logger.warning(f"Cadence scheduler failed to start (non-fatal): {e}")

    yield  # server is running

    # --- shutdown ---
    try:
        from backend.pipeline.manager import get_manager
        await get_manager().shutdown()
    except Exception as e:
        logger.warning(f"ExecutorManager shutdown error: {e}")

    try:
        from backend.pipeline import cadence_scheduler
        await cadence_scheduler.stop()
    except Exception as e:
        logger.warning(f"Cadence scheduler shutdown error: {e}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LinkedIn Enrichment API",
    description="AI-powered LinkedIn profile enrichment for Airtable CRM",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def add_private_network_access_headers(request: Request, call_next):
    """Handle Chrome's Private Network Access preflight requests."""
    if request.method == "OPTIONS":
        response = JSONResponse(content={}, status_code=200)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from backend.api.health import router as health_router
from backend.api.mappings import router as mappings_router
from backend.api.jobs import router as jobs_router
from backend.api.campaigns import router as campaigns_router
from backend.api.auth import router as auth_router
from backend.api.sequences import router as sequences_router
from backend.api.suppressions import router as suppressions_router
from backend.api.redirect import router as redirect_router

app.include_router(health_router)
app.include_router(mappings_router)
app.include_router(jobs_router)
app.include_router(campaigns_router)
app.include_router(auth_router)
app.include_router(sequences_router)
app.include_router(suppressions_router)
app.include_router(redirect_router)


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

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
        reload=False,
        log_level="info",
    )
