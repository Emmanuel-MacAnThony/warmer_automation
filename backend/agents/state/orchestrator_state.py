"""
Orchestrator State - Main supervisor state for CRM agent

Manages routing between different workflows (enrichment, search, outreach, etc.)
"""
from typing import TypedDict, Annotated, Optional, Dict, Any, List, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class OrchestratorState(TypedDict):
    """
    State for the main CRM orchestrator (supervisor).

    Routes user requests to appropriate workflows:
    - enrichment: LinkedIn profile enrichment
    - search: Find and match profiles
    - outreach: Email campaigns and follow-ups
    - analytics: Reports and insights
    - data_management: Updates and cleanup
    """
    # Conversation
    messages: Annotated[List[BaseMessage], add_messages]

    # Routing
    intent: Optional[str]  # Detected user intent (enrichment, search, outreach, etc.)
    workflow: Optional[str]  # Current workflow being executed

    # Context from Chrome extension
    airtable_context: Optional[Dict[str, Any]]  # Base ID, table name, record ID

    # Workflow results
    workflow_result: Optional[Dict[str, Any]]  # Result from subgraph

    # Status
    status: str  # pending, in_progress, completed, failed
    error_message: Optional[str]

    # HITL
    needs_approval: bool  # Whether workflow paused for human approval
    approval_data: Optional[Dict[str, Any]]  # Data for approval UI

    # Internal (for passing config to child workflows)
    _config: Optional[Dict[str, Any]]  # Config with thread_id for interrupts


# Intent types for routing
IntentType = Literal[
    "enrichment",      # Enrich LinkedIn profile
    "search",          # Find/match profiles
    "outreach",        # Email campaigns
    "analytics",       # Reports/insights
    "data_management", # Updates/cleanup
    "unknown"          # Cannot determine intent
]
