"""
Routing Agent - Intelligent query routing to specialist agents.

This agent analyzes user intent and routes queries to the appropriate
specialist agent(s) using LLM-based decision making.
"""
from typing import Dict, Any, Optional, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic

from ..core.config import settings
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class RoutingAgent:
    """
    Routing Agent for intelligent query routing.

    Uses LLM to analyze user intent and select the most appropriate
    specialist agent(s) to handle the query.
    """

    def __init__(self):
        """Initialize Routing Agent."""
        self.llm = ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.0,  # Deterministic routing
        )

        # Available specialist agents
        self.specialist_agents = {
            "performance_diagnosis": {
                "description": "Analyzes campaign performance metrics, identifies issues, provides optimization recommendations",
                "keywords": ["performance", "campaign", "metrics", "ctr", "roas", "conversions", "optimize", "kpis"],
            },
            "budget_risk": {
                "description": "Analyzes budget utilization, pacing, and risk assessment, provides spend optimization and risk mitigation",
                "keywords": ["budget", "pacing", "spend", "allocation", "forecast", "risk", "depletion", "overspend"],
            },
            "delivery_optimization": {
                "description": "Analyzes creative performance and audience targeting effectiveness, provides delivery optimization recommendations",
                "keywords": ["creative", "audience", "segment", "targeting", "fatigue", "refresh", "delivery", "asset"],
            },
        }

    async def route(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Route a query to appropriate specialist agent(s).

        Args:
            query: User query
            session_context: Optional session context

        Returns:
            Dict with:
            - selected_agents: List of agent names to invoke
            - routing_reasoning: Explanation of routing decision
            - confidence: Confidence score (0-1)
        """
        # Build agent descriptions for LLM
        agent_list = []
        for agent_name, info in self.specialist_agents.items():
            agent_list.append(f"- **{agent_name}**: {info['description']}")

        agents_description = "\n".join(agent_list)

        # Build routing prompt
        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year
        
        routing_prompt = f"""You are a routing assistant for a DV360 analysis system. Analyze the user's query and determine which specialist agent(s) should handle it.

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise.

Available agents:
{agents_description}

User query: "{query}"

Instructions:
1. Analyze the query to understand user intent
2. Select the most appropriate agent(s)
3. You can select multiple agents if the query requires multiple perspectives
4. Respond in this exact format:

AGENTS: agent_name_1, agent_name_2 (if multiple needed)
REASONING: Brief explanation of why these agents were selected
CONFIDENCE: A score from 0.0 to 1.0 indicating confidence in this routing decision

Valid agent names: {', '.join(self.specialist_agents.keys())}

If the query is too vague or ambiguous, select the most likely agent and set confidence lower.

Your response:"""

        try:
            # Call LLM for routing decision
            messages = [
                SystemMessage(content="You are a routing assistant that selects specialist agents based on user queries."),
                HumanMessage(content=routing_prompt)
            ]

            response = self.llm.invoke(messages)
            response_text = response.content.strip()

            logger.info(
                "LLM routing response",
                query=query[:50],
                response=response_text[:200]
            )

            # Parse response
            selected_agents = []
            routing_reasoning = ""
            confidence = 0.8  # Default

            for line in response_text.split('\n'):
                line = line.strip()
                if line.startswith("AGENTS:"):
                    agents_part = line.replace("AGENTS:", "").strip()
                    for agent in agents_part.split(','):
                        agent_name = agent.strip().lower().replace('-', '_')
                        if agent_name in self.specialist_agents:
                            selected_agents.append(agent_name)

                elif line.startswith("REASONING:"):
                    routing_reasoning = line.replace("REASONING:", "").strip()

                elif line.startswith("CONFIDENCE:"):
                    try:
                        confidence_str = line.replace("CONFIDENCE:", "").strip()
                        confidence = float(confidence_str)
                        confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                    except ValueError:
                        logger.warning("Failed to parse confidence score", confidence_str=confidence_str)

            # Default to performance_diagnosis if nothing selected
            if not selected_agents:
                logger.info("LLM returned no valid agents, defaulting to performance_diagnosis")
                selected_agents = ["performance_diagnosis"]
                routing_reasoning = "Query was ambiguous, defaulted to performance analysis"
                confidence = 0.5

            logger.info(
                "Routing decision made",
                query=query[:50],
                selected_agents=selected_agents,
                confidence=confidence
            )

            return {
                "selected_agents": selected_agents,
                "routing_reasoning": routing_reasoning,
                "confidence": confidence,
                "raw_response": response_text
            }

        except Exception as e:
            logger.error("LLM routing failed, falling back to keyword matching", error_message=str(e))

            # Fallback to keyword matching
            return self._fallback_keyword_routing(query)

    def _fallback_keyword_routing(self, query: str) -> Dict[str, Any]:
        """
        Fallback routing using simple keyword matching.

        Args:
            query: User query

        Returns:
            Routing decision dict
        """
        query_lower = query.lower()
        selected = []

        for agent_name, info in self.specialist_agents.items():
            keywords = info.get("keywords", [])
            if any(keyword in query_lower for keyword in keywords):
                selected.append(agent_name)

        if not selected:
            selected = ["performance_diagnosis"]

        logger.info(
            "Fallback keyword routing",
            query=query[:50],
            selected_agents=selected
        )

        return {
            "selected_agents": selected,
            "routing_reasoning": "Fallback keyword-based routing",
            "confidence": 0.6,
            "raw_response": None
        }


# Global instance
routing_agent = RoutingAgent()
