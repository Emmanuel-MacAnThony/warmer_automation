"""
Enrichment Workflow - LinkedIn profile enrichment subgraph

LangGraph workflow that manages the multi-step enrichment process.
Uses specialized subagents for LinkedIn analysis and data extraction.
Uses native LangGraph interrupts for HITL (Human-in-the-Loop).
"""

import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.state.agent_state import EnrichmentState
from backend.agents.subagents.linkedin_agent import LinkedInAnalyzerAgent
from backend.clients.linkedin_scraper import scrape_linkedin_profile
from backend.clients.airtable_client import AirtableClient
from backend.config import Config

logger = logging.getLogger(__name__)


class EnrichmentWorkflow:
    """
    LinkedIn enrichment workflow (LangGraph subgraph).

    Multi-step process:
    1. Scrape LinkedIn profile
    2. Analyze with LLM (LinkedInAnalyzerAgent)
    3. Validate extracted fields
    4. HITL approval (human-in-the-loop)
    5. Update Airtable record
    6. Generate similar profiles report
    """

    def __init__(self):
        """Initialize workflow with specialized subagents"""
        self.linkedin_analyzer = LinkedInAnalyzerAgent()
        self.airtable_client = AirtableClient()
        self.graph = self._build_graph()
        logger.info("Initialized EnrichmentWorkflow")

    def _build_graph(self):
        """Build the LangGraph workflow with checkpointer for interrupts"""
        workflow = StateGraph(EnrichmentState)

        # Add agent nodes
        workflow.add_node("scrape_linkedin", self._scrape_linkedin_node)
        workflow.add_node("analyze_linkedin", self._analyze_linkedin_node)
        workflow.add_node("validate_fields", self._validate_fields_node)
        workflow.add_node("hitl_approval", self._hitl_approval_node)
        workflow.add_node("update_airtable", self._update_airtable_node)
        workflow.add_node("generate_report", self._generate_report_node)

        # Set entry point
        workflow.set_entry_point("scrape_linkedin")

        # Define conditional routing
        workflow.add_conditional_edges(
            "scrape_linkedin",
            self._route_after_scrape,
            {"analyze": "analyze_linkedin", "end": END},
        )

        workflow.add_conditional_edges(
            "analyze_linkedin",
            self._route_after_analysis,
            {"validate": "validate_fields", "end": END},
        )

        workflow.add_conditional_edges(
            "validate_fields",
            self._route_after_validation,
            {"hitl": "hitl_approval", "update": "update_airtable", "end": END},
        )

        workflow.add_conditional_edges(
            "hitl_approval",
            self._route_after_hitl,
            {"update": "update_airtable", "end": END},
        )

        workflow.add_conditional_edges(
            "update_airtable",
            self._route_after_update,
            {"report": "generate_report", "end": END},
        )

        workflow.add_edge("generate_report", END)

        # Compile with checkpointer for interrupt/resume support
        # MemorySaver for now (in-memory, but we'll debug thread_id issues first)
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)

    # Agent Nodes

    async def _scrape_linkedin_node(self, state: EnrichmentState) -> EnrichmentState:
        """Scrape LinkedIn profile"""
        try:
            logger.info(f"Scraping LinkedIn: {state['linkedin_url']}")
            linkedin_data = scrape_linkedin_profile(state["linkedin_url"])

            return {
                **state,
                "linkedin_data": linkedin_data,
                "current_agent": "analyze_linkedin",
                "workflow_status": "in_progress",
            }
        except Exception as e:
            logger.error(f"LinkedIn scraping failed: {e}", exc_info=True)
            return {**state, "workflow_status": "failed", "error_message": str(e)}

    async def _analyze_linkedin_node(self, state: EnrichmentState) -> EnrichmentState:
        """Analyze LinkedIn data with LLM"""
        try:
            logger.info("Analyzing LinkedIn data")
            result = await self.linkedin_analyzer.analyze(
                linkedin_data=state["linkedin_data"],
                airtable_fields=state["airtable_fields"],
                profile_name=state.get("linkedin_data", {}).get("full_name", "Unknown"),
            )

            return {
                **state,
                "extracted_fields": result["extracted_fields"],
                "validation_errors": result["validation_errors"],
                "skipped_fields": result["skipped_fields"],
                "current_agent": "validate_fields",
            }
        except Exception as e:
            logger.error(f"LinkedIn analysis failed: {e}", exc_info=True)
            return {**state, "workflow_status": "failed", "error_message": str(e)}

    async def _validate_fields_node(self, state: EnrichmentState) -> EnrichmentState:
        """Validate extracted fields and prepare HITL data"""
        # Validation already done in analyzer, just prepare for HITL
        validated_fields = state.get("extracted_fields", {})

        # Determine if HITL needed
        needs_hitl = len(validated_fields) > 0

        # Prepare HITL data NOW (before interrupt node)
        # This way it's saved in the state before interrupt() is called
        hitl_data = {
            "workflow": "enrichment",
            "record_id": state["airtable_record_id"],
            "record_name": state.get("linkedin_data", {}).get("full_name", "Unknown"),
            "update_fields": validated_fields,
            "update_count": len(validated_fields),
            "similar_profiles_report": state.get("similar_profiles_report"),
            "validation_errors": state.get("validation_errors", []),
            "skipped_fields": state.get("skipped_fields", []),
        }

        return {
            **state,
            "validated_fields": validated_fields,
            "hitl_data": hitl_data,  # Store HITL data here!
            "needs_hitl": needs_hitl,
            "current_agent": "hitl_approval" if needs_hitl else "update_airtable",
        }

    async def _hitl_approval_node(self, state: EnrichmentState) -> EnrichmentState:
        """
        Human-in-the-loop approval checkpoint.

        Uses native LangGraph interrupt() to pause execution for user approval.
        Requires Python 3.12+ for proper contextvar support.
        """
        from langgraph.types import interrupt

        # Check if this is the first time (need to interrupt) or resume (already have approval)
        if not state.get("hitl_approved") and state.get("hitl_approved") is not False:
            # HITL data was already prepared in validation node
            hitl_data = state.get("hitl_data", {})

            logger.info(
                "HITL approval required - interrupting workflow for user approval"
            )
            logger.info(
                f"HITL data: {hitl_data.get('update_count', 0)} fields for {hitl_data.get('record_name', 'Unknown')}"
            )

            # Native LangGraph interrupt - pauses execution here
            interrupt(hitl_data)

        # When resumed after interrupt, state will have hitl_approved field set
        approved = state.get("hitl_approved", False)
        final_fields = state.get("validated_fields", {})

        logger.info(f"User response: {'approved' if approved else 'rejected'}")

        return {
            **state,
            "workflow_status": "completed" if approved else "cancelled",
            "current_agent": "update_airtable" if approved else "end",
        }

    async def _update_airtable_node(self, state: EnrichmentState) -> EnrichmentState:
        """Update Airtable record"""
        try:
            fields_to_update = state.get("validated_fields", {})

            if not fields_to_update:
                logger.warning("No fields to update")
                return {**state, "workflow_status": "completed"}

            logger.info(f"Updating Airtable record {state['airtable_record_id']}")

            # Update record
            self.airtable_client.update_record(
                record_id=state["airtable_record_id"], fields=fields_to_update
            )

            return {
                **state,
                "current_agent": "generate_report",
                "workflow_status": "completed",
            }
        except Exception as e:
            logger.error(f"Airtable update failed: {e}", exc_info=True)
            return {**state, "workflow_status": "failed", "error_message": str(e)}

    async def _generate_report_node(self, state: EnrichmentState) -> EnrichmentState:
        """Generate similar profiles report from peopleAlsoViewed data"""
        logger.info(
            "DEBUG _generate_report_node: NODE REACHED - Starting report generation"
        )
        try:
            linkedin_data = state.get("linkedin_data", {})
            logger.info(
                f"DEBUG _generate_report_node: linkedin_data keys = {list(linkedin_data.keys()) if linkedin_data else 'None'}"
            )

            # peopleAlsoViewed is inside raw_data, not at root level
            raw_data = linkedin_data.get("raw_data", {})
            people_also_viewed = raw_data.get("peopleAlsoViewed", [])
            logger.info(
                f"DEBUG _generate_report_node: peopleAlsoViewed count = {len(people_also_viewed) if people_also_viewed else 0}"
            )

            if people_also_viewed and len(people_also_viewed) > 0:
                logger.info(
                    f"Generating report for {len(people_also_viewed)} similar profiles"
                )

                from backend.utils.report_generator import generate_and_save_report

                profile_name = linkedin_data.get("full_name", "Unknown")
                profile_title = linkedin_data.get("headline") or linkedin_data.get(
                    "position"
                )

                report_data = generate_and_save_report(
                    profile_name=profile_name,
                    profile_title=profile_title,
                    people_also_viewed=people_also_viewed,
                )

                logger.info(f"Report generated: {report_data.get('filename')}")

                return {
                    **state,
                    "similar_profiles_report": report_data,
                    "workflow_status": "completed",
                }
            else:
                logger.info("No similar profiles data available - skipping report")
                return {
                    **state,
                    "similar_profiles_report": None,
                    "workflow_status": "completed",
                }

        except Exception as e:
            logger.error(f"Report generation failed (non-fatal): {e}", exc_info=True)
            # Don't fail the workflow if report generation fails
            return {
                **state,
                "similar_profiles_report": None,
                "workflow_status": "completed",
            }

    # Routing Functions

    def _route_after_scrape(self, state: EnrichmentState) -> Literal["analyze", "end"]:
        """Route after LinkedIn scraping"""
        if state.get("workflow_status") == "failed":
            return "end"
        if state.get("linkedin_data"):
            return "analyze"
        return "end"

    def _route_after_analysis(
        self, state: EnrichmentState
    ) -> Literal["validate", "end"]:
        """Route after LinkedIn analysis"""
        if state.get("workflow_status") == "failed":
            return "end"
        if state.get("extracted_fields"):
            return "validate"
        return "end"

    def _route_after_validation(
        self, state: EnrichmentState
    ) -> Literal["hitl", "update", "end"]:
        """Route after field validation"""
        validated_fields = state.get("validated_fields", {})

        # If no fields to update, end workflow
        if not validated_fields or len(validated_fields) == 0:
            logger.warning("No valid fields extracted - ending workflow")
            return "end"

        # If fields exist, go to HITL for approval
        if state.get("needs_hitl", True):
            return "hitl"

        return "update"

    def _route_after_hitl(self, state: EnrichmentState) -> Literal["update", "end"]:
        """Route after HITL approval"""
        if state.get("hitl_approved", False):
            return "update"
        return "end"

    def _route_after_update(self, state: EnrichmentState) -> Literal["report", "end"]:
        """Route after Airtable update"""
        linkedin_data = state.get("linkedin_data", {})

        # DEBUG: Dump full structure to see what we have
        logger.info(
            f"DEBUG _route_after_update: linkedin_data keys = {list(linkedin_data.keys()) if linkedin_data else 'None'}"
        )

        # peopleAlsoViewed is inside raw_data, not at root level
        raw_data = linkedin_data.get("raw_data", {})
        people_also_viewed = raw_data.get("peopleAlsoViewed", [])

        logger.info(f"DEBUG _route_after_update: raw_data exists = {bool(raw_data)}")
        logger.info(
            f"DEBUG _route_after_update: peopleAlsoViewed type = {type(people_also_viewed)}"
        )
        logger.info(
            f"DEBUG _route_after_update: peopleAlsoViewed length = {len(people_also_viewed) if people_also_viewed else 0}"
        )

        if people_also_viewed and len(people_also_viewed) > 0:
            logger.info(
                f"DEBUG _route_after_update: First profile sample = {people_also_viewed[0] if len(people_also_viewed) > 0 else 'empty'}"
            )

        logger.info(
            f"Routing after update: peopleAlsoViewed count = {len(people_also_viewed) if people_also_viewed else 0}"
        )

        # Generate report if similar profiles exist
        if people_also_viewed and len(people_also_viewed) > 0:
            logger.info(
                f"Routing to report generation for {len(people_also_viewed)} profiles"
            )
            return "report"

        logger.info("No peopleAlsoViewed data - skipping report generation")
        return "end"

    async def run(self, initial_state: EnrichmentState) -> EnrichmentState:
        """
        Run the enrichment workflow.

        Args:
            initial_state: Initial state with linkedin_url, airtable_record_id, etc.

        Returns:
            Final state after workflow completion
        """
        try:
            logger.info(
                f"Starting enrichment workflow for record {initial_state.get('airtable_record_id')}"
            )
            result = await self.graph.ainvoke(initial_state)
            logger.info(
                f"Workflow completed with status: {result.get('workflow_status')}"
            )
            return result
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            return {
                **initial_state,
                "workflow_status": "failed",
                "error_message": str(e),
            }


# Global instance
_workflow = None


def get_enrichment_workflow() -> EnrichmentWorkflow:
    """Get or create enrichment workflow instance"""
    global _workflow
    if _workflow is None:
        _workflow = EnrichmentWorkflow()
    return _workflow
