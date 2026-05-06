"""
ReAct Agent - Reasoning and Acting agent with workflow tools

This agent replaces the hard-coded orchestrator with an intelligent
reasoning layer that can dynamically select and compose tools.
"""
import logging
from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.tools.workflow_tools import get_workflow_tools
from backend.agents.guardrails import get_guardrails
from backend.config import Config

logger = logging.getLogger(__name__)


# System prompt is now loaded from react_prompts.json


class ReActCRMAgent:
    """
    ReAct agent for CRM operations.

    Uses reasoning to decide which workflow tools to call and how to respond to users.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        enable_guardrails: bool = True
    ):
        """
        Initialize ReAct agent.

        Args:
            model: LLM model to use for reasoning
            temperature: LLM temperature (0.0-1.0)
            enable_guardrails: Enable security guardrails
        """
        self.model = model
        self.temperature = temperature
        self.enable_guardrails = enable_guardrails

        # Get tools
        self.tools = get_workflow_tools()

        # Get guardrails
        if self.enable_guardrails:
            self.guardrails = get_guardrails()
        else:
            self.guardrails = None

        # Create LLM
        self.llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            api_key=Config.OPENAI_API_KEY
        )

        # Build system prompt from JSON template
        from backend.agents.prompts.prompt_templates import get_prompt_templates
        prompt_templates = get_prompt_templates()
        tool_descriptions = self._get_tool_descriptions()
        self.system_prompt = prompt_templates.build_react_system_prompt(tool_descriptions)

        # Create checkpointer for state persistence
        self.checkpointer = MemorySaver()

        # Create ReAct agent
        self.agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            checkpointer=self.checkpointer
        )

        logger.info(f"ReAct agent initialized with {len(self.tools)} tools")

    def _get_tool_descriptions(self) -> str:
        """Generate formatted tool descriptions for system prompt."""
        descriptions = []
        for tool in self.tools:
            desc = f"- **{tool.name}**: {tool.description}"
            descriptions.append(desc)
        return "\n".join(descriptions)

    async def run(
        self,
        messages: List[Any],
        context: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the ReAct agent with user messages.

        Args:
            messages: List of message objects (HumanMessage, AIMessage, etc.)
            context: Optional Airtable context
            config: Optional LangGraph config with thread_id
            user_id: Optional user ID for rate limiting

        Returns:
            Dictionary with agent response and metadata
        """
        try:
            # Security: Check guardrails on user input
            if self.enable_guardrails and messages:
                last_message = messages[-1]
                if hasattr(last_message, 'content'):
                    is_safe, error = self.guardrails.check_input(
                        last_message.content,
                        user_id=user_id
                    )
                    if not is_safe:
                        logger.warning(f"GUARDRAIL_BLOCK: {error}")
                        return {
                            "success": False,
                            "response": error,
                            "blocked": True
                        }

            # Build agent input with system prompt prepended
            # Inject system prompt as first message for security constraints
            system_prompt_content = self.system_prompt

            # If context is available, inject it as a user message (not system prompt)
            # This way the agent sees it as current state, not rigid instructions
            if context and context.get('record_id'):
                # We'll inject this as a user message below
                pass

            system_message = SystemMessage(content=system_prompt_content)

            # If there's context, inject it as the LAST message before current request
            # This ensures it's fresh and immediately visible to the agent
            if context and context.get('record_id'):
                from langchain_core.messages import HumanMessage as ContextMessage
                context_msg = ContextMessage(
                    content=f"[System: User has selected Airtable record {context.get('record_id')}]"
                )
                # Insert context right before the last user message
                agent_input = {"messages": [system_message] + messages[:-1] + [context_msg, messages[-1]]}
            else:
                agent_input = {"messages": [system_message] + messages}

            # Set default config if not provided
            if config is None:
                import uuid
                thread_id = f"react-{uuid.uuid4().hex[:12]}"
                config = {"configurable": {"thread_id": thread_id}}

            logger.info(f"AGENT_RUN: Starting with thread_id={config.get('configurable', {}).get('thread_id')}")

            # Run agent (can interrupt for HITL!)
            result = await self.agent.ainvoke(
                agent_input,
                config=config
            )

            # Extract response
            response_messages = result.get("messages", [])
            if response_messages:
                last_message = response_messages[-1]
                response_text = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                response_text = "I couldn't generate a response."

            logger.info(f"AGENT_SUCCESS: Response generated: {response_text[:100]}")

            return {
                "success": True,
                "response": response_text,
                "messages": response_messages,
                "full_state": result
            }

        except Exception as e:
            logger.error(f"AGENT_ERROR: {e}", exc_info=True)
            return {
                "success": False,
                "response": "I encountered an error processing your request. Please try again.",
                "error": str(e)
            }

    def get_state(self, config: Dict[str, Any]) -> Any:
        """Get saved agent state for a given config/thread_id."""
        return self.agent.get_state(config)

    def update_state(self, config: Dict[str, Any], values: Dict[str, Any]):
        """Update agent state (for resuming after HITL)."""
        return self.agent.update_state(config, values)


# Global instance
_react_agent = None


def get_react_agent() -> ReActCRMAgent:
    """Get global ReAct agent instance."""
    global _react_agent
    if _react_agent is None:
        _react_agent = ReActCRMAgent(
            model="gpt-4o",
            temperature=0.3,
            enable_guardrails=True
        )
    return _react_agent
