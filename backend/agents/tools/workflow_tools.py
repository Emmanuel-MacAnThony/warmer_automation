"""
Workflow Tools - LangGraph workflows wrapped as LangChain tools

Each tool wraps a complex LangGraph workflow (subgraph) and exposes it
to the ReAct agent for dynamic tool calling.
"""

import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from langchain.tools import tool

from backend.agents.workflows.enrichment import get_enrichment_workflow
from backend.crm.airtable import AirtableClient
from backend.agents.tools.langchain_tools import get_airtable_schema

logger = logging.getLogger(__name__)


# Input Schemas (Pydantic validation)
# https://www.linkedin.com/in/yusuf-kasim-62329b192/


class EnrichLinkedInInput(BaseModel):
    """Input schema for LinkedIn enrichment tool."""

    record_id: str = Field(
        description="Airtable record ID to enrich (must start with 'rec')"
    )

    @validator("record_id")
    def validate_record_id(cls, v):
        """Validate Airtable record ID format."""
        if not v:
            raise ValueError("record_id is required")
        if not v.startswith("rec"):
            raise ValueError("Invalid Airtable record ID - must start with 'rec'")
        if len(v) != 17:
            raise ValueError("Invalid Airtable record ID length")
        return v


# Tool Implementations


@tool(args_schema=EnrichLinkedInInput)
async def enrich_linkedin_profile(record_id: str) -> Dict[str, Any]:
    """
    Enrich an Airtable contact record with LinkedIn profile data.

    This tool:
    1. Scrapes LinkedIn profile data
    2. Analyzes and validates the data
    3. Requests human approval (HITL)
    4. Updates Airtable with approved fields
    5. Generates a report of similar profiles

    Args:
        record_id: Airtable record ID (e.g., 'recABCDEFGHIJKLMN')

    Returns:
        Dictionary with enrichment results:
        - success: bool
        - fields_updated: int
        - record_name: str
        - similar_profiles_count: int
        - validation_errors: list

    Raises:
        ValueError: If record_id is invalid
        HTTPException: If record not found or no LinkedIn URL

    Example:
        >>> await enrich_linkedin_profile("recABCDEFGHIJKLMN")
        {"success": True, "fields_updated": 15, "record_name": "John Doe"}
    """
    logger.info(f"TOOL_CALL: enrich_linkedin_profile(record_id={record_id})")

    try:
        # Get Airtable record
        airtable = AirtableClient()
        record = airtable.fetch_record_by_id(record_id)

        if not record:
            logger.error(f"TOOL_FAILED: Record {record_id} not found")
            return {"success": False, "error": "Record not found in Airtable"}

        # Extract LinkedIn URL
        fields = record.get("fields", {})
        linkedin_url = None
        for field_name in [
            "LinkedIn",
            "LinkedIn URL",
            "LinkedIn Profile",
            "Profile URL",
        ]:
            if field_name in fields and fields[field_name]:
                linkedin_url = fields[field_name]
                break

        if not linkedin_url:
            logger.error(f"TOOL_FAILED: No LinkedIn URL in record {record_id}")
            return {
                "success": False,
                "error": "This record doesn't have a LinkedIn URL. Please add one and try again.",
            }

        # Get table schema for field validation
        from backend.config import Config

        base_id = Config.AIRTABLE_BASE_ID
        table_name = Config.AIRTABLE_TABLE_NAME

        schema_result = get_airtable_schema(base_id, table_name)
        if not schema_result.get("success"):
            logger.error(f"TOOL_FAILED: Could not fetch schema")
            return {"success": False, "error": "Could not fetch table schema"}

        # Build initial state for enrichment workflow
        initial_state = {
            "linkedin_url": linkedin_url,
            "airtable_record_id": record_id,
            "airtable_fields": schema_result["fields"],
            "workflow_status": "pending",
        }

        # Get workflow instance
        workflow = get_enrichment_workflow()

        # Generate config with thread_id for this execution
        # NOTE: This allows the workflow to interrupt for HITL
        import uuid

        thread_id = f"enrich-{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(
            f"TOOL_EXECUTE: Starting enrichment workflow with thread_id={thread_id}"
        )

        # Invoke workflow - will pause if interrupt() is called
        result = await workflow.graph.ainvoke(initial_state, config=config)

        # Check if workflow was interrupted (paused for HITL)
        state_snapshot = workflow.graph.get_state(config)

        if state_snapshot.next:  # Has pending tasks = workflow interrupted
            # Workflow paused for approval - get hitl_data from state
            hitl_data = state_snapshot.values.get("hitl_data", {})

            logger.info(
                f"TOOL_PAUSED: Workflow interrupted for approval (thread_id={thread_id})"
            )
            logger.info(
                f"HITL data: {hitl_data.get('update_count', 0)} fields for {hitl_data.get('record_name', 'Unknown')}"
            )

            # Return special interrupt response that server will detect
            # Don't include a hardcoded message - let the agent synthesize intelligently
            return {
                "success": False,
                "interrupted": True,
                "thread_id": thread_id,
                "approval_data": hitl_data,
            }

        # Workflow completed
        elif result.get("workflow_status") == "completed":
            validated_fields = result.get("validated_fields", {})
            linkedin_data = result.get("linkedin_data", {})
            similar_report = result.get("similar_profiles_report", {})

            logger.info(f"TOOL_SUCCESS: Enriched {len(validated_fields)} fields")

            return {
                "success": True,
                "fields_updated": len(validated_fields),
                "record_name": linkedin_data.get("full_name", "Contact"),
                "fields": list(validated_fields.keys())[:10],  # First 10 fields
                "similar_profiles_count": (
                    similar_report.get("count", 0) if similar_report else 0
                ),
                "validation_errors": result.get("validation_errors", []),
            }

        # Workflow ended without completion (no fields found)
        elif not state_snapshot.next and not result.get("workflow_status"):
            linkedin_data = result.get("linkedin_data", {})
            validation_errors = result.get("validation_errors", [])
            skipped_fields = result.get("skipped_fields", [])

            logger.warning(f"TOOL_NO_FIELDS: No valid fields extracted for enrichment")

            return {
                "success": False,
                "error": "no_valid_fields",
                "record_name": linkedin_data.get("full_name", "Unknown"),
                "message": f"I couldn't find any valid fields to update. The profile data either doesn't match your Airtable schema, or all fields were already filled.",
                "validation_errors": validation_errors,
                "skipped_fields": skipped_fields,
            }

        else:
            # Workflow failed or cancelled
            error_msg = result.get(
                "error_message", "Enrichment was cancelled or failed"
            )
            logger.error(f"TOOL_FAILED: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(
            f"TOOL_EXCEPTION: enrich_linkedin_profile failed: {e}", exc_info=True
        )
        return {"success": False, "error": str(e)}


# Tool Registry
# Add new workflow tools here and they'll be auto-discovered by ReAct agent

WORKFLOW_TOOLS = [
    enrich_linkedin_profile,
    # TODO: Add more workflow tools:
    # - search_contacts
    # - send_outreach
    # - generate_analytics
]


def get_workflow_tools():
    """Get all registered workflow tools."""
    return WORKFLOW_TOOLS
