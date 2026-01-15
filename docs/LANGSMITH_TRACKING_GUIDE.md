# LangSmith Tracking & Agent Monitoring Guide

## Overview

This guide explains how to view LangSmith tracking, prompts, and agent usage in your DV360 Multi-Agent System.

---

## 1. LangSmith Setup

### Configuration

LangSmith tracking is configured via environment variables in your `.env` file:

```bash
# Enable LangSmith tracing
LANGCHAIN_TRACING_V2=true

# Your LangSmith API key
LANGCHAIN_API_KEY=lsv2_pt_your_key_here

# Project name (all traces will appear under this project)
LANGCHAIN_PROJECT=dv360-agent-system

# Optional: LangSmith endpoint (defaults to https://api.smith.langchain.com)
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

**Location**: `backend/src/core/config.py` (lines 38-41)

### How It Works

LangChain/LangSmith automatically detects these environment variables when:
- LangChain components are initialized (LLMs, agents, tools)
- LangGraph workflows are executed
- Tool calls are made

**No explicit initialization code needed** - LangChain handles it automatically!

---

## 2. Where to View LangSmith Traces

### Access LangSmith Dashboard

1. **Sign up/Login**: https://smith.langchain.com
2. **Navigate to Projects**: Click "Projects" in the sidebar
3. **Select Your Project**: Click on `dv360-agent-system` (or your configured project name)

### What You'll See

#### **Traces Tab** (Main View)
- **All Agent Executions**: Every time an agent processes a request
- **LangGraph Workflows**: Complete execution graphs showing:
  - Node execution order
  - State transitions
  - Tool calls
  - LLM invocations

#### **Trace Details** (Click any trace)
- **Input**: User query/message
- **Output**: Agent response
- **Steps**: Detailed execution steps:
  - **LLM Calls**: Full prompts sent to Claude/GPT
  - **Tool Calls**: Snowflake queries, memory retrievals
  - **State Changes**: How agent state evolved
  - **Timing**: Duration of each step

---

## 3. Viewing Prompts

### Where Prompts Are Logged

#### **A. LangSmith Dashboard** (Recommended)

1. **Open a trace** from the Traces tab
2. **Expand "LLM" steps** to see:
   - **System Prompt**: Agent's instructions (from `get_system_prompt()`)
   - **User Message**: The actual query
   - **Full Context**: Including retrieved memories, previous messages
   - **Model Response**: What the LLM generated

**Example Path**:
```
Traces → [Select Trace] → Steps → [Expand LLM Step] → Input/Output
```

#### **B. PostgreSQL Database** (Agent Decisions)

All agent decisions are logged to `agent_decisions` table with full prompts and reasoning.

**Location**: `backend/src/tools/decision_logger.py`

**Query to View**:
```sql
SELECT 
    agent_name,
    decision_type,
    input_data,      -- Contains user query
    output_data,     -- Contains agent response
    reasoning,       -- Step-by-step reasoning
    tools_used,      -- Which tools were called
    execution_time_ms,
    timestamp
FROM agent_decisions
ORDER BY timestamp DESC
LIMIT 50;
```

**Access via**:
- DBeaver (or any PostgreSQL client)
- Direct SQL query
- API endpoint (if you build one)

---

## 4. Viewing Agent Usage

### A. LangSmith Dashboard

#### **Agent Execution Overview**
1. Go to **Projects** → `dv360-agent-system`
2. **Traces Tab**: See all agent executions
3. **Filter by Agent**:
   - Use search/filter: `agent_name:performance_diagnosis`
   - Or filter by tags/metadata

#### **Agent Performance Metrics**
- **Execution Count**: How many times each agent ran
- **Average Duration**: How long each agent takes
- **Success Rate**: Percentage of successful executions
- **Token Usage**: Total tokens consumed per agent

#### **Agent Comparison**
- Compare different agents side-by-side
- See which agents are used most frequently
- Identify slow or error-prone agents

### B. PostgreSQL Database

#### **Agent Statistics Query**
```sql
-- Most used agents
SELECT 
    agent_name,
    COUNT(*) as total_executions,
    AVG(execution_time_ms) as avg_duration_ms,
    MAX(execution_time_ms) as max_duration_ms,
    MIN(execution_time_ms) as min_duration_ms,
    COUNT(DISTINCT session_id) as unique_sessions
FROM agent_decisions
GROUP BY agent_name
ORDER BY total_executions DESC;
```

#### **Agent Usage Over Time**
```sql
-- Agent usage by day
SELECT 
    DATE(timestamp) as date,
    agent_name,
    COUNT(*) as executions
FROM agent_decisions
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY DATE(timestamp), agent_name
ORDER BY date DESC, executions DESC;
```

#### **Tool Usage by Agent**
```sql
-- Which tools each agent uses
SELECT 
    agent_name,
    jsonb_array_elements_text(tools_used) as tool_name,
    COUNT(*) as usage_count
FROM agent_decisions
WHERE tools_used IS NOT NULL
GROUP BY agent_name, tool_name
ORDER BY agent_name, usage_count DESC;
```

### C. Prometheus Metrics

**Endpoint**: `http://localhost:8000/metrics`

**Agent Metrics Available**:
```
# Total agent executions
agent_executions_total{agent_name="performance_diagnosis", status="success"}

# Agent execution duration
agent_execution_duration_seconds{agent_name="performance_diagnosis"}

# Tool calls per agent
agent_tool_calls_total{agent_name="performance_diagnosis", tool_name="snowflake_query"}
```

**View in Grafana** (if configured):
- Create dashboards showing agent usage over time
- Alert on agent failures
- Monitor agent performance trends

---

## 5. System Prompts Location

### Where Prompts Are Defined

#### **Performance Agent**
**File**: `backend/src/agents/performance_agent.py`  
**Method**: `get_system_prompt()` (lines 39-68)

**Prompt Contents**:
- Agent role and expertise
- Available data sources
- Analysis approach (6-step process)
- Output format expectations

#### **Chat Conductor**
**File**: `backend/src/agents/conductor.py`  
**Method**: `get_system_prompt()` (lines 65-100+)

**Prompt Contents**:
- Routing logic
- Available specialist agents
- When to use each agent
- Response aggregation instructions

#### **Base Agent**
**File**: `backend/src/agents/base.py`  
**Method**: `get_system_prompt()` (abstract method, line 91)

All agents inherit this and implement their own prompts.

---

## 6. Complete Request Flow Tracking

### What Gets Tracked

1. **User Request** → FastAPI endpoint
2. **Chat Conductor** → Routes to specialist agent
3. **Specialist Agent** (e.g., Performance Agent):
   - Retrieves memories
   - Queries Snowflake
   - Analyzes data
   - Generates response
4. **Decision Logging** → Saves to PostgreSQL
5. **LangSmith Tracing** → Records entire flow

### Trace Structure in LangSmith

```
Trace: "Chat Request - Session XYZ"
├── Step 1: Chat Conductor
│   ├── LLM Call: Routing decision
│   └── Output: "Route to performance_diagnosis"
├── Step 2: Performance Agent
│   ├── Tool Call: Memory Retrieval
│   ├── Tool Call: Snowflake Query
│   ├── LLM Call: Analysis with system prompt
│   └── Output: Performance analysis
└── Step 3: Response Aggregation
    └── Final Response to User
```

---

## 7. Debugging with LangSmith

### Common Use Cases

#### **1. Why did agent route incorrectly?**
- View Chat Conductor's LLM call
- See the reasoning in the trace
- Check input context

#### **2. Why is agent slow?**
- Check step-by-step timing in trace
- Identify which tool call is slow
- See if caching is working

#### **3. Why did agent make wrong decision?**
- View full prompt sent to LLM
- Check retrieved memories
- See tool call results

#### **4. What data did agent see?**
- Expand Snowflake tool calls
- See exact query executed
- View query results

---

## 8. Accessing Data Programmatically

### Query Agent Decisions via API

You can build an API endpoint to query agent decisions:

```python
# Example endpoint (not currently implemented)
@app.get("/api/agent-decisions")
async def get_agent_decisions(
    agent_name: Optional[str] = None,
    session_id: Optional[UUID] = None,
    limit: int = 50
):
    decisions = await decision_logger.get_session_decisions(
        session_id=session_id,
        agent_name=agent_name,
        limit=limit
    )
    return decisions
```

### Direct Database Access

Use DBeaver or any PostgreSQL client:
- **Host**: `145.223.88.120` (or your VPS)
- **Database**: `dv360agent`
- **Table**: `agent_decisions`

---

## 9. Best Practices

### ✅ Enable LangSmith in Development
- Always have `LANGCHAIN_TRACING_V2=true` during development
- Review traces after each agent execution
- Use traces to debug issues

### ✅ Monitor Production
- Keep LangSmith enabled in production
- Set up alerts for agent failures
- Review traces weekly for optimization opportunities

### ✅ Use Project Names
- Use different project names for dev/staging/prod
- Example: `dv360-agent-system-dev`, `dv360-agent-system-prod`

### ✅ Review Prompts Regularly
- Check LangSmith traces to see actual prompts sent
- Compare with intended prompts in code
- Iterate on prompts based on agent performance

---

## 10. Quick Reference

### Enable LangSmith
```bash
# In .env file
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key_here
LANGCHAIN_PROJECT=dv360-agent-system
```

### View Traces
1. Go to https://smith.langchain.com
2. Projects → `dv360-agent-system`
3. Traces → Click any trace → Expand steps

### View Prompts
- **LangSmith**: Traces → LLM Steps → Input/Output
- **Database**: Query `agent_decisions` table → `reasoning` column

### View Agent Usage
- **LangSmith**: Projects → Traces → Filter by agent
- **Database**: `SELECT agent_name, COUNT(*) FROM agent_decisions GROUP BY agent_name`
- **Prometheus**: `http://localhost:8000/metrics` → `agent_executions_total`

---

## Troubleshooting

### LangSmith Not Showing Traces?

1. **Check Environment Variables**:
   ```bash
   docker exec -it dv360-backend env | grep LANGCHAIN
   ```

2. **Verify API Key**: Test with LangSmith CLI
   ```bash
   langsmith test
   ```

3. **Check Logs**: Look for LangSmith connection errors
   ```bash
   docker logs dv360-backend | grep -i langsmith
   ```

4. **Restart Backend**: Environment variables loaded at startup
   ```bash
   docker-compose restart backend
   ```

### Prompts Not Visible?

- Ensure `reasoning` field is populated in `agent_decisions` table
- Check that agents are calling `decision_logger.log_decision()`
- Verify JSON serialization is working (check for date errors)

---

## Summary

- **LangSmith**: Full traces, prompts, and agent execution details
- **PostgreSQL**: Persistent decision logs with reasoning
- **Prometheus**: Real-time metrics and performance data

All three systems work together to give you complete visibility into your multi-agent system!

