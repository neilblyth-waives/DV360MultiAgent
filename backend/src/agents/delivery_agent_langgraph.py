"""
Delivery Agent (LangGraph) - Combines Creative + Audience Analysis.

This agent analyzes DV360 delivery optimization including:
- Creative performance and fatigue detection
- Audience segment effectiveness
- Creative-audience correlations
- Delivery optimization recommendations
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
import time
import re
from collections import defaultdict

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent

from .base import BaseAgent
from ..schemas.agent import AgentInput, AgentOutput
from ..schemas.agent_state import DeliveryAgentState, create_initial_delivery_state
from ..tools.agent_tools import get_delivery_agent_tools
from ..core.config import settings
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class DeliveryAgentLangGraph(BaseAgent):
    """
    Delivery Agent using LangGraph for workflow orchestration.

    Responsibilities:
    - Analyze creative performance across campaigns
    - Analyze audience segment performance
    - Identify creative-audience correlations
    - Detect creative fatigue and targeting issues
    - Provide delivery optimization recommendations

    Uses LangGraph for:
    - State management through nodes
    - Conditional routing (ask for clarification if query is vague)
    - ReAct agent for dynamic tool selection
    """

    def __init__(self):
        """Initialize Delivery Agent."""
        super().__init__(
            agent_name="delivery_optimization",
            description="Analyzes DV360 delivery optimization (creative + audience) and provides recommendations",
            tools=[],  # Tools accessed through agent_tools registry
        )

        # Build LangGraph workflow
        self.graph = self._build_graph()

    def get_system_prompt(self) -> str:
        """Return system prompt for the delivery agent."""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year
        
        return f"""You are a DV360 Delivery Optimization Agent using LangGraph.

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise.

Your role:
- Analyze creative asset performance and detect fatigue
- Analyze audience segment effectiveness
- Identify correlations between creatives and audiences
- Provide delivery optimization recommendations

Available tools:
- execute_custom_snowflake_query: Build custom SQL queries
- query_creative_performance: Get creative performance data
- query_audience_performance: Get audience segment data
- query_campaign_performance: Get campaign-level context
- retrieve_relevant_learnings: Access past insights
- get_session_history: Get conversation context

PRIMARY TABLES (use these for most queries):
- reports.reporting_revamp.creative_name_agg: Creative asset performance data
- reports.reporting_revamp.ALL_PERFORMANCE_AGG: Audience/line item performance data (grouped by line_item)

When building custom SQL queries with execute_custom_snowflake_query:
- PRIMARY: Use reports.reporting_revamp.creative_name_agg for creative analysis
- PRIMARY: Use reports.reporting_revamp.ALL_PERFORMANCE_AGG (grouped by line_item) for audience analysis
- Use appropriate date ranges based on the user's question (default to current year/month if not specified)
- Add aggregations (SUM, AVG, etc.) as needed
- Filter by advertiser, insertion_order, line_item, date as relevant
- You can dynamically adapt and use other tables if needed for the specific query

Analysis approach:
1. Retrieve relevant historical learnings
2. Query both creative and audience data
3. Analyze creative performance (CTR, conversions, fatigue)
4. Analyze audience segment performance (targeting effectiveness)
5. Identify creative-audience correlations
6. Generate actionable recommendations

Be data-driven and focused on delivery optimization."""

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph StateGraph for delivery analysis.

        Graph flow:
        parse_query → [decision: clarify OR proceed]
            ├─ clarify → ask_clarification → END
            └─ proceed → retrieve_memory → react_data_collection →
                         analyze_data → generate_recommendations →
                         generate_response → END
        """
        workflow = StateGraph(DeliveryAgentState)

        # Add nodes
        workflow.add_node("parse_query", self._parse_query_node)
        workflow.add_node("ask_clarification", self._ask_clarification_node)
        workflow.add_node("retrieve_memory", self._retrieve_memory_node)
        workflow.add_node("react_data_collection", self._react_data_collection_node)
        workflow.add_node("analyze_data", self._analyze_data_node)
        workflow.add_node("generate_recommendations", self._generate_recommendations_node)
        workflow.add_node("generate_response", self._generate_response_node)

        # Set entry point
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

        # If asking for clarification, end and wait for user
        workflow.add_edge("ask_clarification", END)

        # Normal flow continues
        workflow.add_edge("retrieve_memory", "react_data_collection")
        workflow.add_edge("react_data_collection", "analyze_data")
        workflow.add_edge("analyze_data", "generate_recommendations")
        workflow.add_edge("generate_recommendations", "generate_response")
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    def _parse_query_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Parse the user query to extract campaign/advertiser IDs and calculate confidence.

        Confidence scoring:
        - Found campaign ID: +0.6
        - Found advertiser ID: +0.2
        - Has delivery keywords: +0.2
        Total: 0.0 to 1.0
        """
        query = state["query"]

        # Extract campaign ID
        campaign_id = None
        campaign_patterns = [
            r"campaign\s+([A-Za-z0-9_-]+)",
            r"insertion[_\s]order\s+([A-Za-z0-9_-]+)",
            r"IO\s+([A-Za-z0-9_-]+)",
        ]
        for pattern in campaign_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                campaign_id = match.group(1)
                break

        # Extract advertiser ID
        advertiser_id = None
        advertiser_patterns = [r"advertiser\s+([A-Za-z0-9_-]+)"]
        for pattern in advertiser_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                advertiser_id = match.group(1)
                break

        # Calculate confidence
        confidence = 0.0
        if campaign_id:
            confidence += 0.6
        if advertiser_id:
            confidence += 0.2

        # Check for delivery-related keywords
        delivery_keywords = [
            "creative", "creatives", "ad", "ads", "asset", "assets",
            "audience", "segment", "segments", "targeting",
            "delivery", "fatigue", "refresh", "rotation"
        ]
        query_lower = query.lower()
        if any(keyword in query_lower for keyword in delivery_keywords):
            confidence += 0.2

        logger.info(
            "Parsed delivery query",
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

    def _should_ask_for_clarification(self, state: DeliveryAgentState) -> str:
        """
        Decision function: Should we ask for clarification?

        Returns:
            "clarify": Ask user for more info
            "proceed": Continue with analysis
        """
        confidence = state.get("parse_confidence", 0.0)
        campaign_id = state.get("campaign_id")
        advertiser_id = state.get("advertiser_id")
        query = state.get("query", "")

        # If confidence is very low, ask for clarification
        if confidence < 0.4:
            logger.info("Low confidence, asking for clarification", confidence=confidence)
            return "clarify"

        # If no campaign_id or advertiser_id and query is vague
        if not campaign_id and not advertiser_id and len(query.split()) < 5:
            logger.info("Missing IDs and vague query, asking for clarification")
            return "clarify"

        # Otherwise proceed
        logger.info("Sufficient confidence, proceeding with analysis", confidence=confidence)
        return "proceed"

    def _ask_clarification_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Ask user for clarification when query is too vague.
        """
        query = state.get("query", "")
        campaign_id = state.get("campaign_id")
        advertiser_id = state.get("advertiser_id")

        questions = []

        if not campaign_id:
            questions.append("Which campaign would you like me to analyze? Please provide the campaign name or ID.")

        if not advertiser_id:
            questions.append("Which advertiser is this for? (e.g., 'Quiz', 'BrandX')")

        if len(query.split()) < 5:
            questions.append("Are you interested in creative performance, audience targeting, or both?")

        # Build response
        response = f"""I need a bit more information to help you with that.

Please provide:
{chr(10).join(f'{i}. {q}' for i, q in enumerate(questions, 1))}

Once I have this information, I can provide a detailed delivery optimization analysis!"""

        logger.info("Asked for clarification", questions_count=len(questions))

        return {
            "needs_clarification": True,
            "clarification_questions": questions,
            "response": response,
            "confidence": 0.0,
            "reasoning_steps": [f"Asked for clarification: {len(questions)} questions"]
        }

    def _retrieve_memory_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Retrieve relevant learnings from memory.
        """
        from ..tools.memory_tool import memory_retrieval_tool

        query = state["query"]
        session_id = state.get("session_id")

        if not session_id:
            logger.info("No session_id, skipping memory retrieval")
            return {
                "reasoning_steps": ["Skipped memory retrieval (no session_id)"]
            }

        try:
            session_memory = memory_retrieval_tool.retrieve_context(
                query=query,
                session_id=session_id,
                agent_name=self.agent_name,
                top_k=5,
                min_similarity=0.6,
            )

            relevant_learnings = [
                {
                    "content": learning.content,
                    "confidence": learning.confidence_score,
                    "agent": learning.agent_name
                }
                for learning in session_memory.relevant_learnings
            ]

            logger.info("Retrieved memory", learnings_count=len(relevant_learnings))

            return {
                "relevant_learnings": relevant_learnings,
                "tools_used": ["memory_retrieval"],
                "reasoning_steps": [f"Retrieved {len(relevant_learnings)} relevant learnings"]
            }

        except Exception as e:
            logger.error("Memory retrieval failed", error_message=str(e))
            return {
                "relevant_learnings": [],
                "reasoning_steps": [f"Memory retrieval failed: {str(e)}"]
            }

    def _react_data_collection_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Use ReAct agent to collect both creative and audience data.

        The ReAct agent will decide which tools to call:
        - query_creative_performance
        - query_audience_performance
        - query_campaign_performance
        """
        query = state["query"]
        campaign_id = state["campaign_id"]
        advertiser_id = state["advertiser_id"]

        # Get tools for delivery agent
        tools = get_delivery_agent_tools()

        # Create ReAct agent
        react_agent = create_react_agent(
            model=self.llm,
            tools=tools,
            messages_modifier=SystemMessage(content=f"""You are a data collection agent for DV360 delivery optimization.

Your goal: Collect both creative and audience data to answer the user's query.

User query: "{query}"
Campaign ID: {campaign_id}
Advertiser ID: {advertiser_id}

Available tools:
- query_creative_performance: Get creative asset performance data
- query_audience_performance: Get audience segment performance data
- query_campaign_performance: Get campaign-level context

Instructions:
1. Call query_creative_performance to get creative data
2. Call query_audience_performance to get audience segment data
3. Use campaign_id or advertiser_id if available
4. You only need to collect data - analysis will happen in the next step
5. Once you have the data, return it

Call the tools now to collect the data.""")
        )

        # Invoke the ReAct agent
        try:
            logger.info("Invoking ReAct agent for data collection")

            # Build agent input
            agent_input = {
                "messages": [
                    HumanMessage(content=f"Collect both creative and audience data for: {query}")
                ]
            }

            result = react_agent.invoke(agent_input)

            # Extract data from tool results
            # The ReAct agent's tool calls will be in the messages
            creative_data = []
            audience_data = []

            # Parse messages to find tool call results
            messages = result.get("messages", [])
            for msg in messages:
                if hasattr(msg, 'tool_calls'):
                    # This is a tool call message
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.get('name', '')
                        if tool_name == 'query_creative_performance':
                            # Find the corresponding tool result
                            creative_data = self._extract_data_from_messages(messages, tool_call['id'])
                        elif tool_name == 'query_audience_performance':
                            audience_data = self._extract_data_from_messages(messages, tool_call['id'])

            logger.info(
                "ReAct agent completed data collection",
                creative_records=len(creative_data),
                audience_records=len(audience_data)
            )

            return {
                "creative_data": creative_data,
                "audience_data": audience_data,
                "tools_used": ["react_agent", "snowflake_query"],
                "reasoning_steps": [
                    f"ReAct agent collected creative data ({len(creative_data)} records)",
                    f"ReAct agent collected audience data ({len(audience_data)} records)"
                ]
            }

        except Exception as e:
            logger.error("ReAct agent failed", error_message=str(e))
            return {
                "creative_data": [],
                "audience_data": [],
                "tools_used": ["react_agent"],
                "reasoning_steps": [f"ReAct agent failed: {str(e)}"]
            }

    def _extract_data_from_messages(self, messages: List, tool_call_id: str) -> List[Dict[str, Any]]:
        """
        Extract data from tool result messages.
        """
        import json

        for msg in messages:
            if hasattr(msg, 'tool_call_id') and msg.tool_call_id == tool_call_id:
                # This is the result message
                try:
                    content = msg.content
                    if isinstance(content, str):
                        data = json.loads(content)
                        return data if isinstance(data, list) else []
                except Exception as e:
                    logger.error("Failed to parse tool result", error_message=str(e))
                    return []
        return []

    def _analyze_data_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Analyze both creative and audience data.
        """
        creative_data = state.get("creative_data", [])
        audience_data = state.get("audience_data", [])

        # Analyze creative performance
        creative_analysis = self._analyze_creative_performance(creative_data)

        # Analyze audience performance
        audience_analysis = self._analyze_audience_performance(audience_data)

        # Look for correlations
        correlations = self._find_correlations(creative_analysis, audience_analysis)

        # Combine issues
        all_issues = creative_analysis["issues"] + audience_analysis["issues"]

        # Combine insights
        all_insights = creative_analysis.get("insights", []) + audience_analysis.get("insights", [])

        logger.info(
            "Completed delivery analysis",
            creatives_count=len(creative_analysis["creatives"]),
            segments_count=len(audience_analysis["segments"]),
            issues_count=len(all_issues),
            correlations_count=len(correlations)
        )

        return {
            "creatives": creative_analysis["creatives"],
            "creative_top_performers": creative_analysis["top_performers"],
            "creative_bottom_performers": creative_analysis["bottom_performers"],
            "size_performance": creative_analysis["by_size"],
            "fatigue_indicators": creative_analysis.get("fatigue_indicators", []),
            "audience_segments": audience_analysis["segments"],
            "audience_top_performers": audience_analysis["top_performers"],
            "audience_bottom_performers": audience_analysis["bottom_performers"],
            "summary_metrics": {
                "creative": creative_analysis["summary"],
                "audience": audience_analysis["summary"]
            },
            "issues": all_issues,
            "insights": all_insights,
            "correlations": correlations,
            "reasoning_steps": [
                f"Analyzed {len(creative_analysis['creatives'])} creatives",
                f"Analyzed {len(audience_analysis['segments'])} audience segments",
                f"Found {len(correlations)} correlations"
            ]
        }

    def _analyze_creative_performance(self, creative_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze creative performance (similar to creative_agent logic)."""
        if not creative_data:
            return {
                "creatives": [],
                "top_performers": [],
                "bottom_performers": [],
                "by_size": [],
                "summary": {},
                "issues": ["No creative data available"]
            }

        # Aggregate by creative_name
        creative_metrics = defaultdict(lambda: {
            "impressions": 0,
            "clicks": 0,
            "conversions": 0,
            "spend": 0,
            "revenue": 0,
            "sizes": set()
        })

        size_metrics = defaultdict(lambda: {
            "impressions": 0,
            "clicks": 0,
            "conversions": 0,
            "spend": 0
        })

        for row in creative_data:
            creative_name = row.get("CREATIVE_NAME", "Unknown")
            creative_size = row.get("CREATIVE_SIZE", "Unknown")

            creative_metrics[creative_name]["impressions"] += row.get("IMPRESSIONS", 0) or 0
            creative_metrics[creative_name]["clicks"] += row.get("CLICKS", 0) or 0
            creative_metrics[creative_name]["conversions"] += row.get("TOTAL_CONVERSIONS", 0) or 0
            creative_metrics[creative_name]["spend"] += row.get("SPEND", 0) or 0
            creative_metrics[creative_name]["revenue"] += row.get("TOTAL_REVENUE", 0) or 0
            creative_metrics[creative_name]["sizes"].add(creative_size)

            size_metrics[creative_size]["impressions"] += row.get("IMPRESSIONS", 0) or 0
            size_metrics[creative_size]["clicks"] += row.get("CLICKS", 0) or 0
            size_metrics[creative_size]["conversions"] += row.get("TOTAL_CONVERSIONS", 0) or 0
            size_metrics[creative_size]["spend"] += row.get("SPEND", 0) or 0

        # Calculate derived metrics
        creatives = []
        for creative_name, metrics in creative_metrics.items():
            ctr = (metrics["clicks"] / metrics["impressions"] * 100) if metrics["impressions"] > 0 else 0
            cvr = (metrics["conversions"] / metrics["clicks"] * 100) if metrics["clicks"] > 0 else 0
            cpa = metrics["spend"] / metrics["conversions"] if metrics["conversions"] > 0 else 0
            roas = metrics["revenue"] / metrics["spend"] if metrics["spend"] > 0 else 0

            creatives.append({
                "name": creative_name,
                "impressions": metrics["impressions"],
                "clicks": metrics["clicks"],
                "conversions": metrics["conversions"],
                "spend": metrics["spend"],
                "revenue": metrics["revenue"],
                "ctr": ctr,
                "cvr": cvr,
                "cpa": cpa,
                "roas": roas,
                "sizes": list(metrics["sizes"])
            })

        creatives.sort(key=lambda x: x["impressions"], reverse=True)

        # Size performance
        sizes = []
        for size_name, metrics in size_metrics.items():
            ctr = (metrics["clicks"] / metrics["impressions"] * 100) if metrics["impressions"] > 0 else 0
            sizes.append({
                "size": size_name,
                "impressions": metrics["impressions"],
                "clicks": metrics["clicks"],
                "ctr": ctr
            })
        sizes.sort(key=lambda x: x["ctr"], reverse=True)

        # Summary metrics
        total_impressions = sum(c["impressions"] for c in creatives)
        total_clicks = sum(c["clicks"] for c in creatives)
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        # Top/bottom performers
        top_creatives = sorted([c for c in creatives if c["clicks"] > 0], key=lambda x: x["ctr"], reverse=True)[:3]
        bottom_creatives = sorted([c for c in creatives if c["clicks"] > 0], key=lambda x: x["ctr"])[:3]

        # Identify issues
        issues = []
        low_performing = [c for c in creatives if c["ctr"] < avg_ctr * 0.5 and c["impressions"] > 1000]
        if low_performing:
            issues.append(f"{len(low_performing)} creatives performing significantly below average CTR")

        if len(creatives) < 3:
            issues.append("Limited creative variety - consider testing more variations")

        return {
            "creatives": creatives,
            "top_performers": top_creatives,
            "bottom_performers": bottom_creatives,
            "by_size": sizes,
            "summary": {
                "total_creatives": len(creatives),
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "avg_ctr": avg_ctr
            },
            "issues": issues
        }

    def _analyze_audience_performance(self, audience_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze audience segment performance (similar to audience_agent logic)."""
        if not audience_data:
            return {
                "segments": [],
                "top_performers": [],
                "bottom_performers": [],
                "summary": {},
                "issues": ["No audience data available"]
            }

        # Aggregate by segment
        segment_metrics = {}

        for row in audience_data:
            segment = row.get("LINE_ITEM", "Unknown")

            if segment not in segment_metrics:
                segment_metrics[segment] = {
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "spend": 0,
                    "revenue": 0
                }

            segment_metrics[segment]["impressions"] += row.get("IMPRESSIONS", 0) or 0
            segment_metrics[segment]["clicks"] += row.get("CLICKS", 0) or 0
            segment_metrics[segment]["conversions"] += row.get("TOTAL_CONVERSIONS", 0) or 0
            segment_metrics[segment]["spend"] += row.get("SPEND", 0) or 0
            segment_metrics[segment]["revenue"] += row.get("TOTAL_REVENUE", 0) or 0

        # Calculate derived metrics
        segments = []
        for segment_name, metrics in segment_metrics.items():
            ctr = (metrics["clicks"] / metrics["impressions"] * 100) if metrics["impressions"] > 0 else 0
            cpa = metrics["spend"] / metrics["conversions"] if metrics["conversions"] > 0 else 0
            roas = metrics["revenue"] / metrics["spend"] if metrics["spend"] > 0 else 0

            segments.append({
                "name": segment_name,
                "impressions": metrics["impressions"],
                "clicks": metrics["clicks"],
                "conversions": metrics["conversions"],
                "spend": metrics["spend"],
                "revenue": metrics["revenue"],
                "ctr": ctr,
                "cpa": cpa,
                "roas": roas
            })

        segments.sort(key=lambda x: x["impressions"], reverse=True)

        # Summary metrics
        total_impressions = sum(s["impressions"] for s in segments)
        total_clicks = sum(s["clicks"] for s in segments)
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        # Top/bottom performers
        top_segments = sorted([s for s in segments if s["clicks"] > 0], key=lambda x: x["ctr"], reverse=True)[:3]
        bottom_segments = sorted([s for s in segments if s["clicks"] > 0], key=lambda x: x["ctr"])[:3]

        # Identify issues
        issues = []
        low_performing = [s for s in segments if s["ctr"] < avg_ctr * 0.5 and s["impressions"] > 1000]
        if low_performing:
            issues.append(f"{len(low_performing)} segments performing significantly below average CTR")

        return {
            "segments": segments,
            "top_performers": top_segments,
            "bottom_performers": bottom_segments,
            "summary": {
                "total_segments": len(segments),
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "avg_ctr": avg_ctr
            },
            "issues": issues
        }

    def _find_correlations(
        self,
        creative_analysis: Dict[str, Any],
        audience_analysis: Dict[str, Any]
    ) -> List[str]:
        """Find correlations between creative and audience performance."""
        correlations = []

        # Check if top creative sizes align with top audience segments
        top_creative = creative_analysis.get("top_performers", [])
        top_audience = audience_analysis.get("top_performers", [])

        if top_creative and top_audience:
            correlations.append(
                f"Top creative '{top_creative[0]['name']}' ({top_creative[0]['ctr']:.2f}% CTR) "
                f"aligns with top audience '{top_audience[0]['name']}' ({top_audience[0]['ctr']:.2f}% CTR)"
            )

        # Check for size-segment patterns
        sizes = creative_analysis.get("by_size", [])
        if sizes and len(sizes) > 0:
            top_size = sizes[0]
            correlations.append(
                f"{top_size['size']} format shows strong performance ({top_size['ctr']:.2f}% CTR) "
                f"across audience segments"
            )

        return correlations

    def _generate_recommendations_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Generate delivery optimization recommendations.
        """
        creative_top = state.get("creative_top_performers", [])
        creative_bottom = state.get("creative_bottom_performers", [])
        audience_top = state.get("audience_top_performers", [])
        audience_bottom = state.get("audience_bottom_performers", [])
        issues = state.get("issues", [])
        correlations = state.get("correlations", [])

        recommendations = []

        # Creative recommendations
        if creative_top:
            top_creative = creative_top[0]
            recommendations.append({
                "priority": "high",
                "action": f"Scale creative '{top_creative['name']}'",
                "reason": f"Top performing with {top_creative['ctr']:.2f}% CTR"
            })

        if creative_bottom:
            bottom_creative = creative_bottom[0]
            recommendations.append({
                "priority": "high",
                "action": f"Refresh or pause '{bottom_creative['name']}'",
                "reason": f"Underperforming with {bottom_creative['ctr']:.2f}% CTR"
            })

        # Audience recommendations
        if audience_top:
            top_segment = audience_top[0]
            recommendations.append({
                "priority": "high",
                "action": f"Increase budget for '{top_segment['name']}' segment",
                "reason": f"Top performing segment with {top_segment['ctr']:.2f}% CTR"
            })

        if audience_bottom:
            bottom_segment = audience_bottom[0]
            recommendations.append({
                "priority": "medium",
                "action": f"Optimize or pause '{bottom_segment['name']}' segment",
                "reason": f"Low performance with {bottom_segment['ctr']:.2f}% CTR"
            })

        # Correlation-based recommendations
        if correlations:
            recommendations.append({
                "priority": "medium",
                "action": "Align top creatives with top audience segments",
                "reason": "Identified positive creative-audience correlations"
            })

        logger.info("Generated recommendations", count=len(recommendations))

        return {
            "recommendations": recommendations,
            "reasoning_steps": [f"Generated {len(recommendations)} delivery optimization recommendations"]
        }

    def _generate_response_node(self, state: DeliveryAgentState) -> Dict[str, Any]:
        """
        Generate natural language response using LLM.
        """
        import json

        query = state["query"]
        creatives = state.get("creatives", [])
        audience_segments = state.get("audience_segments", [])
        creative_top = state.get("creative_top_performers", [])
        audience_top = state.get("audience_top_performers", [])
        issues = state.get("issues", [])
        correlations = state.get("correlations", [])
        recommendations = state.get("recommendations", [])

        # Build data summary for LLM
        data_summary = {
            "creatives": {
                "total": len(creatives),
                "top_performers": creative_top[:3],
                "issues": [i for i in issues if "creative" in i.lower()]
            },
            "audience": {
                "total": len(audience_segments),
                "top_performers": audience_top[:3],
                "issues": [i for i in issues if "segment" in i.lower() or "audience" in i.lower()]
            },
            "correlations": correlations,
            "all_issues": issues
        }

        # Build recommendations summary
        recs_summary = "\n".join([
            f"- [{rec['priority']}] {rec['action']}: {rec['reason']}"
            for rec in recommendations[:5]
        ])

        user_prompt = f"""User Query: "{query}"

Delivery Optimization Data Summary:
{json.dumps(data_summary, indent=2)}

Recommendations:
{recs_summary}

Please generate a clear, actionable response that:
1. Summarizes overall delivery performance (creative + audience)
2. Highlights top performers in both categories
3. Identifies any correlations between creative and audience performance
4. Lists detected issues
5. Provides specific, prioritized recommendations

Format your response in markdown with clear sections."""

        try:
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm.invoke(messages)
            final_response = response.content

            logger.info("Generated final response", length=len(final_response))

            return {
                "response": final_response,
                "confidence": 0.9,
                "reasoning_steps": ["Generated natural language response with LLM"]
            }

        except Exception as e:
            logger.error("LLM response generation failed", error_message=str(e))
            return {
                "response": f"Delivery optimization analysis completed with {len(recommendations)} recommendations. (Error generating detailed response: {str(e)})",
                "confidence": 0.5,
                "reasoning_steps": [f"LLM response generation failed: {str(e)}"]
            }

    async def process(self, input_data: AgentInput) -> AgentOutput:
        """
        Process a delivery optimization request using LangGraph.

        Args:
            input_data: User query about delivery optimization

        Returns:
            AgentOutput with delivery analysis and recommendations
        """
        start_time = time.time()

        try:
            # Create initial state
            initial_state = create_initial_delivery_state(
                query=input_data.message,
                session_id=input_data.session_id,
                user_id=input_data.user_id
            )

            # Invoke the graph
            logger.info("Invoking delivery agent graph", query=input_data.message[:50])
            final_state = self.graph.invoke(initial_state)

            # Extract results
            execution_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Delivery agent completed",
                execution_time_ms=execution_time_ms,
                confidence=final_state.get("confidence", 0.0)
            )

            return AgentOutput(
                response=final_state["response"],
                agent_name=self.agent_name,
                reasoning="\n".join(final_state.get("reasoning_steps", [])),
                tools_used=final_state.get("tools_used", []),
                confidence=final_state.get("confidence", 0.0),
                metadata={
                    "creatives_analyzed": len(final_state.get("creatives", [])),
                    "segments_analyzed": len(final_state.get("audience_segments", [])),
                    "recommendations_count": len(final_state.get("recommendations", [])),
                    "execution_time_ms": execution_time_ms
                }
            )

        except Exception as e:
            logger.error("Delivery agent failed", error_message=str(e))
            execution_time_ms = int((time.time() - start_time) * 1000)

            return AgentOutput(
                response=f"I encountered an error analyzing delivery optimization: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Error: {str(e)}",
                tools_used=[],
                confidence=0.0,
                metadata={"execution_time_ms": execution_time_ms, "error": str(e)}
            )


# Global instance
delivery_agent_langgraph = DeliveryAgentLangGraph()
