"""
Base agent class for all DV360 agents.
"""
import os
from typing import Dict, List, Any, Optional, TypedDict
from abc import ABC, abstractmethod
import time
from uuid import UUID

# CRITICAL: Ensure LangSmith env vars are set before importing LangChain components
# This ensures tracing is enabled when LLMs are initialized
if not os.getenv("LANGCHAIN_TRACING_V2") and os.getenv("LANGCHAIN_API_KEY"):
    # Try to enable tracing if API key is present
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if not os.getenv("LANGCHAIN_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = "dv360-agent-system"

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

from ..core.config import settings
from ..core.telemetry import get_logger, log_agent_execution
from ..schemas.agent import AgentInput, AgentOutput, AgentState


logger = get_logger(__name__)


class BaseAgentState(TypedDict):
    """Base state for agent graph."""
    messages: List[BaseMessage]
    session_id: Optional[UUID]
    user_id: str
    next_action: Optional[str]
    tool_calls: List[Dict[str, Any]]
    final_response: Optional[str]


class BaseAgent(ABC):
    """
    Base class for all DV360 agents.

    Provides common functionality:
    - LLM initialization
    - Tool management
    - Decision logging
    - Memory integration
    - LangGraph state management
    """

    def __init__(
        self,
        agent_name: str,
        description: str,
        tools: Optional[List[Any]] = None,
    ):
        """
        Initialize base agent.

        Args:
            agent_name: Unique name for this agent
            description: What this agent does
            tools: List of LangChain tools available to this agent
        """
        self.agent_name = agent_name
        self.description = description
        self.tools = tools or []
        self.llm = self._initialize_llm()
        self.graph = None

        logger.info(f"Initialized agent: {agent_name}", tools_count=len(self.tools))

    def _initialize_llm(self):
        """
        Initialize the LLM based on configuration.

        Priority: Anthropic (Claude) > OpenAI (GPT)
        Note: OpenAI key may also be used for embeddings only.

        LangSmith tracing is automatically enabled when:
        - LANGCHAIN_TRACING_V2=true
        - LANGCHAIN_API_KEY is set
        - LANGCHAIN_PROJECT is set

        No manual tracer setup needed - LangChain handles it automatically.
        """
        # Log tracing status
        if os.getenv("LANGCHAIN_TRACING_V2") == "true":
            logger.info(
                "LangSmith tracing enabled via environment variables",
                project=os.getenv("LANGCHAIN_PROJECT", "default"),
                api_key_set=bool(os.getenv("LANGCHAIN_API_KEY"))
            )

        if settings.anthropic_api_key:
            logger.info("Using Anthropic Claude for LLM", model=settings.anthropic_model)
            return ChatAnthropic(
                model=settings.anthropic_model,
                temperature=0.1,
                api_key=settings.anthropic_api_key,
            )
        elif settings.openai_api_key:
            logger.info("Using OpenAI GPT for LLM", model=settings.openai_model)
            return ChatOpenAI(
                model=settings.openai_model,
                temperature=0.1,
                api_key=settings.openai_api_key,
            )
        else:
            raise ValueError("No LLM API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt for this agent.

        Should describe:
        - Agent's role and expertise
        - Available tools and when to use them
        - Output format expectations
        """
        pass

    @abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        """
        Process an input and return agent output.

        Args:
            input_data: Input to the agent

        Returns:
            AgentOutput with response and metadata
        """
        pass

    def build_graph(self) -> StateGraph:
        """
        Build the LangGraph state graph for this agent.

        Override this method for custom graph structures.
        Default is a simple: input -> process -> output flow.
        """
        workflow = StateGraph(BaseAgentState)

        # Add nodes
        workflow.add_node("process", self._process_node)

        # Set entry point
        workflow.set_entry_point("process")

        # Add edges
        workflow.add_edge("process", END)

        return workflow.compile()

    async def _process_node(self, state: BaseAgentState) -> BaseAgentState:
        """
        Process node in the graph.

        This is called by LangGraph and wraps the agent's process method.
        """
        # Convert messages to input
        last_message = state["messages"][-1] if state["messages"] else None
        if not last_message:
            return state

        input_data = AgentInput(
            message=last_message.content,
            session_id=state.get("session_id"),
            user_id=state["user_id"],
        )

        # Process
        start_time = time.time()
        try:
            output = await self.process(input_data)
            execution_time = int((time.time() - start_time) * 1000)

            # Log execution
            log_agent_execution(
                agent_name=self.agent_name,
                duration_seconds=execution_time / 1000,
                status="success",
                tools_used=output.tools_used,
            )

            # Update state
            state["messages"].append(AIMessage(content=output.response))
            state["final_response"] = output.response

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error("Agent failed", agent_name=self.agent_name, error_message=str(e))

            log_agent_execution(
                agent_name=self.agent_name,
                duration_seconds=execution_time / 1000,
                status="error",
                error=str(e),
            )

            state["final_response"] = f"Error: {str(e)}"

        return state

    async def invoke(self, input_data: AgentInput) -> AgentOutput:
        """
        Invoke the agent with input data.

        This is the main entry point for using the agent.
        """
        start_time = time.time()

        try:
            output = await self.process(input_data)
            execution_time = int((time.time() - start_time) * 1000)

            log_agent_execution(
                agent_name=self.agent_name,
                duration_seconds=execution_time / 1000,
                status="success",
                tools_used=output.tools_used,
            )

            return output

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error("Agent failed", agent_name=self.agent_name, error_message=str(e))

            log_agent_execution(
                agent_name=self.agent_name,
                duration_seconds=execution_time / 1000,
                status="error",
                error=str(e),
            )

            raise

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        """Convert message dicts to LangChain message objects."""
        formatted = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                formatted.append(SystemMessage(content=content))
            elif role == "user":
                formatted.append(HumanMessage(content=content))
            elif role in ["assistant", "agent"]:
                formatted.append(AIMessage(content=content))

        return formatted

    def _build_context(self, input_data: AgentInput, memories: List[Any] = None) -> str:
        """
        Build context string from input and memories.

        Args:
            input_data: Input to the agent
            memories: Relevant memories from vector store

        Returns:
            Formatted context string
        """
        context_parts = []

        # Add memories if available
        if memories:
            context_parts.append("## Relevant Past Learnings:")
            for mem in memories:
                context_parts.append(f"- {mem.content} (confidence: {mem.confidence_score:.2f})")
            context_parts.append("")

        # Add current context
        if input_data.context:
            context_parts.append("## Current Context:")
            for key, value in input_data.context.items():
                context_parts.append(f"- {key}: {value}")
            context_parts.append("")

        return "\n".join(context_parts)
