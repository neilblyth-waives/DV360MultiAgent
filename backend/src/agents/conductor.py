"""
Chat Conductor Agent - Supervisor for routing to specialist agents.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
import time

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from .base import BaseAgent, BaseAgentState
from .performance_agent import performance_agent
from .performance_agent_langgraph import performance_agent_langgraph  # New LangGraph version
from .budget_risk_agent import budget_risk_agent
from .audience_agent import audience_targeting_agent
from .creative_agent import creative_inventory_agent
from ..tools.memory_tool import memory_retrieval_tool
from ..memory.session_manager import session_manager
from ..tools.decision_logger import decision_logger
from ..schemas.agent import AgentInput, AgentOutput, AgentDecisionCreate
from ..schemas.chat import ChatMessageCreate
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class ConductorState(BaseAgentState):
    """Extended state for conductor agent."""
    selected_agents: List[str] = []
    agent_responses: Dict[str, str] = {}
    routing_reasoning: str = ""


class ChatConductor(BaseAgent):
    """
    Chat Conductor Agent - Supervisor for routing user queries.

    Responsibilities:
    - Understand user intent
    - Route to appropriate specialist agent(s)
    - Can invoke multiple agents for complex queries
    - Aggregate responses from multiple agents
    - Maintain conversation flow
    - Store messages in session history
    """

    def __init__(self):
        """Initialize Chat Conductor."""
        super().__init__(
            agent_name="chat_conductor",
            description="Routes user queries to specialist agents and aggregates responses",
            tools=[],
        )

        # Registry of available specialist agents
        self.specialist_agents = {
            "performance_diagnosis": {
                "agent": performance_agent_langgraph,  # Using new LangGraph version!
                "description": "Analyzes campaign performance, identifies issues, provides optimization recommendations",
                "keywords": ["performance", "campaign", "metrics", "ctr", "roas", "conversions", "optimize"],
            },
            "budget_risk": {
                "agent": budget_risk_agent,
                "description": "Analyzes budget utilization, pacing, and risk assessment, provides spend optimization and risk mitigation recommendations",
                "keywords": ["budget", "pacing", "spend", "allocation", "forecast", "over-pacing", "under-pacing", "risk", "depletion"],
            },
            "audience_targeting": {
                "agent": audience_targeting_agent,
                "description": "Analyzes audience segment performance, provides targeting optimization recommendations",
                "keywords": ["audience", "targeting", "segment", "demographic", "lookalike", "remarketing"],
            },
            "creative_inventory": {
                "agent": creative_inventory_agent,
                "description": "Analyzes creative performance, detects fatigue, provides creative refresh recommendations",
                "keywords": ["creative", "ad", "banner", "video", "asset", "design", "fatigue", "refresh"],
            },
        }

    def get_system_prompt(self) -> str:
        """Return system prompt for the conductor."""
        agent_descriptions = "\n".join([
            f"- **{name}**: {info['description']}"
            for name, info in self.specialist_agents.items()
        ])

        return f"""You are the Chat Conductor, an intelligent supervisor agent for a DV360 analysis system.

Your role:
- Understand user queries about DV360 campaigns
- Route queries to the appropriate specialist agent(s)
- Coordinate responses from multiple agents when needed
- Provide a cohesive, helpful response to the user

Available Specialist Agents:
{agent_descriptions}

Routing Guidelines:
1. Analyze the user's question to determine intent
2. Select the most appropriate specialist agent(s)
3. For complex queries, you may invoke multiple agents
4. Synthesize responses into a clear, actionable answer

Response Style:
- Be helpful and conversational
- Focus on actionable insights
- Highlight key findings
- If data is unavailable, explain why and suggest alternatives

When routing:
- Performance questions → performance_diagnosis agent
- Budget/pacing/risk questions → budget_risk agent
- Audience questions → audience_targeting agent
- Creative questions → creative_inventory agent

If unsure, default to the most relevant agent or ask clarifying questions."""

    async def process(self, input_data: AgentInput) -> AgentOutput:
        """
        Process a user query by routing to specialist agents.

        Args:
            input_data: User query

        Returns:
            AgentOutput with aggregated response
        """
        start_time = time.time()
        tools_used = ["routing_decision"]
        reasoning_steps = []

        try:
            # Step 1: Store user message in session
            if input_data.session_id:
                user_message = ChatMessageCreate(
                    session_id=input_data.session_id,
                    role="user",
                    content=input_data.message,
                    agent_name=None,
                )
                await session_manager.add_message(user_message)
                reasoning_steps.append("Stored user message in session")

            # Step 2: Retrieve session context and relevant memories
            session_memory = None
            if input_data.session_id:
                session_memory = await memory_retrieval_tool.retrieve_context(
                    query=input_data.message,
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    top_k=3,
                    min_similarity=0.6,
                )
                tools_used.append("memory_retrieval")
                reasoning_steps.append(
                    f"Retrieved session context with {len(session_memory.messages)} messages "
                    f"and {len(session_memory.relevant_learnings)} learnings"
                )

            # Step 3: Determine which agent(s) to route to
            selected_agents = self._route_to_agents(input_data.message, session_memory)
            reasoning_steps.append(f"Routing to agents: {', '.join(selected_agents)}")

            # Step 4: Invoke selected agent(s)
            agent_responses = {}
            for agent_name in selected_agents:
                agent_info = self.specialist_agents.get(agent_name)
                if not agent_info:
                    logger.warning(f"Agent {agent_name} not found in registry")
                    continue

                agent = agent_info["agent"]
                reasoning_steps.append(f"Invoking {agent_name}")

                try:
                    # Create agent input with context
                    agent_input = AgentInput(
                        message=input_data.message,
                        session_id=input_data.session_id,
                        user_id=input_data.user_id,
                        context=input_data.context,
                    )

                    # Invoke the agent
                    agent_output = await agent.invoke(agent_input)
                    agent_responses[agent_name] = agent_output.response
                    tools_used.extend(agent_output.tools_used)
                    reasoning_steps.append(f"{agent_name} completed successfully")

                except Exception as e:
                    logger.error("Agent invocation failed", agent_name=agent_name, error_message=str(e))
                    agent_responses[agent_name] = f"Error: {str(e)}"
                    reasoning_steps.append(f"{agent_name} failed: {str(e)}")

            # Step 5: Synthesize responses
            if len(agent_responses) == 1:
                # Single agent - return its response directly
                final_response = list(agent_responses.values())[0]
            else:
                # Multiple agents - synthesize responses
                final_response = self._synthesize_responses(agent_responses, input_data.message)

            reasoning_steps.append("Synthesized final response")

            # Step 6: Store assistant response in session
            if input_data.session_id:
                assistant_message = ChatMessageCreate(
                    session_id=input_data.session_id,
                    role="assistant",
                    content=final_response,
                    agent_name=self.agent_name,
                )
                await session_manager.add_message(assistant_message)
                reasoning_steps.append("Stored assistant response in session")

            # Step 7: Log routing decision
            execution_time_ms = int((time.time() - start_time) * 1000)

            if input_data.session_id:
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="routing",
                    input_data={
                        "query": input_data.message,
                        "user_id": input_data.user_id,
                    },
                    output_data={
                        "selected_agents": selected_agents,
                        "agents_invoked": list(agent_responses.keys()),
                    },
                    tools_used=tools_used,
                    reasoning="\n".join(reasoning_steps),
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=final_response,
                agent_name=self.agent_name,
                reasoning="\n".join(reasoning_steps),
                tools_used=tools_used,
                confidence=0.95,
                metadata={
                    "agents_invoked": list(agent_responses.keys()),
                    "total_execution_time_ms": execution_time_ms,
                },
            )

        except Exception as e:
            logger.error("Chat conductor failed", error_message=str(e))

            # Log failed decision
            if input_data.session_id:
                execution_time_ms = int((time.time() - start_time) * 1000)
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="routing",
                    input_data={"query": input_data.message},
                    output_data={"error": str(e)},
                    tools_used=tools_used,
                    reasoning=f"Failed: {str(e)}",
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=f"I encountered an error processing your request: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Error: {str(e)}",
                tools_used=tools_used,
                confidence=0.0,
            )

    def _route_to_agents(self, query: str, session_memory: Optional[Any]) -> List[str]:
        """
        Determine which agent(s) to route the query to using LLM.

        Args:
            query: User query
            session_memory: Session context

        Returns:
            List of agent names to invoke
        """
        # Build agent descriptions for the LLM
        agent_list = []
        for agent_name, info in self.specialist_agents.items():
            agent_list.append(f"- {agent_name}: {info['description']}")

        agents_description = "\n".join(agent_list)

        # Build routing prompt
        routing_prompt = f"""You are a routing assistant. Based on the user's query, decide which specialist agent(s) should handle it.

Available agents:
{agents_description}

User query: "{query}"

Instructions:
- Respond with ONLY the agent name(s), one per line
- You can select multiple agents if the query needs multiple perspectives
- Valid agent names: {', '.join(self.specialist_agents.keys())}
- If unsure, default to: performance_diagnosis

Your response (agent names only):"""

        try:
            # Call LLM for routing decision
            from langchain_core.messages import SystemMessage, HumanMessage

            messages = [
                SystemMessage(content="You are a routing assistant that selects which specialist agents should handle user queries."),
                HumanMessage(content=routing_prompt)
            ]

            response = self.llm.invoke(messages)
            response_text = response.content.strip()

            # Parse agent names from response
            selected = []
            for line in response_text.split('\n'):
                line = line.strip().lower().replace('-', '_')
                # Remove any markdown or formatting
                line = line.strip('*-• ').strip()
                if line in self.specialist_agents:
                    selected.append(line)

            logger.info(
                "LLM routing decision",
                query=query[:50],
                selected_agents=selected,
                llm_response=response_text[:100]
            )

            # Default to performance agent if nothing selected
            if not selected:
                logger.info("LLM returned no valid agents, defaulting to performance_diagnosis")
                selected.append("performance_diagnosis")

            return selected

        except Exception as e:
            logger.error("LLM routing failed, falling back to keyword matching", error_message=str(e))

            # Fallback to keyword matching
            query_lower = query.lower()
            selected = []

            for agent_name, info in self.specialist_agents.items():
                keywords = info.get("keywords", [])
                if any(keyword in query_lower for keyword in keywords):
                    selected.append(agent_name)

            if not selected:
                selected.append("performance_diagnosis")

            return selected

    def _synthesize_responses(
        self,
        agent_responses: Dict[str, str],
        original_query: str
    ) -> str:
        """
        Synthesize responses from multiple agents into a cohesive answer.

        Args:
            agent_responses: Responses from each agent
            original_query: Original user query

        Returns:
            Synthesized response
        """
        parts = []

        parts.append(f"I've analyzed your question from multiple perspectives:\n")

        for agent_name, response in agent_responses.items():
            agent_display_name = agent_name.replace("_", " ").title()
            parts.append(f"## {agent_display_name}")
            parts.append(response)
            parts.append("")

        return "\n".join(parts)

    async def handle_conversation(
        self,
        message: str,
        session_id: UUID,
        user_id: str
    ) -> str:
        """
        Handle a conversation turn (convenience method).

        Args:
            message: User message
            session_id: Session ID
            user_id: User ID

        Returns:
            Response string
        """
        input_data = AgentInput(
            message=message,
            session_id=session_id,
            user_id=user_id,
        )

        output = await self.invoke(input_data)
        return output.response


# Global instance
chat_conductor = ChatConductor()
