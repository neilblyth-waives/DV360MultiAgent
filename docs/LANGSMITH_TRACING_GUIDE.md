# LangSmith Tracing Guide

LangSmith provides visual debugging and monitoring for all LLM calls, agent decisions, and tool executions in your DV360 Agent System.

---

## Quick Start

### 1. Access Your LangSmith Dashboard

**URL**: https://smith.langchain.com/

**Login credentials**: Use the account associated with your API key:
- API Key in .env: `LANGCHAIN_API_KEY=lsv2_pt_...` (set in your .env file)

### 2. Navigate to Your Project

Once logged in:
1. Click on **Projects** in the left sidebar
2. Find and click on **`dv360-agent-system`** (your project name)

You should see all traces from your agent system!

---

## What You'll See in LangSmith

### Trace View

Each user request creates a **trace** (also called a "run") that shows:

```
┌─────────────────────────────────────────────────────────┐
│ Trace: "Test LangSmith tracing - how is campaign..."    │
│ Duration: 4.7s                                           │
│ Status: ✓ Success                                        │
│ Cost: $0.XX                                              │
└─────────────────────────────────────────────────────────┘

├─ ChatAnthropic (Performance Agent)
│  ├─ Input: [System Prompt + User Query + Campaign Data]
│  ├─ Model: claude-3-opus-20240229
│  ├─ Tokens: Input: 1,234 | Output: 567
│  ├─ Duration: 2.1s
│  └─ Output: [Campaign analysis response]
│
├─ OpenAIEmbeddings (Memory Retrieval)
│  ├─ Input: "Test LangSmith tracing..."
│  ├─ Model: text-embedding-3-small
│  ├─ Duration: 0.3s
│  └─ Output: [1536-dim vector]
│
└─ ChatAnthropic (Conductor - if used for routing)
   └─ ... (similar structure)
```

---

## Key Features

### 1. **Visual Tree Structure**

See the entire execution flow:
- Which agents were called
- Which LLMs were invoked
- Tool calls and their results
- Nested operations (conductor → specialist → tools)

### 2. **Timing Breakdown**

Click on any node to see:
- Execution time for that specific step
- What percentage of total time it took
- Latency vs processing time

**Example from your 4.7s request:**
- Performance Agent LLM call: ~2.0s (43%)
- Snowflake query: ~1.5s (32%)
- Memory retrieval: ~0.3s (6%)
- Everything else: ~0.9s (19%)

### 3. **Input/Output Inspection**

Click any step to view:
- **Full prompt** sent to LLM (system + user messages)
- **Complete response** from LLM
- **Metadata**: model, temperature, token counts

### 4. **Cost Tracking**

Each trace shows:
- Total cost for that request
- Cost per LLM call
- Token usage breakdown

### 5. **Error Debugging**

If something fails:
- See exact error message
- Identify which step failed
- View the input that caused the failure

---

## Understanding Your Traces

### Typical Trace Structure for DV360 System

```
Root Trace: User Message
│
├─ [1] Conductor Agent
│   ├─ Store user message (not traced - DB operation)
│   ├─ Memory Retrieval
│   │   └─ OpenAIEmbeddings - Generate embedding
│   ├─ Route to agents (keyword matching - not traced)
│   └─ Invoke Performance Agent
│       │
│       ├─ [2] Performance Agent
│       │   ├─ Memory Retrieval
│       │   │   └─ OpenAIEmbeddings - Generate embedding
│       │   ├─ Snowflake Query (not traced - external DB)
│       │   └─ ChatAnthropic - Generate analysis
│       │       ├─ Input: System prompt + data + context
│       │       ├─ Processing: 2000ms
│       │       └─ Output: Campaign analysis
│       │
│       └─ Return to Conductor
│
└─ Final Response
```

### What Gets Traced

✅ **Traced (visible in LangSmith)**:
- All LLM calls (ChatAnthropic, ChatOpenAI)
- All embedding generation (OpenAIEmbeddings)
- Agent orchestration (if using proper LangGraph)
- Tool calls (if registered as LangChain tools)

❌ **Not Traced** (invisible in LangSmith):
- Direct database queries (PostgreSQL, Redis)
- Snowflake queries (external connector)
- Manual Python operations
- Decision logging
- Session management

**Why?** Only LangChain components are auto-traced. Custom code needs manual instrumentation.

---

## Filtering and Searching

### Filter by:
- **Status**: Success, Error
- **Date range**: Last hour, day, week
- **Duration**: Slow queries (>5s)
- **Cost**: Expensive requests
- **Agent**: Specific agent name
- **User**: user_id from request

### Search by:
- Message content (e.g., "campaign X")
- Error messages
- Session ID

---

## Example: Debugging a Slow Request

**Scenario**: A request took 10 seconds instead of expected 4 seconds.

**Steps**:

1. **Find the trace** in LangSmith project
2. **Expand the tree** to see all steps
3. **Check timing** for each node:
   - LLM call: 2.0s (normal)
   - Embedding: 0.3s (normal)
   - One step shows: 6.5s ← **BOTTLENECK**
4. **Click the slow step** to see details
5. **Identify issue**:
   - Was it a tool call?
   - Was it Snowflake query?
   - Was it conductor routing?

**Action**: Optimize the bottleneck (connection pooling, caching, etc.)

---

## Comparing Requests

**Use Case**: "Why is this query slower than a similar one?"

1. Open both traces
2. Compare tree structures
3. Compare timing per step
4. Look for differences:
   - Different amount of data retrieved?
   - Different agent routing?
   - Cold start vs warm cache?

---

## Current Limitations

Because we're using **simple Python orchestration** (not full LangGraph), you'll see:

1. **Only LLM calls are traced**
   - Memory retrieval (only the embedding generation)
   - Agent LLM responses
   - Not: routing logic, data analysis, Snowflake queries

2. **No tool call traces**
   - Snowflake queries aren't visible
   - Decision logging isn't visible
   - Need to check backend logs for these

3. **Agent execution is simple**
   - Just shows LLM invoke
   - Not: StateGraph transitions, conditional edges, etc.

**Solution**: Full LangGraph refactor (see `FUTURE_IMPROVEMENTS.md` #2)
- Would show complete execution graph
- Tool calls would be traced
- Conditional routing would be visible
- StateGraph transitions would appear

---

## Advanced: Manual Instrumentation

If you want to trace custom operations (like Snowflake queries), you can manually instrument:

```python
from langsmith import traceable

@traceable(name="snowflake_query", run_type="tool")
async def query_snowflake(query: str):
    # Your Snowflake query logic
    result = await execute_query(query)
    return result
```

This makes your custom code visible in LangSmith traces.

---

## Monitoring in Production

### Set Up Alerts

In LangSmith dashboard:
1. Go to **Monitoring** → **Alerts**
2. Create alerts for:
   - Error rate > 5%
   - Average latency > 10s
   - Daily cost > $X
   - Token usage anomalies

### Analyze Trends

1. **Dashboards** → Create custom views
2. Track metrics over time:
   - Average response time
   - Error rate
   - Cost per request
   - Popular queries

### Feedback Loop

1. User reports an issue
2. Find their session_id
3. Search traces for that session
4. Debug the exact execution
5. Fix and deploy
6. Verify fix in new traces

---

## Useful LangSmith Features

### 1. **Annotations**

Mark traces as good/bad examples:
- ⭐ Star: Good response
- 👎 Flag: Bad response
- Use for fine-tuning datasets

### 2. **Datasets**

Create test datasets:
- Common user queries
- Edge cases
- Regression tests
- Run all tests and see results

### 3. **Playground**

Test prompts interactively:
- Modify system prompt
- Try different models
- Compare responses
- See token/cost impact

### 4. **Exports**

Export traces for:
- Training data
- Offline analysis
- Custom dashboards
- Compliance/auditing

---

## Troubleshooting

### "No traces appearing"

**Check**:
1. Environment variables set correctly:
   ```bash
   docker-compose exec backend env | grep LANGCHAIN
   ```
2. Backend restarted after .env changes
3. API key is valid (not expired)
4. Firewall allowing https://api.smith.langchain.com

### "Some calls missing from traces"

**Reason**: Only LangChain components are auto-traced.

**Solutions**:
1. Use LangChain tools (not direct function calls)
2. Manually instrument with `@traceable` decorator
3. Enable full LangGraph (future improvement)

### "Traces are slow to appear"

**Normal**: Traces upload asynchronously
- May take 5-30 seconds to appear in dashboard
- Refresh browser after sending request

---

## Next Steps

### 1. **Test Current Tracing**
- Send various requests
- Explore traces in LangSmith
- Understand timing breakdowns

### 2. **Identify Bottlenecks**
- Find slow LLM calls
- Check if prompts are too long
- Compare costs across queries

### 3. **Optimize**
- Reduce prompt tokens (shorter contexts)
- Cache repeated queries
- Use faster models for simple tasks
- Implement connection pooling for Snowflake

### 4. **Future: Full Observability** (V2)
When you implement full LangGraph:
- All tool calls will be traced
- StateGraph transitions visible
- Conditional routing visible
- Complete execution graph in LangSmith

---

## Resources

- **LangSmith Docs**: https://docs.smith.langchain.com/
- **Best Practices**: https://docs.smith.langchain.com/observability/best-practices
- **Manual Tracing**: https://docs.smith.langchain.com/tracing/tracing-faq
- **Dashboards**: https://docs.smith.langchain.com/monitoring/dashboards

---

## Your Configuration

**Project**: `dv360-agent-system`
**Endpoint**: `https://api.smith.langchain.com`
**Tracing**: Enabled (`LANGCHAIN_TRACING_V2=true`)

**Access**: https://smith.langchain.com/projects/dv360-agent-system

**Current Traces**: Check dashboard now - you should see the test request from today!
