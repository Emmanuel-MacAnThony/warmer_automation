"""
Context builders for chat requests.

All functions for building execution, message, and business context.
"""
import uuid
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

logger = logging.getLogger(__name__)


def build_thread_config(prefix: str = "chat") -> Tuple[str, Dict[str, Any]]:
    """
    Build thread configuration for LangGraph checkpointer.

    Args:
        prefix: Prefix for thread_id (e.g., "chat", "enrichment")

    Returns:
        Tuple of (thread_id, config_dict)
    """
    thread_id = f"{prefix}-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"=== Created thread_id: {thread_id} ===")

    return thread_id, config


def build_message_history(
    history: List[Dict[str, str]],
    current_message: str
) -> List[BaseMessage]:
    """
    Build LangChain message history from frontend format.

    Args:
        history: List of {role: 'user'|'assistant', content: str}
        current_message: Current user message

    Returns:
        List of LangChain BaseMessage objects
    """
    messages = []

    for msg in history:
        if msg['role'] == 'user':
            messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            messages.append(AIMessage(content=msg['content']))

    # Add current message
    messages.append(HumanMessage(content=current_message))

    return messages


def build_airtable_context(context: Optional[Any]) -> Dict[str, Any]:
    """
    Build Airtable context from request.

    Args:
        context: AirtableContext from ChatRequest (or None)

    Returns:
        Dict with record_id, base_id, table_name (empty if no context)
    """
    if not context:
        return {}

    # Strip query parameters from record_id (e.g., ?blocks=hide)
    clean_record_id = context.recordId
    if clean_record_id and '?' in clean_record_id:
        clean_record_id = clean_record_id.split('?')[0]

    return {
        'record_id': clean_record_id,
        'base_id': context.baseId,
        'table_name': context.tableName
    }


def detect_hitl_interrupt(
    result: Dict[str, Any],
    airtable_context: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Detect HITL workflow interrupts from agent result.

    Checks agent's message state for tool results with interrupted=True flag.
    If found, builds ChatResponse data with show_panel for frontend.

    Args:
        result: Agent execution result with full_state
        airtable_context: Airtable context dict (for user_id)

    Returns:
        Dict with ChatResponse fields if interrupted, None otherwise
    """
    full_state = result.get('full_state', {})
    messages_list = full_state.get('messages', [])

    logger.info(f"Checking {len(messages_list)} messages for interrupts")

    for i, msg in enumerate(reversed(messages_list)):
        # Check if this is a ToolMessage
        if not hasattr(msg, 'type'):
            continue

        if msg.type != 'tool':
            continue

        # Get tool result content
        content = getattr(msg, 'content', None)
        if content is None:
            continue

        # Parse content (could be dict or JSON string)
        tool_result = None
        if isinstance(content, dict):
            tool_result = content
        elif isinstance(content, str):
            try:
                tool_result = json.loads(content)
            except:
                continue
        else:
            continue

        # Check if this tool returned an interrupt
        if isinstance(tool_result, dict) and tool_result.get('interrupted'):
            # Found an interrupted workflow!
            approval_data = tool_result.get('approval_data', {})
            workflow_thread_id = tool_result.get('thread_id')
            user_id = airtable_context.get('record_id', 'unknown')

            # Strip query parameters from record_id
            user_id = user_id.split('?')[0] if '?' in user_id else user_id

            logger.info(
                f"HITL_INTERRUPT_DETECTED: approval_data keys={list(approval_data.keys())}, "
                f"thread_id={workflow_thread_id}, user_id={user_id}"
            )

            # Build response message
            update_count = approval_data.get('update_count', 0)
            record_name = approval_data.get('record_name', 'this contact')
            update_fields = approval_data.get('update_fields', {})

            # Show example fields
            field_examples = []
            for field_name, value in list(update_fields.items())[:3]:
                field_examples.append(f"**{field_name}**: {str(value)[:50]}...")

            response_msg = f"Found **{update_count} fields** to enrich for **{record_name}**:\n\n"
            response_msg += "\n".join(field_examples)
            if update_count > 3:
                response_msg += f"\n...and {update_count - 3} more fields"

            # Build panel data for frontend
            panel_data = {
                "type": "approval",
                "workflow": "enrichment",
                "thread_id": workflow_thread_id,
                "data": approval_data
            }

            logger.info(f"HITL_RESPONSE: Returning show_panel with {update_count} fields")

            # Return data for ChatResponse
            return {
                'workflow_data': {
                    'thread_id': workflow_thread_id,
                    'approval_data': approval_data,
                    'record_id': user_id
                },
                'response_data': {
                    'response': response_msg,
                    'success': True,
                    'show_panel': panel_data
                }
            }

    # No interrupt found
    return None


def store_interrupted_workflow(
    storage: Dict[str, Any],
    workflow_data: Dict[str, Any]
) -> None:
    """
    Store interrupted workflow in server's in-memory storage.

    Args:
        storage: Server's _interrupted_workflows dict
        workflow_data: Dict with thread_id, approval_data, record_id
    """
    user_id = workflow_data['record_id']

    storage[user_id] = {
        'thread_id': workflow_data['thread_id'],
        'approval_data': workflow_data['approval_data'],
        'record_id': user_id
    }

    logger.info(f"HITL_INTERRUPT: Stored workflow {workflow_data['thread_id']} for user {user_id}")
    logger.info(f"HITL_INTERRUPT: Storage now has {len(storage)} entries: {list(storage.keys())}")
