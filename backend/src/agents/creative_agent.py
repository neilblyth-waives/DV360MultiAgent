"""
Creative Inventory Agent for analyzing DV360 creative performance.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
import time
import re
from collections import defaultdict

from .base import BaseAgent
from ..tools.snowflake_tool import snowflake_tool
from ..tools.memory_tool import memory_retrieval_tool
from ..tools.decision_logger import decision_logger
from ..schemas.agent import AgentInput, AgentOutput, AgentDecisionCreate
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class CreativeInventoryAgent(BaseAgent):
    """
    Creative Inventory Agent.

    Analyzes creative performance from Snowflake and provides:
    - Creative performance comparison
    - Creative fatigue detection
    - Size/format effectiveness analysis
    - Creative rotation and refresh recommendations
    """

    def __init__(self):
        """Initialize Creative Inventory Agent."""
        super().__init__(
            agent_name="creative_inventory",
            description="Analyzes DV360 creative performance and provides optimization recommendations",
            tools=[],  # Tools called directly, not as LangChain tools
        )

    def get_system_prompt(self) -> str:
        """Return system prompt for the creative inventory agent."""
        return """You are a DV360 Creative Inventory Agent, an expert in creative performance analysis and optimization.

Your role:
- Analyze creative asset performance across campaigns
- Identify high-performing and underperforming creatives
- Detect creative fatigue and declining performance
- Recommend creative refresh strategies and A/B testing
- Optimize creative rotation for maximum impact

Available data sources:
- Snowflake: DV360 creative performance data
- Memory: Past learnings about creative strategies

Analysis approach:
1. Retrieve relevant historical learnings about creative performance
2. Query creative performance data from Snowflake
3. Calculate performance metrics by creative (CTR, CVR, ROAS)
4. Analyze by creative size, format, and messaging
5. Detect fatigue patterns (declining CTR over time)
6. Provide actionable creative recommendations

Output format:
- Clear summary of creative performance
- Top/bottom performing creatives highlighted
- Creative fatigue indicators
- Size/format effectiveness insights
- Specific, actionable recommendations
- Creative refresh priorities

Be data-driven and focused on creative effectiveness and engagement."""

    async def process(self, input_data: AgentInput) -> AgentOutput:
        """
        Process a creative performance analysis request.

        Args:
            input_data: User query about creative performance

        Returns:
            AgentOutput with creative analysis and recommendations
        """
        start_time = time.time()
        tools_used = []
        reasoning_steps = []

        try:
            # Step 1: Parse the request to extract campaign ID
            campaign_id, advertiser_id = self._extract_ids_from_query(input_data.message)

            reasoning_steps.append(f"Extracted IDs - Campaign: {campaign_id}, Advertiser: {advertiser_id}")

            # Step 2: Retrieve relevant memories
            session_memory = None
            if input_data.session_id:
                reasoning_steps.append("Retrieving relevant historical learnings")
                session_memory = await memory_retrieval_tool.retrieve_context(
                    query=input_data.message,
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    top_k=5,
                    min_similarity=0.6,
                )
                tools_used.append("memory_retrieval")
                reasoning_steps.append(
                    f"Retrieved {len(session_memory.relevant_learnings)} relevant learnings"
                )

            # Step 3: Query creative data from Snowflake
            reasoning_steps.append("Querying creative performance data")
            creative_data = await snowflake_tool.get_creative_performance(
                campaign_id=campaign_id or "default_campaign"
            )
            tools_used.append("snowflake_query")
            reasoning_steps.append(f"Retrieved {len(creative_data)} creative records")

            # Step 4: Analyze the data (using Python for metrics)
            analysis = self._analyze_creative_performance(creative_data, session_memory)
            reasoning_steps.append("Completed creative performance analysis")

            # Step 5: Generate recommendations (using Python for rule-based insights)
            recommendations = self._generate_recommendations(analysis, session_memory)
            reasoning_steps.append("Generated creative optimization recommendations")

            # Step 6: Use LLM to generate natural language response
            reasoning_steps.append("Generating natural language analysis with LLM")
            response = await self._generate_llm_response(
                query=input_data.message,
                creative_data=creative_data,
                analysis=analysis,
                recommendations=recommendations,
                session_memory=session_memory
            )
            tools_used.append("llm_analysis")
            reasoning_steps.append("LLM generated final response")

            # Step 7: Log decision
            execution_time_ms = int((time.time() - start_time) * 1000)

            if input_data.session_id:
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="creative_performance_analysis",
                    input_data={
                        "query": input_data.message,
                        "campaign_id": campaign_id,
                        "advertiser_id": advertiser_id,
                    },
                    output_data={
                        "analysis": analysis,
                        "recommendations": recommendations,
                        "creatives_analyzed": len(creative_data),
                    },
                    tools_used=tools_used,
                    reasoning="\n".join(reasoning_steps),
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=response,
                agent_name=self.agent_name,
                reasoning="\n".join(reasoning_steps),
                tools_used=tools_used,
                confidence=0.9,
                metadata={
                    "campaign_id": campaign_id,
                    "advertiser_id": advertiser_id,
                    "creatives_analyzed": len(creative_data),
                    "learnings_used": len(session_memory.relevant_learnings) if session_memory else 0,
                },
            )

        except Exception as e:
            logger.error("Creative performance analysis failed", error_message=str(e))

            # Log failed decision
            if input_data.session_id:
                execution_time_ms = int((time.time() - start_time) * 1000)
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="creative_performance_analysis",
                    input_data={"query": input_data.message},
                    output_data={"error": str(e)},
                    tools_used=tools_used,
                    reasoning=f"Failed: {str(e)}",
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=f"I encountered an error analyzing creative performance: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Error: {str(e)}",
                tools_used=tools_used,
                confidence=0.0,
            )

    def _extract_ids_from_query(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """Extract campaign and advertiser IDs from query."""
        campaign_id = None
        advertiser_id = None

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
                break

        # Try to extract advertiser ID
        advertiser_patterns = [
            r"advertiser\s+([A-Za-z0-9_-]+)",
        ]

        for pattern in advertiser_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                advertiser_id = match.group(1)
                break

        return campaign_id, advertiser_id

    def _analyze_creative_performance(
        self,
        creative_data: List[Dict[str, Any]],
        session_memory: Optional[Any]
    ) -> Dict[str, Any]:
        """
        Analyze creative performance.

        Args:
            creative_data: Creative performance data from Snowflake
            session_memory: Session memory with learnings

        Returns:
            Analysis dictionary with metrics and insights
        """
        if not creative_data:
            return {
                "creatives": [],
                "by_size": {},
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

            # Aggregate by creative
            creative_metrics[creative_name]["impressions"] += row.get("IMPRESSIONS", 0) or 0
            creative_metrics[creative_name]["clicks"] += row.get("CLICKS", 0) or 0
            creative_metrics[creative_name]["conversions"] += row.get("TOTAL_CONVERSIONS", 0) or 0
            creative_metrics[creative_name]["spend"] += row.get("SPEND", 0) or 0
            creative_metrics[creative_name]["revenue"] += row.get("TOTAL_REVENUE", 0) or 0
            creative_metrics[creative_name]["sizes"].add(creative_size)

            # Aggregate by size
            size_metrics[creative_size]["impressions"] += row.get("IMPRESSIONS", 0) or 0
            size_metrics[creative_size]["clicks"] += row.get("CLICKS", 0) or 0
            size_metrics[creative_size]["conversions"] += row.get("TOTAL_CONVERSIONS", 0) or 0
            size_metrics[creative_size]["spend"] += row.get("SPEND", 0) or 0

        # Calculate derived metrics for each creative
        creatives = []
        for creative_name, metrics in creative_metrics.items():
            ctr = (metrics["clicks"] / metrics["impressions"] * 100) if metrics["impressions"] > 0 else 0
            cvr = (metrics["conversions"] / metrics["clicks"] * 100) if metrics["clicks"] > 0 else 0
            cpc = metrics["spend"] / metrics["clicks"] if metrics["clicks"] > 0 else 0
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
                "cpc": cpc,
                "cpa": cpa,
                "roas": roas,
                "sizes": list(metrics["sizes"])
            })

        # Sort by impressions (largest first)
        creatives.sort(key=lambda x: x["impressions"], reverse=True)

        # Calculate size performance
        sizes = []
        for size_name, metrics in size_metrics.items():
            ctr = (metrics["clicks"] / metrics["impressions"] * 100) if metrics["impressions"] > 0 else 0

            sizes.append({
                "size": size_name,
                "impressions": metrics["impressions"],
                "clicks": metrics["clicks"],
                "conversions": metrics["conversions"],
                "ctr": ctr
            })

        sizes.sort(key=lambda x: x["ctr"], reverse=True)

        # Calculate summary metrics
        total_impressions = sum(c["impressions"] for c in creatives)
        total_clicks = sum(c["clicks"] for c in creatives)
        total_spend = sum(c["spend"] for c in creatives)

        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        # Identify top/bottom performers
        top_creatives = sorted([c for c in creatives if c["clicks"] > 0], key=lambda x: x["ctr"], reverse=True)[:3]
        bottom_creatives = sorted([c for c in creatives if c["clicks"] > 0], key=lambda x: x["ctr"])[:3]

        # Identify issues
        issues = []
        if len(creatives) == 0:
            issues.append("No creatives found")

        low_performing = [c for c in creatives if c["ctr"] < avg_ctr * 0.5 and c["impressions"] > 1000]
        if low_performing:
            issues.append(f"{len(low_performing)} creatives performing significantly below average CTR")

        no_conversion_creatives = [c for c in creatives if c["conversions"] == 0 and c["clicks"] > 10]
        if no_conversion_creatives:
            issues.append(f"{len(no_conversion_creatives)} creatives with clicks but no conversions")

        if len(creatives) < 3:
            issues.append("Limited creative variety - consider testing more creative variations")

        return {
            "creatives": creatives,
            "top_performers": top_creatives,
            "bottom_performers": bottom_creatives,
            "by_size": sizes,
            "summary": {
                "total_creatives": len(creatives),
                "total_sizes": len(sizes),
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_spend": total_spend,
                "avg_ctr": avg_ctr,
            },
            "issues": issues,
        }

    def _generate_recommendations(
        self,
        analysis: Dict[str, Any],
        session_memory: Optional[Any]
    ) -> list[Dict[str, str]]:
        """Generate creative optimization recommendations."""
        recommendations = []

        top_performers = analysis.get("top_performers", [])
        bottom_performers = analysis.get("bottom_performers", [])
        summary = analysis.get("summary", {})
        by_size = analysis.get("by_size", [])

        # Recommend scaling top performers
        if top_performers:
            top_creative = top_performers[0]
            recommendations.append({
                "priority": "high",
                "action": f"Increase budget allocation for '{top_creative['name']}'",
                "reason": f"Top performing creative with {top_creative['ctr']:.2f}% CTR, {top_creative['cvr']:.2f}% CVR"
            })

        # Recommend pausing bottom performers
        if bottom_performers:
            bottom_creative = bottom_performers[0]
            recommendations.append({
                "priority": "high",
                "action": f"Pause or refresh '{bottom_creative['name']}'",
                "reason": f"Underperforming creative with only {bottom_creative['ctr']:.2f}% CTR"
            })

        # Recommend testing new sizes
        if by_size and len(by_size) > 0:
            top_size = by_size[0]
            recommendations.append({
                "priority": "medium",
                "action": f"Create more creatives in {top_size['size']} format",
                "reason": f"This size shows strong performance with {top_size['ctr']:.2f}% CTR"
            })

        # Recommend creative refresh
        if summary.get("total_creatives", 0) < 3:
            recommendations.append({
                "priority": "high",
                "action": "Develop additional creative variations",
                "reason": "Limited creative diversity increases risk of fatigue"
            })

        # Recommend A/B testing
        if len(top_performers) >= 2:
            recommendations.append({
                "priority": "medium",
                "action": "Run A/B test between top 2 creatives",
                "reason": "Compare similar performers to identify winning creative elements"
            })

        return recommendations

    async def _generate_llm_response(
        self,
        query: str,
        creative_data: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        recommendations: list[Dict[str, str]],
        session_memory: Optional[Any]
    ) -> str:
        """
        Use LLM to generate natural language creative analysis.
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        import json

        # Build context for LLM
        system_prompt = self.get_system_prompt()

        # Summarize data for LLM
        data_summary = {
            "total_creatives": len(analysis.get("creatives", [])),
            "summary_metrics": analysis.get("summary", {}),
            "top_performers": analysis.get("top_performers", [])[:3],
            "bottom_performers": analysis.get("bottom_performers", [])[:3],
            "size_performance": analysis.get("by_size", [])[:5],
            "issues": analysis.get("issues", []),
        }

        # Build memory context
        memory_context = ""
        if session_memory and session_memory.relevant_learnings:
            memory_context = "\n\nRelevant past learnings:\n"
            for learning in session_memory.relevant_learnings[:3]:
                memory_context += f"- {learning.content} (confidence: {learning.confidence_score:.0%})\n"

        # Build recommendations summary
        recs_summary = "\n".join([
            f"- [{rec['priority']}] {rec['action']}: {rec['reason']}"
            for rec in recommendations[:5]
        ])

        user_prompt = f"""User Query: "{query}"

Creative Performance Data Summary:
{json.dumps(data_summary, indent=2)}

Detected Issues:
{chr(10).join(f'- {issue}' for issue in analysis.get('issues', []))}

Recommended Actions:
{recs_summary}
{memory_context}

Please generate a clear, actionable response that:
1. Summarizes overall creative performance
2. Highlights top and bottom performing creatives
3. Analyzes size/format effectiveness
4. Identifies creative fatigue or concerns
5. Provides specific, prioritized recommendations

Format your response in markdown with clear sections."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm.invoke(messages)
            return response.content

        except Exception as e:
            logger.error("LLM response generation failed, falling back to template", error_message=str(e))
            # Fallback to simple template
            return f"Creative analysis error: {str(e)}"


# Global instance
creative_inventory_agent = CreativeInventoryAgent()
