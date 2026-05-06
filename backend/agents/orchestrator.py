"""
CRM Orchestrator - Main supervisor that routes to specialized workflows

Architecture:
- Main Orchestrator (this file) → routes by intent
- Workflows (subgraphs) → enrichment, search, outreach, analytics
- Subagents → LinkedIn analyzer, matchers, drafters, etc.
"""
import logging
from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from backend.agents.state.orchestrator_state import OrchestratorState
from backend.agents.workflows.enrichment import get_enrichment_workflow
from backend.config import Config

logger = logging.getLogger(__name__)


class CRMOrchestrator:
    """
    Main supervisor for CRM agent.

    Responsibilities:
    1. Classify user intent (enrichment, search, outreach, etc.)
    2. Route to appropriate workflow (subgraph)
    3. Manage HITL coordination across workflows
    4. Sync state between workflows
    5. Return results to user
    """

    def __init__(self):
        """Initialize orchestrator with LLM for intent classification"""
        self.llm = ChatOpenAI(
            model=Config.OPENAI_MODEL,
            temperature=0,
            api_key=Config.OPENAI_API_KEY
        )

        # Initialize workflows (lazy loading)
        self.enrichment_workflow = None

        self.graph = self._build_graph()
        logger.info("Initialized CRMOrchestrator")

    def _build_graph(self) -> StateGraph:
        """Build the main supervisor graph"""
        workflow = StateGraph(OrchestratorState)

        # Add nodes
        workflow.add_node("classify_intent", self._classify_intent_node)
        workflow.add_node("route_workflow", self._route_workflow_node)
        workflow.add_node("enrichment", self._enrichment_workflow_node)
        workflow.add_node("synthesize_response", self._synthesize_response_node)
        workflow.add_node("finalize", self._finalize_node)

        # Set entry point
        workflow.set_entry_point("classify_intent")

        # Route after intent classification
        workflow.add_edge("classify_intent", "route_workflow")

        # Route to workflows based on intent
        workflow.add_conditional_edges(
            "route_workflow",
            self._route_by_intent,
            {
                "enrichment": "enrichment",
                "search": "synthesize_response",  # TODO: implement search workflow
                "outreach": "synthesize_response",  # TODO: implement outreach workflow
                "analytics": "synthesize_response",  # TODO: implement analytics workflow
                "unknown": "synthesize_response"
            }
        )

        # Workflows → Response Synthesis → Finalize → END
        workflow.add_edge("enrichment", "synthesize_response")
        workflow.add_edge("synthesize_response", "finalize")
        workflow.add_edge("finalize", END)

        # Compile with checkpointer for interrupt support
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)

    # Nodes

    async def _classify_intent_node(self, state: OrchestratorState) -> OrchestratorState:
        """Classify user intent using LLM"""
        messages = state.get('messages', [])

        if not messages:
            return {
                **state,
                'intent': 'unknown',
                'status': 'failed',
                'error_message': 'No messages provided'
            }

        # Get last user message
        last_message = messages[-1].content if messages else ""

        # Simple keyword-based classification (can be enhanced with LLM)
        intent = self._classify_intent_simple(last_message)

        logger.info(f"Classified intent: {intent}")

        return {
            **state,
            'intent': intent,
            'status': 'in_progress'
        }

    def _classify_intent_simple(self, message: str) -> str:
        """Simple keyword-based intent classification"""
        message_lower = message.lower()

        # Enrichment keywords
        if any(kw in message_lower for kw in ['enrich', 'linkedin', 'scrape', 'profile', 'update']):
            return 'enrichment'

        # Search keywords
        if any(kw in message_lower for kw in ['find', 'search', 'lookup', 'match']):
            return 'search'

        # Outreach keywords
        if any(kw in message_lower for kw in ['email', 'outreach', 'campaign', 'send']):
            return 'outreach'

        # Analytics keywords
        if any(kw in message_lower for kw in ['report', 'analytics', 'stats', 'insights']):
            return 'analytics'

        return 'unknown'

    async def _route_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Prepare for workflow routing"""
        intent = state.get('intent', 'unknown')

        return {
            **state,
            'workflow': intent
        }

    async def _enrichment_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Execute enrichment workflow (subgraph)"""
        try:
            # Lazy load enrichment workflow
            if self.enrichment_workflow is None:
                self.enrichment_workflow = get_enrichment_workflow()

            # Extract context for enrichment
            airtable_context = state.get('airtable_context', {})

            # Fetch LinkedIn URL from Airtable record if not provided
            linkedin_url = airtable_context.get('linkedin_url')
            if not linkedin_url and airtable_context.get('record_id'):
                logger.info("Fetching LinkedIn URL from Airtable record")
                from backend.crm.airtable import AirtableClient
                airtable_client = AirtableClient()
                record = airtable_client.fetch_record_by_id(airtable_context.get('record_id'))

                if not record:
                    raise ValueError(f"Record {airtable_context.get('record_id')} not found in Airtable")

                # Try common LinkedIn field names
                fields = record.get('fields', {})
                for field_name in ['LinkedIn', 'LinkedIn URL', 'LinkedIn Profile', 'Profile URL']:
                    if field_name in fields and fields[field_name]:
                        linkedin_url = fields[field_name]
                        logger.info(f"Found LinkedIn URL in field '{field_name}': {linkedin_url}")
                        break

                if not linkedin_url:
                    raise ValueError("LinkedIn URL not found in record. Please add a LinkedIn field with the profile URL.")

            # Fetch Airtable schema for field validation
            from backend.agents.tools.langchain_tools import get_airtable_schema
            base_id = airtable_context.get('base_id')
            table_name = airtable_context.get('table_name')

            airtable_fields = []
            if base_id and table_name:
                logger.info(f"Fetching schema for {base_id}/{table_name}")
                schema_result = get_airtable_schema(base_id, table_name)
                if schema_result.get('success'):
                    airtable_fields = schema_result['fields']
                    logger.info(f"Fetched {len(airtable_fields)} fields from Airtable schema")
                else:
                    logger.warning(f"Failed to fetch schema: {schema_result.get('error')}")

            # Build enrichment state from orchestrator state
            enrichment_state = {
                'linkedin_url': linkedin_url,
                'airtable_record_id': airtable_context.get('record_id'),
                'airtable_fields': airtable_fields,
                'workflow_status': 'pending'
            }

            # Get config from state (for thread_id)
            config = state.get('_config', {})
            thread_id = config.get('configurable', {}).get('thread_id', 'MISSING')

            # Run enrichment workflow with config for interrupt support
            logger.info(f"Delegating to enrichment workflow with thread_id: {thread_id}")
            logger.info(f"Config: {config}")
            result = await self.enrichment_workflow.graph.ainvoke(enrichment_state, config=config)

            # Check if workflow needs approval
            if result.get('workflow_status') == 'needs_approval':
                logger.info("Enrichment workflow needs approval - returning state for HITL")

                # Return orchestrator state with needs_approval flag
                # The /chat endpoint will detect this and show the approval panel
                return {
                    **state,
                    'workflow_result': result,
                    'status': 'in_progress',
                    'needs_approval': True,
                    'approval_data': result.get('hitl_data'),
                    'intent': 'enrichment'
                }

            return {
                **state,
                'workflow_result': result,
                'status': result.get('workflow_status', 'completed')
            }

        except Exception as e:
            # Re-raise GraphInterrupt so LangGraph can handle it
            from langgraph.errors import GraphInterrupt
            if isinstance(e, GraphInterrupt):
                raise

            logger.error(f"Enrichment workflow failed: {e}", exc_info=True)
            return {
                **state,
                'status': 'failed',
                'error_message': str(e)
            }

    async def _synthesize_response_node(self, state: OrchestratorState) -> OrchestratorState:
        """
        Generate natural language response based on workflow outcome.
        Uses LLM + prompts.json to create context-aware, helpful messages.
        """
        from backend.utils.prompts import PromptLoader
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            workflow_type = state.get('intent', 'workflow')
            status = state.get('status', 'completed')
            workflow_result = state.get('workflow_result', {})

            # Determine which prompt template to use
            if status == 'completed' and not state.get('needs_approval'):
                # Success case
                validated_fields = workflow_result.get('validated_fields', {})
                field_count = len(validated_fields)
                record_name = workflow_result.get('linkedin_data', {}).get('full_name', 'contact')

                user_prompt = PromptLoader.get(
                    'response_synthesis', 'success',
                    workflow_type=workflow_type,
                    outcome_summary=f"Updated {field_count} fields for {record_name}",
                    key_results=', '.join(list(validated_fields.keys())[:5]) if validated_fields else 'N/A'
                )

            elif status == 'failed':
                # Failure case - sanitize error before showing to user
                raw_error = state.get('error_message', 'Unknown error')
                logger.info(f"[INTERNAL] Full error details: {raw_error}")  # Log for debugging

                # Categorize error (don't expose internal details to user)
                error_category = self._categorize_error(raw_error)

                user_prompt = PromptLoader.get(
                    'response_synthesis', 'failed',
                    workflow_type=workflow_type,
                    error_category=error_category
                )

            elif status == 'cancelled' or not state.get('needs_approval'):
                # Cancelled case
                user_prompt = PromptLoader.get(
                    'response_synthesis', 'cancelled',
                    workflow_type=workflow_type,
                    stage=workflow_result.get('current_agent', 'approval')
                )

            else:
                # Fallback - shouldn't reach here normally
                return {
                    **state,
                    'user_facing_message': f"{workflow_type.capitalize()} workflow in progress."
                }

            # Use LLM to generate response
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
            system_prompt = PromptLoader.get_system('response_synthesis')

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = await llm.ainvoke(messages)

            logger.info(f"Generated user-facing message: {response.content[:100]}")

            return {
                **state,
                'user_facing_message': response.content.strip()
            }

        except Exception as e:
            logger.error(f"Response synthesis failed: {e}", exc_info=True)
            # Fallback to generic message
            return {
                **state,
                'user_facing_message': f"Workflow {status}."
            }

    async def _finalize_node(self, state: OrchestratorState) -> OrchestratorState:
        """Finalize orchestrator execution"""
        status = state.get('status', 'completed')
        workflow = state.get('workflow', 'unknown')

        logger.info(f"Finalized orchestrator - workflow: {workflow}, status: {status}")

        return {
            **state,
            'status': 'completed'
        }

    # Helpers

    def _categorize_error(self, error_message: str) -> str:
        """
        Categorize error into user-friendly categories.
        NEVER expose internal details like API names, services, or stack traces.
        """
        error_lower = error_message.lower()

        # User input errors
        if 'no linkedin url' in error_lower or 'linkedin url' in error_lower and 'not found' in error_lower:
            return "Missing or invalid LinkedIn URL"
        if 'invalid url' in error_lower or 'malformed' in error_lower:
            return "Invalid input format"

        # Data availability errors
        if 'profile not found' in error_lower or 'private profile' in error_lower or '404' in error_lower:
            return "Profile unavailable or private"
        if 'no data' in error_lower or 'empty response' in error_lower:
            return "No data available"

        # Temporary/rate limit errors
        if 'rate limit' in error_lower or 'too many requests' in error_lower or '429' in error_lower:
            return "Request limit reached"
        if 'timeout' in error_lower or 'timed out' in error_lower:
            return "Request timed out"
        if 'credits' in error_lower or 'quota' in error_lower:
            return "Service temporarily unavailable"

        # System errors (catch-all)
        return "System error occurred"

    # Routing

    def _route_by_intent(self, state: OrchestratorState) -> Literal["enrichment", "search", "outreach", "analytics", "unknown"]:
        """Route to workflow based on intent"""
        intent = state.get('intent', 'unknown')

        if intent == 'enrichment':
            return 'enrichment'
        elif intent == 'search':
            return 'search'
        elif intent == 'outreach':
            return 'outreach'
        elif intent == 'analytics':
            return 'analytics'
        else:
            return 'unknown'

    # Execution

    async def run(self, initial_state: OrchestratorState, config: Dict[str, Any] = None) -> OrchestratorState:
        """
        Run the orchestrator.

        Args:
            initial_state: Initial state with messages and context
            config: Optional config with thread_id for interrupt support

        Returns:
            Final state after routing and execution
        """
        try:
            logger.info("Starting CRM orchestrator")

            # Inject config into state so child workflows can access it
            if config:
                initial_state['_config'] = config

            # CRITICAL: Pass config to ainvoke so checkpointer gets thread_id
            result = await self.graph.ainvoke(initial_state, config=config)
            logger.info(f"Orchestrator completed with status: {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"Orchestrator execution failed: {e}", exc_info=True)
            return {
                **initial_state,
                'status': 'failed',
                'error_message': str(e)
            }


# Global instance
_orchestrator = None

def get_orchestrator() -> CRMOrchestrator:
    """Get or create orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CRMOrchestrator()
    return _orchestrator
