"""
Health, schema, and canonical-schema endpoints.
"""
import logging
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.config import Config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    try:
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
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


@router.get("/canonical-schema")
async def get_canonical_schema():
    """Return the canonical LinkedIn profile schema for field mapping UI."""
    import json
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "workspace", "data", "schema", "canonical_profile.json",
    )
    try:
        with open(schema_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return JSONResponse(status_code=500, content={"error": f"canonical_profile.json not found at {schema_path}"})


@router.get("/schema")
async def get_schema(base_id: str, table_id: str):
    """Return field definitions for a given Airtable base + table."""
    try:
        from backend.infra.crm.airtable import AirtableClient
        client = AirtableClient()
        schema = client.get_table_schema(base_id, table_id)
        return schema
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Schema fetch failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
