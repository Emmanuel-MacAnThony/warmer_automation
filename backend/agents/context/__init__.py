"""
Context building module for chat requests.

Centralizes all context building logic:
- Thread context (execution tracking)
- Message context (conversation history)
- Airtable context (business domain context)
- HITL interrupt detection (workflow context)
"""

from .builder import (
    build_thread_config,
    build_message_history,
    build_airtable_context,
    detect_hitl_interrupt,
    store_interrupted_workflow
)

__all__ = [
    'build_thread_config',
    'build_message_history',
    'build_airtable_context',
    'detect_hitl_interrupt',
    'store_interrupted_workflow'
]
