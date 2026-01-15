# Agent Execution Flow

This document shows the exact order of execution when a user sends a message.

---

## Complete Execution Order

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER SENDS MESSAGE                                           │
│    POST /api/chat/                                              │
│    { "message": "How is campaign X performing?",                │
│      "user_id": "test_user" }                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. API ENDPOINT (chat.py:send_message)                          │
│    - Create or verify session                                   │
│    - Build AgentInput object                                    │
│    - Call: await chat_conductor.invoke(agent_input)             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. CONDUCTOR.INVOKE() (base.py)                                 │
│    - Wraps process() call                                       │
│    - Adds timing and logging                                    │
│    - Call: await self.process(input_data)                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. CONDUCTOR.PROCESS() (conductor.py)                           │
│                                                                  │
│    Step 4.1: Store User Message                                 │
│    ├─→ session_manager.add_message()                            │
│    │   └─→ PostgreSQL INSERT into messages table                │
│    │                                                             │
│    Step 4.2: Retrieve Context                                   │
│    ├─→ memory_retrieval_tool.retrieve_context()                 │
│    │   ├─→ Get session history from PostgreSQL                  │
│    │   ├─→ Generate embedding for query (OpenAI)                │
│    │   └─→ Search similar learnings in pgvector                 │
│    │                                                             │
│    Step 4.3: Route to Agent(s)                                  │
│    ├─→ self._route_to_agents()                                  │
│    │   └─→ Keyword matching on message                          │
│    │       (e.g., "performance" → performance_diagnosis)         │
│    │                                                             │
│    Step 4.4: Invoke Selected Agent(s)                           │
│    ├─→ For each selected agent:                                 │
│    │   └─→ await agent.invoke(agent_input)  ──────┐             │
│    │                                                │            │
└────┼────────────────────────────────────────────────┼────────────┘
     │                                                │
     │                                                ▼
     │   ┌─────────────────────────────────────────────────────────┐
     │   │ 5. SPECIALIST AGENT.INVOKE()                            │
     │   │    (e.g., performance_agent)                            │
     │   │    - Call: await self.process(input_data)               │
     │   └────────────────────┬────────────────────────────────────┘
     │                        │
     │                        ▼
     │   ┌─────────────────────────────────────────────────────────┐
     │   │ 6. PERFORMANCE_AGENT.PROCESS()                          │
     │   │    (performance_agent.py)                               │
     │   │                                                          │
     │   │    Step 6.1: Extract IDs from Query                     │
     │   │    ├─→ self._extract_ids_from_query()                   │
     │   │    │   └─→ Parse campaign_id/advertiser_id from message │
     │   │    │                                                     │
     │   │    Step 6.2: Retrieve Memory Context                    │
     │   │    ├─→ memory_retrieval_tool.retrieve_context()         │
     │   │    │   └─→ Same as step 4.2 above                       │
     │   │    │                                                     │
     │   │    Step 6.3: Query Snowflake                            │
     │   │    ├─→ snowflake_tool.get_campaign_performance()        │
     │   │    │   ├─→ Check Redis cache (query hash)               │
     │   │    │   ├─→ If miss: Connect to Snowflake                │
     │   │    │   ├─→ Execute SQL query                            │
     │   │    │   ├─→ Cache results in Redis                       │
     │   │    │   └─→ Return data                                  │
     │   │    │                                                     │
     │   │    Step 6.4: Analyze Performance                        │
     │   │    ├─→ self._analyze_performance()                      │
     │   │    │   ├─→ Calculate trends (impressions, CTR, ROAS)    │
     │   │    │   ├─→ Identify issues (low CTR, poor pacing)       │
     │   │    │   └─→ Generate insights                            │
     │   │    │                                                     │
     │   │    Step 6.5: Generate LLM Response                      │
     │   │    ├─→ Build prompt with system + context + data        │
     │   │    ├─→ Call LLM (Claude Opus or GPT-4)                  │
     │   │    │   └─→ Get natural language response                │
     │   │    │                                                     │
     │   │    Step 6.6: Log Decision                               │
     │   │    ├─→ decision_logger.log_decision()                   │
     │   │    │   └─→ PostgreSQL INSERT into agent_decisions       │
     │   │    │                                                     │
     │   │    Step 6.7: Extract Learnings                          │
     │   │    ├─→ self._extract_learnings()                        │
     │   │    │   └─→ Store in PostgreSQL agent_learnings          │
     │   │    │       (with embeddings for future retrieval)       │
     │   │    │                                                     │
     │   │    Return: AgentOutput                                  │
     │   │    └─→ { response, reasoning, tools_used, confidence }  │
     │   └────────────────────┬────────────────────────────────────┘
     │                        │
     │                        │ Return to Conductor
     │                        ▼
     │   ┌─────────────────────────────────────────────────────────┐
     │   │ 7. CONDUCTOR: Aggregate Responses                       │
     │◄──┤    - If single agent: Use response directly             │
     │   │    - If multiple agents: Synthesize responses           │
     │   │                                                          │
     │   │    Step 7.1: Store Assistant Message                    │
     │   │    ├─→ session_manager.add_message()                    │
     │   │    │   └─→ PostgreSQL INSERT into messages table        │
     │   │    │                                                     │
     │   │    Return: AgentOutput                                  │
     │   │    └─→ Final synthesized response                       │
     │   └────────────────────┬────────────────────────────────────┘
     │                        │
     │                        │ Return to API
     └────────────────────────┼────────────────────────────────────┐
                              │                                    │
                              ▼                                    │
┌─────────────────────────────────────────────────────────────────┤
│ 8. API: Build Response (chat.py)                                │
│    - Calculate total execution time                             │
│    - Return ChatResponse to user                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. USER RECEIVES RESPONSE                                       │
│    {                                                             │
│      "response": "Campaign X is underperforming...",             │
│      "session_id": "a68f17d2-...",                               │
│      "agent_name": "chat_conductor",                             │
│      "reasoning": "Stored user message...",                      │
│      "tools_used": ["memory_retrieval", "snowflake_query"],     │
│      "confidence": 0.95,                                         │
│      "execution_time_ms": 4227                                   │
│    }                                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Points

### 1. **Entry Point**: API Route
- `POST /api/chat/` in `chat.py`
- Creates/verifies session
- Calls conductor

### 2. **Orchestration**: Conductor Agent
- Routes based on keywords
- Invokes one or more specialist agents
- Aggregates responses
- Stores messages in session

### 3. **Execution**: Specialist Agent (e.g., Performance)
- Retrieves memory context
- Queries Snowflake for data
- Analyzes data
- Generates LLM response
- Logs decision
- Extracts learnings

### 4. **Response Path**: Back up the chain
- Specialist → Conductor → API → User

---

## Database Interactions

Throughout execution, the system interacts with:

1. **PostgreSQL**:
   - Read/write session messages (steps 4.1, 7.1)
   - Store agent decisions (step 6.6)
   - Store learnings with embeddings (step 6.7)
   - Query similar learnings (step 4.2, 6.2)

2. **Redis**:
   - Cache Snowflake query results (step 6.3)
   - Cache session info (step 2, 4.1)

3. **Snowflake**:
   - Execute performance queries (step 6.3)
   - Returns campaign metrics

4. **OpenAI API**:
   - Generate embeddings for semantic search (step 4.2, 6.2)

5. **Anthropic/OpenAI API**:
   - Generate LLM responses (step 6.5)

---

## Timing Breakdown (Example: 4.2s total)

Based on your test result:

```
Total: 4227ms

├─ Session Management:        ~200ms  (5%)
│  └─ PostgreSQL queries
│
├─ Memory Retrieval:          ~300ms  (7%)
│  ├─ Embedding generation: 100ms
│  └─ Vector search: 200ms
│
├─ Snowflake Query:          ~1500ms (35%)  ← BIGGEST BOTTLENECK
│  ├─ Connection: 1000ms
│  └─ Query execution: 500ms
│
├─ Data Analysis:             ~100ms  (2%)
│  └─ Python calculations
│
├─ LLM Response:             ~2000ms (47%)  ← SECOND BIGGEST
│  └─ Claude Opus API call
│
└─ Decision Logging:          ~127ms  (3%)
   └─ PostgreSQL inserts
```

---

## Parallel vs Sequential

**Currently: All Sequential** (one step after another)

**Potential Optimization**: Parallel execution
- Memory retrieval + Snowflake query in parallel
- Multiple specialist agents in parallel
- Would require async refactoring

---

## Differences from LangGraph

**Current Implementation**:
- Direct function calls (`await agent.process()`)
- Manual orchestration in Python
- No tool calling loops
- No conditional routing graphs

**With Full LangGraph** (Future):
- StateGraph with nodes and edges
- Agents decide which tools to call
- ReAct loops for complex reasoning
- Conditional branching based on results

See `FUTURE_IMPROVEMENTS.md` for details.

---

## Call Stack Summary

```python
# User request
POST /api/chat/

# Call stack:
api.routes.chat.send_message()
  └─> chat_conductor.invoke()
      └─> chat_conductor.process()
          ├─> session_manager.add_message()          # Store user message
          ├─> memory_retrieval_tool.retrieve_context() # Get context
          ├─> conductor._route_to_agents()           # Keyword routing
          └─> performance_agent.invoke()             # Selected agent
              └─> performance_agent.process()
                  ├─> memory_retrieval_tool.retrieve_context()
                  ├─> snowflake_tool.get_campaign_performance()
                  ├─> performance_agent._analyze_performance()
                  ├─> llm.invoke()                    # Generate response
                  ├─> decision_logger.log_decision()
                  └─> return AgentOutput
          └─> conductor._synthesize_responses()      # Aggregate
          └─> session_manager.add_message()          # Store assistant message
          └─> return AgentOutput
      └─> return AgentOutput
  └─> return ChatResponse
```

---

## How to Trace Execution

### 1. Check Logs
```bash
docker-compose logs backend --tail=100 -f
```

### 2. Enable Debug Logging
In `.env`:
```
LOG_LEVEL=DEBUG
```

### 3. Use pycallgraph2 (See visualization)
```bash
pycallgraph graphviz --max-depth=10 -- python test_single_request.py
```

### 4. Check PostgreSQL for Decision History
```sql
SELECT
    agent_name,
    decision_type,
    tools_used,
    execution_time_ms,
    timestamp
FROM agent_decisions
ORDER BY timestamp DESC
LIMIT 10;
```

---

## Related Documentation

- `ARCHITECTURE.md` - System architecture overview
- `docs/architecture_dependencies.svg` - Module dependency graph
- `FUTURE_IMPROVEMENTS.md` - LangGraph refactor plan
