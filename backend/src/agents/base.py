"""
Base agent class for all DV360 agents.
"""
import os
from typing import Dict, List, Any, Optional, Literal, Union
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
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from ..core.config import settings
from ..core.telemetry import get_logger, log_agent_execution
from ..schemas.agent import AgentInput, AgentOutput, AgentState


logger = get_logger(__name__)


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
        llm: Optional[BaseChatModel] = None,
        llm_choice: Optional[Literal["anthropic", "openai"]] = None,
    ):
        """
        Initialize base agent.

        Args:
            agent_name: Unique name for this agent
            description: What this agent does
            tools: List of LangChain tools available to this agent
            llm: Optional LLM instance to use. If provided, this will be used instead of auto-initialization.
            llm_choice: Optional choice to force a specific LLM provider ("anthropic" or "openai").
                       Only used if llm is not provided. If None, uses default priority (Anthropic > OpenAI).
        """
        self.agent_name = agent_name
        self.description = description
        self.tools = tools or []
        
        # Use provided LLM, or initialize based on choice, or use default
        if llm is not None:
            self.llm = llm
            logger.info(f"Using provided LLM for agent: {agent_name}", llm_type=type(llm).__name__)
        elif llm_choice is not None:
            self.llm = self._initialize_llm(provider=llm_choice)
        else:
            self.llm = self._initialize_llm()
        
        self.graph = None

        logger.info(f"Initialized agent: {agent_name}", tools_count=len(self.tools))

    def _initialize_llm(self, provider: Optional[Literal["anthropic", "openai"]] = None):
        """
        Initialize the LLM based on configuration.

        Args:
            provider: Optional provider choice ("anthropic" or "openai"). 
                     If None, uses default priority: Anthropic (Claude) > OpenAI (GPT)
        
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

        # If provider is specified, use it
        if provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("Anthropic API key not configured. Set ANTHROPIC_API_KEY")
            logger.info("Using Anthropic Claude for LLM", model=settings.anthropic_model)
            return ChatAnthropic(
                model=settings.anthropic_model,
                temperature=0.1,
                api_key=settings.anthropic_api_key,
            )
        elif provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY")
            logger.info("Using OpenAI GPT for LLM", model=settings.openai_model)
            return ChatOpenAI(
                model=settings.openai_model,
                temperature=0.1,
                api_key=settings.openai_api_key,
            )
        
        # Default: try Anthropic first, then OpenAI
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
