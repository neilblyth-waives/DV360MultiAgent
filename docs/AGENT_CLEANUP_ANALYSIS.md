# Agent Cleanup Analysis

## Currently Active Agents (KEEP)

These agents are actively used by the orchestrator:

### RouteFlow Components (Used by Orchestrator)
1. ✅ **`orchestrator.py`** - Main entry point, coordinates all agents
2. ✅ **`routing_agent.py`** - Routes queries to specialist agents
3. ✅ **`gate_node.py`** - Validates routing decisions
4. ✅ **`diagnosis_agent.py`** - Analyzes results from multiple agents
5. ✅ **`early_exit_node.py`** - Determines if recommendations are needed
6. ✅ **`recommendation_agent.py`** - Generates recommendations
7. ✅ **`validation_agent.py`** - Validates recommendations

### Specialist Agents (Used by Orchestrator)
8. ✅ **`performance_agent_simple.py`** - IO-level performance analysis (ReAct)
9. ✅ **`audience_agent_simple.py`** - Line item/audience analysis (ReAct)
10. ✅ **`creative_agent_simple.py`** - Creative performance analysis (ReAct)
11. ✅ **`budget_risk_agent.py`** - Budget pacing analysis (ReAct)
12. ✅ **`delivery_agent_langgraph.py`** - Combined creative + audience (LangGraph, marked as legacy but still used)

### Base Classes
13. ✅ **`base.py`** - Base class for all agents

---

## Agents That Can Be Removed (NOT USED)

These agents are **not actively used** and can be safely removed:

### Legacy Conductor (Replaced by Orchestrator)
1. ❌ **`conductor.py`** - Old Chat Conductor (replaced by orchestrator)
   - **Status**: Imported in `chat.py` but NOT called (line 96 uses `orchestrator` instead)
   - **Reason**: Orchestrator is the active coordinator

### Legacy Specialist Agents (Only Used by Conductor)
2. ❌ **`performance_agent.py`** - Old performance agent
   - **Status**: Only used by `conductor.py` (which isn't used)
   - **Reason**: Replaced by `performance_agent_simple.py`

3. ❌ **`audience_agent.py`** - Old audience agent
   - **Status**: Only used by `conductor.py` (which isn't used)
   - **Reason**: Replaced by `audience_agent_simple.py`

4. ❌ **`creative_agent.py`** - Old creative agent
   - **Status**: Only used by `conductor.py` (which isn't used)
   - **Reason**: Replaced by `creative_agent_simple.py`

### Legacy LangGraph Agent (Only Used by Conductor)
5. ❌ **`performance_agent_langgraph.py`** - LangGraph version of performance agent
   - **Status**: Only used by `conductor.py` (which isn't used)
   - **Reason**: Replaced by `performance_agent_simple.py` (simpler ReAct version)

---

## Removal Impact Analysis

### Files to Remove:
```
backend/src/agents/conductor.py                    (~420 lines)
backend/src/agents/performance_agent.py            (~500 lines)
backend/src/agents/audience_agent.py               (~400 lines)
backend/src/agents/creative_agent.py               (~500 lines)
backend/src/agents/performance_agent_langgraph.py   (~660 lines)
```

**Total**: ~2,480 lines of unused code

### Files to Update:
1. **`backend/src/agents/__init__.py`** - Remove exports of legacy agents
2. **`backend/src/api/routes/chat.py`** - Remove unused `chat_conductor` import
3. **`backend/src/tools/agent_tools.py`** - Remove `get_conductor_tools()` and `chat_conductor` from registry

---

## Verification

### How to Verify Agents Are Not Used:

1. **Conductor**: 
   - ✅ Checked `chat.py` line 96 - uses `orchestrator.invoke()`, not `chat_conductor`
   - ✅ Conductor is imported but never called

2. **Legacy Agents**:
   - ✅ Only imported/used by `conductor.py`
   - ✅ Since conductor isn't used, these agents aren't used

3. **performance_agent_langgraph**:
   - ✅ Only used by `conductor.py` (line 59)
   - ✅ Orchestrator uses `performance_agent_simple` instead

---

## Recommendation

**SAFE TO REMOVE**: All 5 legacy agents listed above can be safely removed. They are:
- Not imported or called by active code
- Replaced by simpler, more maintainable versions
- Creating confusion about which agents are actually used

**Note**: `delivery_agent_langgraph.py` is marked as "legacy" but is still actively used by the orchestrator, so it should be kept for now.

---

## Cleanup Steps

1. Remove 5 agent files listed above
2. Update `__init__.py` to remove exports
3. Update `chat.py` to remove unused import
4. Update `agent_tools.py` to remove conductor tools
5. Test that orchestrator still works correctly

