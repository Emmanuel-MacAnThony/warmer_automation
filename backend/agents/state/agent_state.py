"""
Agent State Management - Shared state across all agents in the enrichment workflow
"""
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class EnrichmentState(TypedDict):
    """
    Shared state for the enrichment workflow.
    
    This state is passed between all agents and accumulates data as the workflow progresses.
    """
    # Message history
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Input data
    linkedin_url: str
    linkedin_data: Optional[Dict[str, Any]]
    airtable_record_id: str
    airtable_fields: List[Dict[str, Any]]
    
    # Agent outputs
    extracted_fields: Optional[Dict[str, Any]]
    matched_fields: Optional[Dict[str, Any]]
    validated_fields: Optional[Dict[str, Any]]
    enriched_fields: Optional[Dict[str, Any]]
    
    # Validation & errors
    validation_errors: List[str]
    skipped_fields: List[str]
    
    # HITL workflow
    needs_hitl: bool
    hitl_approved: bool
    hitl_data: Optional[Dict[str, Any]]
    
    # Similar profiles
    similar_profiles: Optional[List[Dict[str, Any]]]
    similar_profiles_report: Optional[Dict[str, Any]]
    
    # Workflow control
    current_agent: str
    workflow_status: str  # 'pending', 'in_progress', 'completed', 'failed'
    error_message: Optional[str]


class BatchEnrichmentState(TypedDict):
    """State for batch enrichment workflows"""
    records: List[Dict[str, Any]]
    completed: List[str]
    failed: List[str]
    current_index: int
    total_count: int
