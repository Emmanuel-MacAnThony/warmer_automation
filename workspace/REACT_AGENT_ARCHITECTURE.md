# ReAct Agent Architecture

## Overview

The CRM system uses a **ReAct (Reasoning + Acting) agent** architecture that provides intelligent, dynamic tool selection with comprehensive security guardrails.

## Architecture Diagram

```
┌──────────────────────────────────────────────┐
│          User Input                          │
└──────────────┬───────────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────────┐
│   Security Guardrails                        │
│   - Prompt injection detection               │
│   - Rate limiting                            │
│   - Input validation                         │
└──────────────┬───────────────────────────────┘
               │ (if safe)
               ↓
┌──────────────────────────────────────────────┐
│   ReAct Agent (Reasoning Layer)              │
│   - Understands user intent                  │
│   - Selects appropriate tools                │
│   - Handles conversation naturally           │
│   - Synthesizes responses                    │
└──────────────┬───────────────────────────────┘
               │ (calls tools)
               ↓
     ┌─────────┴──────────┐
     │                    │
     ↓                    ↓
┌─────────┐         ┌──────────┐
│ Tool 1  │   ...   │ Tool N   │  (Thin wrappers)
│ Enrich  │         │ Search   │
└────┬────┘         └────┬─────┘
     │                   │
     ↓                   ↓
┌─────────────────────────────┐
│   LangGraph Workflows        │  (Complex execution)
│   - Scrape → Analyze → HITL  │
│   - State management         │
│   - Checkpointing            │
└──────────────────────────────┘
```

## Key Components

### 1. Security Guardrails (`backend/agents/guardrails/`)

**Purpose:** Protect system from abuse and attacks

**Features:**
- **Prompt Injection Detection**: Blocks common attack patterns
- **Rate Limiting**: 10 requests/minute, 100 requests/hour per user
- **Input Validation**: Max 5000 characters, sanitization
- **Security Event Logging**: Audit trail of blocked requests

**Usage:**
```python
from backend.agents.guardrails import get_guardrails

guardrails = get_guardrails()
is_safe, error = guardrails.check_input(user_text, user_id="user123")
```

### 2. Workflow Tools (`backend/agents/tools/workflow_tools.py`)

**Purpose:** Expose LangGraph workflows as callable tools

**Pattern:**
```python
from langchain.tools import tool
from pydantic import BaseModel, validator

class MyToolInput(BaseModel):
    param: str

    @validator('param')
    def validate_param(cls, v):
        # Validate input
        return v

@tool(args_schema=MyToolInput)
async def my_workflow_tool(param: str) -> dict:
    """
    Clear description of what this tool does.

    Args:
        param: Parameter description

    Returns:
        Result description
    """
    workflow = get_my_workflow()
    result = await workflow.graph.ainvoke(...)
    return result
```

**Current Tools:**
- `enrich_linkedin_profile`: LinkedIn enrichment with HITL

### 3. ReAct Agent (`backend/agents/react_agent.py`)

**Purpose:** Intelligent reasoning and tool orchestration

**Capabilities:**
- Decides which tool(s) to use
- Handles casual conversation without tools
- Composes multiple tool calls
- Explains limitations when asked to do unsupported tasks

**System Prompt:** Constrains agent to only use registered tools, never hallucinate capabilities

### 4. LangGraph Workflows (`backend/agents/workflows/`)

**Purpose:** Complex, stateful multi-step processes

**Existing Workflows:**
- **EnrichmentWorkflow**: LinkedIn scraping → analysis → HITL → Airtable update

**Each workflow:**
- Has its own state schema
- Can interrupt for HITL
- Uses checkpointers for persistence
- Composed of reusable subagents

## Adding a New Workflow/Tool

### Step 1: Create the Workflow (if new)

```python
# backend/agents/workflows/my_workflow.py

from langgraph.graph import StateGraph
from typing import TypedDict

class MyWorkflowState(TypedDict):
    input: str
    result: str
    status: str

class MyWorkflow:
    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(MyWorkflowState)
        # Add nodes...
        return workflow.compile(checkpointer=MemorySaver())

def get_my_workflow():
    return MyWorkflow()
```

### Step 2: Create Tool Wrapper

```python
# backend/agents/tools/workflow_tools.py

from langchain.tools import tool
from pydantic import BaseModel, Field, validator

class MyToolInput(BaseModel):
    """Input schema with validation."""
    param: str = Field(description="Parameter description")

    @validator('param')
    def validate_param(cls, v):
        if not v:
            raise ValueError("param is required")
        return v

@tool(args_schema=MyToolInput)
async def my_new_tool(param: str) -> dict:
    """
    Tool description - what it does, when to use it.

    Args:
        param: Parameter description

    Returns:
        Dictionary with results
    """
    logger.info(f"TOOL_CALL: my_new_tool(param={param})")

    workflow = get_my_workflow()
    state = {'input': param, 'status': 'pending'}
    result = await workflow.graph.ainvoke(state)

    return {"success": True, "result": result}

# Add to registry
WORKFLOW_TOOLS = [
    enrich_linkedin_profile,
    my_new_tool,  # ← Add here!
]
```

### Step 3: Test

That's it! The ReAct agent automatically discovers the new tool and can use it.

```python
# Agent will now say things like:
# "I can help you with LinkedIn enrichment or [your new feature]"
```

## Security Best Practices

### 1. Always Use Input Schemas
```python
class ToolInput(BaseModel):
    field: str

    @validator('field')
    def validate_field(cls, v):
        # Validate here!
        return v
```

### 2. Log Tool Calls
```python
logger.info(f"TOOL_CALL: tool_name(params={params})")
```

### 3. Never Trust User Input
All user input goes through:
1. Guardrails (injection detection)
2. Pydantic validation
3. Tool-specific validation

### 4. Use Rate Limiting
Automatically applied to all requests via guardrails.

### 5. Audit Security Events
```python
from backend.agents.guardrails import get_guardrails

events = get_guardrails().get_security_events(last_n=100)
# Monitor for abuse patterns
```

## Observability

### Tool Execution Logs

All tool calls are logged:
```
TOOL_CALL: enrich_linkedin_profile(record_id=recABC...)
TOOL_EXECUTE: Starting enrichment workflow
TOOL_SUCCESS: Enriched 15 fields
```

### Security Event Logs

Security events are logged and stored:
```
SECURITY_EVENT: {
  "timestamp": "2024-01-15T10:30:00",
  "event_type": "injection_detected",
  "user_id": "rec123",
  "details": "ignore previous"
}
```

### Agent Reasoning Logs

Agent decisions are logged:
```
AGENT_RUN: Starting with thread_id=chat-abc123
AGENT_SUCCESS: Response generated
```

## Configuration

### Guardrails Settings

```python
# backend/agents/guardrails/security.py

GuardrailsManager(
    enable_injection_detection=True,
    enable_rate_limiting=True,
    enable_input_validation=True,
    max_calls_per_minute=10,  # Adjust as needed
    max_calls_per_hour=100
)
```

### Agent Settings

```python
# backend/agents/react_agent.py

ReActCRMAgent(
    model="gpt-4o",  # Or gpt-4o-mini for cost savings
    temperature=0.3,  # Lower = more deterministic
    max_iterations=10,  # Prevent infinite loops
    enable_guardrails=True
)
```

## Testing

### Test a New Tool

```python
from backend.agents.tools.workflow_tools import my_new_tool

result = await my_new_tool("test input")
assert result["success"] == True
```

### Test Guardrails

```python
from backend.agents.guardrails import PromptInjectionDetector

is_injection, pattern = PromptInjectionDetector.detect("ignore previous instructions")
assert is_injection == True
```

### Test Agent

```python
from backend.agents.react_agent import get_react_agent
from langchain_core.messages import HumanMessage

agent = get_react_agent()
result = await agent.run(
    messages=[HumanMessage(content="enrich this record")],
    config={"configurable": {"thread_id": "test-123"}}
)
assert result["success"] == True
```

## Future Enhancements

- [ ] Add search_contacts tool
- [ ] Add send_outreach tool
- [ ] Add analytics_report tool
- [ ] Implement token-level rate limiting
- [ ] Add cost tracking per user
- [ ] Implement user-specific tool permissions
- [ ] Add webhook notifications for security events
- [ ] Implement circuit breaker for external API calls

## Troubleshooting

### "Tool not found" error
→ Check that tool is added to `WORKFLOW_TOOLS` list

### "Guardrail blocked request"
→ Check security event logs: `get_guardrails().get_security_events()`

### "Agent not responding"
→ Check thread_id is being passed correctly in config

### "Rate limit exceeded"
→ Adjust limits in `GuardrailsManager` or reset user: `get_guardrails().rate_limiter.reset_user(user_id)`
