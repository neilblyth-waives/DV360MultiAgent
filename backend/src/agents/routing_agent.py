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
                "description": "Analyzes campaign performance at INSERTION ORDER (IO) level - overall campaign metrics, spend, impressions, clicks, conversions, revenue, CTR, ROAS. Use for top-line campaign performance questions.",
                "keywords": ["performance", "campaign", "io", "insertion order", "metrics", "ctr", "roas", "conversions", "optimize", "kpis", "how is", "performing"],
            },
            "audience_targeting": {
                "description": "Analyzes performance at LINE ITEM level - audience segments, targeting tactics, line item comparison within IOs. Use for questions about specific tactics, audiences, or line items.",
                "keywords": ["audience", "line item", "targeting", "segment", "tactic", "line items", "audiences", "remarketing", "prospecting"],
            },
            "creative_inventory": {
                "description": "Analyzes CREATIVE performance by creative name and ad size/format. Use for questions about which creatives or ad sizes are performing best, creative fatigue, or creative optimization.",
                "keywords": ["creative", "ad", "banner", "size", "format", "asset", "fatigue", "300x250", "728x90", "creatives", "ads"],
            },
            "budget_risk": {
                "description": "Analyzes BUDGET data for Quiz advertiser - budget pacing, risk identification, spend optimization. Use for questions about budgets, pacing, underspend, overspend.",
                "keywords": ["budget", "pacing", "spend", "allocation", "forecast", "risk", "depletion", "overspend", "underspend"],
            },
        }

    async def route(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Route a query to appropriate specialist agent(s).

        Args:
            query: User query
            session_context: Optional session context
            conversation_history: Optional list of recent messages [{"role": "user/assistant", "content": "..."}]

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

        # Build conversation context section
        context_section = ""
        if conversation_history and len(conversation_history) > 0:
            # Get last few exchanges for context
            recent_messages = conversation_history[-6:]  # Last 3 exchanges (6 messages)
            context_lines = []
            for msg in recent_messages:
                role = "User" if msg["role"] == "user" else "Assistant"
                # Truncate long messages
                content = msg["content"][:300] + "..." if len(msg["content"]) > 300 else msg["content"]
                context_lines.append(f"{role}: {content}")

            context_section = f"""
CONVERSATION HISTORY (recent messages for context):
{chr(10).join(context_lines)}

IMPORTANT: The current query may be a follow-up or clarification to the conversation above.
- If the user's query is short (like "budget", "performance", "yes", "that one"), interpret it in context of the previous messages.
- If the assistant just asked for clarification, the user's response is likely answering that question.
- If the query starts with "no" followed by dates or a request (e.g., "no pull 4-17"), the user is CORRECTING the previous suggestion, not rejecting it. Route based on what comes after "no".
- If the user provides date ranges (e.g., "4th Jan - 17 Jan", "Jan 4-17", "pull 4-17"), look at the conversation context to determine intent:
  * If previous messages mention "performance", "campaign", "metrics" → performance_diagnosis
  * If previous messages mention "budget", "pacing", "spend" → budget_risk
  * If previous messages mention "audience", "targeting", "line item" → audience_targeting
  * If previous messages mention "creative", "ad", "banner" → creative_inventory
  * If no clear context, default to performance_diagnosis (most common use case)
"""

        # Build routing prompt
        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year

        routing_prompt = f"""You are a routing assistant for a DV360 analysis system. Analyze the user's query and determine which specialist agent(s) should handle it.
{context_section}

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise.

Available agents:
{agents_description}

User query: "{query}"

Instructions:
1. Analyze the query to understand user intent
2. Select the most appropriate agent(s) ONLY if you clearly understand what the user wants
3. You can select multiple agents if the query requires multiple perspectives
4. Respond in this exact format:

AGENTS: agent_name_1, agent_name_2 (or NONE if unclear)
REASONING: Brief explanation of why these agents were selected (or why clarification is needed)
CONFIDENCE: A score from 0.0 to 1.0 indicating confidence in this routing decision
CLARIFICATION: Only include this line if the query is unclear. Ask a specific question to help understand what the user wants.

Valid agent names: {', '.join(self.specialist_agents.keys())}

IMPORTANT: If the query is vague, ambiguous, or you're not sure what the user wants:
- Set AGENTS to NONE
- Set CONFIDENCE to 0.0
- Include a CLARIFICATION line asking what specific information they need

Examples of queries that need clarification (NO conversation context):
- "hello" → needs clarification (greeting, not a question)
- "help" → needs clarification (what kind of help?)
- "show me data" → needs clarification (what data? performance? budget?)
- "what's happening" → needs clarification (with what? campaign? budget?)

Examples of clear queries:
- "How is campaign Quiz performing?" → performance_diagnosis
- "What's the budget status?" → budget_risk
- "Which creatives are doing best?" → creative_inventory

Examples of follow-up queries (WITH conversation context):
- Previous: Assistant asked "What would you like to know about? Performance, budget, creative, or audience?"
  Current: "budget" → budget_risk (user is answering the clarification question)
- Previous: User asked about campaign performance
  Current: "what about the budget?" → budget_risk (follow-up question)
- Previous: Assistant asked for clarification
  Current: "performance for Quiz" → performance_diagnosis (user provided clarification)
- Previous: User asked "how is Quiz performing?" or "Quiz performance"
  Current: "pull 4th Jan - 17 Jan" or "no, pull 4-17" → performance_diagnosis (user is providing dates for performance query)
- Previous: User asked "what's the budget status?" or "budget pacing"
  Current: "4th Jan - 17 Jan" or "Jan 4-17" → budget_risk (user is specifying date range for budget query)
- Previous: User asked "which audiences are performing?"
  Current: "pull 4-17 Jan" → audience_targeting (user is specifying date range for audience query)
- Previous: Assistant asked about date ranges or weeks (with no clear context)
  Current: "pull 4th Jan - 17 Jan" → performance_diagnosis (default to performance if context unclear)

CRITICAL: When users provide date ranges, use conversation context to determine the agent:
- Look at what the user was asking about BEFORE providing dates
- If context is unclear, default to performance_diagnosis (most common)
- Do NOT ask for clarification if dates are provided - route based on context

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
            clarification_question = ""

            for line in response_text.split('\n'):
                line = line.strip()
                if line.startswith("AGENTS:"):
                    agents_part = line.replace("AGENTS:", "").strip()
                    # Check for NONE
                    if agents_part.upper() == "NONE":
                        selected_agents = []
                    else:
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

                elif line.startswith("CLARIFICATION:"):
                    clarification_value = line.replace("CLARIFICATION:", "").strip()
                    # Ignore "None", "N/A", empty, or values that START with "none" (e.g., "None - user intent is clear")
                    clarification_lower = clarification_value.lower()
                    is_no_clarification = (
                        clarification_lower in ("none", "n/a", "na", "null", "") or
                        clarification_lower.startswith("none ") or
                        clarification_lower.startswith("none-") or
                        clarification_lower.startswith("none,") or
                        clarification_lower.startswith("n/a ") or
                        clarification_lower.startswith("not needed") or
                        clarification_lower.startswith("no clarification")
                    )
                    if not is_no_clarification:
                        clarification_question = clarification_value

            # If nothing selected, low confidence, or clarification requested
            if not selected_agents or confidence < 0.4 or clarification_question:
                logger.info(
                    "LLM routing unclear - requesting clarification",
                    selected_agents=selected_agents,
                    confidence=confidence,
                    clarification=clarification_question
                )

                # Use LLM's clarification question if provided, otherwise use default
                if clarification_question:
                    clarification_msg = clarification_question
                else:
                    clarification_msg = (
                        "I'm not sure what you're asking about. Could you please clarify?\n\n"
                        "I can help with:\n"
                        "- **Campaign performance** - metrics like CTR, ROAS, conversions\n"
                        "- **Audience targeting** - line item and segment analysis\n"
                        "- **Creative performance** - which ads/sizes are working best\n"
                        "- **Budget pacing** - spend status and risk analysis\n\n"
                        "What would you like to know?"
                    )

                return {
                    "selected_agents": [],
                    "routing_reasoning": routing_reasoning or "Query is unclear or ambiguous",
                    "confidence": confidence if confidence > 0 else 0.0,
                    "raw_response": response_text,
                    "clarification_needed": True,
                    "clarification_message": clarification_msg
                }

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
                "raw_response": response_text,
                "clarification_needed": False
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
            Routing decision dict with clarification_needed flag if query is unclear
        """
        query_lower = query.lower()
        selected = []

        for agent_name, info in self.specialist_agents.items():
            keywords = info.get("keywords", [])
            if any(keyword in query_lower for keyword in keywords):
                selected.append(agent_name)

        # If no keywords match, query is unclear - ask for clarification
        if not selected:
            logger.info(
                "Fallback keyword routing - query unclear, requesting clarification",
                query=query[:50]
            )

            return {
                "selected_agents": [],
                "routing_reasoning": "Query is unclear - no matching keywords found",
                "confidence": 0.0,
                "raw_response": None,
                "clarification_needed": True,
                "clarification_message": (
                    "I'm not sure what you're asking about. Could you please clarify?\n\n"
                    "I can help with:\n"
                    "- Campaign performance and metrics (CTR, ROAS, conversions)\n"
                    "- Audience targeting and line item analysis\n"
                    "- Creative performance and optimization\n"
                    "- Budget pacing and spend analysis\n\n"
                    "What would you like to know?"
                )
            }

        logger.info(
            "Fallback keyword routing",
            query=query[:50],
            selected_agents=selected
        )

        return {
            "selected_agents": selected,
            "routing_reasoning": "Fallback keyword-based routing",
            "confidence": 0.6,
            "raw_response": None,
            "clarification_needed": False
        }


# Global instance
routing_agent = RoutingAgent()
