# LangGraph Interrupt Flow for HITL

## How Native Interrupts Work

LangGraph's native interrupt mechanism provides battle-tested HITL (Human-in-the-Loop) support:

### 1. Workflow Interruption

```python
# In enrichment workflow - HITL approval node
async def _hitl_approval_node(self, state):
    # Prepare data for UI
    hitl_data = {
        'workflow': 'enrichment',
        'record_id': state['airtable_record_id'],
        'update_fields': state['validated_fields'],
        # ... more data
    }

    # LangGraph interrupt - pauses execution
    user_response = interrupt(hitl_data)

    # When resumed, user_response contains approval
    approved = user_response.get('status') == 'approved'
    return {**state, 'hitl_approved': approved}
```

### 2. Execution with Thread ID

```python
# Start workflow with thread_id for tracking
config = {
    "configurable": {
        "thread_id": f"enrichment-{record_id}"
    }
}

# First invocation - runs until interrupt
result = await workflow.invoke(initial_state, config=config)

# Result contains interrupt data
if result is None:  # Interrupted
    # Get interrupt data from state
    state = workflow.get_state(config)
    hitl_data = state.values.get('hitl_data')
    # Send hitl_data to UI
```

### 3. Resume After Approval

```python
# User approves in UI, server receives response
user_response = {
    'status': 'approved',
    'edited_fields': {...}  # Optional edits
}

# Resume workflow with user input
config = {
    "configurable": {
        "thread_id": f"enrichment-{record_id}"
    }
}

# Continue from where it left off
result = await workflow.invoke(None, config=config, input=user_response)
```

## Server Implementation

### Start Enrichment (with interrupt support)

```python
@app.post("/enrich")
async def enrich_record(request):
    record_id = request.record_id

    # Create thread_id
    thread_id = f"enrichment-{record_id}-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    # Start workflow
    workflow = get_enrichment_workflow()
    result = await workflow.graph.ainvoke(initial_state, config=config)

    # Check if interrupted
    if result is None:
        # Get current state
        state = workflow.graph.get_state(config)

        # Extract HITL data
        hitl_data = state.values

        # Return to UI with thread_id
        return {
            "needs_approval": True,
            "thread_id": thread_id,
            "hitl_data": hitl_data
        }

    # Completed without interrupt
    return {"success": True, "result": result}
```

### Resume After Approval

```python
@app.post("/hitl/response")
async def hitl_response(request):
    thread_id = request.thread_id
    user_response = request.response

    # Resume workflow
    config = {"configurable": {"thread_id": thread_id}}
    workflow = get_enrichment_workflow()

    result = await workflow.graph.invoke(
        None,  # No new input, resume from checkpoint
        config=config,
        input=user_response  # User's approval/rejection
    )

    return {"success": True, "result": result}
```

## Chrome Extension Flow

```javascript
// 1. Start enrichment
const response = await fetch('/enrich', {
    method: 'POST',
    body: JSON.stringify({ record_id: '...' })
});

const data = await response.json();

if (data.needs_approval) {
    // 2. Show approval UI
    showApprovalPanel(data.hitl_data);

    // Store thread_id for resume
    const threadId = data.thread_id;

    // 3. When user approves
    document.getElementById('approve-btn').onclick = async () => {
        await fetch('/hitl/response', {
            method: 'POST',
            body: JSON.stringify({
                thread_id: threadId,
                response: {
                    status: 'approved',
                    edited_fields: getEditedFields()
                }
            })
        });
    };
}
```

## Benefits of Native Interrupts

✅ **Thread-safe** - Each workflow instance has unique thread_id
✅ **Persistent** - State survives server restarts (with SQLiteSaver)
✅ **Battle-tested** - Built into LangGraph, well-maintained
✅ **Simple** - Less custom code than manual checkpoint management
✅ **Concurrent** - Multiple workflows can pause independently

## Checkpointer Options

```python
# In-memory (current - simple but not persistent)
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()

# SQLite (persistent across restarts)
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

# PostgreSQL (production-ready)
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string("postgresql://...")
```

## State Tracking

```python
# Get current state of interrupted workflow
state = workflow.get_state(config)

# State contains:
# - values: Current state dict
# - next: Next nodes to execute
# - metadata: Execution metadata
# - config: Thread config

print(state.values)  # EnrichmentState dict
print(state.next)    # ['update_airtable'] (next node after resume)
```
