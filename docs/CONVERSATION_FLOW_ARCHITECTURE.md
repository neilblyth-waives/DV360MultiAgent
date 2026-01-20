# Conversation Flow Architecture

**Last Updated**: 2026-01-20
**Purpose**: Explains how conversations flow through the system, how each node processes data, and how messages are persisted to the database.

---

## Overview

The DV360 Agent System uses a **RouteFlow architecture** built on LangGraph. Each user message flows through multiple nodes, with conversation history persisted to PostgreSQL for context awareness.

```
User Message
     ↓
┌─────────────────────────────────────────────────────────────┐
│                     API Layer (chat.py)                      │
│  1. Save user message to DB                                  │
│  2. Call orchestrator                                        │
│  3. Save assistant response to DB                            │
└─────────────────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────────────────┐
│                  Orchestrator (LangGraph)                    │
│                                                              │
│  routing → [clarify?] → gate → invoke_agents → diagnosis     │
│              ↓                        ↓                      │
│       generate_response    recommendation → validation       │
│              ↓                        ↓                      │
│            END ←──────────── generate_response → END         │
└─────────────────────────────────────────────────────────────┘
     ↓
Response to User
```

---

## Database Schema

### Sessions Table
Stores conversation sessions.

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    metadata JSONB
);
```

### Messages Table
Stores individual messages within sessions.

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    role VARCHAR NOT NULL,           -- 'user' or 'assistant'
    content TEXT NOT NULL,           -- The message text
    agent_name VARCHAR,              -- Which agent responded (null for user)
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    metadata JSONB                   -- Additional data (confidence, execution_time, etc.)
);
```

---

## Message Persistence Flow

### 1. API Layer (`chat.py`)

When a user sends a message, the API endpoint handles persistence:

```python
@router.post("/stream")
async def send_message_stream(request: ChatRequest):
    # Step 1: Create or get session
    session_id = request.session_id or await session_manager.create_session(...)

    # Step 2: SAVE USER MESSAGE TO DATABASE
    await session_manager.add_message(ChatMessageCreate(
        session_id=session_id,
        role="user",
        content=request.message,      # e.g., "How is Quiz performing?"
        agent_name=None,
        metadata={}
    ))

    # Step 3: Process through orchestrator
    output = await orchestrator.invoke_with_progress(agent_input, progress_callback)

    # Step 4: SAVE ASSISTANT RESPONSE TO DATABASE
    await session_manager.add_message(ChatMessageCreate(
        session_id=session_id,
        role="assistant",
        content=output.response,       # e.g., "Here's the performance analysis..."
        agent_name=output.agent_name,  # e.g., "orchestrator"
        metadata={
            "confidence": output.confidence,
            "execution_time_ms": execution_time_ms
        }
    ))
```

**Database State After Each Message:**

| Message # | role | content | agent_name |
|-----------|------|---------|------------|
| 1 | user | "123" | NULL |
| 2 | assistant | "What would you like to analyze?..." | orchestrator |
| 3 | user | "quiz performance for two weeks" | NULL |
| 4 | assistant | "Just to confirm - Sunday-Saturday?" | orchestrator |
| 5 | user | "Bang on thank you" | NULL |
| 6 | assistant | "Here's the Quiz performance..." | orchestrator |

---

## Orchestrator Nodes

### Node 1: Routing (`_routing_node`)

**Purpose**: Analyze user query and select appropriate specialist agent(s).

**Database Interaction**:
- READS conversation history from `messages` table
- Does NOT write to database

```python
async def _routing_node(self, state: OrchestratorState) -> Dict[str, Any]:
    query = state["query"]
    session_id = state.get("session_id")

    # FETCH CONVERSATION HISTORY FROM DATABASE
    conversation_history = []
    if session_id:
        messages = await session_manager.get_messages(session_id, limit=10)
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    # Pass history to routing agent for context
    routing_result = await routing_agent.route(
        query,
        conversation_history=conversation_history
    )

    # Check if clarification needed
    if routing_result.get("clarification_needed"):
        return {
            "clarification_needed": True,
            "clarification_message": routing_result.get("clarification_message"),
            "selected_agents": [],
            ...
        }

    return {
        "selected_agents": routing_result.get("selected_agents"),
        "routing_confidence": routing_result.get("confidence"),
        "clarification_needed": False,
        ...
    }
```

**Routing Agent Prompt (with context):**
```
CONVERSATION HISTORY (recent messages for context):
User: 123
Assistant: What would you like to analyze?...
User: quiz performance for two weeks
Assistant: Just to confirm - Sunday-Saturday?

IMPORTANT: The current query may be a follow-up or clarification.
- If the user's query is short (like "yes", "budget"), interpret it in context.

User query: "Bang on thank you"

Your response:
AGENTS: performance_diagnosis
REASONING: User confirmed the date format, proceeding with performance analysis
CONFIDENCE: 0.9
```

**Output**:
- `selected_agents`: List of agents to invoke
- `clarification_needed`: Boolean
- `clarification_message`: Message to ask user (if needed)

---

### Node 2: Routing Decision (`_routing_decision`)

**Purpose**: Conditional routing based on whether clarification is needed.

**Database Interaction**: None

```python
def _routing_decision(self, state: OrchestratorState) -> str:
    if state.get("clarification_needed", False):
        return "clarify"      # → Skip to generate_response
    else:
        return "proceed"      # → Continue to gate node
```

**Flow:**
```
routing_decision
    ├── "clarify" → generate_response (shows clarification message)
    └── "proceed" → gate (continues normal flow)
```

---

### Node 3: Gate (`_gate_node`)

**Purpose**: Validate the routing decision and apply business rules.

**Database Interaction**: None

```python
async def _gate_node(self, state: OrchestratorState) -> Dict[str, Any]:
    # Skip if clarification needed
    if state.get("clarification_needed"):
        return {"gate_result": {"valid": False, ...}}

    # Validate routing
    gate_result = gate_node.validate(
        query=state["query"],
        selected_agents=state["selected_agents"],
        routing_confidence=state["routing_confidence"],
        user_id=state["user_id"]
    )

    return {"gate_result": gate_result, ...}
```

**Validation Rules:**
1. Query length (warns if < 3 words)
2. Agent count (max 3 agents)
3. Routing confidence (warns if < 0.4)
4. Valid agent names

**Output**: `gate_result` with `valid`, `approved_agents`, `warnings`

---

### Node 4: Gate Decision (`_gate_decision`)

**Purpose**: Conditional routing based on gate validation.

**Database Interaction**: None

```python
def _gate_decision(self, state: OrchestratorState) -> str:
    gate_result = state.get("gate_result", {})
    if gate_result.get("valid", False):
        return "proceed"      # → invoke_agents
    else:
        return "block"        # → generate_response (error)
```

---

### Node 5: Invoke Agents (`_invoke_agents_node`)

**Purpose**: Execute the approved specialist agents.

**Database Interaction**:
- Agents may READ from various tables (performance data, etc.)
- Does NOT write conversation messages

```python
async def _invoke_agents_node(self, state: OrchestratorState) -> Dict[str, Any]:
    approved_agents = state["gate_result"]["approved_agents"]

    agent_results = {}
    for agent_name in approved_agents:
        agent = self.specialist_agents.get(agent_name)

        # Create input for agent
        agent_input = AgentInput(
            message=state["query"],
            session_id=state["session_id"],
            user_id=state["user_id"]
        )

        # Invoke agent (may query Snowflake, etc.)
        agent_output = await agent.invoke(agent_input)
        agent_results[agent_name] = agent_output

    return {"agent_results": agent_results, ...}
```

**Available Agents:**
| Agent | Description |
|-------|-------------|
| `performance_diagnosis` | Campaign metrics at IO level |
| `budget_risk` | Budget pacing and risk analysis |
| `audience_targeting` | Line item and audience analysis |
| `creative_inventory` | Creative performance by name/size |
| `delivery_optimization` | Combined creative + audience |

---

### Node 6: Diagnosis (`_diagnosis_node`)

**Purpose**: Analyze agent results to find root causes and patterns.

**Database Interaction**: None (works with in-memory agent results)

```python
async def _diagnosis_node(self, state: OrchestratorState) -> Dict[str, Any]:
    agent_results = state["agent_results"]

    # Optimization: Skip for single-agent informational queries
    if len(approved_agents) == 1 and self._is_informational_query(query):
        return {
            "diagnosis": {"summary": agent_output.response, "severity": "low"},
            ...
        }

    # Full diagnosis for complex queries
    diagnosis = await diagnosis_agent.diagnose(agent_results, query)

    return {
        "diagnosis": diagnosis,
        "severity_assessment": diagnosis.get("severity"),
        ...
    }
```

**Output**: `diagnosis` with `summary`, `severity`, `root_causes`, `correlations`

---

### Node 7: Early Exit Decision (`_early_exit_decision`)

**Purpose**: Skip recommendations for simple informational queries.

**Database Interaction**: None

```python
def _early_exit_decision(self, state: OrchestratorState) -> str:
    exit_decision = early_exit_node.should_exit_early(
        diagnosis=state["diagnosis"],
        agent_results=state["agent_results"],
        query=state["query"]
    )

    if exit_decision.get("exit"):
        return "exit"         # → generate_response (skip recommendations)
    else:
        return "continue"     # → recommendation
```

**Exit Criteria:**
- No issues found
- Informational query with low severity
- Simple status check

---

### Node 8: Recommendation (`_recommendation_node`)

**Purpose**: Generate actionable recommendations based on diagnosis.

**Database Interaction**: None

```python
async def _recommendation_node(self, state: OrchestratorState) -> Dict[str, Any]:
    rec_result = await recommendation_agent.generate_recommendations(
        diagnosis=state["diagnosis"],
        agent_results=state["agent_results"],
        query=state["query"]
    )

    return {
        "recommendations": rec_result.get("recommendations"),
        "recommendation_confidence": rec_result.get("confidence"),
        ...
    }
```

**Output**: List of recommendations with `priority`, `action`, `reason`, `expected_impact`

---

### Node 9: Validation (`_validation_node`)

**Purpose**: Validate recommendations before returning to user.

**Database Interaction**: None

```python
async def _validation_node(self, state: OrchestratorState) -> Dict[str, Any]:
    validation_result = validation_agent.validate_recommendations(
        recommendations=state["recommendations"],
        diagnosis=state["diagnosis"],
        agent_results=state["agent_results"]
    )

    return {
        "validated_recommendations": validation_result.get("validated_recommendations"),
        "validation_warnings": validation_result.get("warnings"),
        ...
    }
```

**Validation Rules:**
- Required fields (action, priority, reason)
- Conflict detection
- Vagueness check
- Severity alignment

---

### Node 10: Generate Response (`_generate_response_node`)

**Purpose**: Format the final response to send to the user.

**Database Interaction**: None (response is saved by API layer after this returns)

```python
async def _generate_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
    # Priority 1: Clarification needed
    if state.get("clarification_needed"):
        final_response = state.get("clarification_message")
        confidence = 0.0

    # Priority 2: Early exit
    elif state.get("should_exit_early"):
        final_response = state.get("final_response")
        confidence = 0.8

    # Priority 3: Gate blocked
    elif not state.get("gate_result", {}).get("valid", True):
        final_response = f"Unable to process: {gate_result.get('reason')}"
        confidence = 0.0

    # Priority 4: Normal response with recommendations
    else:
        final_response = self._build_response(state)
        confidence = state.get("recommendation_confidence", 0.8)

    return {
        "final_response": final_response,
        "confidence": confidence,
        ...
    }
```

---

## Complete Flow Example

### Conversation: Clarification → Follow-up → Confirmation

**Message 1: User sends "123"**

```
1. API saves to DB: {role: "user", content: "123"}

2. Orchestrator flow:
   routing (no history) → clarification_needed=True
        ↓
   routing_decision → "clarify"
        ↓
   generate_response → "What would you like to analyze?"
        ↓
   END

3. API saves to DB: {role: "assistant", content: "What would you like..."}
```

**Message 2: User sends "quiz performance for two weeks"**

```
1. API saves to DB: {role: "user", content: "quiz performance..."}

2. Orchestrator flow:
   routing (sees: "123" → clarification) → understands context
        ↓
   Asks for date clarification (confidence 0.9 but needs specifics)
        ↓
   generate_response → "Just to confirm - Sunday-Saturday?"
        ↓
   END

3. API saves to DB: {role: "assistant", content: "Just to confirm..."}
```

**Message 3: User sends "Bang on thank you"**

```
1. API saves to DB: {role: "user", content: "Bang on thank you"}

2. Orchestrator flow:
   routing (sees full history) → understands "Bang on" = confirmation
        ↓
   routing_decision → "proceed"
        ↓
   gate → validates, approved_agents=["performance_diagnosis"]
        ↓
   gate_decision → "proceed"
        ↓
   invoke_agents → runs performance_diagnosis agent
        ↓
   diagnosis → analyzes results
        ↓
   early_exit_decision → "exit" (informational query)
        ↓
   generate_response → formats performance data
        ↓
   END

3. API saves to DB: {role: "assistant", content: "Here's Quiz performance..."}
```

---

## Database Queries

### Fetching Conversation History

Used by routing node to get context:

```sql
SELECT id, session_id, role, content, agent_name, timestamp, metadata
FROM messages
WHERE session_id = $1
ORDER BY timestamp ASC
LIMIT 10;
```

### Saving a Message

Used by API layer after each exchange:

```sql
INSERT INTO messages (session_id, role, content, agent_name, metadata)
VALUES ($1, $2, $3, $4, $5)
RETURNING id;
```

### Updating Session Timestamp

Triggered after each message:

```sql
UPDATE sessions
SET updated_at = NOW()
WHERE id = $1;
```

---

## Summary

| Component | Reads from DB | Writes to DB |
|-----------|---------------|--------------|
| API Layer (`chat.py`) | - | messages (user + assistant) |
| Routing Node | messages (history) | - |
| Gate Node | - | - |
| Invoke Agents | Snowflake (external) | - |
| Diagnosis Node | - | - |
| Recommendation Node | - | - |
| Validation Node | - | - |
| Generate Response | - | - |

**Key Points:**
1. **Only the API layer writes to the messages table** - nodes don't save messages
2. **Only the routing node reads conversation history** - to understand context
3. **Messages are saved BEFORE and AFTER orchestrator processing** - ensures full history
4. **Session ID links all messages** - maintains conversation context across requests
