"""
Performance Diagnosis Agent - LangGraph Implementation.

This is the new LangGraph-based version with ReAct agent for tool calling.
Uses StateGraph with individual node functions.
"""
from typing import Dict, Any
import time
import re
import json

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseAgent
from ..schemas.agent_state import PerformanceAgentState, create_initial_performance_state
from ..tools.agent_tools import get_performance_agent_tools
from ..tools.decision_logger import decision_logger
from ..schemas.agent import AgentOutput, AgentDecisionCreate
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class PerformanceAgentLangGraph(BaseAgent):
    """
    Performance Diagnosis Agent using LangGraph.

    Architecture:
    - StateGraph with individual node functions
    - ReAct agent for dynamic tool selection (data collection)
    - Python functions for deterministic analysis
    - LLM for natural language response generation
    """

    def __init__(self):
        """Initialize Performance Agent with LangGraph."""
        super().__init__(
            agent_name="performance_diagnosis",
            description="Analyzes DV360 campaign performance using LangGraph and ReAct",
            tools=[],
        )

        # Build the graph
        self.graph = self._build_graph()

    def get_system_prompt(self) -> str:
        """Return system prompt for the performance agent."""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year
        
        return f"""You are a DV360 Performance Diagnosis Agent using LangGraph.

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise.

Your role:
- Analyze campaign performance metrics
- Identify issues and opportunities
- Provide data-driven recommendations

You have access to tools for querying Snowflake and retrieving past learnings.

PRIMARY TABLE (use this for most queries):
- reports.reporting_revamp.ALL_PERFORMANCE_AGG: Campaign performance data (impressions, clicks, conversions, spend, revenue)

When building custom SQL queries with execute_custom_snowflake_query:
- PRIMARY: Use reports.reporting_revamp.ALL_PERFORMANCE_AGG for campaign performance analysis
- Use appropriate date ranges based on the user's question (default to current year/month if not specified)
- Add aggregations (SUM, AVG, etc.) as needed
- Filter by advertiser, insertion_order, date as relevant
- You can dynamically adapt and use other tables if needed for the specific query

Use them wisely to gather the data needed to answer the user's question."""

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph StateGraph.

        Flow with conditional routing:
        parse_query → [needs_clarification?]
          ├─ YES → ask_clarification → END (wait for user)
          └─ NO  → retrieve_memory → react_data_collection →
                   analyze_data → generate_recommendations → generate_response → END
        """
        workflow = StateGraph(PerformanceAgentState)

        # Add nodes
        workflow.add_node("parse_query", self._parse_query_node)
        workflow.add_node("ask_clarification", self._ask_clarification_node)
        workflow.add_node("retrieve_memory", self._retrieve_memory_node)
        workflow.add_node("react_data_collection", self._react_data_collection_node)
        workflow.add_node("analyze_data", self._analyze_data_node)
        workflow.add_node("generate_recommendations", self._generate_recommendations_node)
        workflow.add_node("generate_response", self._generate_response_node)

        # Entry point
        workflow.set_entry_point("parse_query")

        # Conditional routing after parse_query
        workflow.add_conditional_edges(
            "parse_query",
            self._should_ask_for_clarification,
            {
                "clarify": "ask_clarification",
                "proceed": "retrieve_memory"
            }
        )

        # If asking for clarification, end and wait for user response
        workflow.add_edge("ask_clarification", END)

        # Normal flow continues
        workflow.add_edge("retrieve_memory", "react_data_collection")
        workflow.add_edge("react_data_collection", "analyze_data")
        workflow.add_edge("analyze_data", "generate_recommendations")
        workflow.add_edge("generate_recommendations", "generate_response")
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    # ========================================================================
    # Node Functions
    # ========================================================================

    def _parse_query_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 1: Parse query to extract campaign_id and advertiser_id.

        This is deterministic (regex-based), no LLM needed.
        Also calculates confidence in the parse.
        """
        query = state["query"]

        campaign_id = None
        advertiser_id = None
        confidence = 0.0

        # Try to extract campaign/insertion order ID
        campaign_patterns = [
            r"campaign\s+([A-Za-z0-9_-]+)",
            r"insertion[_\s]order\s+([A-Za-z0-9_-]+)",
            r"IO\s+([A-Za-z0-9_-]+)",
        ]

        for pattern in campaign_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                campaign_id = match.group(1)
                confidence += 0.6  # Found specific campaign ID
                break

        # Try to extract advertiser ID
        advertiser_patterns = [
            r"advertiser\s+([A-Za-z0-9_-]+)",
        ]

        for pattern in advertiser_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                advertiser_id = match.group(1)
                confidence += 0.2  # Found advertiser

        # Check for general performance keywords (ambiguous queries)
        general_keywords = ["how", "performing", "performance", "status", "metrics"]
        has_general_keywords = any(kw in query.lower() for kw in general_keywords)

        if has_general_keywords:
            confidence += 0.2  # At least we know they want performance data

        # If query is too vague (low confidence), we'll need clarification
        logger.info(
            "Parsed query",
            campaign_id=campaign_id,
            advertiser_id=advertiser_id,
            confidence=confidence
        )

        return {
            "campaign_id": campaign_id,
            "advertiser_id": advertiser_id,
            "parse_confidence": confidence,
            "reasoning_steps": [f"Parsed query: campaign_id={campaign_id}, advertiser_id={advertiser_id}, confidence={confidence:.2f}"]
        }

    def _should_ask_for_clarification(self, state: PerformanceAgentState) -> str:
        """
        Decision function: Should we ask for clarification?

        Returns:
            "clarify" if we need more info from user
            "proceed" if we have enough info to continue
        """
        confidence = state.get("parse_confidence", 0.0)
        campaign_id = state.get("campaign_id")
        query = state.get("query", "")

        # If confidence is very low, ask for clarification
        if confidence < 0.4:
            logger.info("Low confidence, will ask for clarification", confidence=confidence)
            return "clarify"

        # If no campaign_id and query is vague, ask for clarification
        if not campaign_id and len(query.split()) < 5:
            logger.info("Vague query without campaign ID, will ask for clarification")
            return "clarify"

        # Otherwise, proceed with analysis
        logger.info("Sufficient information, proceeding with analysis", confidence=confidence)
        return "proceed"

    def _ask_clarification_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 1b: Ask user for clarification when query is ambiguous.

        Generates specific questions to help narrow down what the user wants.
        """
        query = state["query"]
        campaign_id = state.get("campaign_id")
        advertiser_id = state.get("advertiser_id")

        # Build clarification questions based on what's missing
        questions = []

        if not campaign_id:
            questions.append("Which campaign would you like me to analyze? Please provide the campaign name or ID.")

        if not advertiser_id:
            questions.append("Which advertiser is this for? (e.g., 'Quiz', 'BrandX')")

        # If query is too vague
        if len(query.split()) < 5:
            questions.append("What specific metrics are you interested in? (e.g., CTR, conversions, spend, ROAS)")

        # Generate a friendly response asking for more info
        if questions:
            response_parts = [
                "I need a bit more information to help you with that.",
                "",
                "Please provide:",
            ]

            for i, question in enumerate(questions, 1):
                response_parts.append(f"{i}. {question}")

            response_parts.append("")
            response_parts.append("Once I have this information, I can provide a detailed performance analysis!")

            response = "\n".join(response_parts)
        else:
            # Fallback
            response = "I need more information to analyze the campaign. Which campaign would you like me to look at?"

        logger.info("Asking for clarification", questions_count=len(questions))

        return {
            "needs_clarification": True,
            "clarification_questions": questions,
            "response": response,
            "confidence": 0.0,  # No analysis performed yet
            "reasoning_steps": [f"Asked for clarification: {len(questions)} questions"]
        }

    def _retrieve_memory_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 2: Retrieve session history and relevant learnings.

        This is deterministic (semantic search), no LLM decision needed.
        """
        # For now, skip memory retrieval to simplify
        # In production, you'd call memory_retrieval_tool here

        logger.info("Skipping memory retrieval for MVP")

        return {
            "session_history": [],
            "relevant_learnings": [],
            "reasoning_steps": ["Retrieved memory context (skipped for MVP)"],
            "tools_used": ["memory_retrieval"]
        }

    def _react_data_collection_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 3: Use ReAct agent to collect data from Snowflake.

        This is where the LLM decides which tools to call.
        The ReAct agent will:
        1. See available tools (query_campaign_performance, etc.)
        2. Decide which to call based on the query
        3. Call tools and observe results
        4. Potentially call more tools
        5. Return final data
        """
        query = state["query"]
        campaign_id = state["campaign_id"]
        advertiser_id = state["advertiser_id"]

        # Get tools for performance agent
        tools = get_performance_agent_tools()

        # Create ReAct agent
        # Note: messages_modifier is the correct parameter, not state_modifier
        react_agent = create_react_agent(
            model=self.llm,
            tools=tools,
            messages_modifier=SystemMessage(content=f"""You are a data collection agent for DV360 performance analysis.

Your goal: Collect the necessary data to answer the user's query.

User query: "{query}"
Campaign ID: {campaign_id}
Advertiser ID: {advertiser_id}

Available tools:
- query_campaign_performance: Get campaign metrics (impressions, clicks, conversions, etc.)
- retrieve_relevant_learnings: Get past insights
- get_session_history: Get conversation context

Instructions:
1. Call query_campaign_performance to get the campaign data
2. Use the campaign_id if available, otherwise query all campaigns
3. You only need to collect data - analysis will happen in a later step
4. Once you have the data, return it

Call the tools now to collect the data.""")
        )

        # Invoke the ReAct agent
        try:
            logger.info("Invoking ReAct agent for data collection")

            # Build agent input
            agent_input = {
                "messages": [
                    HumanMessage(content=f"Collect performance data for: {query}")
                ]
            }

            # Run the agent
            result = react_agent.invoke(agent_input)

            # Extract performance data from agent's tool calls
            # The agent will have called query_campaign_performance
            # We need to extract the results

            # For now, parse the agent's final message
            final_message = result["messages"][-1].content if result.get("messages") else ""

            logger.info(
                "ReAct agent completed",
                final_message_preview=final_message[:200]
            )

            # Try to extract JSON from the message
            # The tool returns JSON strings, so parse them
            performance_data = []
            try:
                # Look for JSON in the message
                import re
                json_match = re.search(r'\[.*\]', final_message, re.DOTALL)
                if json_match:
                    performance_data = json.loads(json_match.group(0))
            except:
                logger.warning("Could not parse performance data from ReAct agent output")

            return {
                "performance_data": performance_data if performance_data else None,
                "reasoning_steps": ["ReAct agent collected data from Snowflake"],
                "tools_used": ["react_agent", "snowflake_query"]
            }

        except Exception as e:
            logger.error("ReAct agent failed", error=str(e))
            return {
                "performance_data": None,
                "reasoning_steps": [f"ReAct agent failed: {str(e)}"],
                "tools_used": ["react_agent"]
            }

    def _analyze_data_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 4: Analyze performance data (Python, deterministic).

        Calculate metrics, identify trends, detect issues.
        """
        performance_data = state.get("performance_data")

        if not performance_data:
            return {
                "metrics": {},
                "trends": {},
                "issues": ["No performance data available"],
                "insights": [],
                "reasoning_steps": ["Analysis skipped - no data"]
            }

        # Calculate aggregate metrics
        total_impressions = sum(row.get("IMPRESSIONS", 0) or 0 for row in performance_data)
        total_clicks = sum(row.get("CLICKS", 0) or 0 for row in performance_data)
        total_conversions = sum(row.get("TOTAL_CONVERSIONS", 0) or 0 for row in performance_data)
        total_spend = sum(row.get("SPEND", 0) or 0 for row in performance_data)
        total_revenue = sum(row.get("TOTAL_REVENUE", 0) or 0 for row in performance_data)

        # Calculate derived metrics
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        cpc = total_spend / total_clicks if total_clicks > 0 else 0
        cpa = total_spend / total_conversions if total_conversions > 0 else 0
        roas = total_revenue / total_spend if total_spend > 0 else 0

        metrics = {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "conversions": total_conversions,
            "spend": total_spend,
            "revenue": total_revenue,
            "ctr": ctr,
            "cpc": cpc,
            "cpa": cpa,
            "roas": roas,
        }

        # Calculate trends (first half vs second half)
        mid = len(performance_data) // 2
        if mid > 0:
            first_half = performance_data[mid:]  # Most recent (DESC order)
            second_half = performance_data[:mid]  # Older

            first_impr = sum(row.get("IMPRESSIONS", 0) or 0 for row in first_half)
            second_impr = sum(row.get("IMPRESSIONS", 0) or 0 for row in second_half)

            first_clicks = sum(row.get("CLICKS", 0) or 0 for row in first_half)
            second_clicks = sum(row.get("CLICKS", 0) or 0 for row in second_half)

            impr_change = ((first_impr - second_impr) / second_impr * 100) if second_impr > 0 else 0
            clicks_change = ((first_clicks - second_clicks) / second_clicks * 100) if second_clicks > 0 else 0

            trends = {
                "impressions_change": impr_change,
                "clicks_change": clicks_change,
            }
        else:
            trends = {}

        # Detect issues
        issues = []
        insights = []

        if total_conversions == 0 and total_clicks > 10:
            issues.append("No conversions despite significant clicks - check conversion tracking")

        if ctr < 0.5:
            issues.append(f"Low CTR ({ctr:.2f}%) - may indicate targeting or creative issues")
        else:
            insights.append(f"CTR ({ctr:.2f}%) is within acceptable range")

        if total_spend == 0:
            issues.append("No spend recorded - campaign may not be running")

        logger.info(
            "Analysis complete",
            metrics=metrics,
            issues=issues,
            insights=insights
        )

        return {
            "metrics": metrics,
            "trends": trends,
            "issues": issues,
            "insights": insights,
            "reasoning_steps": ["Analyzed performance data with Python calculations"]
        }

    def _generate_recommendations_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 5: Generate recommendations (Python, rule-based).
        """
        metrics = state.get("metrics", {})
        issues = state.get("issues", [])

        recommendations = []

        # Rule-based recommendations
        if "No conversions" in str(issues):
            recommendations.append({
                "priority": "high",
                "action": "Verify conversion tags are firing correctly",
                "reason": "Clicks without conversions suggests tracking issues"
            })

        ctr = metrics.get("ctr", 0)
        if ctr < 0.5:
            recommendations.append({
                "priority": "medium",
                "action": "Review targeting and creative",
                "reason": f"CTR of {ctr:.2f}% is below industry benchmarks"
            })

        if not recommendations:
            recommendations.append({
                "priority": "low",
                "action": "Continue monitoring performance",
                "reason": "No critical issues detected"
            })

        logger.info("Generated recommendations", count=len(recommendations))

        return {
            "recommendations": recommendations,
            "reasoning_steps": ["Generated rule-based recommendations"]
        }

    def _generate_response_node(self, state: PerformanceAgentState) -> Dict[str, Any]:
        """
        Node 6: Generate natural language response (LLM).
        """
        query = state["query"]
        metrics = state.get("metrics", {})
        trends = state.get("trends", {})
        issues = state.get("issues", [])
        insights = state.get("insights", [])
        recommendations = state.get("recommendations", [])

        # Build prompt for LLM
        system_prompt = """You are a DV360 Performance Analysis Agent.

Generate a clear, actionable response about campaign performance.

Format your response in markdown with sections:
## Performance Summary
## Key Metrics
## Issues & Recommendations"""

        user_prompt = f"""User Query: "{query}"

Metrics:
{json.dumps(metrics, indent=2)}

Trends:
{json.dumps(trends, indent=2)}

Issues Detected:
{chr(10).join(f'- {issue}' for issue in issues)}

Insights:
{chr(10).join(f'- {insight}' for insight in insights)}

Recommendations:
{chr(10).join(f'- [{rec["priority"]}] {rec["action"]}: {rec["reason"]}' for rec in recommendations)}

Generate a professional, actionable response."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            result = self.llm.invoke(messages)
            response = result.content

            logger.info("Generated LLM response", length=len(response))

            return {
                "response": response,
                "confidence": 0.9,
                "reasoning_steps": ["Generated natural language response with LLM"],
                "tools_used": ["llm_analysis"]
            }

        except Exception as e:
            logger.error("LLM response generation failed", error=str(e))
            return {
                "response": f"Error generating response: {str(e)}",
                "confidence": 0.0,
                "reasoning_steps": [f"LLM failed: {str(e)}"]
            }

    # ========================================================================
    # Main Entry Point
    # ========================================================================

    async def invoke(self, input_data: Any) -> AgentOutput:
        """
        Invoke the agent (main entry point).

        Args:
            input_data: AgentInput with query, session_id, user_id

        Returns:
            AgentOutput with response
        """
        start_time = time.time()

        # Create initial state
        initial_state = create_initial_performance_state(
            query=input_data.message,
            session_id=input_data.session_id,
            user_id=input_data.user_id
        )

        try:
            # Run the graph
            logger.info("Running Performance Agent LangGraph")
            final_state = self.graph.invoke(initial_state)

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Log decision
            if input_data.session_id:
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="performance_analysis_langgraph",
                    input_data={
                        "query": input_data.message,
                        "campaign_id": final_state.get("campaign_id"),
                    },
                    output_data={
                        "metrics": final_state.get("metrics"),
                        "issues": final_state.get("issues"),
                        "recommendations": final_state.get("recommendations"),
                    },
                    tools_used=final_state.get("tools_used", []),
                    reasoning="\n".join(final_state.get("reasoning_steps", [])),
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=final_state.get("response", "No response generated"),
                agent_name=self.agent_name,
                reasoning="\n".join(final_state.get("reasoning_steps", [])),
                tools_used=final_state.get("tools_used", []),
                confidence=final_state.get("confidence", 0.0),
                metadata={
                    "campaign_id": final_state.get("campaign_id"),
                    "metrics": final_state.get("metrics"),
                    "execution_time_ms": execution_time_ms,
                },
            )

        except Exception as e:
            logger.error("Performance Agent LangGraph failed", error=str(e))

            return AgentOutput(
                response=f"Error: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Failed: {str(e)}",
                tools_used=[],
                confidence=0.0,
            )

    # Legacy process method for backward compatibility
    async def process(self, input_data: Any) -> AgentOutput:
        """Legacy process method - calls invoke."""
        return await self.invoke(input_data)


# Global instance
performance_agent_langgraph = PerformanceAgentLangGraph()
