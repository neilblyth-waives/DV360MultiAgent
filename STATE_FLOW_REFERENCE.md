# LangGraph State Flow Reference

## Overview

This document explains how state flows through LangGraph nodes in our agent system.

Each agent has a **TypedDict state** that:
- Starts with initial values
- Flows through a series of nodes
- Gets updated by each node
- Ends with final output

---

## State Accumulation with `Annotated`

### Why Use `Annotated[List[str], operator.add]`?

When multiple nodes update the same field, you need to tell LangGraph **how to merge** the updates.

```python
class MyState(TypedDict):
    # Without Annotated - overwrites on each update
    simple_field: str

    # With Annotated - accumulates across updates
    tools_used: Annotated[List[str], operator.add]
```

**Example flow**:
```python
# Node 1 updates:
state["tools_used"] = ["memory_retrieval"]

# Node 2 updates:
state["tools_used"] = ["snowflake_query"]

# Without Annotated: ["snowflake_query"] (overwritten)
# With Annotated: ["memory_retrieval", "snowflake_query"] (accumulated)
```

---

## Conductor State Flow

### State: `ConductorState`

```
Input (User)
  ↓
┌─────────────────────────────────────────────┐
│ user_message: "Is my campaign over-pacing?" │
│ session_id: UUID                            │
│ user_id: "user123"                          │
└─────────────────────────────────────────────┘
  ↓
Node: retrieve_context
  ↓
┌─────────────────────────────────────────────┐
│ session_history: [{role, content, ...}]    │
│ relevant_learnings: [{content, conf, ...}] │
│ reasoning_steps: ["Retrieved context"]     │
└─────────────────────────────────────────────┘
  ↓
Node: route_to_agents (LLM call)
  ↓
┌─────────────────────────────────────────────┐
│ selected_agents: ["budget_pacing"]         │
│ routing_reasoning: "Query about budget..." │
│ tools_used: ["routing_decision"]           │
│ reasoning_steps: [..., "Routed to budget"] │
└─────────────────────────────────────────────┘
  ↓
Node: invoke_agents (calls sub-graphs)
  ↓
┌─────────────────────────────────────────────┐
│ agent_responses: {                          │
│   "budget_pacing": "Your campaign is..."   │
│ }                                           │
│ agent_metadata: {                           │
│   "budget_pacing": {exec_time: 3500, ...}  │
│ }                                           │
│ tools_used: [..., "budget_agent"]          │
└─────────────────────────────────────────────┘
  ↓
Node: aggregate_responses
  ↓
┌─────────────────────────────────────────────┐
│ final_response: "Your campaign is..."      │
│ confidence: 0.9                             │
│ reasoning_steps: [..., "Aggregated"]       │
└─────────────────────────────────────────────┘
  ↓
Node: store_and_respond
  ↓
Output (User receives final_response)
```

---

## Performance Agent State Flow

### State: `PerformanceAgentState`

```
Input (from Conductor or direct call)
  ↓
┌─────────────────────────────────────────────┐
│ query: "How is campaign X performing?"     │
│ session_id: UUID                            │
│ user_id: "user123"                          │
│ campaign_id: None (to be parsed)           │
└─────────────────────────────────────────────┘
  ↓
Node: parse_query
  ↓
┌─────────────────────────────────────────────┐
│ campaign_id: "X"                            │
│ advertiser_id: None                         │
│ reasoning_steps: ["Parsed campaign_id=X"]  │
└─────────────────────────────────────────────┘
  ↓
Node: retrieve_memory
  ↓
┌─────────────────────────────────────────────┐
│ session_history: [{...}]                    │
│ relevant_learnings: [{...}]                 │
│ tools_used: ["retrieve_relevant_learnings"]│
└─────────────────────────────────────────────┘
  ↓
Node: query_data (ReAct agent with tools)
  ↓
┌─────────────────────────────────────────────┐
│ performance_data: [{date, impr, clicks}]   │
│ tools_used: [..., "query_campaign_perf"]   │
│ reasoning_steps: [..., "Queried 30 days"]  │
└─────────────────────────────────────────────┘
  ↓
Node: analyze_data
  ↓
┌─────────────────────────────────────────────┐
│ metrics: {ctr: 0.72, roas: 0, ...}         │
│ trends: {impressions_change: 25.1, ...}    │
│ issues: ["No conversions despite clicks"]  │
│ insights: ["CTR is above average"]         │
└─────────────────────────────────────────────┘
  ↓
Node: generate_recommendations
  ↓
┌─────────────────────────────────────────────┐
│ recommendations: [                          │
│   {priority: "high", action: "Check..."    │
│ ]                                           │
└─────────────────────────────────────────────┘
  ↓
Node: generate_response (LLM call)
  ↓
┌─────────────────────────────────────────────┐
│ response: "## Campaign Performance..."     │
│ confidence: 0.9                             │
│ tools_used: [..., "llm_analysis"]          │
└─────────────────────────────────────────────┘
  ↓
Output (returns to Conductor or user)
```

---

## Budget Agent State Flow

### State: `BudgetAgentState`

```
Input
  ↓
┌─────────────────────────────────────────────┐
│ query: "What's the budget status?"         │
└─────────────────────────────────────────────┘
  ↓
Node: parse_query
  ↓
┌─────────────────────────────────────────────┐
│ campaign_id: "extracted_id"                 │
└─────────────────────────────────────────────┘
  ↓
Node: retrieve_memory
  ↓
┌─────────────────────────────────────────────┐
│ relevant_learnings: [{...}]                 │
│ tools_used: ["retrieve_relevant_learnings"]│
└─────────────────────────────────────────────┘
  ↓
Node: query_data (ReAct agent)
  ↓
┌─────────────────────────────────────────────┐
│ budget_data: {                              │
│   total_budget: 10000,                      │
│   spent_to_date: 6000,                      │
│   days_elapsed: 15,                         │
│   days_remaining: 15                        │
│ }                                           │
│ tools_used: [..., "query_budget_pacing"]   │
└─────────────────────────────────────────────┘
  ↓
Node: analyze_pacing
  ↓
┌─────────────────────────────────────────────┐
│ budget_metrics: {                           │
│   spend_percentage: 60.0,                   │
│   time_percentage: 50.0,                    │
│   pacing_ratio: 1.2                         │
│ }                                           │
│ pacing_status: "over_pacing"                │
│ forecast: {depletion_date: "2026-01-20"}   │
│ issues: ["Over-pacing by 20%"]             │
└─────────────────────────────────────────────┘
  ↓
Node: generate_recommendations
  ↓
┌─────────────────────────────────────────────┐
│ recommendations: [                          │
│   {priority: "high",                        │
│    action: "Reduce daily spend",            │
│    reason: "Current rate will deplete..."}  │
│ ]                                           │
└─────────────────────────────────────────────┘
  ↓
Node: generate_response
  ↓
┌─────────────────────────────────────────────┐
│ response: "## Budget Status\n..."          │
│ confidence: 0.9                             │
└─────────────────────────────────────────────┘
  ↓
Output
```

---

## Audience Agent State Flow

### State: `AudienceAgentState`

```
Input
  ↓
Node: parse_query
  ↓
Node: retrieve_memory
  ↓
Node: query_data (ReAct agent)
  ↓
┌─────────────────────────────────────────────┐
│ audience_data: [                            │
│   {line_item: "Segment A", impr: 10000}    │
│   {line_item: "Segment B", impr: 5000}     │
│ ]                                           │
│ tools_used: [..., "query_audience_perf"]   │
└─────────────────────────────────────────────┘
  ↓
Node: analyze_segments
  ↓
┌─────────────────────────────────────────────┐
│ segments: [                                 │
│   {name: "Segment A", ctr: 1.2, ...}       │
│   {name: "Segment B", ctr: 0.3, ...}       │
│ ]                                           │
│ top_performers: [{name: "Segment A", ...}] │
│ bottom_performers: [{name: "Segment B"}]   │
│ summary_metrics: {avg_ctr: 0.75, ...}      │
│ issues: ["Segment B underperforming"]      │
└─────────────────────────────────────────────┘
  ↓
Node: generate_recommendations
  ↓
Node: generate_response
  ↓
Output
```

---

## Creative Agent State Flow

### State: `CreativeAgentState`

```
Input
  ↓
Node: parse_query
  ↓
Node: retrieve_memory
  ↓
Node: query_data (ReAct agent)
  ↓
┌─────────────────────────────────────────────┐
│ creative_data: [                            │
│   {creative_name: "Banner A", ctr: 1.5}    │
│   {creative_name: "Banner B", ctr: 0.2}    │
│ ]                                           │
│ tools_used: [..., "query_creative_perf"]   │
└─────────────────────────────────────────────┘
  ↓
Node: analyze_creatives
  ↓
┌─────────────────────────────────────────────┐
│ creatives: [{name, ctr, cvr, ...}]         │
│ top_performers: [{name: "Banner A", ...}]  │
│ bottom_performers: [{name: "Banner B"}]    │
│ size_performance: [                         │
│   {size: "728x90", ctr: 1.2}               │
│ ]                                           │
│ fatigue_indicators: [                       │
│   "Banner A showing declining CTR"          │
│ ]                                           │
│ issues: ["Limited creative variety"]       │
└─────────────────────────────────────────────┘
  ↓
Node: generate_recommendations
  ↓
Node: generate_response
  ↓
Output
```

---

## Key State Patterns

### 1. Input Fields (Set Once)
```python
query: str
session_id: Optional[UUID]
user_id: str
```
These are set at initialization and don't change.

### 2. Accumulated Fields (Annotated)
```python
tools_used: Annotated[List[str], operator.add]
reasoning_steps: Annotated[List[str], operator.add]
```
These accumulate across all node updates.

### 3. Progressive Enrichment
```python
# Start:
campaign_id: None

# After parse_query node:
campaign_id: "X"

# After query_data node:
performance_data: [{...}]

# After analyze node:
metrics: {ctr: 0.72, ...}
```
Each node adds more information to the state.

### 4. Optional Fields
```python
performance_data: Optional[List[Dict[str, Any]]]
```
These start as `None` and get populated by specific nodes.

### 5. List Fields (Issues, Recommendations)
```python
issues: List[str]  # Starts as []
recommendations: List[Dict[str, str]]  # Starts as []
```
These start empty and get populated during analysis.

---

## State Reducers

### `operator.add` (Built-in)
```python
Annotated[List[str], operator.add]

# Updates merge like:
existing = ["a", "b"]
new = ["c"]
result = ["a", "b", "c"]  # Concatenated
```

### Custom Reducers

#### `append_to_list`
```python
def append_to_list(existing: List[Any], new: List[Any]) -> List[Any]:
    return existing + new
```

#### `merge_dicts`
```python
def merge_dicts(existing: Dict, new: Dict) -> Dict:
    merged = existing.copy()
    merged.update(new)  # New values override existing
    return merged
```

---

## Example: Tracking Tools Across Nodes

```python
class MyAgentState(TypedDict):
    tools_used: Annotated[List[str], operator.add]

# Node 1
def node1(state: MyAgentState):
    return {"tools_used": ["memory_retrieval"]}

# Node 2
def node2(state: MyAgentState):
    return {"tools_used": ["snowflake_query"]}

# Node 3
def node3(state: MyAgentState):
    return {"tools_used": ["llm_analysis"]}

# Final state:
# tools_used = ["memory_retrieval", "snowflake_query", "llm_analysis"]
```

---

## Initialization Helpers

Each agent has a helper function:

```python
initial_state = create_initial_performance_state(
    query="How is campaign X performing?",
    session_id=UUID("..."),
    user_id="user123"
)

# Returns fully populated state with defaults:
# {
#   query: "...",
#   session_id: UUID(...),
#   user_id: "user123",
#   campaign_id: None,
#   performance_data: None,
#   tools_used: [],
#   issues: [],
#   ...
# }
```

Use these to ensure all required fields are present before invoking the graph.

---

## Best Practices

1. **Use `Optional` for fields populated later**
   ```python
   performance_data: Optional[List[Dict[str, Any]]]  # Populated by query_data node
   ```

2. **Use `Annotated` for accumulated fields**
   ```python
   tools_used: Annotated[List[str], operator.add]  # Accumulates across nodes
   ```

3. **Initialize lists and dicts properly**
   ```python
   issues: List[str]  # Start as []
   agent_responses: Dict[str, str]  # Start as {}
   ```

4. **Document what each field is for**
   ```python
   pacing_ratio: Optional[float]  # spend_% / time_%, shows over/under-pacing
   ```

5. **Use helper functions for initialization**
   ```python
   state = create_initial_budget_state(query, session_id, user_id)
   # vs manually building dict (error-prone)
   ```

---

## Next Steps

With state definitions in place, we can now:
- **Sprint 3**: Build node functions that operate on these states
- **Sprint 4**: Wire nodes together into StateGraphs
- **Sprint 5**: Replace class-based agents with graph-based agents

States are the foundation - nodes are the logic that transforms them!
