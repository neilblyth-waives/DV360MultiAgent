# DV360 Agent System - Complete Summary for Future Agents

**Last Updated**: 2026-01-15
**Status**: ✅ Production Ready - RouteFlow Architecture Fully Operational
**Primary Coordinator**: Orchestrator (RouteFlow)
**API Version**: v1

---

## 📋 Quick Reference

### What This System Does
Multi-agent DV360 (Display & Video 360) analysis system that:
- Routes user queries to specialist agents using LLM-based intelligent routing
- Analyzes campaign performance, budget, creative, and audience data from Snowflake
- Generates root cause diagnoses across multiple perspectives
- Provides validated, actionable recommendations
- Maintains conversation history and learns from past interactions using pgvector

### Current Production Setup
✅ **Active Coordinator**: Orchestrator (RouteFlow) at `backend/src/agents/orchestrator.py`
✅ **API Endpoint**: `/api/chat/` routes to Orchestrator
✅ **Active Agents**: PerformanceAgent (ReAct), DeliveryAgentLangGraph, BudgetRiskAgent (ReAct)
✅ **Memory**: PostgreSQL + pgvector + Redis + OpenAI embeddings
✅ **Tracing**: LangSmith (if enabled)
✅ **Backend Running**: FastAPI on port 8000

---

## 🏗️ Architecture Overview

### RouteFlow Pattern (7-Phase Pipeline)

```
┌────────────────────────────────────────────────────────────────┐
│                    User Query via API                           │
│                  POST /api/chat/                                │
└───────────────────────────┬────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│               ORCHESTRATOR (Main Controller)                    │
│              backend/src/agents/orchestrator.py                │
└────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
┌───────▼────────┐                   ┌─────────▼──────────┐
│  PHASE 1:      │                   │   PHASE 2:         │
│  ROUTING       │──────────────────►│   GATE             │
│  (LLM-based)   │                   │   (Validation)     │
└────────────────┘                   └─────────┬──────────┘
                                               │
                                    ┌──────────┴───────────┐
                                    │                      │
                              (valid) ▼              (blocked) ▼
                        ┌──────────────────┐   ┌─────────────┐
                        │  PHASE 3:        │   │  Error      │
                        │  INVOKE AGENTS   │   │  Response   │
                        │  (Parallel)      │   └─────────────┘
                        └────────┬─────────┘
                                 │
        ┌────────────────────────┴────────────────────────┐
        │                                                  │
┌───────▼─────────┐  ┌──────────────┐  ┌────────────────┐
│ Performance     │  │  Delivery    │  │  Budget Risk   │
│ Agent           │  │  Agent       │  │  Agent         │
│ (LangGraph)     │  │ (LangGraph)  │  │  (ReAct)       │
└───────┬─────────┘  └──────┬───────┘  └────────┬───────┘
        │                   │                    │
        └───────────────────┴────────────────────┘
                            │
                    ┌───────▼───────┐
                    │  PHASE 4:     │
                    │  DIAGNOSIS    │
                    │  (Root Cause) │
                    └───────┬───────┘
                            │
                    ┌───────▼────────┐
                    │  PHASE 5:      │
                    │  EARLY EXIT    │
                    │  (Conditional) │
                    └───────┬────────┘
                            │
                ┌───────────┴────────────┐
                │                        │
         (exit early)              (continue)
                │                        │
                ▼                        ▼
        ┌──────────────┐      ┌──────────────────┐
        │  Skip to     │      │  PHASE 6:        │
        │  Response    │      │  RECOMMENDATION  │
        └──────────────┘      │  (Generate)      │
                              └────────┬─────────┘
                                       │
                               ┌───────▼──────────┐
                               │  PHASE 7:        │
                               │  VALIDATION      │
                               │  (Check Quality) │
                               └────────┬─────────┘
                                        │
                            ┌───────────▼────────────┐
                            │  GENERATE RESPONSE     │
                            │  (Markdown formatted)  │
                            └────────────────────────┘
```

### Component Breakdown

| Phase | Component | File | Type | Purpose |
|-------|-----------|------|------|---------|
| 1 | Routing Agent | `routing_agent.py` | LLM-based | Selects which specialist agents to use |
| 2 | Gate Node | `gate_node.py` | Rule-based | Validates query & routing, applies business rules |
| 3 | Performance Agent | `performance_agent_langgraph.py` | LangGraph + ReAct | Campaign performance analysis |
| 3 | Delivery Agent | `delivery_agent_langgraph.py` | LangGraph + ReAct | Creative + Audience analysis |
| 3 | Budget Risk Agent | `budget_risk_agent.py` | ReAct minimal | Budget pacing & risk assessment |
| 4 | Diagnosis Agent | `diagnosis_agent.py` | LLM-based | Root cause analysis across agent results |
| 5 | Early Exit Node | `early_exit_node.py` | Rule-based | Determines if recommendations needed |
| 6 | Recommendation Agent | `recommendation_agent.py` | LLM-based | Generates prioritized recommendations |
| 7 | Validation Agent | `validation_agent.py` | Rule-based | Validates recommendations for conflicts |

---

## 🔧 All Available Tools

### Snowflake Tools (1 tool)

#### 1. `execute_custom_snowflake_query` - **ONLY Snowflake Tool**
```python
# LLM generates arbitrary SQL queries dynamically
# Used by ALL ReAct agents for flexible data access
# File: backend/src/tools/snowflake_tools.py

Input: query (str) - SQL query to execute
Returns: JSON string - Query results as JSON array

Available Tables:
  - reports.reporting_revamp.ALL_PERFORMANCE_AGG (main performance data)
  - reports.reporting_revamp.creative_name_agg (creative performance)
  - reports.multi_agent.DV360_BUDGETS_QUIZ (budget data)

Schema Documentation: See docs/SNOWFLAKE_SCHEMA_REFERENCE.md

Example Usage:
  - Agents build SQL queries based on user query
  - Full schema information provided in system prompts
  - LLM decides what data is needed and constructs query
```

**Note**: All bespoke query tools removed (query_campaign_performance, query_budget_pacing, query_audience_performance, query_creative_performance). Agents now build SQL dynamically using complete schema information in their system prompts.

### Memory Tools (2 tools)

#### 6. `retrieve_relevant_learnings`
```python
# Semantic search over past learnings using pgvector
# File: backend/src/tools/memory_tools.py

Input: query (str), user_id (str), top_k (int, default=5)
Returns: List of relevant learnings with similarity scores
Uses: OpenAI embeddings + PostgreSQL pgvector
Example: "Find past insights about campaign performance issues"
```

#### 7. `get_session_history`
```python
# Recent conversation history for context
Input: session_id (UUID), limit (int, default=10)
Returns: Recent messages in the conversation
Source: PostgreSQL sessions + messages tables
```

### Legacy Tools (3 tools - backward compatibility)

#### 8. `snowflake_tool` (SnowflakeTool class)
```python
# Direct Snowflake access (legacy)
# Still used by some class-based agents
```

#### 9. `memory_retrieval_tool` (MemoryRetrievalTool class)
```python
# Memory context retrieval (legacy)
# Wrapped by retrieve_relevant_learnings
```

#### 10. `decision_logger` (DecisionLogger class)
```python
# Logs agent decisions to agent_decisions table
# Used for audit trail and debugging
```

### Tool Registry by Agent

```python
# File: backend/src/tools/agent_tools.py

AGENT_TOOL_REGISTRY = {
    "performance_diagnosis": [
        execute_custom_snowflake_query,  # ONLY Snowflake tool
        retrieve_relevant_learnings,
        get_session_history
    ],
    "budget_risk": [
        execute_custom_snowflake_query,  # ONLY Snowflake tool
        retrieve_relevant_learnings,
        get_session_history
    ],
    "delivery_optimization": [
        execute_custom_snowflake_query,  # ONLY Snowflake tool
        retrieve_relevant_learnings,
        get_session_history
    ]
}

# All agents use execute_custom_snowflake_query to build SQL dynamically
# Schema information provided in each agent's system prompt
```

---

## 🧠 Memory System Implementation

### Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Memory System                            │
└────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
┌───────▼────────┐                   ┌─────────▼──────────┐
│  Short-Term    │                   │   Long-Term        │
│  (Session)     │                   │   (Learnings)      │
│  PostgreSQL    │                   │   pgvector         │
│  + Redis       │                   │                    │
└────────────────┘                   └────────────────────┘
        │                                       │
        ├─ Recent messages                     ├─ Semantic search
        ├─ Session context                     ├─ Past insights
        └─ Cached in Redis                     ├─ User preferences
           (TTL: 24h)                           └─ Pattern learnings
```

### Database Schema

#### Sessions Table
```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
```

#### Messages Table
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,  -- 'user', 'assistant', 'agent'
    content TEXT NOT NULL,
    agent_name VARCHAR(100),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);
```

#### Agent Learnings Table (pgvector)
```sql
CREATE TABLE agent_learnings (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536) NOT NULL,  -- OpenAI text-embedding-3-small
    source_session_id UUID REFERENCES sessions(id),
    agent_name VARCHAR(100),
    learning_type VARCHAR(100),  -- 'pattern', 'insight', 'rule', 'preference'
    confidence_score FLOAT NOT NULL DEFAULT 0.0,  -- 0.0 to 1.0
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Vector similarity search index
CREATE INDEX ON agent_learnings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_learnings_agent ON agent_learnings(agent_name);
CREATE INDEX idx_learnings_type ON agent_learnings(learning_type);
```

#### Agent Decisions Table (Audit Trail)
```sql
CREATE TABLE agent_decisions (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    message_id UUID REFERENCES messages(id),
    agent_name VARCHAR(100) NOT NULL,
    decision_type VARCHAR(100),
    input_data JSONB,
    output_data JSONB,
    tools_used JSONB,
    reasoning TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    execution_time_ms INTEGER
);

CREATE INDEX idx_decisions_session ON agent_decisions(session_id);
CREATE INDEX idx_decisions_agent ON agent_decisions(agent_name);
CREATE INDEX idx_decisions_timestamp ON agent_decisions(timestamp DESC);
```

### Vector Store Implementation

**File**: `backend/src/memory/vector_store.py`

```python
class VectorStore:
    """
    Manages semantic memory using pgvector + OpenAI embeddings
    """

    def __init__(self):
        self.embedding_model = "text-embedding-3-small"  # 1536 dimensions
        self.openai_client = OpenAI(api_key=settings.openai_api_key)

    async def add_learning(
        self,
        content: str,
        agent_name: str,
        learning_type: str,
        confidence_score: float,
        session_id: Optional[UUID] = None,
        metadata: Dict[str, Any] = None
    ) -> UUID:
        """
        Stores a new learning with embedding

        1. Generate embedding with OpenAI
        2. Insert into agent_learnings table
        3. Return learning ID
        """
        embedding = self._generate_embedding(content)
        # Insert into PostgreSQL with pgvector

    async def search_similar(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.7
    ) -> List[LearningWithSimilarity]:
        """
        Semantic search using cosine similarity

        1. Generate query embedding
        2. Query pgvector: ORDER BY embedding <=> query_embedding
        3. Filter by min_similarity threshold
        4. Return top_k results
        """
```

### Session Manager Implementation

**File**: `backend/src/memory/session_manager.py`

```python
class SessionManager:
    """
    Manages conversation sessions with PostgreSQL + Redis
    """

    async def create_session(self, user_id: str, metadata: Dict = None) -> UUID:
        """Creates new session in PostgreSQL, caches in Redis"""

    async def add_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
        metadata: Dict = None
    ) -> UUID:
        """Adds message to session, invalidates cache"""

    async def get_session_history(
        self,
        session_id: UUID,
        limit: int = 10
    ) -> List[Dict]:
        """Returns recent messages (from cache if available)"""

    async def get_session_memory(
        self,
        session_id: UUID,
        query: Optional[str] = None
    ) -> SessionMemory:
        """
        Returns combined memory:
        - Recent messages (session history)
        - Relevant learnings (semantic search)
        - Working memory (cached context)
        """
```

### Memory Retrieval Flow

```
User Query
    │
    ├─► 1. Embed query with OpenAI (1536 dimensions)
    │
    ├─► 2. Semantic search in pgvector
    │      SELECT content, embedding <=> query_embedding AS distance
    │      FROM agent_learnings
    │      WHERE distance < (1 - min_similarity)
    │      ORDER BY distance
    │      LIMIT top_k
    │
    ├─► 3. Get recent session messages
    │      SELECT * FROM messages
    │      WHERE session_id = ?
    │      ORDER BY timestamp DESC
    │      LIMIT 10
    │
    └─► 4. Combine into SessionMemory
           {
             "session_history": [...],
             "relevant_learnings": [...],
             "working_memory": {...}
           }
```

### Redis Caching

**File**: `backend/src/core/cache.py`

```python
# Cache keys and TTLs
session:{session_id} → SessionInfo (TTL: 24 hours)
query:{hash} → QueryResult (TTL: 60 minutes)
ratelimit:{user_id}:minute → Counter (TTL: 60 seconds)
```

---

## 🗄️ Database Configuration

### PostgreSQL Connection

```python
# File: backend/src/core/database.py

SQLALCHEMY_DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

Engine Config:
- pool_size=20
- max_overflow=10
- pool_recycle=3600  # Recycle connections every hour
- echo=False  # Set True for SQL logging

asyncpg Config:
- min_size=5
- max_size=20
- command_timeout=60
```

### Current PostgreSQL Instance

```bash
Host: 145.223.88.120
Port: 5432
Database: dv360agent
User: dvdbowner
Password: dvagentlangchain

# From .env:
DATABASE_URL=postgresql+asyncpg://dvdbowner:dvagentlangchain@145.223.88.120:5432/dv360agent
```

### Redis Configuration

```python
# File: backend/src/core/cache.py

# Current Redis Cloud Instance
REDIS_HOST=redis-10054.c338.eu-west-2-1.ec2.cloud.redislabs.com
REDIS_PORT=10054
REDIS_PASSWORD=zXh9aAVl3HmD3ngwJY2mytoDNd5teRzJ

# Connection pool
max_connections=50
decode_responses=True
```

### Snowflake Configuration

```python
# From .env:
SNOWFLAKE_ACCOUNT=ai60319.eu-west-1
SNOWFLAKE_USER=neilb@sub2tech.com
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=REPORTS
SNOWFLAKE_SCHEMA=METRICS
SNOWFLAKE_ROLE=SYSADMIN

# Tables used:
- DV360_PERFORMANCE_QUIZ
- DV360_BUDGETS_QUIZ
- DV360_CREATIVE_QUIZ
- DV360_AUDIENCE_QUIZ
```

---

## 🎯 Agent Implementations

### 1. Orchestrator (Main Controller)

**File**: `backend/src/agents/orchestrator.py`

**Pattern**: LangGraph StateGraph with 8 nodes

**State**: `OrchestratorState` (25+ fields)

**Graph Structure**:
```python
workflow = StateGraph(OrchestratorState)

# Nodes
workflow.add_node("routing", self._routing_node)
workflow.add_node("gate", self._gate_node)
workflow.add_node("invoke_agents", self._invoke_agents_node)
workflow.add_node("diagnosis", self._diagnosis_node)
workflow.add_node("recommendation", self._recommendation_node)
workflow.add_node("validation", self._validation_node)
workflow.add_node("generate_response", self._generate_response_node)

# Entry
workflow.set_entry_point("routing")

# Flow
workflow.add_edge("routing", "gate")
workflow.add_conditional_edges("gate", gate_decision, {
    "proceed": "invoke_agents",
    "block": "generate_response"
})
workflow.add_edge("invoke_agents", "diagnosis")
workflow.add_conditional_edges("diagnosis", early_exit_decision, {
    "exit": "generate_response",
    "continue": "recommendation"
})
workflow.add_edge("recommendation", "validation")
workflow.add_edge("validation", "generate_response")
workflow.add_edge("generate_response", END)
```

**Key Methods**:
```python
async def process(self, input_data: AgentInput) -> AgentOutput:
    """
    Main entry point called by API

    1. Create initial state
    2. Invoke graph: await self.graph.ainvoke(initial_state)
    3. Return AgentOutput with response, confidence, metadata
    """
```

**Specialist Agent Registry**:
```python
self.specialist_agents = {
    "performance_diagnosis": performance_agent_langgraph,
    "delivery_optimization": delivery_agent_langgraph,
    "budget_risk": budget_risk_agent,
}
```

### 2. Performance Agent (LangGraph + ReAct)

**File**: `backend/src/agents/performance_agent_langgraph.py`

**Pattern**: LangGraph StateGraph (7 nodes) with ReAct agent for tool calling

**State**: `PerformanceAgentState` (19 fields)

**Graph Flow**:
```
parse_query → [confidence check]
    ├─ low confidence → ask_clarification → END
    └─ high confidence → retrieve_memory → react_data_collection →
                         analyze_data → generate_recommendations →
                         generate_response → END
```

**ReAct Agent**:
```python
async def _react_data_collection_node(self, state: PerformanceAgentState):
    """
    Creates ReAct agent that dynamically selects tools

    Tools available:
    - execute_custom_snowflake_query (dynamic SQL - builds queries based on user needs)
    - retrieve_relevant_learnings (memory search)
    - get_session_history (context)
    """
    tools = get_performance_agent_tools()

    react_agent = create_react_agent(
        model=self.llm,
        tools=tools,
        messages_modifier=SystemMessage(content=system_prompt)
    )

    messages = [HumanMessage(content=query)]
    result = await react_agent.ainvoke({"messages": messages})
```

**Key Features**:
- Confidence scoring: 0-1 based on extracted entities (campaign_id, advertiser_id)
- Conditional clarification: Asks questions if parse_confidence < 0.6
- Dynamic tool selection: LLM chooses which SQL queries to run
- Data analysis: LLM analyzes metrics and identifies issues

### 3. Delivery Agent (LangGraph + ReAct)

**File**: `backend/src/agents/delivery_agent_langgraph.py`

**Pattern**: LangGraph StateGraph (7 nodes) with ReAct

**State**: `DeliveryAgentState` (30+ fields)

**Unique Features**:
- Combines creative + audience analysis in one agent
- Correlation analysis between creative and audience performance
- Dual data collection (creative_data + audience_data)
- Top/bottom performer identification for both creative and audience

**Graph Flow**: Same as Performance Agent

**Example Analysis**:
```
Creative Performance:
- Creative ID 123: CTR 2.5% (top performer)
- Creative ID 456: CTR 0.8% (bottom performer)

Audience Performance:
- Segment "Tech Enthusiasts": CTR 3.1%
- Segment "General Audience": CTR 1.2%

Correlation:
- Creative 123 performs best with Tech Enthusiasts segment
- Creative 456 underperforms across all segments
```

### 4. Budget Risk Agent (ReAct Minimal)

**File**: `backend/src/agents/budget_risk_agent.py`

**Pattern**: Class-based with minimal ReAct wrapper

**Why Simpler**: Budget analysis is more straightforward (fewer tools, clearer logic)

**Key Features**:
- Budget utilization percentage
- Pacing status (ahead/behind/on-track)
- Risk levels (critical/high/medium/low)
- Days remaining vs spend rate

**Risk Assessment**:
```python
if spend_rate > 1.5 * target_rate: risk = "critical"
elif spend_rate > 1.2 * target_rate: risk = "high"
elif spend_rate > 0.8 * target_rate: risk = "medium"
else: risk = "low"
```

### 5. Routing Agent

**File**: `backend/src/agents/routing_agent.py`

**Pattern**: LLM-based with keyword fallback

**How It Works**:
```python
async def route(self, query: str, session_context: Optional[Dict] = None):
    """
    1. Constructs prompt with available agents
    2. LLM analyzes query intent
    3. Selects 1-3 agents
    4. Returns: selected_agents, reasoning, confidence

    Fallback: If LLM fails, uses keyword matching
    """

    prompt = f"""
    Available agents:
    - performance_diagnosis: Campaign metrics, CTR, ROAS, conversions
    - budget_risk: Budget pacing, spend rate, risk assessment
    - delivery_optimization: Creative performance, audience targeting

    User query: "{query}"

    Select appropriate agents. Format:
    AGENTS: agent1, agent2
    REASONING: Brief explanation
    CONFIDENCE: 0.0 to 1.0
    """

    response = self.llm.invoke([HumanMessage(content=prompt)])
    # Parse response
```

**Temperature**: 0.0 (deterministic routing)

### 6. Gate Node

**File**: `backend/src/agents/gate_node.py`

**Pattern**: Rule-based validation

**Validation Rules**:
```python
1. Minimum query length: 3 words (if confidence < 0.6 → block)
2. Maximum agents: 3 per query
3. Low confidence warning: < 0.4 → add warning
4. Agent name validation: Check against valid agent names
5. Minimum agents: At least 1 agent must be selected
```

**Decision**:
```python
def validate(query, selected_agents, routing_confidence, user_id):
    if validation_fails:
        return {
            "valid": False,
            "proceed": False,
            "reason": "Query too vague and routing confidence low",
            "approved_agents": [],
            "warnings": [...]
        }
    else:
        return {
            "valid": True,
            "proceed": True,
            "approved_agents": selected_agents[:3],  # Limit to 3
            "warnings": [...]
        }
```

### 7. Diagnosis Agent

**File**: `backend/src/agents/diagnosis_agent.py`

**Pattern**: LLM-based analysis

**What It Does**:
- Analyzes results from multiple specialist agents
- Identifies root causes (not just symptoms)
- Finds correlations between findings
- Assesses overall severity

**Example**:
```
Agent Results:
- Performance: CTR declining 15% week-over-week
- Delivery: Creative fatigue detected (seen by 80% of audience)
- Budget: Pacing on track

Diagnosis:
ROOT CAUSES:
- Creative fatigue is primary driver of CTR decline
- Audience has seen same creative too many times

CORRELATIONS:
- CTR decline started 2 weeks after campaign launch
- Coincides with frequency cap being reached

SEVERITY: high
```

**Temperature**: 0.3 (slightly creative for analysis)

### 8. Early Exit Node

**File**: `backend/src/agents/early_exit_node.py`

**Pattern**: Rule-based decision

**Exit Conditions**:
```python
1. No issues found → EXIT (return diagnosis only)
2. Severity is "low" AND informational query → EXIT
3. Severity is "critical" or "high" → CONTINUE (need recommendations)
4. Issues found → CONTINUE
```

**Benefit**: Saves tokens and latency for simple queries

### 9. Recommendation Agent

**File**: `backend/src/agents/recommendation_agent.py`

**Pattern**: LLM-based generation

**What It Generates**:
```
RECOMMENDATION 1:
Priority: high
Action: Pause underperforming creative ID 456
Reason: CTR 70% below average, wasting budget
Expected Impact: Reduce wasted spend by ~$5000/week, improve overall CTR

RECOMMENDATION 2:
Priority: medium
Action: Expand Tech Enthusiasts audience segment budget by 30%
Reason: Best performing segment with lowest CPA
Expected Impact: Increase conversions by 20-25%

CONFIDENCE: 0.85
```

**Temperature**: 0.4 (allow creativity for recommendations)

**Output**: 3-5 prioritized recommendations with rationale

### 10. Validation Agent

**File**: `backend/src/agents/validation_agent.py`

**Pattern**: Rule-based validation

**Validation Rules**:
```python
1. Required fields check: action, priority, reason
2. Conflict detection: Check if recommendations contradict
3. Vagueness check: "improve", "optimize" without specifics → warning
4. Severity alignment: High severity → must have high-priority recommendations
5. Recommendation limit: Max 5 recommendations
```

**Conflict Example**:
```
Recommendation 1: Increase budget for Campaign A
Recommendation 3: Decrease overall budget
→ WARNING: Potential conflict detected
```

---

## 🔄 State Management

### TypedDict Pattern

All LangGraph agents use TypedDict for type-safe state:

```python
from typing import TypedDict, Annotated, List
import operator

class MyAgentState(TypedDict):
    # Input fields
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Intermediate data
    parsed_entities: Dict[str, Any]
    data: Optional[List[Dict]]

    # Analysis results
    issues: List[str]
    insights: List[str]

    # Recommendations
    recommendations: List[Dict[str, str]]

    # Output
    response: str
    confidence: float

    # Tracking (accumulates across nodes)
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
```

**Key Pattern**: `Annotated[List[T], operator.add]`
- Automatically accumulates across nodes
- Each node appends to the list
- Final state has complete history

### State Initialization

```python
# File: backend/src/schemas/agent_state.py

def create_initial_orchestrator_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> OrchestratorState:
    return OrchestratorState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        routing_decision={},
        routing_confidence=0.0,
        selected_agents=[],
        gate_result={},
        approved_agents=[],
        gate_warnings=[],
        agent_results={},
        agent_errors={},
        diagnosis={},
        correlations=[],
        severity_assessment="",
        should_exit_early=False,
        early_exit_reason=None,
        recommendations=[],
        recommendation_confidence=0.0,
        validation_result={},
        validated_recommendations=[],
        validation_warnings=[],
        final_response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0
    )
```

### Updating State in Nodes

```python
async def my_node(self, state: MyAgentState) -> Dict[str, Any]:
    """
    Nodes return partial state updates (dicts)
    LangGraph merges updates into current state
    """

    query = state["query"]
    # ... do work ...

    # Return only fields that changed
    return {
        "data": results,
        "issues": identified_issues,
        "tools_used": ["snowflake_query"],  # Appended to existing list
        "reasoning_steps": ["Analyzed campaign data"]  # Appended
    }
```

---

## 📡 API Structure

### Endpoints

```python
# File: backend/src/api/routes/chat.py

POST /api/chat/
  Body: {
    "message": str (required, 1-10000 chars),
    "session_id": UUID (optional),
    "user_id": str (required),
    "context": dict (optional)
  }
  Returns: {
    "response": str,
    "session_id": UUID,
    "agent_name": str,
    "reasoning": str,
    "tools_used": List[str],
    "confidence": float,
    "metadata": dict,
    "execution_time_ms": int
  }

POST /api/chat/sessions
  Body: {
    "user_id": str (required),
    "metadata": dict (optional)
  }
  Returns: SessionInfo

GET /api/chat/sessions/{session_id}
  Returns: SessionInfo with metadata

GET /api/chat/sessions/{session_id}/messages
  Query: limit (int, default=10), offset (int, default=0)
  Returns: MessageHistoryResponse

GET /health
  Returns: {"status": "healthy", "timestamp": "..."}
```

### Request Flow

```python
# 1. API receives request
request = ChatRequest(
    message="How is campaign TestCampaign performing?",
    user_id="test_user_123"
)

# 2. Create/validate session
session_id = await session_manager.create_session(user_id)

# 3. Invoke orchestrator
agent_input = AgentInput(
    message=request.message,
    session_id=session_id,
    user_id=request.user_id
)
output = await orchestrator.invoke(agent_input)

# 4. Return response
return ChatResponse(
    response=output.response,
    session_id=session_id,
    agent_name=output.agent_name,
    tools_used=output.tools_used,
    confidence=output.confidence,
    execution_time_ms=execution_time_ms
)
```

### Middleware

```python
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    correlation_id = str(uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    return response
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# LLM Providers
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-3-haiku-20240307
OPENAI_API_KEY=sk-proj-o-...
OPENAI_MODEL=gpt-4-turbo-preview
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# LangSmith Tracing (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=dv360-agent-system

# PostgreSQL
POSTGRES_HOST=145.223.88.120
POSTGRES_PORT=5432
POSTGRES_DB=dv360agent
POSTGRES_USER=dvdbowner
POSTGRES_PASSWORD=dvagentlangchain
DATABASE_URL=postgresql+asyncpg://dvdbowner:dvagentlangchain@145.223.88.120:5432/dv360agent

# Redis
REDIS_HOST=redis-10054.c338.eu-west-2-1.ec2.cloud.redislabs.com
REDIS_PORT=10054
REDIS_PASSWORD=zXh9aAVl3HmD3ngwJY2mytoDNd5teRzJ

# Snowflake
SNOWFLAKE_ACCOUNT=ai60319.eu-west-1
SNOWFLAKE_USER=neilb@sub2tech.com
SNOWFLAKE_PASSWORD=Jigaloo0
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=REPORTS
SNOWFLAKE_SCHEMA=METRICS

# Memory Configuration
VECTOR_DIMENSION=1536
MEMORY_TOP_K=5
LEARNING_CONFIDENCE_THRESHOLD=0.7
SESSION_TTL_HOURS=24
MAX_MESSAGES_PER_SESSION=100

# Query Caching
QUERY_CACHE_TTL_MINUTES=60
ENABLE_QUERY_CACHE=true

# Telemetry
LOG_LEVEL=INFO
ENABLE_PROMETHEUS=true
```

### Settings Class

```python
# File: backend/src/core/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Environment
    environment: str = "development"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # LLM (Anthropic prioritized if both keys set)
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-haiku-20240307"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4-turbo-preview"

    # PostgreSQL
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Redis
    redis_host: str
    redis_port: int = 6379
    redis_password: Optional[str] = None

    # Snowflake
    snowflake_account: str
    snowflake_user: str
    snowflake_password: str
    snowflake_warehouse: str
    snowflake_database: str
    snowflake_schema: str

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

---

## 🧪 Testing & Debugging

### Manual Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How is campaign TestCampaign performing?",
    "user_id": "test_user_123"
  }'

# Create session
curl -X POST http://localhost:8000/api/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_123"
  }'

# Get session history
curl http://localhost:8000/api/chat/sessions/{session_id}/messages
```

### Log Filtering

```bash
# Filter by agent
grep "orchestrator" /tmp/backend.log

# Filter by level
grep "error" /tmp/backend.log

# Follow logs in real-time
tail -f /tmp/backend.log | grep "invoke"
```

### LangSmith Tracing

If `LANGCHAIN_TRACING_V2=true`:
1. Go to https://smith.langchain.com
2. Select project "dv360-agent-system"
3. View traces for each agent execution
4. See tool calls, LLM inputs/outputs, latencies

### Common Issues

#### Issue 1: Agent not selected by routing
```
Fix: Check routing_agent.py keywords
- Add relevant keywords to agent description
- Test routing with: routing_agent.route("your query")
```

#### Issue 2: Snowflake query fails
```
Fix: Check SQL query in logs
- Verify table name (DV360_PERFORMANCE_QUIZ, etc.)
- Check column names
- Test query directly in Snowflake UI
```

#### Issue 3: Memory not retrieving past learnings
```
Fix: Check vector_store.py
- Verify OpenAI API key is set
- Check min_similarity threshold (default 0.7)
- Verify pgvector extension: SELECT * FROM pg_extension WHERE extname = 'vector'
```

#### Issue 4: Orchestrator error
```
Fix: Check async/await pattern
- All orchestrator nodes must be async
- Use await self.graph.ainvoke() not .invoke()
- Check for asyncio.run() inside async functions
```

---

## 📁 Directory Structure

```
backend/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                           # BaseAgent class
│   │   ├── orchestrator.py                   # Main RouteFlow controller
│   │   ├── routing_agent.py                  # LLM-based routing
│   │   ├── gate_node.py                      # Validation
│   │   ├── diagnosis_agent.py                # Root cause analysis
│   │   ├── early_exit_node.py                # Conditional exit
│   │   ├── recommendation_agent.py           # Recommendation generation
│   │   ├── validation_agent.py               # Recommendation validation
│   │   ├── performance_agent_simple.py        # Performance specialist (ReAct)
│   │   ├── delivery_agent_langgraph.py       # Delivery specialist (LangGraph)
│   │   ├── budget_risk_agent.py              # Budget specialist (ReAct)
│   │   ├── audience_agent_simple.py          # Audience specialist (ReAct)
│   │   └── creative_agent_simple.py          # Creative specialist (ReAct)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── snowflake_tools.py                # 1 Snowflake query tool (execute_custom_snowflake_query)
│   │   ├── memory_tools.py                   # 2 memory retrieval tools
│   │   ├── agent_tools.py                    # Tool registry
│   │   ├── snowflake_tool.py                 # Legacy Snowflake (class)
│   │   ├── memory_tool.py                    # Legacy memory (class)
│   │   └── decision_logger.py                # Decision tracking
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── vector_store.py                   # pgvector + OpenAI embeddings
│   │   └── session_manager.py                # Session + message management
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── agent_state.py                    # All TypedDict states
│   │   ├── agent.py                          # AgentInput, AgentOutput
│   │   ├── chat.py                           # ChatMessage, ChatRequest
│   │   └── memory.py                         # Learning, SessionMemory
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                           # FastAPI app
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py                       # Chat endpoints
│   │       └── health.py                     # Health check
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                         # Settings (Pydantic)
│   │   ├── database.py                       # PostgreSQL connection
│   │   ├── cache.py                          # Redis connection
│   │   └── telemetry.py                      # Logging, tracing
│   └── __init__.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
├── alembic/                                   # DB migrations
├── requirements.txt
├── .env
└── Dockerfile

Root:
├── COMPLETE_SYSTEM_SUMMARY.md                # This file
├── SYSTEM_ARCHITECTURE_GUIDE.md              # Detailed architecture guide
├── ROUTEFLOW_MIGRATION_COMPLETE.md           # Migration history
├── docs/
│   ├── LANGSMITH_TRACING_GUIDE.md
│   ├── TESTING_GUIDE.md
│   ├── SNOWFLAKE_QUERY_GUIDE.md
│   ├── SNOWFLAKE_TOOL_EXPLAINED.md
│   ├── CLAUDE_SETUP.md
│   ├── REDIS_CLOUD_SETUP.md
│   └── PRODUCTION_CONFIG.md
└── README.md
```

---

## 🎓 Quick Start for Future Agents

### Understanding the Flow

1. **User sends query** → `/api/chat/`
2. **Orchestrator receives** → Creates initial state
3. **Routing Agent** → Selects specialist agents (LLM decision)
4. **Gate Node** → Validates (rule-based)
5. **Specialist Agents** → Execute in parallel (Performance, Delivery, Budget)
6. **Diagnosis Agent** → Finds root causes (LLM analysis)
7. **Early Exit Check** → Skip recommendations if not needed (rule-based)
8. **Recommendation Agent** → Generates recommendations (LLM generation)
9. **Validation Agent** → Validates quality (rule-based)
10. **Response Generation** → Formats markdown output
11. **API returns** → User receives response

### Adding a New Feature

#### Example: Add "Competitor Analysis" Agent

**Step 1**: Create agent file
```python
# File: backend/src/agents/competitor_agent.py

from .base import BaseAgent

class CompetitorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="competitor_analysis",
            description="Analyzes competitor campaigns and market positioning",
            tools=[]
        )

    async def invoke(self, input_data: AgentInput) -> AgentOutput:
        # Implementation
```

**Step 2**: Register in routing agent
```python
# File: backend/src/agents/routing_agent.py

self.specialist_agents = {
    "performance_diagnosis": {...},
    "budget_risk": {...},
    "delivery_optimization": {...},
    "competitor_analysis": {  # NEW
        "description": "Analyzes competitor campaigns...",
        "keywords": ["competitor", "competition", "market share", "benchmark"]
    }
}
```

**Step 3**: Register in orchestrator
```python
# File: backend/src/agents/orchestrator.py

self.specialist_agents = {
    "performance_diagnosis": performance_agent_langgraph,
    "delivery_optimization": delivery_agent_langgraph,
    "budget_risk": budget_risk_agent,
    "competitor_analysis": competitor_agent,  # NEW
}
```

**Step 4**: Create tools (if needed)
```python
# File: backend/src/tools/snowflake_tools.py

@tool
def query_competitor_data(campaign_id: str) -> str:
    """Query competitor campaign data"""
    # Implementation
```

**Done!** The agent will now be automatically considered by routing.

### Debugging Tips

1. **Check LangSmith traces** for detailed execution flow
2. **Read logs** with `tail -f /tmp/backend.log | grep agent_name`
3. **Test routing** directly: `routing_agent.route("your query")`
4. **Verify tools** are returning data: Check Snowflake queries
5. **Check state** at each node: Add logging in node functions

---

## 📊 Performance Metrics

### Typical Execution Times

- **Simple query** (1 agent, no recommendations): ~5-8 seconds
- **Complex query** (3 agents, recommendations): ~12-15 seconds
- **Routing decision**: ~1-2 seconds
- **Specialist agent**: ~3-5 seconds each (parallel)
- **Diagnosis + Recommendations**: ~4-6 seconds

### Optimization Opportunities

1. **Cache Snowflake queries** (60-minute TTL already implemented)
2. **Parallel agent execution** (already implemented)
3. **Early exit** (skip recommendations when not needed - implemented)
4. **Redis caching** for sessions (24-hour TTL - implemented)
5. **Connection pooling** (PostgreSQL, Redis - implemented)

---

## 🔐 Security Notes

### Current Setup
- **No authentication** on API endpoints (add if exposing publicly)
- **No rate limiting** implemented in code (rely on infrastructure)
- **Database credentials** in .env (should use secrets management in production)
- **API keys** in .env (should use secrets management)

### Recommended for Production
1. Add API key authentication
2. Implement rate limiting per user
3. Use AWS Secrets Manager / Azure Key Vault for credentials
4. Add input validation on all endpoints
5. Enable HTTPS only
6. Set up firewall rules (only allow specific IPs to PostgreSQL/Redis)

---

## ✅ System Status

### What's Working
✅ Orchestrator (RouteFlow) fully operational
✅ 3 specialist agents active (Performance, Delivery, Budget)
✅ LLM-based routing working
✅ Memory system (pgvector + embeddings) functional
✅ All 10 tools available and tested
✅ API endpoints responding
✅ Database connections stable
✅ LangSmith tracing enabled

### What's Legacy (Still Available)
⚠️ Chat Conductor (old router) - not used by default
⚠️ Class-based agents (Audience, Creative) - available but not routed to
⚠️ Legacy tools - wrapped by new tools

### Known Limitations
- No frontend UI (API only)
- No authentication
- No rate limiting in code
- Snowflake queries can be slow (5-10 seconds)
- pgvector requires OpenAI API key (no local embeddings)

---

## 📞 Contact & Support

### Documentation Files
- **This file**: Complete system overview
- **SYSTEM_ARCHITECTURE_GUIDE.md**: Detailed component documentation
- **ROUTEFLOW_MIGRATION_COMPLETE.md**: Migration history and changes
- **docs/TESTING_GUIDE.md**: Testing procedures
- **docs/LANGSMITH_TRACING_GUIDE.md**: Observability setup

### Key Files to Modify
- **Add agent**: `agents/` folder + register in orchestrator
- **Add tool**: `tools/snowflake_tools.py` + `tools/agent_tools.py`
- **Change routing**: `agents/routing_agent.py`
- **Modify validation**: `agents/gate_node.py`, `agents/validation_agent.py`
- **Update API**: `api/routes/chat.py`
- **Configure**: `.env` file

---

**End of Complete System Summary**

*This document should provide future AI agents with everything needed to understand, maintain, and extend the DV360 Agent System.*
