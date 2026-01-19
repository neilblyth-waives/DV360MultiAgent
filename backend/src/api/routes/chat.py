"""
Chat API endpoints for interacting with the agent system.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from ...agents.orchestrator import orchestrator
from ...memory.session_manager import session_manager
from ...schemas.agent import AgentInput
from ...schemas.chat import ChatMessage, SessionInfo, SessionCreate
from ...core.telemetry import get_logger


logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# Request/Response Models
class ChatRequest(BaseModel):
    """Request to send a chat message."""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[UUID] = None
    user_id: str = Field(..., min_length=1, max_length=255)
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    response: str
    session_id: UUID
    agent_name: str
    reasoning: Optional[str] = None
    tools_used: List[str] = Field(default_factory=list)
    confidence: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: int


class MessageHistoryResponse(BaseModel):
    """Message history response."""
    session_id: UUID
    messages: List[Dict[str, Any]]
    total_count: int


# Endpoints
@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def send_message(request: ChatRequest):
    """
    Send a message and get a response from the agent system.

    The conductor will route to the appropriate specialist agent(s) based on the message content.

    Args:
        request: Chat request with message, session_id, and user_id

    Returns:
        ChatResponse with agent response and metadata
    """
    import time
    start_time = time.time()

    try:
        # Create or use existing session
        if request.session_id:
            # Verify session exists
            session = await session_manager.get_session_info(request.session_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {request.session_id} not found"
                )
            session_id = request.session_id
        else:
            # Create new session
            session_id = await session_manager.create_session(
                user_id=request.user_id,
                metadata=request.context
            )
            logger.info(f"Created new session: {session_id}")

        # Process message through orchestrator (RouteFlow architecture)
        agent_input = AgentInput(
            message=request.message,
            session_id=session_id,
            user_id=request.user_id,
            context=request.context,
        )

        # Use new orchestrator instead of old conductor
        output = await orchestrator.invoke(agent_input)

        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Chat request processed",
            session_id=str(session_id),
            user_id=request.user_id,
            execution_time_ms=execution_time_ms,
        )

        return ChatResponse(
            response=output.response,
            session_id=session_id,
            agent_name=output.agent_name,
            reasoning=output.reasoning,
            tools_used=output.tools_used,
            confidence=output.confidence,
            metadata=output.metadata,
            execution_time_ms=execution_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat request failed", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.post("/sessions", response_model=SessionInfo, status_code=status.HTTP_201_CREATED)
async def create_session(request: SessionCreate):
    """
    Create a new chat session.

    Sessions maintain conversation history and context across multiple messages.

    Args:
        request: Session creation request with user_id

    Returns:
        SessionInfo with session information
    """
    try:
        session_id = await session_manager.create_session(
            user_id=request.user_id,
            metadata=request.metadata
        )

        logger.info(
            "Session created",
            session_id=str(session_id),
            user_id=request.user_id,
        )

        # Fetch the full session info from database (which has all fields)
        session_info = await session_manager.get_session_info(session_id)

        return session_info

    except Exception as e:
        logger.error("Failed to create session", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: UUID):
    """
    Get session information.

    Args:
        session_id: Session UUID

    Returns:
        SessionInfo with session metadata
    """
    try:
        session = await session_manager.get_session_info(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )

        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get session", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}"
        )


@router.get("/sessions/{session_id}/messages", response_model=MessageHistoryResponse)
async def get_message_history(session_id: UUID, limit: int = 50):
    """
    Get message history for a session.

    Args:
        session_id: Session UUID
        limit: Maximum number of messages to return (default: 50)

    Returns:
        MessageHistoryResponse with messages
    """
    try:
        # Verify session exists
        session = await session_manager.get_session_info(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )

        # Get messages
        messages = await session_manager.get_messages(
            session_id=session_id,
            limit=limit
        )

        # Convert to dict format
        message_dicts = [
            {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "agent_name": msg.agent_name,
                "timestamp": msg.timestamp.isoformat(),
                "metadata": msg.metadata,
            }
            for msg in messages
        ]

        return MessageHistoryResponse(
            session_id=session_id,
            messages=message_dicts,
            total_count=len(message_dicts),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get message history", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get message history: {str(e)}"
        )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: UUID):
    """
    Delete a session and all its messages.

    Args:
        session_id: Session UUID to delete
    """
    try:
        # Verify session exists
        session = await session_manager.get_session_info(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )

        # TODO: Implement session deletion in session_manager
        # For now, just log
        logger.info(f"Session deletion requested: {session_id}")

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Session deletion not yet implemented"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete session", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}"
        )
