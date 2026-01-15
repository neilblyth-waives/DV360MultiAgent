# Snowflake Query Guide for Agents

This guide explains where and how agents can query Snowflake data.

---

## Overview

Agents can query Snowflake data in **two ways**:

1. **Direct Method Calls** - Import `snowflake_tool` and call methods directly
2. **LangChain Tools** - Use LangChain tools (for LangGraph/ReAct agents)

---

## Method 1: Direct Method Calls

### Import Statement
```python
from ..tools.snowflake_tool import snowflake_tool
```

### Available Methods

#### 1. `get_campaign_performance()`
**Location**: `backend/src/tools/snowflake_tool.py` (lines 174-222)

**Usage**:
```python
performance_data = await snowflake_tool.get_campaign_performance(
    insertion_order="12345",      # Optional: Campaign ID
    advertiser="Quiz",            # Optional: Advertiser name
    start_date="2024-01-01",     # Optional: YYYY-MM-DD
    end_date="2024-01-31",        # Optional: YYYY-MM-DD
    limit=30                       # Optional: Max results (default 100)
)
```

**Returns**: `List[Dict[str, Any]]` with fields:
- `advertiser`, `date`, `insertion_order`
- `SPEND`, `impressions`, `clicks`
- `TOTAL_CONVERSIONS`, `TOTAL_REVENUE`

**Query Source**: `reports.reporting_revamp.ALL_PERFORMANCE_AGG`

**Used By**:
- `performance_agent.py` (line 108)
- `budget_risk_agent.py` (for context)
- `audience_agent.py` (for context)
- `creative_agent.py` (for context)

---

#### 2. `get_budget_pacing()`
**Location**: `backend/src/tools/snowflake_tool.py` (lines 224-245)

**Usage**:
```python
budget_data = await snowflake_tool.get_budget_pacing(
    campaign_id="12345",           # Required: Campaign ID
    period_days=30                 # Optional: Analysis period (default 30)
)
```

**Returns**: `Dict[str, Any]` with budget and pacing metrics

**Query Source**: `reports.multi_agent.DV360_BUDGETS_QUIZ`

**Used By**:
- `budget_risk_agent.py` (line 114)

---

#### 3. `get_audience_performance()`
**Location**: `backend/src/tools/snowflake_tool.py` (lines 247-296)

**Usage**:
```python
audience_data = await snowflake_tool.get_audience_performance(
    advertiser_id="Quiz",          # Required: Advertiser ID
    start_date="2024-01-01",       # Optional: YYYY-MM-DD
    end_date="2024-01-31",         # Optional: YYYY-MM-DD
    min_impressions=1000            # Optional: Filter threshold (default 1000)
)
```

**Returns**: `List[Dict[str, Any]]` with audience segment performance

**Query Source**: `reports.reporting_revamp.ALL_PERFORMANCE_AGG` (grouped by line_item)

**Used By**:
- `audience_agent.py` (line 107)

---

#### 4. `get_creative_performance()`
**Location**: `backend/src/tools/snowflake_tool.py` (lines 298-341)

**Usage**:
```python
creative_data = await snowflake_tool.get_creative_performance(
    campaign_id="12345",           # Required: Campaign ID
    start_date="2024-01-01",       # Optional: YYYY-MM-DD
    end_date="2024-01-31"          # Optional: YYYY-MM-DD
)
```

**Returns**: `List[Dict[str, Any]]` with creative performance metrics

**Query Source**: `reports.reporting_revamp.creative_name_agg`

**Used By**:
- `creative_agent.py` (line 111)

---

#### 5. `execute_query()` (Custom SQL)
**Location**: `backend/src/tools/snowflake_tool.py` (lines 116-172)

**Usage**:
```python
results = await snowflake_tool.execute_query(
    query="SELECT * FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG LIMIT 10",
    use_cache=True                  # Optional: Enable caching (default True)
)
```

**Returns**: `List[Dict[str, Any]]` with query results

**Features**:
- Automatic query caching (60min TTL)
- Date serialization (converts dates to ISO strings)
- Async execution (non-blocking)

**Used By**: 
- All methods above use this internally
- Can be called directly for custom queries

---

## Method 2: LangChain Tools (For LangGraph Agents)

### Import Statement
```python
from ..tools.agent_tools import get_performance_agent_tools
# or
from ..tools.snowflake_tools import query_campaign_performance
```

### Available LangChain Tools

**Location**: `backend/src/tools/snowflake_tools.py`

#### 1. `query_campaign_performance`
**Tool Decorator**: `@tool` (lines 18-68)

**Parameters**:
- `insertion_order: Optional[str]`
- `advertiser: Optional[str]`
- `start_date: Optional[str]` (YYYY-MM-DD)
- `end_date: Optional[str]` (YYYY-MM-DD)
- `limit: int = 30`

**Returns**: JSON string of results

**Used By**: LangGraph agents via ReAct pattern

---

#### 2. `query_budget_pacing`
**Tool Decorator**: `@tool` (lines 71-111)

**Parameters**:
- `campaign_id: str` (required)
- `period_days: int = 30`

**Returns**: JSON string of budget metrics

---

#### 3. `query_audience_performance`
**Tool Decorator**: `@tool` (lines 114-159)

**Parameters**:
- `advertiser_id: str` (required)
- `start_date: Optional[str]`
- `end_date: Optional[str]`
- `min_impressions: int = 1000`

**Returns**: JSON string of audience segment data

---

#### 4. `query_creative_performance`
**Tool Decorator**: `@tool` (lines 162-204)

**Parameters**:
- `campaign_id: str` (required)
- `start_date: Optional[str]`
- `end_date: Optional[str]`

**Returns**: JSON string of creative performance data

---

#### 5. `execute_custom_snowflake_query`
**Tool Decorator**: `@tool` (lines 207-238)

**Parameters**:
- `query: str` (SQL query string)

**Returns**: JSON string of query results

**Note**: Use for custom queries not covered by specialized tools

---

## Agent Tool Registry

**Location**: `backend/src/tools/agent_tools.py`

### Tool Sets by Agent

#### Performance Agent
```python
from ..tools.agent_tools import get_performance_agent_tools

tools = get_performance_agent_tools()
# Returns: [query_campaign_performance, retrieve_relevant_learnings, get_session_history]
```

#### Budget Risk Agent
```python
from ..tools.agent_tools import get_budget_agent_tools

tools = get_budget_agent_tools()
# Returns: [query_budget_pacing, query_campaign_performance, retrieve_relevant_learnings, get_session_history]
```

#### Audience Agent
```python
from ..tools.agent_tools import get_audience_agent_tools

tools = get_audience_agent_tools()
# Returns: [query_audience_performance, query_campaign_performance, retrieve_relevant_learnings, get_session_history]
```

#### Creative Agent
```python
from ..tools.agent_tools import get_creative_agent_tools

tools = get_creative_agent_tools()
# Returns: [query_creative_performance, query_campaign_performance, retrieve_relevant_learnings, get_session_history]
```

#### Delivery Agent
```python
from ..tools.agent_tools import get_delivery_agent_tools

tools = get_delivery_agent_tools()
# Returns: [query_creative_performance, query_audience_performance, query_campaign_performance, retrieve_relevant_learnings, get_session_history]
```

---

## Usage Examples

### Example 1: Direct Method Call (Traditional Agent)
```python
# In performance_agent.py or budget_risk_agent.py
from ..tools.snowflake_tool import snowflake_tool

async def process(self, input_data: AgentInput) -> AgentOutput:
    # Query Snowflake directly
    performance_data = await snowflake_tool.get_campaign_performance(
        insertion_order=campaign_id,
        advertiser=advertiser_id,
        limit=30
    )
    
    # Process results...
    return AgentOutput(...)
```

### Example 2: LangChain Tool (LangGraph Agent)
```python
# In performance_agent_langgraph.py
from ..tools.agent_tools import get_performance_agent_tools
from langgraph.prebuilt import create_react_agent

def _react_data_collection_node(self, state):
    # Get tools for this agent
    tools = get_performance_agent_tools()
    
    # Create ReAct agent - LLM will choose which tools to call
    react_agent = create_react_agent(
        model=self.llm,
        tools=tools  # LLM sees: query_campaign_performance, etc.
    )
    
    # LLM decides which tools to call based on query
    result = react_agent.invoke({"messages": [HumanMessage(content=query)]})
    
    return {"data": result}
```

---

## Snowflake Tables Available

### Main Tables

1. **`reports.reporting_revamp.ALL_PERFORMANCE_AGG`**
   - Daily campaign performance data
   - Fields: `advertiser`, `date`, `insertion_order`, `spend_gbp`, `impressions`, `clicks`, `total_conversions_pm`, `total_revenue_gbp_pm`
   - Used by: `get_campaign_performance()`, `get_audience_performance()`

2. **`reports.reporting_revamp.creative_name_agg`**
   - Creative-level performance data
   - Fields: `advertiser`, `date`, `insertion_order`, `CREATIVE`, `creative_size`, performance metrics
   - Used by: `get_creative_performance()`

3. **`reports.multi_agent.DV360_BUDGETS_QUIZ`**
   - Budget and pacing data
   - Used by: `get_budget_pacing()`

---

## Configuration

### Connection Settings
**Location**: `backend/src/core/config.py`

**Environment Variables** (from `.env`):
```bash
SNOWFLAKE_ACCOUNT=your_account.region
SNOWFLAKE_USER=your_username
SNOWFLAKE_PASSWORD=your_password          # Optional if using key pair
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=reports
SNOWFLAKE_SCHEMA=reporting_revamp
SNOWFLAKE_ROLE=your_role                  # Optional
SNOWFLAKE_PRIVATE_KEY_PATH=/app/rsa_key.p8  # Preferred - no 2FA
```

### Authentication
- **Preferred**: Key pair authentication (no 2FA)
- **Fallback**: Password authentication (may require 2FA)

---

## Key Features

### ✅ Query Caching
- All queries are cached in Redis (60min TTL)
- Reduces redundant Snowflake queries
- Speeds up repeated queries

### ✅ Date Serialization
- Automatically converts `date`/`datetime` objects to ISO strings
- Prevents JSON serialization errors
- Ensures compatibility with PostgreSQL JSONB

### ✅ Async Execution
- Non-blocking query execution
- Thread pool for sync Snowflake connector
- Compatible with FastAPI async endpoints

### ✅ Error Handling
- Comprehensive logging
- Graceful error handling
- Detailed error messages

---

## Adding New Query Methods

### Step 1: Add Method to SnowflakeTool
**File**: `backend/src/tools/snowflake_tool.py`

```python
async def get_your_new_query(
    self,
    param1: str,
    param2: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Your query description."""
    query = f"""
        SELECT ...
        FROM reports.your_schema.your_table
        WHERE ...
    """
    return await self.execute_query(query)
```

### Step 2: Create LangChain Tool (Optional)
**File**: `backend/src/tools/snowflake_tools.py`

```python
@tool
async def query_your_new_data(param1: str, param2: Optional[int] = None) -> str:
    """Tool description for LLM."""
    results = await snowflake_tool.get_your_new_query(param1, param2)
    return json.dumps(results, default=str)
```

### Step 3: Add to Agent Tool Registry
**File**: `backend/src/tools/agent_tools.py`

```python
def get_your_agent_tools() -> List[BaseTool]:
    return [
        query_your_new_data,
        # ... other tools
    ]
```

---

## Summary

### Direct Method Calls
- **Use When**: Traditional agents, deterministic queries, full control needed
- **Import**: `from ..tools.snowflake_tool import snowflake_tool`
- **Methods**: `get_campaign_performance()`, `get_budget_pacing()`, `get_audience_performance()`, `get_creative_performance()`, `execute_query()`

### LangChain Tools
- **Use When**: LangGraph agents, ReAct pattern, LLM decides which tools to call
- **Import**: `from ..tools.agent_tools import get_[agent]_tools`
- **Tools**: `query_campaign_performance`, `query_budget_pacing`, `query_audience_performance`, `query_creative_performance`, `execute_custom_snowflake_query`

### Global Instance
- **Location**: `backend/src/tools/snowflake_tool.py` (line 364)
- **Instance**: `snowflake_tool = SnowflakeTool()`
- **Shared**: Single instance used by all agents (connection pooling, shared cache)

---

**Last Updated**: 2026-01-14
**Reference**: See `docs/SNOWFLAKE_TOOL_EXPLAINED.md` for detailed tool documentation

