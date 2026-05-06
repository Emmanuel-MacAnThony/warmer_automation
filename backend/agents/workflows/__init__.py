"""LangGraph workflows (subgraphs) for CRM agent"""
from backend.agents.workflows.enrichment import EnrichmentWorkflow, get_enrichment_workflow

__all__ = [
    'EnrichmentWorkflow',
    'get_enrichment_workflow'
]
