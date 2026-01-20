# Future Improvements

This document tracks planned enhancements and improvements to the system.

## Routing Agent: Context-Aware Clarification Requests

### Problem Statement

Currently, when a user query is unclear, the routing agent asks for clarification without any context from previous messages in the conversation. This can lead to generic clarification requests that don't leverage the conversation history.

**Example:**
- User: "How is Quiz performing?"
- Assistant: "Here's the performance data..."
- User: "What about the budget?" (unclear - which budget?)
- Current behavior: Generic clarification request
- Desired behavior: "I see you asked about Quiz performance earlier. Are you asking about the Quiz advertiser's budget for the same time period?"

### Current State

- ✅ `OrchestratorState` has `session_history: List[Dict[str, Any]]` field
- ✅ `routing_agent.route()` accepts `session_context` parameter (but unused)
- ✅ `SessionManager.get_messages()` exists and can retrieve message history
- ❌ `session_history` is initialized as empty `[]` in `create_initial_orchestrator_state()`
- ❌ Previous messages are not loaded or passed to routing agent
- ❌ Clarification messages don't use conversation context

### Proposed Design

#### Option A: Load History in Initial State (Recommended)

**Approach:** Load recent messages when creating initial state, pass them through the state, and use them in routing for clarification.

**Pros:**
- Simple and consistent
- History available to all nodes if needed
- Clear data flow

**Cons:**
- Always loads messages (even if not needed)
- Slight performance overhead

#### Option B: Load On-Demand in Routing Node

**Approach:** Load messages only when clarification is needed.

**Pros:**
- More efficient (only loads when needed)
- Reduces unnecessary database calls

**Cons:**
- More complex logic
- History not available to other nodes

**Recommendation:** Option A - Load recent messages upfront for simplicity and consistency.

### Implementation Plan

#### Step 1: Load Messages in `orchestrator.process()`

Load session history before creating initial state, then pass it to the state creator.

**File:** `backend/src/agents/orchestrator.py`

**Changes:**
```python
async def process(self, input_data: AgentInput) -> AgentOutput:
    """Process a query through the orchestrator."""
    start_time = time.time()

    try:
        # Load session history if session exists
        session_history = []
        if input_data.session_id:
            from ..memory.session_manager import session_manager
            messages = await session_manager.get_messages(
                session_id=input_data.session_id,
                limit=10  # Last 10 messages for context
            )
            session_history = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

        # Create initial state with session history
        initial_state = create_initial_orchestrator_state(
            query=input_data.message,
            session_id=input_data.session_id,
            user_id=input_data.user_id,
            session_history=session_history  # Pass loaded history
        )
        
        # ... rest of method
```

#### Step 2: Update State Creator Signature

Add `session_history` parameter to `create_initial_orchestrator_state()`.

**File:** `backend/src/schemas/agent_state.py`

**Changes:**
```python
def create_initial_orchestrator_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str,
    session_history: Optional[List[Dict[str, Any]]] = None  # New parameter
) -> OrchestratorState:
    """Create initial state for Orchestrator agent (RouteFlow)."""
    return OrchestratorState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        session_history=session_history or [],  # Use provided or empty
        relevant_learnings=[],
        # ... rest of fields
    )
```

#### Step 3: Pass Session History to Routing Agent

Use `session_history` from state in `_routing_node()`.

**File:** `backend/src/agents/orchestrator.py`

**Changes:**
```python
async def _routing_node(self, state: OrchestratorState) -> Dict[str, Any]:
    """Route query to appropriate specialist agents."""
    query = state["query"]
    session_history = state.get("session_history", [])

    logger.info("Routing query", query=query[:50])

    # Emit progress: started
    await self._emit_progress("routing", "started", {"message": "Routing query to specialist agents..."})

    # Use routing agent with session context
    routing_result = await routing_agent.route(
        query=query,
        session_context={
            "session_id": state.get("session_id"),
            "previous_messages": session_history
        }
    )
    
    # ... rest of method
```

#### Step 4: Enhance Clarification Messages

Use previous messages to build context-aware clarification prompts.

**File:** `backend/src/agents/routing_agent.py`

**Changes:**
```python
async def route(
    self,
    query: str,
    session_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Route a query to appropriate specialist agent(s).
    
    Args:
        query: User query
        session_context: Optional session context with previous_messages
    """
    previous_messages = []
    if session_context:
        previous_messages = session_context.get("previous_messages", [])
    
    # ... existing routing logic ...
    
    # When clarification is needed
    if not selected_agents or confidence < 0.3:
        clarification_message = self._build_clarification_message(
            query=query,
            previous_messages=previous_messages
        )
        return {
            "selected_agents": [],
            "clarification_needed": True,
            "clarification_message": clarification_message,
            # ... rest of fields
        }

def _build_clarification_message(
    self,
    query: str,
    previous_messages: List[Dict[str, Any]]
) -> str:
    """
    Build a context-aware clarification message.
    
    Args:
        query: Current unclear query
        previous_messages: Previous messages in the conversation
        
    Returns:
        Clarification message string
    """
    if not previous_messages:
        # No context - use generic message
        return (
            "I'm not sure what you're asking about. Could you please clarify?\n\n"
            "I can help with:\n"
            "- Campaign performance and metrics (CTR, ROAS, conversions)\n"
            "- Audience targeting and line item analysis\n"
            "- Creative performance and optimization\n"
            "- Budget pacing and spend analysis\n\n"
            "What would you like to know?"
        )
    
    # Extract recent user queries for context
    recent_queries = []
    for msg in previous_messages[-6:]:  # Last 3 exchanges (user + assistant pairs)
        if msg.get("role") == "user":
            recent_queries.append(msg.get("content", ""))
    
    context_snippet = ""
    if recent_queries:
        last_query = recent_queries[-1]
        context_snippet = (
            f"I see you asked about '{last_query[:100]}' earlier. "
        )
    
    return (
        f"{context_snippet}"
        f"Your current question '{query}' is a bit unclear. Could you clarify what you'd like to know?\n\n"
        "I can help with:\n"
        "- Campaign performance and metrics (CTR, ROAS, conversions)\n"
        "- Audience targeting and line item analysis\n"
        "- Creative performance and optimization\n"
        "- Budget pacing and spend analysis\n\n"
        "What would you like to know?"
    )
```

### Design Considerations

#### 1. How Many Previous Messages?

**Recommendation:** Last 5-10 messages (configurable)

- Provides enough context for clarification
- Not too much to overwhelm the prompt
- Can be made configurable via settings

**Implementation:**
```python
limit = settings.session_history_limit or 10
messages = await session_manager.get_messages(
    session_id=session_id,
    limit=limit
)
```

#### 2. Message Format

**Current:** `ChatMessage` objects with `role`, `content`, `timestamp`, etc.

**For State:** Simple dict format `{"role": "user", "content": "..."}`

**Rationale:**
- Lightweight
- Easy to serialize
- Contains essential information

#### 3. When to Use Previous Messages

**Options:**
- **Always:** Include in all routing decisions (more context-aware)
- **Only when clarification needed:** Use only when query is unclear (more efficient)

**Recommendation:** Start with "only when clarification needed", can expand later.

#### 4. Privacy & Filtering

**Considerations:**
- Should we filter sensitive data from history?
- Should we limit context to same session only?
- Should we include metadata (agent_name, timestamp)?

**Current Approach:** Include all messages from the session, no filtering.

**Future Enhancement:** Add configurable filtering for sensitive data.

### Example Scenarios

#### Scenario 1: First Message (No Context)

**User:** "hello"

**Current Response:**
```
I'm not sure what you're asking about. Could you please clarify?
```

**With Context-Aware (No Change):**
```
I'm not sure what you're asking about. Could you please clarify?
```

#### Scenario 2: Follow-up Query (With Context)

**Conversation:**
- User: "How is Quiz performing?"
- Assistant: "Here's Quiz's performance data for January 2026..."
- User: "What about the budget?" (unclear)

**Current Response:**
```
I'm not sure what you're asking about. Could you please clarify?
```

**With Context-Aware:**
```
I see you asked about 'How is Quiz performing?' earlier. Your current question 'What about the budget?' is a bit unclear. Could you clarify what you'd like to know?

Are you asking about:
- Quiz advertiser's budget for January 2026?
- Budget pacing compared to the performance we just discussed?
- Budget allocation across insertion orders?

What would you like to know?
```

#### Scenario 3: Ambiguous Query (With Context)

**Conversation:**
- User: "Show me audience performance"
- Assistant: "Here's audience performance data..."
- User: "compare that" (unclear - compare to what?)

**With Context-Aware:**
```
I see you asked about 'Show me audience performance' earlier. Your current question 'compare that' is a bit unclear. Could you clarify what you'd like to compare?

- Compare to previous period?
- Compare to other audiences?
- Compare to campaign performance?

What would you like to know?
```

### Testing Plan

1. **Unit Tests:**
   - Test `_build_clarification_message()` with no context
   - Test `_build_clarification_message()` with context
   - Test message loading in `process()`

2. **Integration Tests:**
   - Test full flow with session history
   - Test clarification request with previous messages
   - Test backward compatibility (no session_id)

3. **Manual Testing:**
   - Start new conversation → unclear query → verify generic message
   - Multi-turn conversation → unclear query → verify context-aware message
   - Test with various conversation lengths

### Performance Considerations

- **Database Query:** One additional query per request (if session exists)
- **Memory:** ~1-2KB per message (10 messages = ~10-20KB)
- **Latency:** Minimal impact (~5-10ms for message retrieval)

**Mitigation:**
- Cache recent messages in Redis
- Limit to last 10 messages
- Only load when session_id exists

### Future Enhancements

1. **Semantic Context:** Use embeddings to find relevant past queries, not just recent ones
2. **Context Summarization:** Summarize long conversation history instead of raw messages
3. **Multi-Session Context:** Allow referencing previous sessions
4. **User Preferences:** Learn from clarification patterns to improve routing

### Related Files

- `backend/src/agents/orchestrator.py` - Main orchestrator logic
- `backend/src/agents/routing_agent.py` - Routing agent implementation
- `backend/src/schemas/agent_state.py` - State definitions
- `backend/src/memory/session_manager.py` - Session and message management

### Status

**Status:** 📋 Planned

**Priority:** Medium

**Estimated Effort:** 2-3 hours

**Dependencies:** None

---

## Other Future Improvements

*Additional improvements will be documented here as they are identified.*

