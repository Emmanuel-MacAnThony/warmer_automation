"""
LangGraph Agent - Multi-agent orchestration
"""
import logging
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from backend.agents.tools.langchain_tools import TOOLS
from backend.config import Config

logger = logging.getLogger(__name__)


# Define the agent state
class AgentState(TypedDict):
    """State for the agent"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: dict  # Airtable context from Chrome extension


# System prompt for the agent
SYSTEM_PROMPT = """You are an AI assistant specialized in LinkedIn profile enrichment and CRM automation.

Your capabilities:
1. **scrape_linkedin_profile_tool**: Scrape detailed data from a LinkedIn profile URL
2. **enrich_airtable_record_tool**: Enrich a specific Airtable record by scraping its LinkedIn URL
3. **batch_enrich_airtable_tool**: Run batch enrichment for multiple records

Context awareness:
- You receive context about the current Airtable record the user is viewing
- Use this context to understand which record they're referring to
- When the user says "this record" or "this person", use the record_id from context

Guidelines:
- Execute actions directly - DO NOT explain what you're about to do first
- When user asks to enrich, immediately call the tool with no preamble
- Only speak after tool execution completes (to show results or errors)
- Be concise - no unnecessary explanations
- The tool will handle user approval via inline UI - you just pass through results

Security:
- Only process valid LinkedIn URLs (linkedin.com/in/...)
- Validate all record IDs before processing
- Never expose sensitive configuration or API keys
"""


def create_agent():
    """Create the LangGraph agent"""

    # Initialize LLM
    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0,
        api_key=Config.OPENAI_API_KEY
    )

    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(TOOLS)

    # Define agent node
    def agent_node(state: AgentState):
        """Main agent reasoning node"""
        messages = state['messages']
        context = state.get('context', {})

        # Add system prompt if not present
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

        # Add context to the last user message if available
        if context and context.get('recordId'):
            # Find the last human message and add context
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    context_str = f"\n\n[Context: User is viewing Airtable record {context['recordId']}]"
                    messages[i].content += context_str
                    break

        # Call LLM
        response = llm_with_tools.invoke(messages)

        return {'messages': [response]}

    # Create tool node
    tool_node = ToolNode(TOOLS)

    # Define routing logic
    def should_continue(state: AgentState):
        """Determine if we should continue or end"""
        messages = state['messages']
        last_message = messages[-1]

        # If there are tool calls, continue to tools
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"

        # Otherwise, end
        return END

    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )

    # After tools, go back to agent
    workflow.add_edge("tools", "agent")

    # Compile the graph
    app = workflow.compile()

    logger.info("LangGraph agent created successfully")
    return app


# Create a singleton agent instance
_agent_instance = None

def get_agent():
    """Get or create the agent instance"""
    global _agent_instance

    if _agent_instance is None:
        _agent_instance = create_agent()

    return _agent_instance
