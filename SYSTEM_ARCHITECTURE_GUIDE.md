# DV360 Agent System - Architecture Guide for AI Agents

**Purpose**: This guide helps future AI assistants understand the complete system architecture, how components interact, and how to make modifications.

**Last Updated**: 2026-01-15
**Architecture**: RouteFlow with LangGraph
**Status**: Production Ready ✅

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Pattern: RouteFlow](#architecture-pattern-routeflow)
3. [Directory Structure](#directory-structure)
4. [Core Components](#core-components)
5. [Data Flow](#data-flow)
6. [Agent Types & Patterns](#agent-types--patterns)
7. [State Management](#state-management)
8. [How to Extend the System](#how-to-extend-the-system)
9. [Common Tasks](#common-tasks)
10. [Testing & Debugging](#testing--debugging)

---

## System Overview

### What This System Does

This is a **multi-agent DV360 (Display & Video 360) analysis system** that:
- Routes user queries to specialist agents using LLM-based intelligent routing
- Analyzes campaign performance, budget, creative, and audience data
- Generates root cause diagnoses across multiple perspectives
- Provides validated, actionable recommendations
- Maintains conversation history and learns from past interactions

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | LangGraph | Agent orchestration & workflow |
| **LLM** | Anthropic Claude 3 Haiku | LLM inference |
| **API** | FastAPI | REST API endpoints |
| **Database** | PostgreSQL + pgvector | State & semantic memory |
| **Cache** | Redis | Sessions & caching |
| **Data** | Snowflake | DV360 campaign data (read-only) |
| **Tracing** | LangSmith | Observability & debugging |
| **Language** | Python 3.11+ | Backend implementation |

### Key Design Principles

1. **Separation of Concerns**: Each agent has a single, clear responsibility
2. **LangGraph Workflows**: All complex flows use LangGraph for state management
3. **Async-First**: All agents and nodes are async for performance
4. **Type Safety**: TypedDict states enforce data contracts
5. **Observability**: Full LangSmith integration for debugging
6. **Extensibility**: Easy to add new agents without modifying existing ones

---

## Architecture Pattern: RouteFlow

### High-Level Flow

```
User Query
    ↓
API Endpoint (/api/chat/)
    ↓
Orchestrator (LangGraph StateGraph)
    ├─► 1. Routing Agent (LLM decides which specialist agents to use)
    ├─► 2. Gate Node (validates query and routing decision)
    ├─► 3. Invoke Specialist Agents in PARALLEL
    │       ├─► Performance Agent (LangGraph + ReAct)
    │       ├─► Delivery Agent (LangGraph + ReAct)
    │       └─► Budget Risk Agent (class-based)
    ├─► 4. Diagnosis Agent (finds root causes across agents)
    ├─► 5. Early Exit Check (conditional: skip recommendations if not needed)
    ├─► 6. Recommendation Agent (generates actionable recommendations)
    ├─► 7. Validation Agent (validates recommendations)
    └─► 8. Generate Response (markdown formatted)
    ↓
Response to User
```

### Why This Pattern?

**Before RouteFlow** (Simple Conductor):
- ❌ Keyword-based routing (brittle)
- ❌ Sequential agent execution (slow)
- ❌ No validation or diagnosis
- ❌ Ad-hoc recommendations

**After RouteFlow**:
- ✅ LLM-based intelligent routing
- ✅ Parallel agent execution (3x faster)
- ✅ Root cause diagnosis
- ✅ Multi-layer validation
- ✅ Automated recommendation generation

---

## Directory Structure

```
backend/src/
├── agents/                     # All agent implementations
│   ├── base.py                # BaseAgent abstract class
│   ├── orchestrator.py        # Main RouteFlow orchestrator (LangGraph)
│   ├── routing_agent.py       # LLM-based routing
│   ├── gate_node.py           # Validation & business rules
│   ├── diagnosis_agent.py     # Root cause analysis
│   ├── early_exit_node.py     # Optimization logic
│   ├── recommendation_agent.py # Recommendation generation
│   ├── validation_agent.py    # Recommendation validation
│   │
│   # Specialist Agents (LangGraph)
│   ├── performance_agent_langgraph.py  # Campaign performance analysis
│   ├── delivery_agent_langgraph.py     # Creative + Audience combined
│   │
│   # Legacy Agents (class-based, maintained for compatibility)
│   ├── budget_risk_agent.py   # Budget pacing & risk
│   ├── audience_agent.py      # Audience targeting (deprecated)
│   ├── creative_agent.py      # Creative inventory (deprecated)
│   └── conductor.py           # Old conductor (deprecated)
│
├── tools/                      # LangChain tools for agents
│   ├── snowflake_tools.py     # Individual Snowflake query tools
│   ├── memory_tools.py        # Memory retrieval tools
│   └── agent_tools.py         # Tool registry (maps agents → tools)
│
├── schemas/                    # Pydantic & TypedDict schemas
│   ├── agent.py               # AgentInput, AgentOutput
│   ├── agent_state.py         # State schemas for all agents
│   └── chat.py                # Chat message schemas
│
├── memory/                     # Memory & session management
│   ├── vector_store.py        # pgvector integration
│   ├── session_manager.py     # Session CRUD
│   └── learning_store.py      # Semantic memory storage
│
├── api/                        # FastAPI application
│   ├── main.py                # FastAPI app initialization
│   └── routes/
│       ├── chat.py            # Chat endpoints (uses orchestrator)
│       └── health.py          # Health checks
│
└── core/                       # Core utilities
    ├── config.py              # Settings (loads from env)
    ├── database.py            # DB connections
    └── telemetry.py           # Structured logging
```

---

## Core Components

### 1. Orchestrator (Main Controller)

**File**: `backend/src/agents/orchestrator.py`

**What It Does**:
- Main entry point for all user queries
- Manages the complete RouteFlow pipeline
- Uses LangGraph StateGraph with 8 nodes
- Tracks state through `OrchestratorState`

**Key Methods**:
```python
class Orchestrator(BaseAgent):
    async def process(input_data: AgentInput) -> AgentOutput:
        # Creates initial state
        # Invokes graph with await self.graph.ainvoke(state)
        # Returns AgentOutput with response

    # Node functions (all async):
    async def _routing_node(state) -> Dict
    async def _gate_node(state) -> Dict
    async def _invoke_agents_node(state) -> Dict
    async def _diagnosis_node(state) -> Dict
    async def _recommendation_node(state) -> Dict
    async def _validation_node(state) -> Dict
    def _generate_response_node(state) -> Dict

    # Decision functions (not async):
    def _gate_decision(state) -> str  # Returns "proceed" or "block"
    def _early_exit_decision(state) -> str  # Returns "exit" or "continue"
```

**Important**:
- All node functions must be `async` because they call other async agents
- Decision functions are NOT async (they just evaluate state)
- Use `await self.graph.ainvoke(state)` not `invoke()`

**How Graph is Built**:
```python
workflow = StateGraph(OrchestratorState)
workflow.add_node("routing", self._routing_node)
workflow.add_node("gate", self._gate_node)
# ... more nodes

# Conditional routing
workflow.add_conditional_edges(
    "gate",
    self._gate_decision,
    {"proceed": "invoke_agents", "block": "generate_response"}
)

return workflow.compile()
```

### 2. Routing Agent

**File**: `backend/src/agents/routing_agent.py`

**What It Does**:
- Uses LLM to analyze user intent
- Selects which specialist agents to invoke
- Returns confidence score

**Key Method**:
```python
class RoutingAgent:
    async def route(query: str, session_context: Optional[Dict] = None) -> Dict:
        # Returns:
        # {
        #     "selected_agents": ["performance_diagnosis", "budget_risk"],
        #     "routing_reasoning": "Query asks about performance and budget",
        #     "confidence": 0.9,
        #     "raw_response": "..."
        # }
```

**Available Specialist Agents**:
- `performance_diagnosis`: Campaign metrics analysis
- `budget_risk`: Budget pacing & risk assessment
- `delivery_optimization`: Creative + Audience combined

**How to Add New Agent to Routing**:
1. Add to `self.specialist_agents` dict in `__init__`
2. Include description and keywords
3. Routing Agent will automatically consider it

### 3. Gate Node

**File**: `backend/src/agents/gate_node.py`

**What It Does**:
- Validates queries before processing
- Applies business rules
- Filters invalid agent selections

**Validation Rules**:
1. Minimum query length (3 words)
2. Maximum agents (3 per query)
3. Low confidence warnings (< 0.4)
4. Agent name validation
5. Ensures at least 1 agent selected

**Key Method**:
```python
class GateNode:
    def validate(
        query: str,
        selected_agents: List[str],
        routing_confidence: float,
        user_id: Optional[str] = None
    ) -> Dict:
        # Returns:
        # {
        #     "valid": bool,
        #     "approved_agents": [...],
        #     "warnings": [...],
        #     "reason": "..."
        # }
```

### 4. Specialist Agents

#### A. Performance Agent (LangGraph)

**File**: `backend/src/agents/performance_agent_langgraph.py`

**Pattern**: LangGraph StateGraph with 7 nodes + ReAct agent

**Graph Flow**:
```
parse_query → [confidence check]
    ├─ low confidence → ask_clarification → END
    └─ high confidence → retrieve_memory → react_data_collection →
                         analyze_data → generate_recommendations →
                         generate_response → END
```

**Key Features**:
- **Confidence scoring**: Calculates 0-1 score based on extracted entities
- **Conditional routing**: Asks for clarification if query too vague
- **ReAct agent**: Dynamically selects tools (query_campaign_performance, etc.)
- **State management**: `PerformanceAgentState` with 19 fields

**How It Works**:
```python
class PerformanceAgentLangGraph(BaseAgent):
    def __init__(self):
        # Build graph
        self.graph = self._build_graph()

    async def process(input_data: AgentInput) -> AgentOutput:
        # Create initial state
        initial_state = create_initial_performance_state(...)
        # Invoke graph
        final_state = self.graph.invoke(initial_state)  # Sync invoke OK here
        # Return output
        return AgentOutput(...)
```

**ReAct Data Collection**:
```python
def _react_data_collection_node(state):
    tools = get_performance_agent_tools()

    react_agent = create_react_agent(
        model=self.llm,
        tools=tools,
        messages_modifier=SystemMessage(content="...")
    )

    result = react_agent.invoke({"messages": [HumanMessage(...)]})
    # Extract data from tool results
    return {"performance_data": data, ...}
```

#### B. Delivery Agent (LangGraph)

**File**: `backend/src/agents/delivery_agent_langgraph.py`

**Pattern**: Same as Performance Agent, but combines creative + audience analysis

**Unique Features**:
- **Dual data collection**: Queries both creative and audience data
- **Correlation analysis**: Finds patterns between creatives and audiences
- **Combined recommendations**: Addresses both creative refresh and targeting

**State**: `DeliveryAgentState` with 30+ fields including:
- `creative_data`, `audience_data`
- `creative_top_performers`, `audience_top_performers`
- `correlations` (list of creative-audience patterns)

#### C. Budget Risk Agent (Class-based)

**File**: `backend/src/agents/budget_risk_agent.py`

**Pattern**: Traditional class-based agent (not LangGraph)

**Why Not LangGraph?**:
- Simple linear flow (no conditional routing needed)
- Maintained for backward compatibility
- Will be migrated to LangGraph in future sprint

**Structure**:
```python
class BudgetRiskAgent(BaseAgent):
    async def process(input_data: AgentInput) -> AgentOutput:
        # 1. Parse query
        # 2. Retrieve memories
        # 3. Query Snowflake
        # 4. Analyze (Python)
        # 5. Generate recommendations (Python)
        # 6. Use LLM for natural language response
        return AgentOutput(...)
```

### 5. Diagnosis Agent

**File**: `backend/src/agents/diagnosis_agent.py`

**What It Does**:
- Takes results from multiple agents
- Uses LLM to identify root causes (not just symptoms)
- Finds correlations between agent findings
- Assesses overall severity

**Key Method**:
```python
class DiagnosisAgent:
    async def diagnose(
        agent_results: Dict[str, Any],  # {agent_name: AgentOutput}
        query: str
    ) -> Dict:
        # Uses LLM with temperature=0.3
        # Returns:
        # {
        #     "issues": [...],
        #     "root_causes": [...],
        #     "severity": "critical|high|medium|low",
        #     "correlations": [...],
        #     "summary": "..."
        # }
```

**LLM Prompt Structure**:
```
Agent Results Summary: {...}
Identified Issues: [...]

Your task:
1. Identify ROOT CAUSES (not just symptoms)
2. Find CORRELATIONS between agent findings
3. Assess SEVERITY
4. Provide SUMMARY

Format:
ROOT_CAUSES:
- [cause 1]
CORRELATIONS:
- [correlation 1]
SEVERITY: high
SUMMARY: ...
```

### 6. Early Exit Node

**File**: `backend/src/agents/early_exit_node.py`

**What It Does**:
- Determines if recommendations are needed
- Saves LLM tokens for simple queries
- Improves response time

**Exit Criteria**:
```python
def should_exit_early(diagnosis, agent_results, query) -> Dict:
    # EXIT EARLY if:
    # - No issues found
    # - Informational query + minimal issues

    # CONTINUE if:
    # - Severity is high
    # - Many issues detected

    return {
        "exit": bool,
        "reason": str,
        "final_response": Optional[str]
    }
```

### 7. Recommendation Agent

**File**: `backend/src/agents/recommendation_agent.py`

**What It Does**:
- Generates 3-5 prioritized recommendations
- Uses diagnosis results as input
- Each recommendation has: priority, action, reason, expected_impact

**Key Method**:
```python
class RecommendationAgent:
    async def generate_recommendations(
        diagnosis: Dict,
        agent_results: Dict,
        query: str
    ) -> Dict:
        # Uses LLM with temperature=0.4
        # Returns:
        # {
        #     "recommendations": [
        #         {
        #             "priority": "high|medium|low",
        #             "action": "Specific action",
        #             "reason": "Why this helps",
        #             "expected_impact": "What improves"
        #         }
        #     ],
        #     "confidence": 0.8,
        #     "action_plan": "..."
        # }
```

### 8. Validation Agent

**File**: `backend/src/agents/validation_agent.py`

**What It Does**:
- Validates recommendations before returning to user
- Checks for conflicts, vagueness, required fields
- Ensures alignment with severity

**Validation Rules**:
```python
def validate_recommendations(recommendations, diagnosis, agent_results) -> Dict:
    # Rule 1: Check required fields (action, priority, reason)
    # Rule 2: Check for conflicts (opposing actions)
    # Rule 3: Check for vagueness (short actions, vague verbs)
    # Rule 4: Check severity alignment (high severity → high priority recs)
    # Rule 5: Limit recommendations (max 7)

    return {
        "valid": bool,
        "validated_recommendations": [...],
        "warnings": [...],
        "errors": [...]
    }
```

---

## Data Flow

### Request Flow (Detailed)

```
1. API Receives Request
   POST /api/chat/
   Body: {"message": "...", "user_id": "..."}

2. Create/Retrieve Session
   session_manager.create_session() or .get_session_info()

3. Invoke Orchestrator
   orchestrator.invoke(AgentInput(...))

4. Orchestrator Creates Initial State
   OrchestratorState with all fields initialized

5. Graph Execution (await self.graph.ainvoke(state))

   Node: routing
   ├─ Calls routing_agent.route(query)
   ├─ LLM analyzes query → selects agents
   └─ Updates state: routing_decision, selected_agents, routing_confidence

   Node: gate
   ├─ Calls gate_node.validate(...)
   ├─ Validates agents and query
   └─ Updates state: gate_result, approved_agents, gate_warnings

   Decision: _gate_decision
   ├─ If valid=False → "block" → generate_response (error)
   └─ If valid=True → "proceed" → invoke_agents

   Node: invoke_agents (PARALLEL)
   ├─ For each approved_agent:
   │   ├─ agent.invoke(AgentInput(...))
   │   └─ Stores result in agent_results[agent_name]
   └─ Updates state: agent_results, agent_errors

   Node: diagnosis
   ├─ Calls diagnosis_agent.diagnose(agent_results, query)
   ├─ LLM finds root causes and correlations
   └─ Updates state: diagnosis, severity_assessment, correlations

   Decision: _early_exit_decision
   ├─ Calls early_exit_node.should_exit_early(...)
   ├─ If exit=True → "exit" → generate_response (early exit)
   └─ If exit=False → "continue" → recommendation

   Node: recommendation
   ├─ Calls recommendation_agent.generate_recommendations(...)
   ├─ LLM generates 3-5 recommendations
   └─ Updates state: recommendations, recommendation_confidence

   Node: validation
   ├─ Calls validation_agent.validate_recommendations(...)
   ├─ Checks for conflicts, vagueness, errors
   └─ Updates state: validated_recommendations, validation_warnings

   Node: generate_response
   ├─ Builds markdown response from state
   └─ Updates state: final_response, confidence

6. Return AgentOutput
   {
       "response": "...",
       "agent_name": "orchestrator",
       "confidence": 0.8,
       "metadata": {
           "agents_invoked": [...],
           "severity": "high",
           "recommendations_count": 3
       }
   }

7. API Returns ChatResponse
   HTTP 200 with JSON body
```

### State Flow Example

**Initial State**:
```python
{
    "query": "How is campaign X performing?",
    "user_id": "user123",
    "session_id": UUID("..."),
    "routing_decision": {},  # Empty
    "selected_agents": [],
    "approved_agents": [],
    "agent_results": {},
    "diagnosis": {},
    "recommendations": [],
    "final_response": "",
    # ... all other fields initialized
}
```

**After Routing Node**:
```python
{
    # ... previous fields ...
    "routing_decision": {
        "selected_agents": ["performance_diagnosis"],
        "confidence": 0.8,
        "reasoning": "..."
    },
    "selected_agents": ["performance_diagnosis"],
    "routing_confidence": 0.8,
    "reasoning_steps": ["Routing: selected performance_diagnosis with confidence 0.80"]
}
```

**After Invoke Agents Node**:
```python
{
    # ... previous fields ...
    "agent_results": {
        "performance_diagnosis": AgentOutput(
            response="Campaign X has 0.72% CTR...",
            confidence=0.9,
            # ...
        )
    },
    "reasoning_steps": [
        "Routing: selected performance_diagnosis with confidence 0.80",
        "Invoked 1 agents successfully, 0 failed"
    ]
}
```

---

## Agent Types & Patterns

### Pattern 1: LangGraph Agent with ReAct

**Use When**:
- Agent needs conditional routing (clarification, early exit)
- Agent needs dynamic tool selection
- Agent has complex multi-step workflow

**Example**: Performance Agent, Delivery Agent

**Template**:
```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent

class MyAgentLangGraph(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="my_agent", ...)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(MyAgentState)

        # Add nodes
        workflow.add_node("parse_query", self._parse_query_node)
        workflow.add_node("ask_clarification", self._ask_clarification_node)
        workflow.add_node("process", self._process_node)

        # Entry point
        workflow.set_entry_point("parse_query")

        # Conditional routing
        workflow.add_conditional_edges(
            "parse_query",
            self._should_clarify,
            {"clarify": "ask_clarification", "proceed": "process"}
        )

        workflow.add_edge("ask_clarification", END)
        workflow.add_edge("process", END)

        return workflow.compile()

    def _parse_query_node(self, state: MyAgentState) -> Dict[str, Any]:
        # Calculate confidence
        confidence = self._calculate_confidence(state["query"])
        return {
            "parse_confidence": confidence,
            "reasoning_steps": [f"Parsed with confidence {confidence}"]
        }

    def _should_clarify(self, state: MyAgentState) -> str:
        return "clarify" if state["parse_confidence"] < 0.4 else "proceed"

    def _ask_clarification_node(self, state: MyAgentState) -> Dict[str, Any]:
        return {
            "response": "Please provide more details...",
            "needs_clarification": True
        }

    def _process_node(self, state: MyAgentState) -> Dict[str, Any]:
        # Use ReAct agent for dynamic tool selection
        tools = get_my_agent_tools()
        react_agent = create_react_agent(
            model=self.llm,
            tools=tools,
            messages_modifier=SystemMessage(content="You are...")
        )
        result = react_agent.invoke({"messages": [...]})
        # Process result...
        return {"data": extracted_data}

    async def process(self, input_data: AgentInput) -> AgentOutput:
        initial_state = create_initial_my_agent_state(...)
        final_state = self.graph.invoke(initial_state)  # Sync OK for specialist agents
        return AgentOutput(response=final_state["response"], ...)
```

### Pattern 2: Class-Based Agent

**Use When**:
- Simple linear workflow
- No conditional routing needed
- Legacy compatibility

**Example**: Budget Risk Agent

**Template**:
```python
class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="my_agent", ...)

    async def process(self, input_data: AgentInput) -> AgentOutput:
        # Step 1: Parse
        entities = self._parse(input_data.message)

        # Step 2: Retrieve memories
        memories = await memory_retrieval_tool.retrieve_context(...)

        # Step 3: Query data
        data = await snowflake_tool.get_data(...)

        # Step 4: Analyze (Python)
        analysis = self._analyze(data)

        # Step 5: Generate recommendations (Python)
        recommendations = self._generate_recommendations(analysis)

        # Step 6: LLM for natural language
        response = await self._generate_llm_response(...)

        return AgentOutput(response=response, ...)
```

### Pattern 3: Function Node

**Use When**:
- Simple stateless logic
- No LLM needed
- Validation or business rules

**Example**: Gate Node, Early Exit Node

**Template**:
```python
class MyNode:
    def evaluate(self, state_data: Dict) -> Dict:
        # Apply rules
        result = self._apply_rules(state_data)
        return {
            "decision": "proceed" if result.valid else "block",
            "reason": result.reason
        }
```

### Pattern 4: LLM-Only Node

**Use When**:
- Primary logic is LLM reasoning
- No tools needed
- Analysis or generation task

**Example**: Routing Agent, Diagnosis Agent, Recommendation Agent

**Template**:
```python
class MyAgent:
    def __init__(self):
        self.llm = ChatAnthropic(model="...", temperature=...)

    async def analyze(self, input_data: Dict) -> Dict:
        prompt = self._build_prompt(input_data)

        messages = [
            SystemMessage(content="You are..."),
            HumanMessage(content=prompt)
        ]

        response = self.llm.invoke(messages)
        parsed = self._parse_response(response.content)

        return parsed
```

---

## State Management

### State Schemas

**File**: `backend/src/schemas/agent_state.py`

All state schemas use `TypedDict` for type safety:

```python
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator

class MyAgentState(TypedDict):
    # Input (always include these)
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Parsed data
    campaign_id: Optional[str]

    # Retrieved data
    data: Optional[List[Dict[str, Any]]]

    # Analysis results
    metrics: Optional[Dict[str, float]]
    issues: List[str]

    # Recommendations
    recommendations: List[Dict[str, str]]

    # Output
    response: str
    confidence: float

    # Tracking (use Annotated for accumulation)
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int
```

**Key Points**:
- Use `Optional` for fields that may not be set
- Use `Annotated[List[str], operator.add]` for fields that accumulate across nodes
- Always include: `query`, `session_id`, `user_id`, `response`, `confidence`
- Always include tracking: `tools_used`, `reasoning_steps`

### State Initialization

Always provide initialization helpers:

```python
def create_initial_my_agent_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> MyAgentState:
    return MyAgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        campaign_id=None,
        data=None,
        metrics=None,
        issues=[],
        recommendations=[],
        response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )
```

### Updating State in Nodes

**Node functions return partial state updates**:

```python
def _my_node(self, state: MyAgentState) -> Dict[str, Any]:
    # Only return fields you want to update
    return {
        "campaign_id": "ABC123",
        "tools_used": ["snowflake_query"],  # Will accumulate
        "reasoning_steps": ["Extracted campaign ID"]  # Will accumulate
    }
```

LangGraph automatically merges these updates into the full state.

---

## How to Extend the System

### Adding a New Specialist Agent

**Example**: Adding a "Frequency Agent" to analyze ad frequency

**Step 1**: Create state schema (`schemas/agent_state.py`)
```python
class FrequencyAgentState(TypedDict):
    query: str
    session_id: Optional[UUID]
    user_id: str
    campaign_id: Optional[str]
    frequency_data: Optional[List[Dict]]
    frequency_cap_issues: List[str]
    recommendations: List[Dict[str, str]]
    response: str
    confidence: float
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int

def create_initial_frequency_state(...) -> FrequencyAgentState:
    return FrequencyAgentState(...)
```

**Step 2**: Create Snowflake tool (`tools/snowflake_tools.py`)
```python
@tool
async def query_frequency_data(
    campaign_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """Query ad frequency data from Snowflake."""
    results = await snowflake_tool.get_frequency_data(...)
    return json.dumps(results, default=str)

# Add to ALL_SNOWFLAKE_TOOLS
ALL_SNOWFLAKE_TOOLS = [
    # ... existing tools
    query_frequency_data,
]
```

**Step 3**: Register tools (`tools/agent_tools.py`)
```python
def get_frequency_agent_tools() -> List[BaseTool]:
    return [
        query_frequency_data,
        query_campaign_performance,  # For context
        retrieve_relevant_learnings,
        get_session_history,
    ]

AGENT_TOOL_REGISTRY = {
    # ... existing agents
    "frequency_analysis": get_frequency_agent_tools,
}
```

**Step 4**: Create agent (`agents/frequency_agent_langgraph.py`)
```python
class FrequencyAgentLangGraph(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="frequency_analysis",
            description="Analyzes ad frequency and frequency cap effectiveness",
            tools=[],
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(FrequencyAgentState)
        # Add nodes...
        return workflow.compile()

    async def process(self, input_data: AgentInput) -> AgentOutput:
        # Implementation...
```

**Step 5**: Register in orchestrator (`agents/orchestrator.py`)
```python
class Orchestrator(BaseAgent):
    def __init__(self):
        # ...
        self.specialist_agents = {
            # ... existing agents
            "frequency_analysis": frequency_agent_langgraph,
        }
```

**Step 6**: Register in routing (`agents/routing_agent.py`)
```python
class RoutingAgent:
    def __init__(self):
        self.specialist_agents = {
            # ... existing agents
            "frequency_analysis": {
                "description": "Analyzes ad frequency and frequency cap effectiveness",
                "keywords": ["frequency", "frequency cap", "impressions per user", "reach"],
            },
        }
```

**Step 7**: Export (`agents/__init__.py`)
```python
from .frequency_agent_langgraph import FrequencyAgentLangGraph, frequency_agent_langgraph

__all__ = [
    # ... existing exports
    "FrequencyAgentLangGraph",
    "frequency_agent_langgraph",
]
```

**Step 8**: Restart backend
```bash
docker-compose restart backend
```

### Adding a New Tool

**Example**: Adding a "competitor analysis" tool

**Step 1**: Add to Snowflake tool (`tools/snowflake_tool.py`)
```python
class SnowflakeTool:
    async def get_competitor_data(
        self,
        advertiser_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = """
        SELECT competitor_name, impressions, spend, ctr
        FROM competitor_analysis
        WHERE advertiser_id = %s
        """
        return await self.execute_query(query, [advertiser_id])
```

**Step 2**: Create LangChain tool wrapper (`tools/snowflake_tools.py`)
```python
@tool
async def query_competitor_data(
    advertiser_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """Query competitor analysis data from Snowflake."""
    results = await snowflake_tool.get_competitor_data(...)
    return json.dumps(results, default=str)
```

**Step 3**: Add to agent's tool list (`tools/agent_tools.py`)
```python
def get_performance_agent_tools() -> List[BaseTool]:
    return [
        query_campaign_performance,
        query_competitor_data,  # NEW
        retrieve_relevant_learnings,
        get_session_history,
    ]
```

### Adding a New Node to Orchestrator

**Example**: Adding a "sentiment analysis" node

**Step 1**: Create the node class/function (`agents/sentiment_node.py`)
```python
class SentimentNode:
    async def analyze_sentiment(
        self,
        agent_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Analyze sentiment of recommendations
        return {
            "sentiment": "positive",
            "confidence": 0.9
        }

sentiment_node = SentimentNode()
```

**Step 2**: Add to orchestrator (`agents/orchestrator.py`)
```python
from .sentiment_node import sentiment_node

class Orchestrator(BaseAgent):
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(OrchestratorState)

        # ... existing nodes
        workflow.add_node("sentiment_analysis", self._sentiment_node)

        # Add to flow
        workflow.add_edge("diagnosis", "sentiment_analysis")
        workflow.add_edge("sentiment_analysis", "recommendation")

        return workflow.compile()

    async def _sentiment_node(self, state: OrchestratorState) -> Dict[str, Any]:
        result = await sentiment_node.analyze_sentiment(state["agent_results"])
        return {
            "sentiment_result": result,
            "reasoning_steps": ["Analyzed sentiment"]
        }
```

**Step 3**: Update state schema (`schemas/agent_state.py`)
```python
class OrchestratorState(TypedDict):
    # ... existing fields
    sentiment_result: Optional[Dict[str, Any]]  # NEW
```

---

## Common Tasks

### Task 1: Debugging Why an Agent Wasn't Selected

**Check**:
1. Look at LangSmith trace for routing decision
2. Check routing agent logs: `docker-compose logs backend | grep "Routing decision"`
3. Verify agent is registered in routing agent's `specialist_agents`
4. Check if keywords match query
5. Test routing directly:
```python
from agents.routing_agent import routing_agent
import asyncio
result = asyncio.run(routing_agent.route("your query here"))
print(result)
```

### Task 2: Agent Returning Empty/Wrong Data

**Check**:
1. Verify Snowflake query in `tools/snowflake_tool.py`
2. Check if ReAct agent is selecting correct tool
3. Look at LangSmith trace for tool calls
4. Test tool directly:
```python
from tools.snowflake_tools import query_campaign_performance
import asyncio
result = asyncio.run(query_campaign_performance.ainvoke({"campaign_id": "test"}))
print(result)
```

### Task 3: Recommendations Not Generating

**Check**:
1. Verify diagnosis completed successfully
2. Check early exit decision: `docker-compose logs backend | grep "Early exit"`
3. Verify recommendation agent is invoked
4. Check LangSmith trace for recommendation node
5. Review diagnosis severity (too low = early exit)

### Task 4: Adding New Validation Rule

**Edit**: `agents/validation_agent.py`

```python
class ValidationAgent:
    def validate_recommendations(self, recommendations, diagnosis, agent_results):
        # ... existing rules

        # NEW RULE: Check for budget constraints
        for i, rec in enumerate(recommendations):
            action = rec.get("action", "").lower()
            if "increase budget" in action:
                # Check if budget available
                budget_data = agent_results.get("budget_risk")
                if budget_data and has_budget_constraint(budget_data):
                    warnings.append(f"Recommendation {i+1}: Budget may be constrained")

        # ... rest of validation
```

### Task 5: Changing Routing Logic

**Edit**: `agents/routing_agent.py`

To change confidence threshold:
```python
class RoutingAgent:
    def __init__(self):
        self.min_confidence = 0.6  # Change this
```

To change LLM temperature:
```python
self.llm = ChatAnthropic(
    model=settings.anthropic_model,
    api_key=settings.anthropic_api_key,
    temperature=0.0,  # Change this (0 = deterministic, 1 = creative)
)
```

To change routing prompt:
```python
async def route(self, query: str, ...) -> Dict[str, Any]:
    routing_prompt = f"""NEW PROMPT HERE

    Available agents:
    {agents_description}

    User query: "{query}"

    YOUR INSTRUCTIONS
    """
```

### Task 6: Modifying Response Format

**Edit**: `agents/orchestrator.py`

```python
def _build_response(self, state: OrchestratorState) -> str:
    parts = []

    # Change header format
    parts.append(f"🎯 **Analysis for**: {state['query']}\n")

    # Add new section
    agents_used = list(state.get("agent_results", {}).keys())
    parts.append(f"**Agents Consulted**: {', '.join(agents_used)}\n")

    # ... rest of response building

    return "\n".join(parts)
```

---

## Testing & Debugging

### Running Tests

**Unit Tests**:
```bash
docker-compose exec backend pytest tests/unit/
```

**Integration Tests**:
```bash
docker-compose exec backend pytest tests/integration/
```

**Test Single Component**:
```bash
# Test routing agent
docker-compose exec backend python -m pytest tests/unit/test_routing_agent.py -v

# Test orchestrator
docker-compose exec backend python -m pytest tests/integration/test_orchestrator.py -v
```

### Manual Testing via API

**Simple Query**:
```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How is campaign TestCampaign performing?",
    "user_id": "test_user"
  }' | jq .
```

**Multi-Agent Query**:
```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Analyze campaign TestCampaign performance, budget, and creative",
    "user_id": "test_user"
  }' | jq .
```

**Check Metadata**:
```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Your query",
    "user_id": "test_user"
  }' | jq '.metadata'
```

### Debugging with Logs

**View Real-Time Logs**:
```bash
docker-compose logs -f backend
```

**Filter Logs**:
```bash
# Routing decisions
docker-compose logs backend | grep "Routing"

# Agent invocations
docker-compose logs backend | grep "Invoking agents"

# Diagnosis results
docker-compose logs backend | grep "Diagnosis"

# Errors
docker-compose logs backend | grep -E "ERROR|exception"

# Full orchestrator flow
docker-compose logs backend | grep -E "(Routing|Gate|Invoking|Diagnosis|Recommendation|Validation)"
```

### Using LangSmith

**View Traces**:
1. Go to https://smith.langchain.com/
2. Select project: `dv360-agent-system`
3. Find your trace by query or timestamp

**What to Look For**:
- **Graph visualization**: See complete node execution flow
- **LLM calls**: View prompts, responses, token usage
- **Tool calls**: See which tools were invoked with what params
- **State transitions**: View state before/after each node
- **Execution times**: Identify performance bottlenecks

**Enable Debug Logging**:
```python
# In core/telemetry.py
import structlog

logger = structlog.get_logger()
logger.setLevel("DEBUG")  # Change from INFO
```

### Common Issues & Solutions

**Issue**: "asyncio.run() cannot be called from a running event loop"
**Solution**: Use `await` instead of `asyncio.run()` in node functions

**Issue**: "No synchronous function provided to node"
**Solution**: Use `await self.graph.ainvoke(state)` instead of `.invoke()`

**Issue**: Agent not returning data
**Solution**: Check if ReAct agent is calling tools correctly, verify tool returns JSON string

**Issue**: State field not updating
**Solution**: Ensure you're returning Dict from node, check if field uses `Annotated[..., operator.add]`

**Issue**: Routing selecting wrong agent
**Solution**: Check routing prompt, verify agent keywords, increase temperature for more exploration

**Issue**: Gate blocking valid queries
**Solution**: Adjust validation thresholds in `gate_node.py`, check warnings in logs

---

## Configuration

### Environment Variables

**File**: `.env` (copy from `.env.example`)

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-haiku-20240307

# LangSmith (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=dv360-agent-system

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=dv360_agents
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Snowflake
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PRIVATE_KEY_PATH=/app/rsa_key.p8
SNOWFLAKE_DATABASE=REPORTS
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
```

### Changing Models

**Performance Agent** (`agents/performance_agent_langgraph.py`):
```python
self.llm = ChatAnthropic(
    model="claude-3-opus-20240229",  # Change to Opus for higher quality
    api_key=settings.anthropic_api_key,
    temperature=0.0,
)
```

**Routing Agent** (`agents/routing_agent.py`):
```python
self.llm = ChatAnthropic(
    model="claude-3-haiku-20240307",  # Keep Haiku for speed
    temperature=0.0,  # Keep deterministic
)
```

**Recommendation Agent** (`agents/recommendation_agent.py`):
```python
self.llm = ChatAnthropic(
    model="claude-3-sonnet-20240229",  # Sonnet for balance
    temperature=0.4,  # Allow creativity
)
```

---

## Key Conventions

1. **Async by Default**: All agent methods, node functions (in orchestrator), and tool calls are async
2. **State Updates**: Node functions return partial Dict, not full state
3. **Logging**: Use structured logging: `logger.info("message", key=value)`
4. **Error Handling**: Always return AgentOutput even on error, set confidence=0.0
5. **Tool Returns**: Tools must return JSON strings, not Python objects
6. **Node Naming**: Use verb_noun format: `parse_query`, `invoke_agents`, `generate_response`
7. **State Naming**: Use PascalCase with "State" suffix: `PerformanceAgentState`
8. **Agent Naming**: Use snake_case for agent_name: `performance_diagnosis`

---

## Summary for Future Agents

**When you need to**:

✅ **Add a new specialist agent**: Follow "Adding a New Specialist Agent" section
✅ **Modify routing logic**: Edit `routing_agent.py`
✅ **Add validation rule**: Edit `validation_agent.py`
✅ **Add new tool**: Create in `snowflake_tools.py`, register in `agent_tools.py`
✅ **Change response format**: Edit `orchestrator.py` `_build_response()` method
✅ **Debug routing decision**: Check LangSmith traces + routing logs
✅ **Debug agent output**: Check LangSmith tool calls + agent logs
✅ **Test changes**: Use curl to POST to `/api/chat/`, check logs and LangSmith

**Key Files**:
- **Orchestrator**: `agents/orchestrator.py` (main flow)
- **Routing**: `agents/routing_agent.py` (agent selection)
- **States**: `schemas/agent_state.py` (all state schemas)
- **Tools**: `tools/agent_tools.py` (tool registry)
- **API**: `api/routes/chat.py` (entry point)

**Architecture Philosophy**:
- **RouteFlow**: Routing → Gate → Parallel Agents → Diagnosis → Recommendations → Validation → Response
- **LangGraph**: All complex flows use StateGraph for visibility
- **Specialist Agents**: Focus on single domain (performance, budget, delivery)
- **Orchestrator**: Coordinates everything, never does domain analysis itself
- **Validation**: Multiple layers (gate, early exit, recommendation validation)

---

**Last Updated**: 2026-01-15
**Version**: RouteFlow v1.0
**Status**: Production Ready ✅

For questions or issues, check:
1. This guide
2. LangSmith traces (https://smith.langchain.com/)
3. Docker logs (`docker-compose logs backend`)
4. Individual agent files for implementation details
