"""
Schemas module for DV360 Agent System.
"""
from .agent import AgentInput, AgentOutput, AgentDecisionCreate
from .chat import ChatMessage, ChatMessageCreate, SessionCreate
from .memory import Learning, LearningCreate, LearningWithSimilarity, SessionMemory, WorkingMemory

# New LangGraph state definitions
from .agent_state import (
    ConductorState,
    PerformanceAgentState,
    BudgetAgentState,
    AudienceAgentState,
    CreativeAgentState,
    AgentDecision,
    ToolCallResult,
    create_initial_conductor_state,
    create_initial_performance_state,
    create_initial_budget_state,
    create_initial_audience_state,
    create_initial_creative_state,
    append_to_list,
    merge_dicts,
)

__all__ = [
    # Legacy schemas
    "AgentInput",
    "AgentOutput",
    "AgentDecisionCreate",
    "ChatMessage",
    "ChatMessageCreate",
    "SessionCreate",
    "Learning",
    "LearningCreate",
    "LearningWithSimilarity",
    "SessionMemory",
    "WorkingMemory",
    # LangGraph state definitions
    "ConductorState",
    "PerformanceAgentState",
    "BudgetAgentState",
    "AudienceAgentState",
    "CreativeAgentState",
    "AgentDecision",
    "ToolCallResult",
    # State initialization helpers
    "create_initial_conductor_state",
    "create_initial_performance_state",
    "create_initial_budget_state",
    "create_initial_audience_state",
    "create_initial_creative_state",
    # State reducers
    "append_to_list",
    "merge_dicts",
]
