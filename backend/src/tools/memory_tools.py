"""
LangChain-compatible memory retrieval tools.

These tools allow agents to access past learnings and session context.
"""
from typing import Optional
from uuid import UUID
import json
from langchain_core.tools import tool

from .memory_tool import memory_retrieval_tool
from ..core.telemetry import get_logger


logger = get_logger(__name__)


@tool
async def retrieve_relevant_learnings(
    query: str,
    agent_name: str,
    top_k: int = 5,
    min_similarity: float = 0.6
) -> str:
    """
    Search for relevant past learnings using semantic similarity.

    Use this tool when you need context from previous analyses,
    patterns discovered in the past, or successful strategies used before.

    Args:
        query: Search query describing what you're looking for
        agent_name: Your agent name (e.g., 'performance_diagnosis')
        top_k: Number of learnings to retrieve (default 5)
        min_similarity: Minimum similarity score 0-1 (default 0.6)

    Returns:
        JSON string with relevant learnings and their confidence scores
    """
    try:
        logger.info(
            "LLM calling retrieve_relevant_learnings",
            query=query[:50],
            agent_name=agent_name,
            top_k=top_k
        )

        # Note: We need to create a temporary session ID for tool-only calls
        # In practice, the agent will have a session_id in its state
        from uuid import uuid4
        temp_session_id = uuid4()

        context = await memory_retrieval_tool.retrieve_context(
            query=query,
            session_id=temp_session_id,
            agent_name=agent_name,
            top_k=top_k,
            min_similarity=min_similarity,
            include_session_history=False  # Only get learnings, not messages
        )

        # Format learnings for LLM
        learnings_data = [
            {
                "content": learning.content,
                "confidence": learning.confidence_score,
                "agent": learning.agent_name,
                "type": learning.learning_type,
            }
            for learning in context.relevant_learnings
        ]

        return json.dumps({
            "learnings": learnings_data,
            "count": len(learnings_data)
        }, default=str)

    except Exception as e:
        logger.error("retrieve_relevant_learnings failed", error=str(e))
        return json.dumps({"error": str(e)})


@tool
async def get_session_history(
    session_id: str,
    limit: int = 10
) -> str:
    """
    Retrieve recent conversation history from the current session.

    Use this tool when you need context from earlier in the conversation,
    to understand what the user has already asked, or to build on previous responses.

    Args:
        session_id: Session ID (UUID string)
        limit: Maximum number of recent messages (default 10)

    Returns:
        JSON string with recent messages
    """
    try:
        logger.info(
            "LLM calling get_session_history",
            session_id=session_id[:8],
            limit=limit
        )

        from uuid import UUID
        session_uuid = UUID(session_id)

        context = await memory_retrieval_tool.retrieve_context(
            query="",  # Empty query for history only
            session_id=session_uuid,
            agent_name="system",
            top_k=0,  # No learnings needed
            min_similarity=1.0,
            include_session_history=True,
            max_history_messages=limit
        )

        return json.dumps({
            "messages": context.messages,
            "count": len(context.messages)
        }, default=str)

    except Exception as e:
        logger.error("get_session_history failed", error=str(e))
        return json.dumps({"error": str(e)})


# Export all memory tools
ALL_MEMORY_TOOLS = [
    retrieve_relevant_learnings,
    get_session_history,
]
