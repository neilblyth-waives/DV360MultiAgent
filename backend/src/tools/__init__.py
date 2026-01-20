"""
Tools module for DV360 Agent System.
"""
from .snowflake_tool import snowflake_tool, SnowflakeTool
from .memory_tool import memory_retrieval_tool, MemoryRetrievalTool
from .decision_logger import decision_logger, DecisionLogger

# New LangChain-compatible tools
from .snowflake_tools import (
    execute_custom_snowflake_query,
    ALL_SNOWFLAKE_TOOLS,
)
from .memory_tools import (
    retrieve_relevant_learnings,
    get_session_history,
    ALL_MEMORY_TOOLS,
)
from .agent_tools import (
    ALL_TOOLS,
    AGENT_TOOL_REGISTRY,
    get_performance_agent_tools,
    get_budget_agent_tools,
    get_audience_agent_tools,
    get_creative_agent_tools,
)

__all__ = [
    # Legacy tool instances (for backward compatibility)
    "snowflake_tool",
    "SnowflakeTool",
    "memory_retrieval_tool",
    "MemoryRetrievalTool",
    "decision_logger",
    "DecisionLogger",
    # New LangChain tools
    "execute_custom_snowflake_query",
    "retrieve_relevant_learnings",
    "get_session_history",
    # Tool collections
    "ALL_TOOLS",
    "ALL_SNOWFLAKE_TOOLS",
    "ALL_MEMORY_TOOLS",
    "AGENT_TOOL_REGISTRY",
    # Helper functions
    "get_performance_agent_tools",
    "get_budget_agent_tools",
    "get_audience_agent_tools",
    "get_creative_agent_tools",
]
