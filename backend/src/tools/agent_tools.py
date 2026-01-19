"""
Consolidated tool registry for LangGraph agents.

This module provides all available tools that agents can use,
organized by category.
"""
from typing import List
from langchain_core.tools import BaseTool

from .snowflake_tools import (
    execute_custom_snowflake_query,
    ALL_SNOWFLAKE_TOOLS,
)
from .memory_tools import (
    retrieve_relevant_learnings,
    get_session_history,
    ALL_MEMORY_TOOLS,
)


# Tool collections by category
SNOWFLAKE_TOOLS = ALL_SNOWFLAKE_TOOLS
MEMORY_TOOLS = ALL_MEMORY_TOOLS

# All tools available to any agent
ALL_TOOLS = SNOWFLAKE_TOOLS + MEMORY_TOOLS


def get_performance_agent_tools() -> List[BaseTool]:
    """
    Get tools relevant for Performance Diagnosis Agent.

    The agent can execute custom SQL queries, retrieve past learnings,
    and access session history.
    """
    return [
        execute_custom_snowflake_query,  # Primary tool - build SQL queries for performance data
        retrieve_relevant_learnings,
        get_session_history,
    ]


def get_budget_agent_tools() -> List[BaseTool]:
    """
    Get tools relevant for Budget Pacing Agent.

    The agent can execute custom SQL queries for budget data and retrieve
    past learnings about budget management.
    """
    return [
        execute_custom_snowflake_query,  # Primary tool - build SQL queries for budget data
        retrieve_relevant_learnings,
        get_session_history,
    ]


def get_audience_agent_tools() -> List[BaseTool]:
    """
    Get tools relevant for Audience Targeting Agent.

    The agent can execute custom SQL queries for audience/line item performance
    and retrieve past learnings about audience strategies.
    """
    return [
        execute_custom_snowflake_query,  # Primary tool - build SQL queries for audience data
        retrieve_relevant_learnings,
        get_session_history,
    ]


def get_creative_agent_tools() -> List[BaseTool]:
    """
    Get tools relevant for Creative Inventory Agent.

    The agent can execute custom SQL queries for creative performance
    and retrieve past learnings about creative strategies.
    """
    return [
        execute_custom_snowflake_query,  # Primary tool - build SQL queries for creative data
        retrieve_relevant_learnings,
        get_session_history,
    ]


def get_delivery_agent_tools() -> List[BaseTool]:
    """
    Get tools relevant for Delivery Agent (combines Creative + Audience).

    The agent can execute custom SQL queries for both creative and audience performance
    and retrieve past learnings about delivery optimization strategies.
    """
    return [
        execute_custom_snowflake_query,  # Primary tool - build SQL queries for creative and audience data
        retrieve_relevant_learnings,
        get_session_history,
    ]


# Tool registry for easy lookup
AGENT_TOOL_REGISTRY = {
    "performance_diagnosis": get_performance_agent_tools,
    "budget_risk": get_budget_agent_tools,  # Renamed from budget_pacing
    "audience_targeting": get_audience_agent_tools,
    "creative_inventory": get_creative_agent_tools,
    "delivery_optimization": get_delivery_agent_tools,
}


def get_tools_for_agent(agent_name: str) -> List[BaseTool]:
    """
    Get the appropriate tool set for a given agent.

    Args:
        agent_name: Name of the agent

    Returns:
        List of tools available to that agent

    Raises:
        KeyError: If agent name not recognized
    """
    if agent_name not in AGENT_TOOL_REGISTRY:
        raise KeyError(
            f"Unknown agent: {agent_name}. "
            f"Available agents: {list(AGENT_TOOL_REGISTRY.keys())}"
        )

    return AGENT_TOOL_REGISTRY[agent_name]()
